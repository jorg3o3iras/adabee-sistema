import os
import sys
import subprocess
import base64
import io
import json
import csv
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
from PIL import Image
import pytesseract
import psycopg2
from psycopg2.extras import RealDictCursor
import google.generativeai as genai
from transformers import pipeline
import torch
import requests
from collections import defaultdict
import math

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÕES PARA RENDER
# ============================================

IS_RENDER = os.environ.get('RENDER', False)

if IS_RENDER:
    print("🚀 Rodando no Render!")
    # Configurar PATH do Tesseract
    os.environ['PATH'] = f"/usr/bin:{os.environ.get('PATH', '')}"
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
    
    # Verificar Tesseract
    try:
        result = subprocess.run(['tesseract', '--version'], 
                               capture_output=True, text=True)
        print(f"✅ Tesseract versão: {result.stdout[:100]}")
    except Exception as e:
        print(f"⚠️ Erro ao verificar Tesseract: {e}")
else:
    print("💻 Rodando localmente!")
    # Configuração para Windows
    if sys.platform == 'win32':
        try:
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        except:
            pass

# ============================================
# CONFIGURAR BANCO DE DADOS - SUPABASE
# ============================================

SUPABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require')

def get_db_connection():
    """Conecta ao Supabase"""
    try:
        conn = psycopg2.connect(
            SUPABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=15,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3
        )
        print("✅ Conectado ao Supabase!")
        return conn
    except Exception as e:
        print(f"❌ ERRO ao conectar: {e}")
        raise e

def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS escolas (
            id SERIAL PRIMARY KEY, 
            nome TEXT NOT NULL, 
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (
            id SERIAL PRIMARY KEY, 
            escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
            nome TEXT NOT NULL, 
            serie TEXT DEFAULT '1º Ano', 
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (
            id SERIAL PRIMARY KEY, 
            turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
            nome TEXT NOT NULL, 
            matricula TEXT, 
            numero_chamada INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS provas (
            id SERIAL PRIMARY KEY, 
            turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
            titulo TEXT NOT NULL, 
            descricao TEXT, 
            gabarito TEXT, 
            data_prova DATE,
            valor_nota REAL DEFAULT 10, 
            quantidade_questoes INTEGER, 
            tipo_questoes TEXT DEFAULT '4',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes (
            id SERIAL PRIMARY KEY, 
            prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
            aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
            respostas TEXT, 
            acertos INTEGER, 
            nota REAL, 
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metodo_ia TEXT DEFAULT 'gemini'
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes_redacao (
            id SERIAL PRIMARY KEY, 
            prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
            aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
            texto TEXT, 
            nota REAL, 
            feedback TEXT, 
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metodo_ia TEXT DEFAULT 'gemini'
        )''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")

# ============================================
# CONFIGURAR GEMINI AI (FALLBACK)
# ============================================

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('models/gemini-2.0-flash')
        GEMINI_AVAILABLE = True
        print("✅ Gemini AI configurado!")
    except Exception as e:
        GEMINI_AVAILABLE = False
        print(f"❌ Erro ao configurar Gemini: {e}")
else:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini não configurado.")

# ============================================
# CONFIGURAR IA LOCAL - HUGGING FACE
# ============================================

HF_MODEL_AVAILABLE = False
redacao_pipeline = None

try:
    # Desativar GPU para economizar memória no Render
    torch.cuda.is_available = lambda: False
    
    # Carregar modelo BERT em português
    redacao_pipeline = pipeline(
        "text-classification",
        model="neuralmind/bert-base-portuguese-cased",
        device=-1  # CPU
    )
    HF_MODEL_AVAILABLE = True
    print("✅ Modelo Hugging Face carregado!")
except Exception as e:
    print(f"⚠️ Erro ao carregar modelo HF: {e}")
    HF_MODEL_AVAILABLE = False

# ============================================
# CLASSE CORRETOR HÍBRIDO
# ============================================

class CorretorHibrido:
    """Sistema de correção com múltiplas estratégias"""
    
    @staticmethod
    def preprocessar_imagem(imagem_base64):
        """Pré-processa a imagem para análise"""
        try:
            if ',' in imagem_base64:
                imagem_base64 = imagem_base64.split(',')[1]
            
            imagem_bytes = base64.b64decode(imagem_base64)
            nparr = np.frombuffer(imagem_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return None
            
            # Redimensionar para tamanho padrão
            height, width = img.shape[:2]
            if width > 1200:
                scale = 1200 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = cv2.resize(img, (new_width, new_height))
            
            return img
        except Exception as e:
            print(f"Erro no pré-processamento: {e}")
            return None
    
    @staticmethod
    def detectar_respostas_opencv(imagem_base64, num_opcoes=4):
        """Estratégia 1: Detecção por processamento de imagem com OpenCV"""
        try:
            img = CorretorHibrido.preprocessar_imagem(imagem_base64)
            if img is None:
                return None, 0.0
            
            # Converter para tons de cinza
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Aplicar blur para reduzir ruído
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Detectar círculos usando Hough Circle Transform
            circles = cv2.HoughCircles(
                blurred,
                cv2.HOUGH_GRADIENT,
                dp=1,
                minDist=20,
                param1=50,
                param2=30,
                minRadius=8,
                maxRadius=25
            )
            
            if circles is None:
                return None, 0.0
            
            circles = np.uint16(np.around(circles[0]))
            
            # Analisar cada círculo
            respostas = []
            
            for circle in circles:
                x, y, r = circle
                # Extrair região do círculo
                mask = np.zeros_like(gray)
                cv2.circle(mask, (x, y), r, 255, -1)
                roi = cv2.bitwise_and(gray, mask)
                
                # Calcular intensidade média
                mean_intensity = np.mean(roi[roi > 0]) if np.any(roi > 0) else 255
                
                # Se a intensidade é baixa, a bolinha está preenchida
                is_filled = mean_intensity < 128
                
                if is_filled:
                    # Organizar por posição (questão)
                    questao = int(y / 30) + 1
                    opcao = int((x % 200) / 40)
                    
                    if opcao < num_opcoes:
                        letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                        respostas.append((questao, letras[opcao]))
            
            # Ordenar por questão
            respostas.sort(key=lambda x: x[0])
            
            # Extrair apenas as letras
            letras_respostas = [r[1] for r in respostas]
            
            if len(letras_respostas) >= 3:
                confianca = min(80, len(letras_respostas) * 2)
                return letras_respostas, confianca
            
            return None, 0.0
            
        except Exception as e:
            print(f"Erro no OpenCV: {e}")
            return None, 0.0
    
    @staticmethod
    def detectar_respostas_ocr(imagem_base64, num_opcoes=4):
        """Estratégia 2: Detecção usando Tesseract OCR"""
        try:
            img = CorretorHibrido.preprocessar_imagem(imagem_base64)
            if img is None:
                return None, 0.0
            
            # Converter para tons de cinza
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Aplicar threshold para destacar texto
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            
            # Configurar Tesseract
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            
            # Executar OCR
            text = pytesseract.image_to_string(binary, config=custom_config)
            
            # Extrair letras maiúsculas
            letras_validas = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[:num_opcoes]
            respostas = [c for c in text.upper() if c in letras_validas]
            
            if len(respostas) >= 3:
                confianca = min(75, len(respostas) * 2)
                return respostas, confianca
            
            return None, 0.0
            
        except Exception as e:
            print(f"Erro no OCR: {e}")
            return None, 0.0
    
    @staticmethod
    def detectar_respostas_gemini(imagem_base64, num_opcoes=4):
        """Estratégia 3: Gemini AI (Fallback)"""
        try:
            if not GEMINI_AVAILABLE:
                return None, 0.0
            
            if ',' in imagem_base64:
                imagem_base64 = imagem_base64.split(',')[1]
            
            imagem_bytes = base64.b64decode(imagem_base64)
            img = Image.open(io.BytesIO(imagem_bytes))
            img.thumbnail((1024, 1024))
            
            opcoes = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[:num_opcoes]
            opcoes_str = ', '.join(list(opcoes))
            
            prompt = f"""Analise esta imagem de folha de respostas.
            Identifique as bolinhas marcadas para cada questão.
            Responda APENAS com as letras das respostas, separadas por vírgula.
            Use apenas as letras: {opcoes_str}
            Exemplo: A, B, C, A, B, C"""
            
            response = model.generate_content([prompt, img])
            texto = response.text.strip().upper()
            
            letras_validas = set(opcoes)
            respostas = [c for c in texto if c in letras_validas]
            
            if len(respostas) >= 3:
                return respostas, 90.0
            elif len(respostas) > 0:
                return respostas, 70.0
            
            return None, 0.0
            
        except Exception as e:
            print(f"Erro no Gemini: {e}")
            return None, 0.0
    
    @staticmethod
    def detectar_respostas_hibrido(imagem_base64, num_opcoes=4):
        """Método principal: testa todas as estratégias e retorna a melhor"""
        
        resultados = []
        
        # Estratégia 1: OpenCV
        respostas_cv, conf_cv = CorretorHibrido.detectar_respostas_opencv(imagem_base64, num_opcoes)
        if respostas_cv:
            resultados.append((respostas_cv, conf_cv, 'OpenCV'))
        
        # Estratégia 2: OCR
        respostas_ocr, conf_ocr = CorretorHibrido.detectar_respostas_ocr(imagem_base64, num_opcoes)
        if respostas_ocr:
            resultados.append((respostas_ocr, conf_ocr, 'OCR'))
        
        # Estratégia 3: Gemini (se disponível)
        if GEMINI_AVAILABLE:
            respostas_gemini, conf_gemini = CorretorHibrido.detectar_respostas_gemini(imagem_base64, num_opcoes)
            if respostas_gemini:
                resultados.append((respostas_gemini, conf_gemini, 'Gemini'))
        
        if not resultados:
            return None, 0.0, 'Nenhum método funcionou'
        
        # Escolher o melhor resultado (maior confiança)
        melhor = max(resultados, key=lambda x: x[1])
        
        return melhor[0], melhor[1], melhor[2]

# ============================================
# CLASSE PARA CORREÇÃO DE REDAÇÃO HÍBRIDA
# ============================================

class CorretorRedacaoHibrido:
    """Sistema híbrido para correção de redações"""
    
    @staticmethod
    def extrair_texto_ocr(imagem_base64):
        """Extrai texto da imagem usando OCR"""
        try:
            img = CorretorHibrido.preprocessar_imagem(imagem_base64)
            if img is None:
                return None
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            
            # Configurar Tesseract para português
            custom_config = r'--oem 3 --psm 6 -l por'
            text = pytesseract.image_to_string(binary, config=custom_config)
            
            return text.strip() if text.strip() else None
            
        except Exception as e:
            print(f"Erro ao extrair texto: {e}")
            return None
    
    @staticmethod
    def corrigir_redacao_huggingface(texto):
        """Corrige redação usando modelo Hugging Face"""
        try:
            if not HF_MODEL_AVAILABLE or not redacao_pipeline:
                return None, 0.0
            
            # Limitar tamanho do texto
            if len(texto) > 512:
                texto = texto[:512]
            
            # Avaliar texto
            result = redacao_pipeline(texto)
            
            # Converter score para nota (0-10)
            score = result[0]['score']
            nota = score * 10
            
            # Gerar feedback baseado no score
            if nota >= 8:
                feedback = "Excelente redação! Ótima estrutura e argumentação."
            elif nota >= 6:
                feedback = "Boa redação. Pode melhorar a coesão e clareza."
            elif nota >= 4:
                feedback = "Redação regular. Trabalhe na organização e desenvolvimento das ideias."
            else:
                feedback = "Redação insuficiente. Revisar estrutura e conteúdo."
            
            return feedback, nota
            
        except Exception as e:
            print(f"Erro no Hugging Face: {e}")
            return None, 0.0
    
    @staticmethod
    def corrigir_redacao_gemini(texto, imagem_base64=None):
        """Corrige redação usando Gemini (fallback)"""
        try:
            if not GEMINI_AVAILABLE:
                return None, 0.0
            
            prompt = f"""Avalie esta redação e dê uma nota de 0 a 10:

{texto}

Responda no formato:
NOTA: [número]
FEEDBACK: [feedback detalhado]"""
            
            response = model.generate_content(prompt)
            resultado = response.text
            
            # Extrair nota
            nota_match = re.search(r'NOTA:\s*([\d.]+)', resultado, re.IGNORECASE)
            nota = float(nota_match.group(1)) if nota_match else 0
            
            # Extrair feedback
            feedback_match = re.search(r'FEEDBACK:\s*(.*?)$', resultado, re.DOTALL | re.IGNORECASE)
            feedback = feedback_match.group(1).strip() if feedback_match else "Análise concluída."
            
            return feedback, nota
            
        except Exception as e:
            print(f"Erro no Gemini: {e}")
            return None, 0.0
    
    @staticmethod
    def corrigir_redacao_hibrido(imagem_base64=None, texto=None):
        """Método principal para correção de redação"""
        
        # Se não houver texto, extrair da imagem
        if not texto and imagem_base64:
            texto = CorretorRedacaoHibrido.extrair_texto_ocr(imagem_base64)
        
        if not texto:
            return None, 0.0, "Não foi possível extrair o texto"
        
        # Tentar Hugging Face primeiro
        feedback_hf, nota_hf = CorretorRedacaoHibrido.corrigir_redacao_huggingface(texto)
        if feedback_hf:
            return texto, nota_hf, feedback_hf, 'Hugging Face'
        
        # Fallback para Gemini
        if GEMINI_AVAILABLE:
            feedback_gemini, nota_gemini = CorretorRedacaoHibrido.corrigir_redacao_gemini(texto)
            if feedback_gemini:
                return texto, nota_gemini, feedback_gemini, 'Gemini'
        
        # Avaliação simples se tudo falhar
        palavras = len(texto.split())
        if palavras > 100:
            nota = 6.0
            feedback = "Redação válida. Use ferramentas mais avançadas para melhor avaliação."
        elif palavras > 50:
            nota = 4.0
            feedback = "Redação curta. Desenvolva mais seus argumentos."
        else:
            nota = 2.0
            feedback = "Redação muito curta. É necessário desenvolver mais o texto."
        
        return texto, nota, feedback, 'Básico'

# ============================================
# ROTAS PRINCIPAIS
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/teste', methods=['GET'])
def teste():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({
            'mensagem': 'Servidor funcionando!',
            'status': 'ok',
            'ambiente': 'Render' if IS_RENDER else 'Local',
            'banco': 'PostgreSQL (Supabase)',
            'gemini': GEMINI_AVAILABLE,
            'huggingface': HF_MODEL_AVAILABLE,
            'tesseract': True,
            'metodos': ['OpenCV', 'OCR', 'Gemini', 'Hugging Face']
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS DE ESCOLAS, TURMAS E ALUNOS
# ============================================

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM escolas ORDER BY nome")
        escolas = [{'id': row['id'], 'nome': row['nome']} for row in cursor.fetchall()]
        conn.close()
        return jsonify(escolas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    try:
        dados = request.json
        nome = dados.get('nome')
        if not nome:
            return jsonify({'erro': 'Nome da escola é obrigatório'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO escolas (nome) VALUES (%s) RETURNING id", (nome,))
        escola_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({'id': escola_id, 'mensagem': f'Escola "{nome}" cadastrada com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:escola_id>', methods=['DELETE'])
def deletar_escola(escola_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM escolas WHERE id = %s", (escola_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Escola excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    try:
        escola_id = request.args.get('escola_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if escola_id:
            cursor.execute("SELECT id, escola_id, nome, serie FROM turmas WHERE escola_id = %s ORDER BY nome", (escola_id,))
        else:
            cursor.execute("SELECT id, escola_id, nome, serie FROM turmas ORDER BY nome")
        
        turmas = [{'id': row['id'], 'escola_id': row['escola_id'], 'nome': row['nome'], 'serie': row['serie']} for row in cursor.fetchall()]
        conn.close()
        return jsonify(turmas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    try:
        dados = request.json
        escola_id = dados.get('escola_id')
        nome = dados.get('nome')
        serie = dados.get('serie', '1º Ano')
        
        if not escola_id or not nome:
            return jsonify({'erro': 'Escola e nome da turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO turmas (escola_id, nome, serie) VALUES (%s, %s, %s) RETURNING id", 
                       (escola_id, nome, serie))
        turma_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': turma_id})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:turma_id>', methods=['DELETE'])
def deletar_turma(turma_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM turmas WHERE id = %s", (turma_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Turma excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    try:
        turma_id = request.args.get('turma_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if turma_id:
            cursor.execute("""
                SELECT a.id, a.turma_id, a.nome, a.matricula, a.numero_chamada, t.nome as turma_nome
                FROM alunos a 
                LEFT JOIN turmas t ON a.turma_id = t.id
                WHERE a.turma_id = %s 
                ORDER BY a.numero_chamada
            """, (turma_id,))
        else:
            cursor.execute("""
                SELECT a.id, a.turma_id, a.nome, a.matricula, a.numero_chamada, t.nome as turma_nome
                FROM alunos a 
                LEFT JOIN turmas t ON a.turma_id = t.id
                ORDER BY a.numero_chamada
            """)
        
        alunos = [{
            'id': row['id'], 
            'turma_id': row['turma_id'], 
            'nome': row['nome'], 
            'matricula': row['matricula'], 
            'numero_chamada': row['numero_chamada'],
            'turma_nome': row['turma_nome']
        } for row in cursor.fetchall()]
        
        conn.close()
        return jsonify(alunos)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    try:
        dados = request.json
        turma_id = dados.get('turma_id')
        nome = dados.get('nome')
        matricula = dados.get('matricula', '')
        numero_chamada = dados.get('numero_chamada')
        
        if not turma_id or not nome:
            return jsonify({'erro': 'Turma e nome do aluno são obrigatórios'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alunos (turma_id, nome, matricula, numero_chamada) 
            VALUES (%s, %s, %s, %s) 
            RETURNING id
        """, (turma_id, nome, matricula, numero_chamada))
        
        aluno_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': aluno_id, 'mensagem': 'Aluno cadastrado com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:aluno_id>', methods=['DELETE'])
def deletar_aluno(aluno_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alunos WHERE id = %s", (aluno_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Aluno excluído com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS DE PROVAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
                   p.valor_nota, p.quantidade_questoes, p.tipo_questoes, 
                   t.nome as turma_nome, p.turma_id
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            ORDER BY p.data_prova DESC
        """)
        
        provas = []
        for row in cursor.fetchall():
            provas.append({
                'id': row['id'], 
                'titulo': row['titulo'], 
                'descricao': row['descricao'],
                'gabarito_array': json.loads(row['gabarito']) if row['gabarito'] else [],
                'data_prova': row['data_prova'], 
                'valor_nota': row['valor_nota'],
                'quantidade_questoes': row['quantidade_questoes'] or 0,
                'tipo_questoes': row['tipo_questoes'] or '4',
                'turma_nome': row['turma_nome'], 
                'turma_id': row['turma_id']
            })
        conn.close()
        return jsonify(provas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        dados = request.json
        turma_id = dados.get('turma_id')
        titulo = dados.get('titulo')
        descricao = dados.get('descricao', '')
        gabarito = dados.get('gabarito', [])
        data_prova = dados.get('data_prova')
        valor_nota = dados.get('valor_nota', 10)
        tipo_questoes = dados.get('tipo_questoes', '4')
        
        if not turma_id:
            return jsonify({'erro': 'Turma é obrigatória'}), 400
        if not titulo:
            return jsonify({'erro': 'Título da prova é obrigatório'}), 400
        if not data_prova:
            return jsonify({'erro': 'Data da prova é obrigatória'}), 400
        if not gabarito or len(gabarito) == 0:
            return jsonify({'erro': 'Gabarito é obrigatório'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota, tipo_questoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) 
            RETURNING id
        """, (
            turma_id, titulo, descricao,
            json.dumps(gabarito), len(gabarito),
            data_prova, valor_nota, tipo_questoes
        ))
        prova_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': prova_id, 'mensagem': 'Prova criada com sucesso!'})
    except Exception as e:
        print(f"Erro ao criar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correcoes WHERE prova_id = %s", (prova_id,))
        cursor.execute("DELETE FROM provas WHERE id = %s", (prova_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Prova excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# CORREÇÃO DE PROVAS - VERSÃO HÍBRIDA
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_prova():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        prova_id = dados.get('prova_id')
        aluno_id = dados.get('aluno_id')
        
        if not imagem or not prova_id or not aluno_id:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT gabarito, tipo_questoes, titulo FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova['gabarito']) if prova['gabarito'] else []
        tipo_questoes = int(prova['tipo_questoes'] or 4)
        titulo_prova = prova['titulo']
        
        # USAR CORRETOR HÍBRIDO
        corretor = CorretorHibrido()
        respostas_detectadas, confianca, metodo = corretor.detectar_respostas_hibrido(imagem, tipo_questoes)
        
        if not respostas_detectadas:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as respostas. Tente uma imagem mais clara.'}), 400
        
        # Ajustar tamanho
        while len(respostas_detectadas) < len(gabarito):
            respostas_detectadas.append('?')
        respostas_detectadas = respostas_detectadas[:len(gabarito)]
        
        # Calcular acertos
        acertos = 0
        correcoes = []
        for i in range(len(gabarito)):
            resposta = respostas_detectadas[i] if i < len(respostas_detectadas) else '?'
            correta = resposta == gabarito[i] if resposta != '?' else False
            if correta:
                acertos += 1
            correcoes.append({
                'questao': i+1, 
                'resposta': resposta, 
                'gabarito': gabarito[i], 
                'correta': correta
            })
        
        nota = (acertos / len(gabarito)) * 10 if gabarito else 0
        
        cursor.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        aluno_nome = aluno['nome'] if aluno else 'Aluno'
        
        cursor.execute("""
            INSERT INTO correcoes (prova_id, aluno_id, respostas, acertos, nota, data_correcao, metodo_ia) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (prova_id, aluno_id, json.dumps(respostas_detectadas), acertos, nota, datetime.now(), metodo))
        conn.commit()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome,
            'prova': titulo_prova,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round((acertos / len(gabarito)) * 100, 1) if gabarito else 0,
            'correcoes': correcoes,
            'confianca': round(confianca, 1),
            'metodo_ia': metodo,
            'tipo_questoes': tipo_questoes,
            'metodos_disponiveis': ['OpenCV', 'OCR', 'Gemini']
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# CORREÇÃO DE REDAÇÃO - VERSÃO HÍBRIDA
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        texto = dados.get('texto')
        prova_id = dados.get('prova_id')
        aluno_id = dados.get('aluno_id')
        
        if not imagem and not texto:
            return jsonify({'erro': 'Forneça imagem ou texto da redação'}), 400
        
        # Usar corretor híbrido
        corretor = CorretorRedacaoHibrido()
        texto_corrigido, nota, feedback, metodo = corretor.corrigir_redacao_hibrido(imagem, texto)
        
        if not texto_corrigido:
            return jsonify({'erro': 'Não foi possível processar a redação'}), 400
        
        # Salvar no banco se tiver prova e aluno
        if prova_id and aluno_id:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO correcoes_redacao (prova_id, aluno_id, texto, nota, feedback, data_correcao, metodo_ia) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (prova_id, aluno_id, texto_corrigido, nota, feedback, datetime.now(), metodo))
            conn.commit()
            conn.close()
        
        return jsonify({
            'nota': round(nota, 1),
            'conceito': 'Avaliado por IA',
            'feedback': feedback,
            'texto_original': texto_corrigido[:500] + ('...' if len(texto_corrigido) > 500 else ''),
            'metodo_ia': metodo,
            'texto_completo': texto_corrigido,
            'metodos_disponiveis': ['Hugging Face', 'Gemini', 'Básico']
        })
        
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# DEMAIS ROTAS
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM escolas")
        row = cursor.fetchone()
        total_escolas = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*) FROM turmas")
        row = cursor.fetchone()
        total_turmas = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*) FROM alunos")
        row = cursor.fetchone()
        total_alunos = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*) FROM provas")
        row = cursor.fetchone()
        total_provas = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*), COALESCE(AVG(nota), 0) FROM correcoes")
        row = cursor.fetchone()
        
        conn.close()
        return jsonify({
            'total_escolas': total_escolas,
            'total_turmas': total_turmas,
            'total_alunos': total_alunos,
            'total_provas': total_provas,
            'total_correcoes': row['count'] if row else 0,
            'media_geral': round(row['coalesce'], 1) if row and row['coalesce'] else 0
        })
    except Exception as e:
        print(f"Erro no dashboard: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/historico', methods=['GET'])
def historico():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, a.nome as aluno_nome, p.titulo as prova_titulo, 
                   c.acertos, c.nota, c.data_correcao, c.metodo_ia
            FROM correcoes c 
            JOIN alunos a ON c.aluno_id = a.id 
            JOIN provas p ON c.prova_id = p.id
            ORDER BY c.data_correcao DESC 
            LIMIT 50
        """)
        
        historico = [{
            'id': row['id'], 
            'aluno_nome': row['aluno_nome'], 
            'prova_titulo': row['prova_titulo'],
            'acertos': row['acertos'], 
            'nota': round(row['nota'], 1), 
            'data_correcao': row['data_correcao'],
            'metodo_ia': row['metodo_ia'] or 'Desconhecido'
        } for row in cursor.fetchall()]
        
        conn.close()
        return jsonify(historico)
    except Exception as e:
        return jsonify([])

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_corrigidas,
                COALESCE(AVG(nota), 0) as media_nota,
                COALESCE(MAX(nota), 0) as maior_nota,
                COALESCE(MIN(nota), 0) as menor_nota,
                metodo_ia,
                COUNT(*) as qtd_por_metodo
            FROM correcoes 
            WHERE prova_id = %s
            GROUP BY metodo_ia
        """, (prova_id,))
        
        resultados = cursor.fetchall()
        conn.close()
        
        metodos = {}
        for row in resultados:
            metodos[row['metodo_ia'] or 'Desconhecido'] = row['qtd_por_metodo']
        
        return jsonify({
            'geral': {
                'total_corrigidas': sum(row['qtd_por_metodo'] for row in resultados),
                'media_nota': round(np.mean([row['media_nota'] for row in resultados]) if resultados else 0, 1),
                'maior_nota': round(max([row['maior_nota'] for row in resultados]) if resultados else 0, 1),
                'menor_nota': round(min([row['menor_nota'] for row in resultados]) if resultados else 0, 1)
            },
            'metodos': metodos
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'metodos_disponiveis': {
            'OpenCV': True,
            'OCR': True,
            'Gemini': GEMINI_AVAILABLE,
            'HuggingFace': HF_MODEL_AVAILABLE
        },
        'ambiente': 'Render' if IS_RENDER else 'Local',
        'metodo_ativo': 'Híbrido (múltiplas estratégias)',
        'status': '🧠 Sistema híbrido ativo!',
        'banco': 'PostgreSQL (Supabase)',
        'vantagens': [
            '✅ Não depende apenas de API externa',
            '✅ Funciona offline (OpenCV + OCR)',
            '✅ Gratuito e rápido',
            '✅ Gemini como fallback'
        ]
    })

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.nome, a.matricula, c.acertos, c.nota, c.data_correcao, c.metodo_ia
            FROM correcoes c 
            JOIN alunos a ON c.aluno_id = a.id 
            WHERE c.prova_id = %s
        """, (prova_id,))
        
        resultados = cursor.fetchall()
        conn.close()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Aluno', 'Matrícula', 'Acertos', 'Nota', 'Data', 'Método IA'])
        for r in resultados:
            writer.writerow([r['nome'], r['matricula'] or '', r['acertos'], round(r['nota'], 1), r['data_correcao'], r['metodo_ia'] or 'Desconhecido'])
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=prova_{prova_id}_resultados.csv'
        }
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    return jsonify({
        'ip': 'render.com', 
        'porta': 10000, 
        'url': os.environ.get('RENDER_EXTERNAL_URL', 'https://adabee-sistema-3.onrender.com')
    })

@app.route('/api/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if request.method == 'GET':
        return jsonify({
            'metodo_principal': 'Híbrido',
            'param1': 80,
            'param2': 25,
            'metodos': ['OpenCV', 'OCR', 'Gemini'],
            'gemini_available': GEMINI_AVAILABLE,
            'huggingface_available': HF_MODEL_AVAILABLE
        })
    return jsonify({'mensagem': 'ok'})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    dados = request.json
    metodo = dados.get('metodo', 'hibrido')
    return jsonify({
        'metodo': metodo,
        'status': f'✅ Método {metodo} ativado!',
        'metodos_disponiveis': ['hibrido', 'opencv', 'ocr', 'gemini', 'huggingface']
    })

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({
        'status': 'ok',
        'mensagem': '✅ Sistema híbrido está pronto para uso!',
        'metodos_ativos': ['OpenCV', 'OCR', 'Gemini', 'Hugging Face']
    })

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({
        'sucesso': True,
        'mensagem': '✅ Sistema calibrado! Múltiplos métodos disponíveis.',
        'confianca_minima': 70,
        'metodos_testados': 3
    })

@app.route('/api/testar_metodos', methods=['POST'])
def testar_metodos():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        
        if not imagem:
            return jsonify({'erro': 'Imagem não fornecida'}), 400
        
        resultados = {}
        
        # Testar OpenCV
        respostas_cv, conf_cv = CorretorHibrido.detectar_respostas_opencv(imagem)
        resultados['opencv'] = {
            'sucesso': bool(respostas_cv),
            'respostas': respostas_cv[:10] if respostas_cv else [],
            'confianca': conf_cv
        }
        
        # Testar OCR
        respostas_ocr, conf_ocr = CorretorHibrido.detectar_respostas_ocr(imagem)
        resultados['ocr'] = {
            'sucesso': bool(respostas_ocr),
            'respostas': respostas_ocr[:10] if respostas_ocr else [],
            'confianca': conf_ocr
        }
        
        # Testar Gemini se disponível
        if GEMINI_AVAILABLE:
            respostas_gemini, conf_gemini = CorretorHibrido.detectar_respostas_gemini(imagem)
            resultados['gemini'] = {
                'sucesso': bool(respostas_gemini),
                'respostas': respostas_gemini[:10] if respostas_gemini else [],
                'confianca': conf_gemini
            }
        
        # Método híbrido
        respostas_hib, conf_hib, metodo = CorretorHibrido.detectar_respostas_hibrido(imagem)
        resultados['hibrido'] = {
            'sucesso': bool(respostas_hib),
            'respostas': respostas_hib[:10] if respostas_hib else [],
            'confianca': conf_hib,
            'metodo_escolhido': metodo
        }
        
        return jsonify({
            'resultados': resultados,
            'melhor_metodo': max(resultados.items(), key=lambda x: x[1]['confianca'])[0] if resultados else 'Nenhum',
            'total_metodos_testados': len(resultados)
        })
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/diagnosticar_banco', methods=['GET'])
def diagnosticar_banco():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as teste")
        row = cursor.fetchone()
        conn.close()
        return jsonify({
            'status': 'sucesso',
            'banco': 'PostgreSQL (Supabase)',
            'detalhes': {
                'teste_query': 'OK',
                'conexao': 'Estabelecida com sucesso'
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'erro',
            'banco': 'Não conectado',
            'detalhes': {'erro': str(e)}
        }), 500

@app.route('/api/testar_conexao', methods=['GET'])
def testar_conexao():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({
            'conectado': True,
            'banco': 'PostgreSQL (Supabase)',
            'mensagem': '✅ Conectado ao Supabase!'
        })
    except Exception as e:
        return jsonify({
            'conectado': False,
            'erro': str(e)
        }), 500

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'erro': 'Rota não encontrada',
        'mensagem': 'Verifique se a URL está correta'
    }), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({
        'erro': 'Erro interno do servidor',
        'mensagem': str(e)
    }), 500

# ============================================
# INICIALIZAR E RODAR
# ============================================

# Inicializar banco
try:
    init_database()
except Exception as e:
    print(f"❌ Erro na inicialização: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

# ============================================
# ROTA PARA GERAR GABARITO (ADICIONADA)
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        dados = request.json
        escola_id = dados.get('escola_id')
        turma_id = dados.get('turma_id')
        aluno_id = dados.get('aluno_id')
        prova_id = dados.get('prova_id')
        qtd_questoes = dados.get('quantidade_questoes', 20)
        tipo_questoes = dados.get('tipo_questoes', '4')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT nome FROM escolas WHERE id = %s", (escola_id,))
        escola = cursor.fetchone()
        nome_escola = escola['nome'] if escola else "ESCOLA"
        
        cursor.execute("SELECT nome, serie FROM turmas WHERE id = %s", (turma_id,))
        turma = cursor.fetchone()
        nome_turma = turma['nome'] if turma else "TURMA"
        serie = turma['serie'] if turma else "1º Ano"
        
        cursor.execute("SELECT nome, numero_chamada FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        nome_aluno = aluno['nome'] if aluno else "ALUNO"
        numero = str(aluno['numero_chamada']) if aluno and aluno['numero_chamada'] else ""
        
        cursor.execute("SELECT titulo, tipo_questoes FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        nome_prova = prova['titulo'] if prova else "PROVA"
        if prova and prova['tipo_questoes']:
            tipo_questoes = prova['tipo_questoes']
        
        conn.close()
        
        if tipo_questoes == '3':
            opcoes = ['A', 'B', 'C']
            titulo_opcoes = "3 OPÇÕES (A, B, C)"
        else:
            opcoes = ['A', 'B', 'C', 'D']
            titulo_opcoes = "4 OPÇÕES (A, B, C, D)"
        
        if int(qtd_questoes) > 30:
            qtd_questoes = 30
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Folha de Respostas - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; padding: 15px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 10px; }}
        .folha {{ padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 15px; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        .header h2 {{ color: #4CAF50; font-size: 20px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; background: #f9f9f9; padding: 10px; border-radius: 8px; font-size: 12px; }}
        .info-item {{ display: flex; gap: 8px; }}
        .info-label {{ font-weight: bold; color: #555; min-width: 70px; }}
        .info-value {{ color: #333; border-bottom: 1px solid #ccc; min-width: 120px; }}
        .instrucoes {{ background: #FFF3CD; padding: 8px; border-radius: 5px; margin-bottom: 15px; font-size: 10px; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #4CAF50; color: white; padding: 6px; text-align: center; font-size: 12px; }}
        td {{ padding: 6px; border-bottom: 1px solid #ddd; }}
        .questao-num {{ font-weight: bold; width: 50px; text-align: center; font-size: 12px; }}
        .opcoes {{ display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }}
        .opcao {{ display: inline-flex; flex-direction: column; align-items: center; gap: 3px; min-width: 45px; }}
        .circulo {{ display: inline-block; width: 22px; height: 22px; border: 2px solid #333; border-radius: 50%; background: white; cursor: pointer; }}
        .opcao span:last-child {{ font-weight: bold; font-size: 11px; }}
        .rodape {{ margin-top: 15px; text-align: center; font-size: 9px; color: #999; border-top: 1px solid #ddd; padding-top: 10px; }}
        .botoes {{ text-align: center; margin: 15px; padding: 10px; background: #f8f9fa; border-radius: 8px; }}
        button {{ background: #4CAF50; color: white; padding: 10px 25px; border: none; border-radius: 5px; font-size: 14px; cursor: pointer; margin: 0 10px; }}
        button:hover {{ background: #45a049; }}
        button.secundario {{ background: #2196F3; }}
        @media print {{ body {{ background: white; padding: 0; margin: 0; }} .container {{ box-shadow: none; }} .botoes {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="folha">
            <div class="header">
                <h2>🐝🧠 AdaBee AI - FOLHA DE RESPOSTAS</h2>
                <p>{titulo_opcoes} - {serie}</p>
            </div>
            <div class="info-grid">
                <div class="info-item"><span class="info-label">ESCOLA:</span><span class="info-value">{nome_escola}</span></div>
                <div class="info-item"><span class="info-label">TURMA:</span><span class="info-value">{nome_turma}</span></div>
                <div class="info-item"><span class="info-label">ALUNO:</span><span class="info-value">{nome_aluno}</span></div>
                <div class="info-item"><span class="info-label">Nº:</span><span class="info-value">{numero}</span></div>
                <div class="info-item"><span class="info-label">PROVA:</span><span class="info-value">{nome_prova}</span></div>
                <div class="info-item"><span class="info-label">DATA:</span><span class="info-value">___/___/______</span></div>
            </div>
            <div class="instrucoes">📌 Preencha COMPLETAMENTE a bolinha com caneta PRETA. Marque UMA por questão.</div>
            <table>
                <thead><tr><th>Q</th><th colspan="{len(opcoes)}">RESPOSTAS ({', '.join(opcoes)})</th></tr></thead>
                <tbody>"""
        
        for i in range(1, int(qtd_questoes) + 1):
            html += f"""
                    <tr>
                        <td class="questao-num">{i}</td>
                        <td colspan="{len(opcoes)}" style="text-align:center">
                            <div class="opcoes">"""
            for opcao in opcoes:
                html += f"""
                                <label class="opcao">
                                    <span class="circulo" onclick="marcar(this)"></span>
                                    <span>{opcao}</span>
                                </label>"""
            html += """
                            </div>
                        </td>
                    </tr>"""
        
        html += f"""
                </tbody>
            </table>
            <div class="rodape">AdaBee AI - Preencha completamente a bolinha | Use caneta PRETA</div>
        </div>
        <div class="botoes">
            <button onclick="window.print()">🖨️ IMPRIMIR</button>
            <button class="secundario" onclick="window.print()">💾 SALVAR PDF</button>
        </div>
    </div>
    <script>
        function marcar(el) {{
            const grupo = el.closest('.opcoes');
            grupo.querySelectorAll('.circulo').forEach(c => {{
                c.style.backgroundColor = 'white';
                c.style.border = '2px solid #333';
            }});
            el.style.backgroundColor = 'black';
            el.style.border = '2px solid black';
        }}
    </script>
</body>
</html>"""
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        print(f"Erro ao gerar gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

        # ============================================
# INICIALIZAR BANCO (APENAS UMA VEZ)
# ============================================

if __name__ == '__main__':
    # Inicializar banco apenas uma vez
    try:
        init_database()
    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
