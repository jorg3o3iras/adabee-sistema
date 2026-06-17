from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import io
import csv
import re
from datetime import datetime
import os
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
import pytesseract
import requests

app = Flask(__name__)
CORS(app)

# ============================================
# HUGGING FACE - DESATIVADO
# ============================================
HF_AVAILABLE = False
print("ℹ️ Hugging Face desativado - Usando OpenCV + OCR + Análise Avançada")

# ============================================
# CONFIGURAR BANCO DE DADOS - SUPABASE
# ============================================

SUPABASE_URL = 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require'

def get_db_connection():
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
            metodo_ia TEXT DEFAULT 'hibrido'
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes_redacao (
            id SERIAL PRIMARY KEY, 
            prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
            aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
            texto TEXT, 
            nota REAL, 
            feedback TEXT, 
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metodo_ia TEXT DEFAULT 'hibrido'
        )''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")

# ============================================
# GEMINI - DESATIVADO
# ============================================

GEMINI_AVAILABLE = False
print("ℹ️ Gemini AI desativado - Usando sistema híbrido")

# ============================================
# CLASSE CORRETOR HÍBRIDO (COM OPENCV MELHORADO)
# ============================================

class CorretorHibrido:
    @staticmethod
    def preprocessar_imagem(imagem_base64):
        try:
            if ',' in imagem_base64:
                imagem_base64 = imagem_base64.split(',')[1]
            imagem_bytes = base64.b64decode(imagem_base64)
            nparr = np.frombuffer(imagem_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return None
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
def detectar_bolinhas(imagem_base64):

    try:

        img = CorretorHibrido.preprocessar_imagem(imagem_base64)

        if img is None:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )

        gray = clahe.apply(gray)

        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=25,
            param1=50,
            param2=20,
            minRadius=8,
            maxRadius=25
        )

        if circles is None:
            return []

        circles = np.round(circles[0]).astype("int")

        bolinhas = []

        for (x, y, r) in circles:

            mask = np.zeros(gray.shape, dtype=np.uint8)

            cv2.circle(
                mask,
                (x, y),
                int(r * 0.7),
                255,
                -1
            )

            pixels = gray[mask == 255]

            if len(pixels) == 0:
                continue

            intensidade_media = np.mean(pixels)

            preenchimento = 1 - (intensidade_media / 255)

            bolinhas.append({
                'x': int(x),
                'y': int(y),
                'r': int(r),
                'preenchimento': float(preenchimento),
                'intensidade': float(intensidade_media)
            })

        print(f"Bolinhas detectadas: {len(bolinhas)}")

        return bolinhas

    except Exception as e:
        print(f"Erro detectar_bolinhas: {e}")
        return None
    
    @staticmethod
def detectar_respostas(imagem_base64, num_opcoes=4):

    try:

        bolinhas = CorretorHibrido.detectar_bolinhas(imagem_base64)

        if not bolinhas:
            return None, 0.0, "Nenhuma bolinha detectada"

        bolinhas.sort(key=lambda b: b['y'])

        linhas = []

        tolerancia_y = 20

        for bolinha in bolinhas:

            adicionada = False

            for linha in linhas:

                media_y = np.mean(
                    [b['y'] for b in linha]
                )

                if abs(bolinha['y'] - media_y) <= tolerancia_y:

                    linha.append(bolinha)

                    adicionada = True

                    break

            if not adicionada:
                linhas.append([bolinha])

        respostas = []

        letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        for idx, linha in enumerate(linhas, start=1):

            linha.sort(key=lambda b: b['x'])

            if len(linha) < num_opcoes:
                continue

            linha = linha[:num_opcoes]

            preenchimentos = [
                b['preenchimento']
                for b in linha
            ]

            maior = max(preenchimentos)

            posicao = preenchimentos.index(maior)

            if maior >= 0.55:
                resposta = letras[posicao]
            else:
                resposta = '?'

            respostas.append(
                (idx, resposta)
            )

        if len(respostas) == 0:
            return None, 0.0, "Nenhuma resposta"

        respostas.sort(key=lambda x: x[0])

        letras_respostas = [
            r[1]
            for r in respostas
        ]

        validas = sum(
            1
            for r in letras_respostas
            if r != '?'
        )

        confianca = round(
            (validas / len(letras_respostas)) * 100,
            1
        )

        print("========== DEBUG ==========")
        print(f"Bolinhas: {len(bolinhas)}")
        print(f"Linhas: {len(linhas)}")
        print(f"Respostas: {letras_respostas}")
        print("===========================")

        return (
            letras_respostas,
            confianca,
            "OMR Melhorado"
        )

    except Exception as e:

        print(f"Erro detectar_respostas: {e}")

        return None, 0.0, "Erro"
                
                # ============================================
                # ANALISAR CADA BOLINHA DA LINHA
                # ============================================
                
                # Verificar se todas as bolinhas da linha estão presentes
                # Se faltar alguma, preencher com '?'
                
                # Analisar cada posição (A, B, C, D)
                opcao_encontrada = '?'
                melhor_preenchimento = 0
                melhor_pos = -1
                
                for pos in range(num_opcoes):
                    if pos < len(linha):
                        bolinha = linha[pos]
                        preenchimento = bolinha['preenchimento']
                        
                        # Se a bolinha for PRETA (preenchimento alto)
                        if preenchimento > 0.30:  # Mais de 30% preenchida
                            if preenchimento > melhor_preenchimento:
                                melhor_preenchimento = preenchimento
                                melhor_pos = pos
                
                # Se encontrou uma bolinha preenchida
                if melhor_pos >= 0:
                    letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                    opcao_encontrada = letras[melhor_pos] if melhor_pos < len(letras) else '?'
                
                respostas.append((idx, opcao_encontrada))
            
            # 5. Verificar se encontrou respostas
            if len(respostas) == 0:
                return None, 0.0, 'Nenhuma resposta detectada'
            
            respostas.sort(key=lambda x: x[0])
            letras_respostas = [r[1] for r in respostas]
            
            num_validas = sum(1 for r in letras_respostas if r != '?')
            confianca = min(85, (num_validas / len(letras_respostas)) * 100)
            
            return letras_respostas, confianca, 'Contorno'
            
        except Exception as e:
            print(f"Erro na detecção: {e}")
            return None, 0.0, 'Erro'
    
    @staticmethod
    def detectar_respostas_opencv(imagem_base64, num_opcoes=4):
        """Método alternativo usando HoughCircles"""
        try:
            img = CorretorHibrido.preprocessar_imagem(imagem_base64)
            if img is None:
                return None, 0.0, 'Erro no pré-processamento'
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            gray = clahe.apply(gray)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            circles = cv2.HoughCircles(
                blurred,
                cv2.HOUGH_GRADIENT,
                dp=1.2,
                minDist=15,
                param1=40,
                param2=25,
                minRadius=6,
                maxRadius=30
            )
            
            if circles is None:
                return None, 0.0, 'Nenhum círculo detectado'
            
            circles = np.uint16(np.around(circles[0]))
            
            # Mapear círculos por linha
            linhas = {}
            
            for circle in circles:
                x, y, r = circle
                mask = np.zeros_like(gray)
                cv2.circle(mask, (x, y), r, 255, -1)
                roi = cv2.bitwise_and(gray, mask)
                pixels = roi[roi > 0]
                
                if len(pixels) > 0:
                    intensidade_media = np.mean(pixels)
                    preenchimento = 1 - (intensidade_media / 255)
                    
                    linha_key = int(y / 35) * 35
                    if linha_key not in linhas:
                        linhas[linha_key] = []
                    
                    linhas[linha_key].append({
                        'x': x,
                        'preenchimento': preenchimento
                    })
            
            respostas = []
            linhas_keys = sorted(linhas.keys())
            
            for idx, linha_key in enumerate(linhas_keys, start=1):
                if idx > 50:
                    break
                
                linha = linhas[linha_key]
                linha.sort(key=lambda b: b['x'])
                
                melhor_preenchimento = 0
                melhor_pos = -1
                
                for pos in range(num_opcoes):
                    if pos < len(linha):
                        bolinha = linha[pos]
                        if bolinha['preenchimento'] > melhor_preenchimento:
                            melhor_preenchimento = bolinha['preenchimento']
                            melhor_pos = pos
                
                if melhor_pos >= 0 and melhor_preenchimento > 0.30:
                    letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                    respostas.append((idx, letras[melhor_pos]))
                else:
                    respostas.append((idx, '?'))
            
            if len(respostas) == 0:
                return None, 0.0, 'Nenhuma resposta'
            
            respostas.sort(key=lambda x: x[0])
            letras_respostas = [r[1] for r in respostas]
            
            num_validas = sum(1 for r in letras_respostas if r != '?')
            confianca = min(80, (num_validas / len(letras_respostas)) * 100)
            
            return letras_respostas, confianca, 'OpenCV'
            
        except Exception as e:
            print(f"Erro no OpenCV: {e}")
            return None, 0.0, 'Erro'
    
   @staticmethod
def detectar_respostas_hibrido(imagem_base64, num_opcoes=4):

    respostas, confianca, metodo = CorretorHibrido.detectar_respostas(
        imagem_base64,
        num_opcoes
    )

    if respostas and len(respostas) >= 1:
        return respostas, confianca, metodo

    respostas, confianca, metodo = CorretorHibrido.detectar_respostas_opencv(
        imagem_base64,
        num_opcoes
    )

    if respostas and len(respostas) >= 1:
        return respostas, confianca, metodo

    return None, 0.0, 'Nenhum método funcionou'
# ============================================
# CLASSE PARA CORREÇÃO DE REDAÇÃO (ANÁLISE AVANÇADA)
# ============================================

class CorretorRedacaoHibrido:
    @staticmethod
    def extrair_texto_ocr(imagem_base64):
        try:
            if ',' in imagem_base64:
                imagem_base64 = imagem_base64.split(',')[1]
            imagem_bytes = base64.b64decode(imagem_base64)
            nparr = np.frombuffer(imagem_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            custom_config = r'--oem 3 --psm 6 -l por'
            text = pytesseract.image_to_string(binary, config=custom_config)
            return text.strip() if text.strip() else None
        except Exception as e:
            print(f"Erro ao extrair texto: {e}")
            return None
    
    @staticmethod
    def analisar_redacao(texto):
        """Análise detalhada da redação sem IA pesada"""
        
        palavras = texto.split()
        num_palavras = len(palavras)
        num_frases = len(re.split(r'[.!?]+', texto)) - 1
        num_paragrafos = len(texto.split('\n\n')) if '\n\n' in texto else 1
        
        palavras_unicas = len(set([p.lower() for p in palavras]))
        proporcao_vocabulario = (palavras_unicas / num_palavras) * 100 if num_palavras > 0 else 0
        
        conectores = ['e', 'mas', 'porém', 'contudo', 'entretanto', 'portanto', 'assim', 'logo', 'pois', 'porque', 'além', 'também', 'bem como', 'da mesma forma', 'outrossim', 'todavia', 'conquanto', 'embora', 'apesar', 'enquanto', 'quando', 'como', 'onde', 'cujo', 'que', 'qual', 'quem']
        num_conectores = sum(1 for p in palavras if p.lower() in conectores)
        
        # Critérios
        if num_palavras >= 200:
            nota_coerencia = 8.0
        elif num_palavras >= 150:
            nota_coerencia = 6.0
        elif num_palavras >= 100:
            nota_coerencia = 4.0
        elif num_palavras >= 50:
            nota_coerencia = 2.0
        else:
            nota_coerencia = 0.0
        
        if num_paragrafos >= 3 and num_frases >= 8:
            nota_estrutura = 8.0
        elif num_paragrafos >= 2 and num_frases >= 5:
            nota_estrutura = 6.0
        elif num_paragrafos >= 1 and num_frases >= 3:
            nota_estrutura = 4.0
        else:
            nota_estrutura = 2.0
        
        if proporcao_vocabulario >= 60:
            nota_vocabulario = 8.0
        elif proporcao_vocabulario >= 45:
            nota_vocabulario = 6.0
        elif proporcao_vocabulario >= 30:
            nota_vocabulario = 4.0
        else:
            nota_vocabulario = 2.0
        
        if num_conectores >= 10:
            nota_gramatica = 8.0
        elif num_conectores >= 6:
            nota_gramatica = 6.0
        elif num_conectores >= 3:
            nota_gramatica = 4.0
        else:
            nota_gramatica = 2.0
        
        nota_final = (nota_coerencia * 0.3 + nota_estrutura * 0.25 + 
                     nota_vocabulario * 0.25 + nota_gramatica * 0.2)
        nota_final = round(nota_final * 2) / 2
        
        # Feedback
        feedback_parts = []
        
        if num_palavras >= 200:
            feedback_parts.append("✅ Ótimo desenvolvimento do tema. Texto bem extenso e detalhado.")
        elif num_palavras >= 150:
            feedback_parts.append("✅ Bom desenvolvimento. Continue expandindo suas ideias.")
        elif num_palavras >= 100:
            feedback_parts.append("📝 Desenvolvimento razoável. Tente aprofundar mais seus argumentos.")
        elif num_palavras >= 50:
            feedback_parts.append("⚠️ Texto curto. É importante desenvolver mais suas ideias.")
        else:
            feedback_parts.append("❌ Texto muito curto. É necessário desenvolver mais o conteúdo.")
        
        if num_paragrafos >= 3:
            feedback_parts.append("✅ Boa organização em parágrafos. Estrutura clara.")
        elif num_paragrafos >= 2:
            feedback_parts.append("📝 Estrutura razoável. Tente dividir melhor em parágrafos.")
        else:
            feedback_parts.append("⚠️ Poucos parágrafos. Organize melhor suas ideias.")
        
        if proporcao_vocabulario >= 60:
            feedback_parts.append("✅ Vocabulário rico e variado. Ótimo uso de palavras.")
        elif proporcao_vocabulario >= 45:
            feedback_parts.append("✅ Bom vocabulário. Continue expandindo seu repertório.")
        else:
            feedback_parts.append("📝 Vocabulário limitado. Busque usar palavras mais variadas.")
        
        if num_conectores >= 8:
            feedback_parts.append("✅ Excelente uso de conectores. Texto muito coeso.")
        elif num_conectores >= 5:
            feedback_parts.append("✅ Bom uso de conectores. Texto coeso.")
        else:
            feedback_parts.append("📝 Poucos conectores. Use mais palavras de ligação.")
        
        dicas = []
        if num_palavras < 150:
            dicas.append("📌 Escreva mais sobre o tema, desenvolvendo cada argumento.")
        if num_paragrafos < 3:
            dicas.append("📌 Divida seu texto em introdução, desenvolvimento e conclusão.")
        if proporcao_vocabulario < 45:
            dicas.append("📌 Busque sinônimos e evite repetir as mesmas palavras.")
        if num_conectores < 5:
            dicas.append("📌 Use mais conectores como 'portanto', 'contudo', 'além disso'.")
        
        if dicas:
            feedback_parts.append("\n💡 **Dicas para melhorar:**")
            feedback_parts.extend(dicas)
        
        if nota_final >= 8:
            conceito = "Excelente"
        elif nota_final >= 6:
            conceito = "Bom"
        elif nota_final >= 4:
            conceito = "Regular"
        else:
            conceito = "Insuficiente"
        
        feedback_completo = "\n\n".join(feedback_parts)
        
        metricas = {
            'palavras': num_palavras,
            'frases': num_frases,
            'paragrafos': num_paragrafos,
            'palavras_unicas': palavras_unicas,
            'proporcao_vocabulario': round(proporcao_vocabulario, 1),
            'conectores': num_conectores,
            'nota_coerencia': round(nota_coerencia, 1),
            'nota_estrutura': round(nota_estrutura, 1),
            'nota_vocabulario': round(nota_vocabulario, 1),
            'nota_gramatica': round(nota_gramatica, 1)
        }
        
        return nota_final, conceito, feedback_completo, metricas
    
    @staticmethod
    def corrigir_redacao_hibrido(imagem_base64=None, texto=None):
        if not texto and imagem_base64:
            texto = CorretorRedacaoHibrido.extrair_texto_ocr(imagem_base64)
        
        if not texto:
            return None, 0.0, None, "Não foi possível extrair o texto", None
        
        nota, conceito, feedback, metricas = CorretorRedacaoHibrido.analisar_redacao(texto)
        
        return texto, nota, conceito, feedback, metricas, 'OCR + Análise Avançada'

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
            'banco': 'PostgreSQL (Supabase)',
            'metodos': ['Contorno', 'OpenCV', 'OCR', 'Análise Avançada']
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'metodos_disponiveis': {
            'Contorno': True,
            'OpenCV': True,
            'OCR': True,
            'Analise_Avancada': True
        },
        'metodo_ativo': 'Híbrido (Contorno + OpenCV + OCR + Análise Avançada)',
        'status': '🧠 Sistema híbrido ativo!',
        'banco': 'PostgreSQL (Supabase)',
        'vantagens': [
            '✅ 100% gratuito',
            '✅ Sem limites de uso',
            '✅ Correção de provas com detecção por contorno',
            '✅ Correção de redações com análise avançada'
        ]
    })

# ============================================
# ROTAS DE ESCOLAS
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

# ============================================
# ROTAS DE TURMAS
# ============================================

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

# ============================================
# ROTAS DE ALUNOS
# ============================================

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
# CORREÇÃO DE PROVAS - HÍBRIDO (COM CONTORNO)
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
        
        corretor = CorretorHibrido()
        respostas_detectadas, confianca, metodo = corretor.detectar_respostas_hibrido(imagem, tipo_questoes)
        
        if not respostas_detectadas:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as respostas'}), 400
        
        while len(respostas_detectadas) < len(gabarito):
            respostas_detectadas.append('?')
        respostas_detectadas = respostas_detectadas[:len(gabarito)]
        
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
            'tipo_questoes': tipo_questoes
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# CORREÇÃO DE REDAÇÃO - HÍBRIDO
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
        
        corretor = CorretorRedacaoHibrido()
        resultado = corretor.corrigir_redacao_hibrido(imagem, texto)
        
        if resultado is None or resultado[0] is None:
            return jsonify({'erro': 'Não foi possível processar a redação'}), 400
        
        texto_corrigido, nota, conceito, feedback, metricas, metodo = resultado
        
        if prova_id and aluno_id:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO correcoes_redacao (prova_id, aluno_id, texto, nota, feedback, data_correcao, metodo_ia) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (prova_id, aluno_id, texto_corrigido, nota, feedback, datetime.now(), metodo))
                conn.commit()
                conn.close()
        
        cores = {
            'Excelente': '#28a745',
            'Bom': '#17a2b8',
            'Regular': '#ffc107',
            'Insuficiente': '#dc3545'
        }
        
        return jsonify({
            'nota': round(nota, 1),
            'conceito': conceito,
            'cor_conceito': cores.get(conceito, '#6c757d'),
            'feedback': feedback,
            'metricas': metricas,
            'texto_original': texto_corrigido[:500] + ('...' if len(texto_corrigido) > 500 else ''),
            'texto_completo': texto_corrigido,
            'metodo_ia': metodo
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

@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    return jsonify({
        'ip': 'render.com', 
        'porta': 10000, 
        'url': 'https://adabee-sistema-3.onrender.com'
    })

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

if __name__ == '__main__':
    try:
        init_database()
    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")
    
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Servidor rodando na porta {port}")
    print("🧠 Sistema Híbrido - Contorno + OpenCV + OCR + Análise Avançada de Redação")
    app.run(host='0.0.0.0', port=port, debug=False)
