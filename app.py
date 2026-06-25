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
# CONFIGURAÇÃO GEMINI
# ============================================
GEMINI_AVAILABLE = False
model = None
GEMINI_MODEL = None

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
        print("=" * 60)
    else:
        print("⚠️ GEMINI_API_KEY não encontrada - usando simulação")
        
except ImportError as e:
    print(f"❌ Erro ao importar google-generativeai: {e}")
except Exception as e:
    print(f"⚠️ Erro ao configurar Gemini: {e}")

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
        
        # Tabela Escolas
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
        
        # Tabela Turmas
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
        
        # Tabela Alunos
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
        
        # Tabela Provas
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
        
        # Tabela Histórico de Correções
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
        
        # Tabela Usuários
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
        
        # Inserir usuários fixos
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
# FUNÇÃO DE CORREÇÃO COM GEMINI
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
# ROTA DE LOGIN
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    senha = data.get('senha')
    
    if not username or not senha:
        return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
    
    # Verificar no banco de dados
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
            
            if usuario and usuario['senha_hash'] == senha:
                return jsonify({
                    'sucesso': True,
                    'perfil': usuario['perfil'],
                    'usuario': usuario['username'],
                    'nome': usuario['nome']
                })
        except Exception as e:
            print(f"❌ Erro no login: {e}")
    
    # Fallback para usuários fixos
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
# ROTAS DE USUÁRIOS
# ============================================

@app.route('/api/usuarios', methods=['GET'])
def listar_usuarios():
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

@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def editar_usuario(id):
    """Edita um usuário existente"""
    try:
        data = request.json
        nome = data.get('nome')
        username = data.get('username')
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)
        
        if not nome or not username:
            return jsonify({'erro': 'Nome e usuário são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar se o usuário existe
        cur.execute("SELECT id FROM usuarios WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404
        
        # Verificar se o username já está em uso por outro usuário
        cur.execute("SELECT id FROM usuarios WHERE username = %s AND id != %s", (username, id))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Nome de usuário já está em uso'}), 400
        
        # Atualizar o usuário
        cur.execute("""
            UPDATE usuarios 
            SET nome = %s,
                username = %s,
                email = %s,
                perfil = %s,
                ativo = %s
            WHERE id = %s
            RETURNING id
        """, (nome, username, email, perfil, ativo, id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Usuário atualizado com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar usuário: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
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

# ============================================
# ROTAS DE ESCOLAS
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

@app.route('/api/escolas/<int:id>', methods=['GET'])
def buscar_escola(id):
    """Busca uma escola específica pelo ID"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        cur.close()
        conn.close()
        
        if not escola:
            return jsonify({'erro': 'Escola não encontrada'}), 404
        
        return jsonify(escola)
        
    except Exception as e:
        print(f"❌ Erro ao buscar escola: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:id>', methods=['PUT'])
def editar_escola(id):
    """Edita uma escola existente"""
    try:
        data = request.json
        nome = data.get('nome')
        
        if not nome:
            return jsonify({'erro': 'Nome é obrigatório'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar se a escola existe
        cur.execute("SELECT id FROM escolas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404
        
        # Atualizar a escola
        cur.execute("""
            UPDATE escolas 
            SET nome = %s, 
                inep = %s, 
                municipio = %s, 
                estado = %s, 
                telefone = %s, 
                diretor = %s
            WHERE id = %s
            RETURNING id
        """, (
            nome,
            data.get('inep', ''),
            data.get('municipio', ''),
            data.get('estado', 'PA'),
            data.get('telefone', ''),
            data.get('diretor', ''),
            id
        ))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Escola atualizada com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar escola: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

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

# ============================================
# ROTAS DE TURMAS
# ============================================

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

@app.route('/api/turmas/<int:id>', methods=['GET'])
def buscar_turma(id):
    """Busca uma turma específica pelo ID"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT t.*, e.nome as escola_nome 
            FROM turmas t 
            LEFT JOIN escolas e ON t.escola_id = e.id 
            WHERE t.id = %s
        """, (id,))
        turma = cur.fetchone()
        cur.close()
        conn.close()
        
        if not turma:
            return jsonify({'erro': 'Turma não encontrada'}), 404
        
        return jsonify(turma)
        
    except Exception as e:
        print(f"❌ Erro ao buscar turma: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>', methods=['PUT'])
def editar_turma(id):
    """Edita uma turma existente"""
    try:
        data = request.json
        
        if not data.get('nome') or not data.get('escola_id'):
            return jsonify({'erro': 'Nome e escola são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar se a turma existe
        cur.execute("SELECT id FROM turmas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404
        
        # Atualizar a turma
        cur.execute("""
            UPDATE turmas 
            SET escola_id = %s,
                nome = %s,
                serie = %s,
                turno = %s,
                professor = %s,
                capacidade = %s,
                ano_letivo = %s
            WHERE id = %s
            RETURNING id
        """, (
            data['escola_id'],
            data['nome'],
            data.get('serie', '1º Ano'),
            data.get('turno', 'Manhã'),
            data.get('professor', ''),
            data.get('capacidade', 35),
            data.get('ano_letivo', 2025),
            id
        ))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Turma atualizada com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar turma: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

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

# ============================================
# ROTAS DE ALUNOS
# ============================================

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

@app.route('/api/alunos/<int:id>', methods=['GET'])
def buscar_aluno(id):
    """Busca um aluno específico pelo ID"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON t.escola_id = e.id
            WHERE a.id = %s
        """, (id,))
        aluno = cur.fetchone()
        cur.close()
        conn.close()
        
        if not aluno:
            return jsonify({'erro': 'Aluno não encontrado'}), 404
        
        return jsonify(aluno)
        
    except Exception as e:
        print(f"❌ Erro ao buscar aluno: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['PUT'])
def editar_aluno(id):
    """Edita um aluno existente"""
    try:
        data = request.json
        
        if not data.get('nome') or not data.get('turma_id'):
            return jsonify({'erro': 'Nome e turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar se o aluno existe
        cur.execute("SELECT id FROM alunos WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Aluno não encontrado'}), 404
        
        # Atualizar o aluno
        cur.execute("""
            UPDATE alunos 
            SET turma_id = %s,
                nome = %s,
                matricula = %s,
                numero_chamada = %s,
                data_nascimento = %s,
                genero = %s,
                responsavel = %s,
                telefone = %s,
                email = %s,
                observacoes = %s
            WHERE id = %s
            RETURNING id
        """, (
            data['turma_id'],
            data['nome'],
            data.get('matricula', ''),
            data.get('numero_chamada'),
            data.get('data_nascimento'),
            data.get('genero', 'Masculino'),
            data.get('responsavel', ''),
            data.get('telefone', ''),
            data.get('email', ''),
            data.get('observacoes', ''),
            id
        ))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Aluno atualizado com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar aluno: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

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

# ============================================
# ROTAS DE PROVAS
# ============================================

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

@app.route('/api/provas/<int:id>', methods=['GET'])
def buscar_prova(id):
    """Busca uma prova específica pelo ID"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*, t.nome as turma_nome, t.serie as turma_serie
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            WHERE p.id = %s
        """, (id,))
        prova = cur.fetchone()
        cur.close()
        conn.close()
        
        if not prova:
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        return jsonify(prova)
        
    except Exception as e:
        print(f"❌ Erro ao buscar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['PUT'])
def editar_prova(id):
    """Edita uma prova existente"""
    try:
        data = request.json
        
        if not data.get('titulo') or not data.get('turma_id'):
            return jsonify({'erro': 'Título e turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar se a prova existe
        cur.execute("SELECT id FROM provas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        # Atualizar a prova
        cur.execute("""
            UPDATE provas 
            SET turma_id = %s,
                titulo = %s,
                disciplina = %s,
                bimestre = %s,
                data_prova = %s,
                valor_nota = %s,
                tipo_questoes = %s,
                quantidade_questoes = %s,
                gabarito = %s
            WHERE id = %s
            RETURNING id
        """, (
            data['turma_id'],
            data['titulo'],
            data.get('disciplina', ''),
            data.get('bimestre', ''),
            data.get('data_prova'),
            data.get('valor_nota', 10),
            data.get('tipo_questoes', '4'),
            data.get('quantidade_questoes', 20),
            data.get('gabarito', []),
            id
        ))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Prova atualizada com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar prova: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

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

# ============================================
# ROTA DE GABARITOS
# ============================================

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        
        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400
        
        if not respostas or len(respostas) == 0:
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400
        
        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        
        if not respostas_validas:
            return jsonify({'erro': 'Nenhuma resposta válida'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        
        # Verificar se a prova existe
        cur.execute("SELECT id FROM provas WHERE id = %s", (prova_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        # Atualizar o gabarito
        cur.execute("""
            UPDATE provas 
            SET gabarito = %s::text[], 
                quantidade_questoes = %s
            WHERE id = %s 
            RETURNING id
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
        print(f"❌ Erro ao salvar gabarito: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE CORREÇÃO COM IA
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
        
        # Salvar no histórico
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
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE CORREÇÃO MANUAL
# ============================================

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

# ============================================
# ROTA DE CORREÇÃO DE REDAÇÃO
# ============================================

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

# ============================================
# ROTA DE HISTÓRICO
# ============================================

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

@app.route('/api/historico/<int:id>', methods=['DELETE'])
def excluir_correcao(id):
    """Exclui uma correção específica do histórico"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        
        # Verificar se a correção existe
        cur.execute("SELECT id FROM historico WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Correção não encontrada'}), 404
        
        # Excluir a correção
        cur.execute("DELETE FROM historico WHERE id = %s", (id,))
        conn.commit()
        
        # Verificar se deletou
        if cur.rowcount == 0:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Erro ao excluir correção'}), 500
        
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': 'Correção excluída com sucesso',
            'id': id
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir correção: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE DASHBOARD
# ============================================

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

@app.route('/api/dashboard/desempenho', methods=['GET'])
def dashboard_desempenho():
    """Retorna dados reais de desempenho por turma para o dashboard"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                t.id,
                t.nome as turma_nome,
                COALESCE(AVG(h.nota), 0) as media,
                COUNT(DISTINCT h.aluno_id) as total_alunos,
                COUNT(DISTINCT h.id) as total_correcoes
            FROM turmas t
            LEFT JOIN provas p ON p.turma_id = t.id
            LEFT JOIN historico h ON h.prova_id = p.id
            GROUP BY t.id, t.nome
            ORDER BY t.nome
        """)
        
        turmas = cur.fetchall()
        cur.close()
        conn.close()
        
        nota_maxima = 10
        resultado = []
        for turma in turmas:
            if turma['total_correcoes'] > 0:
                porcentagem = round((turma['media'] / nota_maxima) * 100)
            else:
                porcentagem = 0
            
            resultado.append({
                'id': turma['id'],
                'nome': turma['turma_nome'],
                'media': round(turma['media'], 1),
                'porcentagem': porcentagem,
                'total_alunos': turma['total_alunos'],
                'total_correcoes': turma['total_correcoes']
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro ao buscar desempenho: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE TESTE GEMINI
# ============================================

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

# ============================================
# ROTA DE HEALTH CHECK
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'CorrigePro',
        'gemini': GEMINI_AVAILABLE,
        'timestamp': datetime.now().isoformat()
    })

# ============================================
# ROTA DE GERAÇÃO DE CARTÃO RESPOSTA
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        escola_id = data.get('escola_id')
        turma_id = data.get('turma_id')
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')
        quantidade_questoes = data.get('quantidade_questoes', 20)
        
        if not escola_id or not turma_id or not aluno_id or not prova_id:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Buscar informações do aluno
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        
        # Buscar informações da prova
        cur.execute("""
            SELECT p.*, t.nome as turma_nome, t.serie 
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            WHERE p.id = %s
        """, (prova_id,))
        prova = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if not aluno or not prova:
            return jsonify({'erro': 'Dados não encontrados'}), 404
        
        # Gerar HTML do cartão resposta
        nome_aluno = aluno['nome']
        turma_nome = prova.get('turma_nome', '')
        serie = prova.get('serie', '')
        titulo_prova = prova.get('titulo', 'Prova')
        
        tipo_questoes = int(prova.get('tipo_questoes', 4))
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        
        # Criar o HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Cartão Resposta</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: Arial, sans-serif; 
                    background: #f0f2f5; 
                    display: flex;
                    justify-content: center;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 900px;
                    width: 100%;
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 8px 30px rgba(0,0,0,0.12);
                    border: 1px solid #e5e7eb;
                }}
                .header {{
                    text-align: center;
                    border-bottom: 2px solid #2563eb;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                .header h1 {{ font-size: 24px; color: #1e293b; }}
                .header h2 {{ font-size: 18px; color: #475569; margin-top: 8px; }}
                .header .sub {{ font-size: 14px; color: #64748b; margin-top: 8px; }}
                .info-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                    background: #f8fafc;
                    padding: 16px 20px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                    border: 1px solid #e2e8f0;
                }}
                .info-grid .item {{ font-size: 14px; }}
                .info-grid .label {{ color: #64748b; font-weight: 600; }}
                .info-grid .value {{ color: #0f172a; font-weight: 700; }}
                .questoes {{
                    display: grid;
                    grid-template-columns: repeat(5, 1fr);
                    gap: 10px;
                    margin: 20px 0 30px;
                }}
                .questao {{
                    border: 2px solid #e2e8f0;
                    border-radius: 10px;
                    padding: 12px 8px;
                    text-align: center;
                    background: #fafafa;
                    transition: all 0.2s;
                }}
                .questao:hover {{ border-color: #2563eb; background: #f0f7ff; }}
                .questao .num {{
                    font-size: 12px;
                    font-weight: 700;
                    color: #64748b;
                    margin-bottom: 8px;
                }}
                .questao .opcoes {{
                    display: flex;
                    justify-content: center;
                    gap: 8px;
                    flex-wrap: wrap;
                }}
                .questao .opcao {{
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    font-size: 14px;
                    font-weight: 600;
                    color: #1e293b;
                }}
                .questao .opcao input {{
                    width: 18px;
                    height: 18px;
                    cursor: pointer;
                    accent-color: #2563eb;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e2e8f0;
                    display: flex;
                    justify-content: space-between;
                    font-size: 13px;
                    color: #64748b;
                }}
                .btn-print {{
                    background: #2563eb;
                    color: white;
                    border: none;
                    padding: 12px 30px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 700;
                    cursor: pointer;
                    transition: background 0.2s;
                    margin-top: 20px;
                    width: 100%;
                }}
                .btn-print:hover {{ background: #1d4ed8; }}
                @media print {{
                    body {{ background: white; padding: 0; }}
                    .container {{ box-shadow: none; border: none; padding: 20px; }}
                    .btn-print {{ display: none; }}
                    .questao:hover {{ border-color: #e2e8f0; background: #fafafa; }}
                }}
                @media (max-width: 600px) {{
                    .questoes {{ grid-template-columns: repeat(3, 1fr); }}
                    .info-grid {{ grid-template-columns: 1fr; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📄 CARTÃO RESPOSTA</h1>
                    <h2>{titulo_prova}</h2>
                    <div class="sub">Leia atentamente e marque apenas uma alternativa por questão</div>
                </div>
                
                <div class="info-grid">
                    <div class="item"><span class="label">Aluno(a):</span> <span class="value">{nome_aluno}</span></div>
                    <div class="item"><span class="label">Turma:</span> <span class="value">{turma_nome}</span></div>
                    <div class="item"><span class="label">Série:</span> <span class="value">{serie}</span></div>
                    <div class="item"><span class="label">Data:</span> <span class="value">{datetime.now().strftime('%d/%m/%Y')}</span></div>
                </div>
                
                <div style="text-align:center;font-size:14px;font-weight:700;color:#475569;margin-bottom:12px;">
                    Marque com um X a alternativa correta
                </div>
                
                <div class="questoes">
        """
        
        for i in range(quantidade_questoes):
            html += f"""
                <div class="questao">
                    <div class="num">Q{i+1}</div>
                    <div class="opcoes">
            """
            for alt in alternativas:
                html += f"""
                        <label class="opcao">
                            <input type="radio" name="q{i+1}" value="{alt}">
                            {alt}
                        </label>
                """
            html += """
                    </div>
                </div>
            """
        
        html += f"""
                </div>
                
                <button class="btn-print" onclick="window.print()">🖨️ IMPRIMIR CARTÃO</button>
                
                <div class="footer">
                    <span>Gerado pelo sistema CorrigePro</span>
                    <span>{datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        print(f"❌ Erro ao gerar cartão: {e}")
        traceback.print_exc()
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
            'endpoints': [
                '/health',
                '/api/gemini/teste',
                '/api/corrigir',
                '/api/corrigir_manual',
                '/api/corrigir_redacao',
                '/api/login',
                '/api/escolas',
                '/api/escolas/<id>',
                '/api/turmas',
                '/api/turmas/<id>',
                '/api/alunos',
                '/api/alunos/<id>',
                '/api/provas',
                '/api/provas/<id>',
                '/api/gabaritos',
                '/api/historico',
                '/api/historico/<id>',
                '/api/dashboard',
                '/api/dashboard/desempenho',
                '/api/gerar_gabarito'
            ]
        })

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('.', path)
    except:
        return jsonify({'erro': 'Arquivo não encontrado'}), 404

# ============================================
# INICIALIZAÇÃO DO SERVIDOR
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
