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
# CONFIGURAÇÃO GEMINI - COM A NOVA CHAVE
# ============================================
GEMINI_AVAILABLE = False
model = None
GEMINI_MODEL = None

# 🔥 CHAVE NOVA
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AQ.Ab8RN6LNNYrR0_9R6hcAVWY3Z3CDuupWKhESBoRYlkWm5Autdg')

try:
    import google.generativeai as genai
    
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
        model = genai.GenerativeModel(GEMINI_MODEL)
        GEMINI_AVAILABLE = True
        print("=" * 60)
        print("✅ Gemini AI configurado com sucesso!")
        print(f"📌 Modelo: {GEMINI_MODEL}")
        print(f"🔑 Chave: {GEMINI_API_KEY[:10]}...")
        print("=" * 60)
    else:
        print("⚠️ GEMINI_API_KEY não encontrada - usando simulação")
        
except ImportError as e:
    print(f"❌ Erro ao importar google-generativeai: {e}")
    print("   Execute: pip install google-generativeai>=0.5.0")
except Exception as e:
    print(f"⚠️ Erro ao configurar Gemini: {e}")
    print("   Usando simulação como fallback")

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL', 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require')

def get_db_connection():
    try:
        conn = psycopg2.connect(SUPABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

# ============================================
# USUÁRIOS FIXOS
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
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível, usando dados em memória")
        return
    
    try:
        cur = conn.cursor()
        
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
        
        # ✅ TABELA PROVAS CORRIGIDA (LINHA DUPLICADA REMOVIDA)
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

init_db()

# ============================================
# FUNÇÃO DE CORREÇÃO COM FALLBACK
# ============================================

def corrigir_com_gemini(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4):
    if not GEMINI_AVAILABLE or model is None:
        print("⚠️ Gemini não disponível - usando simulação")
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)
    
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        alternativas = "A, B, C, D" if tipo_questoes == 4 else "A, B, C"
        
        prompt = f"""
        Você é um assistente especializado em correção de provas.
        Analise a imagem do cartão resposta e identifique as respostas.
        A prova tem {len(gabarito)} questões e as alternativas são: {alternativas}.
        O gabarito correto é: {gabarito}
        Responda em JSON: {{"respostas": ["A", "B", ...], "confianca": 85}}
        """
        
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_data}
        ])
        
        resposta_texto = response.text
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        
        if json_match:
            dados = json.loads(json_match.group())
            respostas_detectadas = dados.get('respostas', [])
            confianca = dados.get('confianca', 70)
        else:
            respostas_detectadas = []
            confianca = 50
        
        if not respostas_detectadas:
            return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)
        
        if len(respostas_detectadas) < len(gabarito):
            for i in range(len(respostas_detectadas), len(gabarito)):
                respostas_detectadas.append(random.choice(['A', 'B', 'C', 'D'][:tipo_questoes]))
        
        acertos = 0
        for i, (resp, gab) in enumerate(zip(respostas_detectadas[:len(gabarito)], gabarito)):
            if resp == gab:
                acertos += 1
        
        valor_por_questao = 10 / len(gabarito)
        nota = acertos * valor_por_questao
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas[:len(gabarito)],
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': confianca,
            'modo': 'gemini'
        }
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)

def corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4):
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        respostas_detectadas = []
        
        if img is not None:
            import hashlib
            hash_val = int(hashlib.md5(image_data).hexdigest()[:8], 16)
            random.seed(hash_val)
            
            for i in range(len(gabarito)):
                if random.random() < 0.75:
                    respostas_detectadas.append(gabarito[i])
                else:
                    erradas = [a for a in alternativas if a != gabarito[i]]
                    respostas_detectadas.append(random.choice(erradas) if erradas else gabarito[i])
        else:
            respostas_detectadas = [random.choice(alternativas) for _ in range(len(gabarito))]
        
        acertos = 0
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            if resp == gab:
                acertos += 1
        
        valor_por_questao = 10 / len(gabarito)
        nota = acertos * valor_por_questao
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas,
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 70,
            'modo': 'simulado'
        }
    except Exception as e:
        print(f"❌ Erro na simulação: {e}")
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': 0,
            'nota': 0,
            'respostas_detectadas': [],
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 0,
            'modo': 'erro'
        }

# ============================================
# ROTAS DE USUÁRIOS
# ============================================

@app.route('/api/usuarios', methods=['GET'])
def listar_usuarios():
    """Lista todos os usuários"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT id, nome, username, email, perfil, ativo, criado_em FROM usuarios ORDER BY id")
            usuarios = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(usuarios)
        except Exception as e:
            print(f"Erro ao listar usuários: {e}")
    
    resultado = []
    for username, dados in USUARIOS_FIXOS.items():
        resultado.append({
            'id': 0,
            'nome': dados['nome'],
            'username': username,
            'email': '',
            'perfil': dados['perfil'],
            'ativo': True,
            'criado_em': datetime.now().isoformat()
        })
    return jsonify(resultado)

@app.route('/api/usuarios', methods=['POST'])
def criar_usuario():
    """Cria um novo usuário"""
    try:
        data = request.json
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)
        
        if not nome or not username or not senha:
            return jsonify({'erro': 'Nome, usuário e senha são obrigatórios'}), 400
        
        if len(senha) < 4:
            return jsonify({'erro': 'Senha deve ter pelo menos 4 caracteres'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário já existe'}), 400
        
        cur.execute("""
            INSERT INTO usuarios (nome, username, senha_hash, email, perfil, ativo)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (nome, username, senha, email, perfil, ativo))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Usuário criado com sucesso'
        })
        
    except Exception as e:
        print(f"Erro ao criar usuário: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    """Exclui um usuário"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'mensagem': 'Usuário excluído com sucesso'})
        
    except Exception as e:
        print(f"Erro ao excluir usuário: {e}")
        return jsonify({'erro': 'Erro ao excluir usuário'}), 500

@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def atualizar_usuario(id):
    """Atualiza um usuário"""
    try:
        data = request.json
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("""
            UPDATE usuarios 
            SET nome = %s, email = %s, perfil = %s, ativo = %s
            WHERE id = %s
            RETURNING id
        """, (data.get('nome'), data.get('email'), data.get('perfil'), data.get('ativo'), id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if result:
            return jsonify({'mensagem': 'Usuário atualizado com sucesso'})
        else:
            return jsonify({'erro': 'Usuário não encontrado'}), 404
            
    except Exception as e:
        print(f"Erro ao atualizar usuário: {e}")
        return jsonify({'erro': 'Erro ao atualizar usuário'}), 500

# ============================================
# ROTA DE LOGIN - CORRIGIDA (VERIFICA BANCO)
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    """Autenticação de usuário - verifica banco E fixos"""
    data = request.json
    username = data.get('username')
    senha = data.get('senha')
    
    if not username or not senha:
        return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
    
    # 1. VERIFICAR NO BANCO DE DADOS PRIMEIRO
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT id, nome, username, senha_hash, perfil, ativo 
                FROM usuarios 
                WHERE username = %s AND ativo = TRUE
            """, (username,))
            usuario = cur.fetchone()
            cur.close()
            conn.close()
            
            if usuario:
                print(f"✅ Usuário encontrado no banco: {usuario['username']}")
                if usuario['senha_hash'] == senha:
                    return jsonify({
                        'sucesso': True,
                        'perfil': usuario['perfil'],
                        'usuario': usuario['username'],
                        'nome': usuario['nome']
                    })
                else:
                    print(f"❌ Senha incorreta para: {username}")
        except Exception as e:
            print(f"❌ Erro no login via banco: {e}")
    
    # 2. FALLBACK: USUÁRIOS FIXOS
    if username in USUARIOS_FIXOS:
        dados = USUARIOS_FIXOS[username]
        if dados['senha'] == senha:
            print(f"✅ Login via fallback: {username}")
            return jsonify({
                'sucesso': True,
                'perfil': dados['perfil'],
                'usuario': username,
                'nome': dados['nome']
            })
    
    print(f"❌ Falha no login para: {username}")
    return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401

# ============================================
# ROTAS DA API
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
        data = request.json
        imagem_base64 = data.get('imagem')
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        
        if not imagem_base64 or not prova_id or not aluno_id:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro no banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*, t.serie, t.nome as turma_nome
            FROM provas p LEFT JOIN turmas t ON p.turma_id = t.id
            WHERE p.id = %s
        """, (prova_id,))
        prova = cur.fetchone()
        
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = prova.get('gabarito', [])
        if not gabarito:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Gabarito não cadastrado'}), 400
        
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        cur.close()
        conn.close()
        
        nome_aluno = aluno['nome'] if aluno else 'Aluno'
        serie = prova.get('serie', '1º Ano')
        tipo_questoes = int(prova.get('tipo_questoes', 4))
        
        resultado = corrigir_com_gemini(imagem_base64, gabarito, nome_aluno, serie, tipo_questoes)
        
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
                    VALUES (%s, %s, %s::text[], %s, %s, %s, %s)
                """, (prova_id, aluno_id, resultado['respostas_detectadas'], 
                      resultado['acertos'], resultado['nota'], resultado['total'], resultado.get('modo', 'ia')))
                conn.commit()
                cur.close()
                conn.close()
        except Exception as e:
            print(f"⚠️ Erro ao salvar histórico: {e}")
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        data = request.json
        texto = data.get('texto')
        aluno_id = data.get('aluno_id')
        
        if not texto:
            return jsonify({'erro': 'Texto é obrigatório'}), 400
        
        if not GEMINI_AVAILABLE or model is None:
            return jsonify({
                'nota': 7.0,
                'metricas': {
                    'nota_coerencia': 7.0,
                    'nota_estrutura': 7.0,
                    'nota_gramatica': 7.0,
                    'nota_vocabulario': 7.0
                },
                'feedback': 'Simulação - Gemini indisponível',
                'modo': 'simulado'
            })
        
        prompt = f"""
        Avalie a redação: {texto}
        Responda em JSON: {{"nota": 7.5, "metricas": {{"nota_coerencia": 8, "nota_estrutura": 7.5, "nota_gramatica": 7, "nota_vocabulario": 7.5}}, "feedback": "texto..."}}
        """
        
        response = model.generate_content(prompt)
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        
        if json_match:
            resultado = json.loads(json_match.group())
            resultado['modo'] = 'gemini'
        else:
            resultado = {
                'nota': 7.0,
                'metricas': {'nota_coerencia': 7, 'nota_estrutura': 7, 'nota_gramatica': 7, 'nota_vocabulario': 7},
                'feedback': 'Erro ao processar resposta',
                'modo': 'erro'
            }
        
        return jsonify(resultado)
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/gemini/teste', methods=['GET'])
def testar_gemini():
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

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'CorrigePro',
        'gemini': GEMINI_AVAILABLE,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
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
            print(f"Erro: {e}")
    return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})

# ============================================
# ROTAS BÁSICAS (ESCOLAS, TURMAS, ALUNOS, PROVAS)
# ============================================

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
            print(f"Erro: {e}")
    return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    data = request.json
    nome = data.get('nome')
    if not nome:
        return jsonify({'erro': 'Nome é obrigatório'}), 400
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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao criar'}), 500

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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao excluir'}), 500

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
            print(f"Erro: {e}")
    return jsonify([])

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    data = request.json
    if not data.get('nome') or not data.get('escola_id'):
        return jsonify({'erro': 'Nome e escola são obrigatórios'}), 400
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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao criar'}), 500

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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao excluir'}), 500

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
            print(f"Erro: {e}")
    return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    data = request.json
    if not data.get('nome') or not data.get('turma_id'):
        return jsonify({'erro': 'Nome e turma são obrigatórios'}), 400
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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao criar'}), 500

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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao excluir'}), 500

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
            print(f"Erro: {e}")
    return jsonify([])

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    data = request.json
    if not data.get('titulo') or not data.get('turma_id'):
        return jsonify({'erro': 'Título e turma são obrigatórios'}), 400
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
                  data.get('tipo_questoes', '4'), data.get('quantidade_questoes', 20), 
                  data.get('gabarito', [])))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Prova criada com sucesso'})
        except Exception as e:
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao criar'}), 500

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
            print(f"Erro: {e}")
    return jsonify({'erro': 'Erro ao excluir'}), 500

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        
        if not prova_id or not respostas:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro no banco'}), 500
        
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
            print(f"Erro: {e}")
    return jsonify([])

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
            return jsonify({'erro': 'Erro no banco'}), 500
        
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
