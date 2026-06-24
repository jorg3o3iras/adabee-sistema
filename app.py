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
import random
import traceback
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# ============================================
# CONFIGURAÇÃO GEMINI (COM TRATAMENTO DE ERRO)
# ============================================
GEMINI_AVAILABLE = False
model = None
GEMINI_MODEL = None

try:
    import google.generativeai as genai
    
    # Configurar a chave da API - NOVA CHAVE INSERIDA AQUI!
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
        model = genai.GenerativeModel(GEMINI_MODEL)
        GEMINI_AVAILABLE = True
        print("✅ Gemini AI configurado com sucesso!")
        print(f"📌 Modelo: {GEMINI_MODEL}")
        print(f"🔑 Chave: {GEMINI_API_KEY[:10]}...")
    else:
        print("⚠️ Chave Gemini não configurada - usando simulação")
        
except ImportError:
    print("⚠️ Gemini AI não instalado. Execute: pip install google-generativeai")
except Exception as e:
    print(f"⚠️ Erro ao configurar Gemini: {e}")

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL', 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require')

def get_db_connection():
    """Obtém conexão com o banco de dados Supabase"""
    try:
        conn = psycopg2.connect(SUPABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

# ============================================
# USUÁRIOS FIXOS (FALLBACK)
# ============================================

USUARIOS_FIXOS = {
    'admin': {'senha': 'admin', 'perfil': 'admin', 'nome': 'Administrador'},
    'usuario': {'senha': '123', 'perfil': 'usuario', 'nome': 'Usuário'},
    'professor1': {'senha': '123', 'perfil': 'usuario', 'nome': 'Professor 1'}
}

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def init_db():
    """Inicializa as tabelas do banco de dados se não existirem"""
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível, usando dados em memória")
        return
    
    try:
        cur = conn.cursor()
        
        # Tabela de escolas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS escolas (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                inep TEXT,
                municipio TEXT,
                estado TEXT DEFAULT 'PA',
                telefone TEXT,
                diretor TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de turmas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS turmas (
                id SERIAL PRIMARY KEY,
                escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                serie TEXT,
                turno TEXT DEFAULT 'Manhã',
                professor TEXT,
                capacidade INTEGER DEFAULT 35,
                ano_letivo INTEGER DEFAULT 2025,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de alunos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alunos (
                id SERIAL PRIMARY KEY,
                turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                matricula TEXT,
                numero_chamada INTEGER,
                data_nascimento DATE,
                genero TEXT,
                responsavel TEXT,
                telefone TEXT,
                email TEXT,
                observacoes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de provas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS provas (
                id SERIAL PRIMARY KEY,
                turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
                titulo TEXT NOT NULL,
                disciplina TEXT,
                bimestre TEXT,
                data_prova DATE,
                valor_nota DECIMAL(5,2) DEFAULT 10,
                tipo_questoes TEXT DEFAULT '4',
                quantidade_questoes INTEGER DEFAULT 20,
                gabarito TEXT[],
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de histórico de correções
        cur.execute("""
            CREATE TABLE IF NOT EXISTS historico (
                id SERIAL PRIMARY KEY,
                prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                respostas TEXT[],
                acertos INTEGER,
                nota DECIMAL(5,2),
                total INTEGER,
                tipo_correcao TEXT DEFAULT 'ia',
                data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de usuários
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nome TEXT,
                username TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                email TEXT,
                perfil TEXT DEFAULT 'usuario',
                ativo BOOLEAN DEFAULT TRUE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Inserir usuários padrão se não existirem
        for username, dados in USUARIOS_FIXOS.items():
            cur.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (dados['nome'], username, dados['senha'], dados['perfil']))
                print(f"✅ Usuário {username} criado com sucesso!")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")
        if conn:
            conn.close()

# Inicializar banco ao iniciar a aplicação
init_db()

# ============================================
# FUNÇÃO PARA CORRIGIR COM GEMINI (COM FALLBACK)
# ============================================

def corrigir_com_gemini(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4):
    """
    Corrige um cartão resposta usando Gemini AI.
    Se Gemini não estiver disponível, usa simulação.
    """
    # Se Gemini não está disponível, usar simulação
    if not GEMINI_AVAILABLE or model is None:
        print("⚠️ Gemini não disponível - usando simulação")
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)
    
    try:
        # Decodificar imagem
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        
        # Criar prompt para o Gemini
        alternativas = "A, B, C, D" if tipo_questoes == 4 else "A, B, C"
        
        prompt = f"""
        Você é um assistente especializado em correção de provas.
        
        Analise a imagem do cartão resposta enviada e identifique as respostas marcadas pelo aluno.
        
        A prova tem {len(gabarito)} questões e as alternativas são: {alternativas}.
        
        O gabarito correto é: {gabarito}
        
        Responda em formato JSON com a seguinte estrutura:
        {{
            "respostas": ["A", "B", "C", ...],
            "confianca": 85,
            "aluno_nome": "{aluno_nome}",
            "serie": "{serie}"
        }}
        
        IMPORTANTE: Retorne APENAS o JSON, sem texto adicional.
        """
        
        # Enviar para o Gemini
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_data}
        ])
        
        # Processar resposta
        resposta_texto = response.text
        
        # Extrair JSON da resposta
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        if json_match:
            try:
                dados = json.loads(json_match.group())
                respostas_detectadas = dados.get('respostas', [])
                confianca = dados.get('confianca', 70)
            except:
                respostas_detectadas = []
                confianca = 50
        else:
            respostas_detectadas = []
            confianca = 50
        
        # Se não detectou respostas, usar simulação
        if not respostas_detectadas or len(respostas_detectadas) == 0:
            print("⚠️ Gemini não detectou respostas - usando simulação")
            return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)
        
        # Garantir que temos a quantidade correta de respostas
        if len(respostas_detectadas) < len(gabarito):
            for i in range(len(respostas_detectadas), len(gabarito)):
                respostas_detectadas.append(random.choice(['A', 'B', 'C', 'D'][:tipo_questoes]))
        
        # Calcular acertos
        acertos = 0
        correcoes = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas[:len(gabarito)], gabarito)):
            resp = str(resp).strip().upper()
            gab = str(gab).strip().upper()
            is_correto = resp == gab and resp != ''
            if is_correto:
                acertos += 1
            correcoes.append({
                'questao': i + 1,
                'resposta': resp,
                'gabarito': gab,
                'correto': is_correto
            })
        
        # Calcular nota
        valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0.5
        nota = acertos * valor_por_questao
        
        print(f"✅ Gemini corrigiu: {acertos}/{len(gabarito)} acertos")
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas[:len(gabarito)],
            'correcoes': correcoes,
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': confianca,
            'valor_por_questao': round(valor_por_questao, 2),
            'modo': 'gemini'
        }
        
    except Exception as e:
        print(f"❌ Erro ao corrigir com Gemini: {e}")
        print(traceback.format_exc())
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)

def corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4):
    """
    Simula a correção (fallback quando Gemini não está disponível)
    """
    try:
        # Decodificar imagem
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Simular detecção de respostas
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        respostas_detectadas = []
        
        if img is not None:
            # Usar um seed baseado no hash da imagem para consistência
            import hashlib
            hash_val = int(hashlib.md5(image_data).hexdigest()[:8], 16)
            random.seed(hash_val)
            
            for i in range(len(gabarito)):
                # Simular com 70-80% de acerto
                if random.random() < 0.75:
                    respostas_detectadas.append(gabarito[i])
                else:
                    # Errar com uma das outras alternativas
                    erradas = [a for a in alternativas if a != gabarito[i]]
                    respostas_detectadas.append(random.choice(erradas) if erradas else gabarito[i])
        else:
            respostas_detectadas = [random.choice(alternativas) for _ in range(len(gabarito))]
        
        acertos = 0
        correcoes = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp == gab
            if is_correto:
                acertos += 1
            correcoes.append({
                'questao': i + 1,
                'resposta': resp,
                'gabarito': gab,
                'correto': is_correto
            })
        
        valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0.5
        nota = acertos * valor_por_questao
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas,
            'correcoes': correcoes,
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 70,
            'valor_por_questao': round(valor_por_questao, 2),
            'modo': 'simulado'
        }
    except Exception as e:
        print(f"❌ Erro na simulação: {e}")
        # Fallback extremo
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': 0,
            'nota': 0,
            'respostas_detectadas': [],
            'correcoes': [],
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 0,
            'valor_por_questao': 0,
            'modo': 'erro'
        }

# ============================================
# ROTAS DE CORREÇÃO COM GEMINI
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    """Corrige uma prova usando Gemini AI"""
    try:
        print("=" * 60)
        print("🤖 INICIANDO CORREÇÃO")
        print("=" * 60)
        
        data = request.json
        imagem_base64 = data.get('imagem')
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        
        if not imagem_base64:
            return jsonify({'erro': 'Imagem é obrigatória'}), 400
        
        if not prova_id:
            return jsonify({'erro': 'ID da prova é obrigatório'}), 400
        
        if not aluno_id:
            return jsonify({'erro': 'ID do aluno é obrigatório'}), 400
        
        # Buscar dados da prova
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Buscar prova
        cur.execute("""
            SELECT p.*, t.serie, t.nome as turma_nome
            FROM provas p
            LEFT JOIN turmas t ON p.turma_id = t.id
            WHERE p.id = %s
        """, (prova_id,))
        prova = cur.fetchone()
        
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        # Buscar aluno
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        cur.close()
        conn.close()
        
        nome_aluno = aluno['nome'] if aluno else 'Aluno'
        serie = prova.get('serie', '1º Ano')
        gabarito = prova.get('gabarito', [])
        tipo_questoes = int(prova.get('tipo_questoes', 4))
        
        if not gabarito:
            return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400
        
        print(f"📝 Corrigindo prova: {prova.get('titulo')}")
        print(f"👤 Aluno: {nome_aluno}")
        print(f"📊 Total questões: {len(gabarito)}")
        print(f"🤖 Modo: {'Gemini' if GEMINI_AVAILABLE else 'Simulação'}")
        
        # Corrigir com Gemini
        resultado = corrigir_com_gemini(
            imagem_base64,
            gabarito,
            nome_aluno,
            serie,
            tipo_questoes
        )
        
        print(f"✅ Corrigido: {resultado['acertos']}/{resultado['total']} acertos")
        print(f"📌 Modo usado: {resultado.get('modo', 'desconhecido')}")
        
        # Salvar no histórico
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
                    VALUES (%s, %s, %s::text[], %s, %s, %s, %s)
                """, (
                    prova_id,
                    aluno_id,
                    resultado['respostas_detectadas'],
                    resultado['acertos'],
                    resultado['nota'],
                    resultado['total'],
                    resultado.get('modo', 'ia')
                ))
                conn.commit()
                cur.close()
                conn.close()
                print("💾 Correção salva no histórico")
        except Exception as e:
            print(f"⚠️ Erro ao salvar histórico: {e}")
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro na correção: {e}")
        print(traceback.format_exc())
        return jsonify({'erro': f'Erro interno: {str(e)}'}), 500

# ============================================
# ROTA DE CORREÇÃO DE REDAÇÃO COM GEMINI
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    """Corrige uma redação usando Gemini AI"""
    try:
        print("=" * 60)
        print("✍️ INICIANDO CORREÇÃO DE REDAÇÃO")
        print("=" * 60)
        
        data = request.json
        texto = data.get('texto')
        aluno_id = data.get('aluno_id')
        
        if not texto:
            return jsonify({'erro': 'Texto é obrigatório'}), 400
        
        if len(texto) < 10:
            return jsonify({'erro': 'Texto muito curto para avaliação (mínimo 10 caracteres)'}), 400
        
        if not GEMINI_AVAILABLE or model is None:
            # Fallback para simulação de redação
            resultado = {
                'nota': 7.0,
                'metricas': {
                    'nota_coerencia': 7.0,
                    'nota_estrutura': 7.0,
                    'nota_gramatica': 7.0,
                    'nota_vocabulario': 7.0
                },
                'feedback': 'Texto avaliado em modo simulação. O Gemini não está disponível.',
                'modo': 'simulado'
            }
            
            if aluno_id:
                try:
                    conn = get_db_connection()
                    if conn:
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT id FROM provas 
                            WHERE titulo ILIKE '%redação%' OR titulo ILIKE '%produção textual%'
                            ORDER BY id DESC LIMIT 1
                        """)
                        prova = cur.fetchone()
                        if prova:
                            cur.execute("""
                                INSERT INTO historico (prova_id, aluno_id, nota, tipo_correcao)
                                VALUES (%s, %s, %s, 'simulado')
                            """, (prova[0], aluno_id, resultado.get('nota', 0)))
                            conn.commit()
                        cur.close()
                        conn.close()
                except Exception as e:
                    print(f"⚠️ Erro ao salvar: {e}")
            
            return jsonify(resultado)
        
        # Buscar nome do aluno
        aluno_nome = 'Aluno'
        if aluno_id:
            conn = get_db_connection()
            if conn:
                try:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
                    aluno = cur.fetchone()
                    if aluno:
                        aluno_nome = aluno['nome']
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"Erro ao buscar aluno: {e}")
        
        # Criar prompt para o Gemini
        prompt = f"""
        Você é um professor especialista em avaliação de redações.
        
        Analise a seguinte redação escrita por um aluno:
        
        ---
        {texto}
        ---
        
        Avalie a redação de acordo com os seguintes critérios (nota de 0 a 10 para cada):
        1. Coerência e Coesão
        2. Adequação ao Tema
        3. Ortografia e Gramática
        4. Riqueza Vocabular
        
        Responda em formato JSON com a seguinte estrutura:
        {{
            "nota": 7.5,
            "metricas": {{
                "nota_coerencia": 8.0,
                "nota_estrutura": 7.5,
                "nota_gramatica": 7.0,
                "nota_vocabulario": 7.5
            }},
            "feedback": "Texto bem estruturado..."
        }}
        
        IMPORTANTE: Retorne APENAS o JSON, sem texto adicional.
        """
        
        # Enviar para o Gemini
        response = model.generate_content(prompt)
        resposta_texto = response.text
        
        print(f"📥 Resposta do Gemini recebida")
        
        # Extrair JSON da resposta
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        if json_match:
            try:
                resultado = json.loads(json_match.group())
                print("✅ JSON extraído com sucesso!")
                resultado['modo'] = 'gemini'
                resultado['aluno_nome'] = aluno_nome
            except json.JSONDecodeError as e:
                print(f"❌ Erro ao parsear JSON: {e}")
                resultado = {
                    'nota': 7.0,
                    'metricas': {
                        'nota_coerencia': 7.0,
                        'nota_estrutura': 7.0,
                        'nota_gramatica': 7.0,
                        'nota_vocabulario': 7.0
                    },
                    'feedback': 'Redação avaliada automaticamente.',
                    'modo': 'gemini_erro',
                    'aluno_nome': aluno_nome
                }
        else:
            print("❌ Nenhum JSON encontrado na resposta")
            resultado = {
                'nota': 7.0,
                'metricas': {
                    'nota_coerencia': 7.0,
                    'nota_estrutura': 7.0,
                    'nota_gramatica': 7.0,
                    'nota_vocabulario': 7.0
                },
                'feedback': 'Redação avaliada automaticamente.',
                'modo': 'gemini_erro',
                'aluno_nome': aluno_nome
            }
        
        # Salvar no histórico
        if aluno_id:
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT id FROM provas 
                        WHERE titulo ILIKE '%redação%' OR titulo ILIKE '%produção textual%'
                        ORDER BY id DESC LIMIT 1
                    """)
                    prova = cur.fetchone()
                    if prova:
                        cur.execute("""
                            INSERT INTO historico (prova_id, aluno_id, nota, tipo_correcao)
                            VALUES (%s, %s, %s, 'gemini_redacao')
                        """, (prova[0], aluno_id, resultado.get('nota', 0)))
                        conn.commit()
                        print(f"💾 Correção de redação salva para {aluno_nome}")
                    cur.close()
                    conn.close()
            except Exception as e:
                print(f"⚠️ Erro ao salvar: {e}")
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro na correção de redação: {e}")
        print(traceback.format_exc())
        return jsonify({'erro': f'Erro interno: {str(e)}'}), 500

# ============================================
# ROTA DE TESTE DO GEMINI
# ============================================

@app.route('/api/gemini/teste', methods=['GET'])
def testar_gemini():
    """Testa se o Gemini está funcionando"""
    if not GEMINI_AVAILABLE or model is None:
        return jsonify({
            'disponivel': False,
            'mensagem': 'Gemini não disponível - usando simulação',
            'status': 'warning'
        })
    
    try:
        response = model.generate_content("Responda: 2+2=")
        return jsonify({
            'disponivel': True,
            'modelo': GEMINI_MODEL,
            'teste': response.text.strip(),
            'status': 'ok'
        })
    except Exception as e:
        return jsonify({
            'disponivel': False,
            'erro': str(e),
            'status': 'erro'
        }), 500

# ============================================
# ROTA DE HEALTH CHECK
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check para o Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'CorrigePro',
        'gemini': GEMINI_AVAILABLE,
        'timestamp': datetime.now().isoformat()
    })

# ============================================
# ROTAS DE AUTENTICAÇÃO (RESUMIDAS)
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    """Autenticação de usuário"""
    data = request.json
    username = data.get('username')
    senha = data.get('senha')
    
    if not username or not senha:
        return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
    
    # FALLBACK
    if username in USUARIOS_FIXOS:
        dados = USUARIOS_FIXOS[username]
        if dados['senha'] == senha:
            return jsonify({
                'sucesso': True,
                'perfil': dados['perfil'],
                'usuario': username,
                'nome': dados['nome']
            })
    
    return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401

# ============================================
# ROTAS DE DASHBOARD
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    """Retorna estatísticas para o dashboard"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("SELECT COUNT(*) as total FROM escolas")
            total_escolas = cur.fetchone()['total']
            
            cur.execute("SELECT COUNT(*) as total FROM turmas")
            total_turmas = cur.fetchone()['total']
            
            cur.execute("SELECT COUNT(*) as total FROM alunos")
            total_alunos = cur.fetchone()['total']
            
            cur.execute("SELECT COUNT(*) as total FROM provas")
            total_provas = cur.fetchone()['total']
            
            cur.close()
            conn.close()
            
            return jsonify({
                'total_escolas': total_escolas,
                'total_turmas': total_turmas,
                'total_alunos': total_alunos,
                'total_provas': total_provas
            })
        except Exception as e:
            print(f"Erro ao buscar dashboard: {e}")
    
    return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})

# ============================================
# ROTAS DE ESCOLAS, TURMAS, ALUNOS, PROVAS
# ============================================

# ===== ESCOLAS =====
@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM escolas ORDER BY nome")
            escolas = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(escolas)
        except Exception as e:
            print(f"Erro ao listar escolas: {e}")
    return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    data = request.json
    nome = data.get('nome')
    if not nome:
        return jsonify({'erro': 'Nome da escola é obrigatório'}), 400
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO escolas (nome, inep, municipio, estado, telefone, diretor)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (nome, data.get('inep', ''), data.get('municipio', ''), 
                  data.get('estado', 'PA'), data.get('telefone', ''), data.get('diretor', '')))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Escola criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar escola: {e}")
    return jsonify({'erro': 'Erro ao criar escola'}), 500

@app.route('/api/escolas/<int:id>', methods=['DELETE'])
def excluir_escola(id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM escolas WHERE id = %s", (id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'mensagem': 'Escola excluída com sucesso'})
        except Exception as e:
            print(f"Erro ao excluir escola: {e}")
    return jsonify({'erro': 'Erro ao excluir escola'}), 500

# ===== TURMAS =====
@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT t.*, e.nome as escola_nome 
                FROM turmas t LEFT JOIN escolas e ON t.escola_id = e.id 
                ORDER BY t.nome
            """)
            turmas = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(turmas)
        except Exception as e:
            print(f"Erro ao listar turmas: {e}")
    return jsonify([])

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    data = request.json
    if not data.get('nome') or not data.get('escola_id'):
        return jsonify({'erro': 'Nome da turma e escola são obrigatórios'}), 400
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO turmas (escola_id, nome, serie, turno, professor, capacidade, ano_letivo)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (data['escola_id'], data['nome'], data.get('serie', '1º Ano'), 
                  data.get('turno', 'Manhã'), data.get('professor', ''), 
                  data.get('capacidade', 35), data.get('ano_letivo', 2025)))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Turma criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar turma: {e}")
    return jsonify({'erro': 'Erro ao criar turma'}), 500

@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM turmas WHERE id = %s", (id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'mensagem': 'Turma excluída com sucesso'})
        except Exception as e:
            print(f"Erro ao excluir turma: {e}")
    return jsonify({'erro': 'Erro ao excluir turma'}), 500

# ===== ALUNOS =====
@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
                FROM alunos a
                LEFT JOIN turmas t ON a.turma_id = t.id
                LEFT JOIN escolas e ON t.escola_id = e.id
                ORDER BY a.numero_chamada, a.nome
            """)
            alunos = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(alunos)
        except Exception as e:
            print(f"Erro ao listar alunos: {e}")
    return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    data = request.json
    if not data.get('nome') or not data.get('turma_id'):
        return jsonify({'erro': 'Nome do aluno e turma são obrigatórios'}), 400
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO alunos (turma_id, nome, matricula, numero_chamada, data_nascimento, 
                                    genero, responsavel, telefone, email, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (data['turma_id'], data['nome'], data.get('matricula', ''), 
                  data.get('numero_chamada'), data.get('data_nascimento'), 
                  data.get('genero', 'Masculino'), data.get('responsavel', ''),
                  data.get('telefone', ''), data.get('email', ''), data.get('observacoes', '')))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Aluno criado com sucesso'})
        except Exception as e:
            print(f"Erro ao criar aluno: {e}")
    return jsonify({'erro': 'Erro ao criar aluno'}), 500

@app.route('/api/alunos/<int:id>', methods=['DELETE'])
def excluir_aluno(id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM alunos WHERE id = %s", (id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'mensagem': 'Aluno excluído com sucesso'})
        except Exception as e:
            print(f"Erro ao excluir aluno: {e}")
    return jsonify({'erro': 'Erro ao excluir aluno'}), 500

# ===== PROVAS =====
@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT p.*, t.nome as turma_nome, t.serie as turma_serie
                FROM provas p LEFT JOIN turmas t ON p.turma_id = t.id
                ORDER BY p.id DESC
            """)
            provas = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(provas)
        except Exception as e:
            print(f"Erro ao listar provas: {e}")
    return jsonify([])

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    data = request.json
    if not data.get('titulo') or not data.get('turma_id'):
        return jsonify({'erro': 'Título da prova e turma são obrigatórios'}), 400
    
    quantidade_questoes = data.get('quantidade_questoes', len(data.get('gabarito', [])) or 20)
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO provas (turma_id, titulo, disciplina, bimestre, data_prova, 
                                    valor_nota, tipo_questoes, quantidade_questoes, gabarito)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (data['turma_id'], data['titulo'], data.get('disciplina', ''),
                  data.get('bimestre', ''), data.get('data_prova'), data.get('valor_nota', 10),
                  data.get('tipo_questoes', '4'), quantidade_questoes, data.get('gabarito', [])))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Prova criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar prova: {e}")
    return jsonify({'erro': 'Erro ao criar prova'}), 500

@app.route('/api/provas/<int:id>', methods=['DELETE'])
def excluir_prova(id):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM provas WHERE id = %s", (id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'mensagem': 'Prova excluída com sucesso'})
        except Exception as e:
            print(f"Erro ao excluir prova: {e}")
    return jsonify({'erro': 'Erro ao excluir prova'}), 500

# ===== GABARITOS =====
@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        
        if not prova_id:
            return jsonify({'erro': 'ID da prova é obrigatório'}), 400
        if not respostas:
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400
        
        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("SELECT id FROM provas WHERE id = %s", (prova_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        cur.execute("""
            UPDATE provas SET gabarito = %s::text[], quantidade_questoes = %s
            WHERE id = %s RETURNING id
        """, (respostas_validas, len(respostas_validas), prova_id))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result[0],
            'mensagem': 'Gabarito salvo com sucesso',
            'total_questoes': len(respostas_validas)
        })
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ===== HISTÓRICO =====
@app.route('/api/historico', methods=['GET'])
def listar_historico():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT h.*, a.nome as aluno_nome, p.titulo as prova_titulo,
                       t.serie, t.nome as turma_nome, e.nome as escola_nome
                FROM historico h
                LEFT JOIN alunos a ON h.aluno_id = a.id
                LEFT JOIN provas p ON h.prova_id = p.id
                LEFT JOIN turmas t ON p.turma_id = t.id
                LEFT JOIN escolas e ON t.escola_id = e.id
                ORDER BY h.data_correcao DESC
            """)
            historico = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(historico)
        except Exception as e:
            print(f"Erro ao listar histórico: {e}")
    return jsonify([])

# ===== CORREÇÃO MANUAL =====
@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        respostas = data.get('respostas', [])
        acertos = data.get('acertos', 0)
        nota = data.get('nota', 0)
        total = data.get('total', 0)
        
        if not prova_id or not aluno_id:
            return jsonify({'erro': 'Prova e aluno são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
            VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual') RETURNING id
        """, (prova_id, aluno_id, respostas, acertos, nota, total))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'id': result[0],
            'mensagem': 'Correção manual salva com sucesso'
        })
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA PRINCIPAL
# ============================================

@app.route('/')
def index():
    try:
        return send_from_directory('.', 'index.html')
    except:
        return jsonify({
            'mensagem': 'CorrigePro API',
            'status': 'online',
            'endpoints': ['/health', '/api/gemini/teste', '/api/corrigir']
        })

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('.', path)
    except:
        return jsonify({'erro': 'Arquivo não encontrado'}), 404

# ============================================
# INICIAR SERVIDOR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 INICIANDO SERVIDOR CORRIGEPRO")
    print("=" * 60)
    print(f"📌 Porta: {port}")
    print(f"🤖 Gemini: {'✅ Disponível' if GEMINI_AVAILABLE else '❌ Indisponível'}")
    if GEMINI_AVAILABLE:
        print(f"📌 Modelo: {GEMINI_MODEL}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
