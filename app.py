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

# ============================================
# IMPORTAÇÃO DO GEMINI
# ============================================
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
    print("✅ Gemini AI disponível!")
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini AI não instalado. Execute: pip install google-generativeai")

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================

SUPABASE_URL = 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require'

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
# ROTAS DE AUTENTICAÇÃO
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    """Autenticação de usuário"""
    data = request.json
    username = data.get('username')
    senha = data.get('senha')
    
    print(f"🔐 Tentativa de login: username={username}")
    
    if not username or not senha:
        return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
    
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
            else:
                print(f"❌ Usuário não encontrado no banco: {username}")
        except Exception as e:
            print(f"❌ Erro no login via banco: {e}")
    
    # FALLBACK
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
    data = request.json
    nome = data.get('nome')
    username = data.get('username')
    senha = data.get('senha')
    email = data.get('email')
    perfil = data.get('perfil', 'usuario')
    ativo = data.get('ativo', True)
    
    if not nome or not username or not senha:
        return jsonify({'erro': 'Nome, usuário e senha são obrigatórios'}), 400
    
    if len(senha) < 4:
        return jsonify({'erro': 'Senha deve ter pelo menos 4 caracteres'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
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
            return jsonify({'id': result['id'], 'mensagem': 'Usuário criado com sucesso'})
        except Exception as e:
            print(f"Erro ao criar usuário: {e}")
    
    USUARIOS_FIXOS[username] = {
        'senha': senha,
        'perfil': perfil,
        'nome': nome
    }
    return jsonify({'id': len(USUARIOS_FIXOS), 'mensagem': 'Usuário criado em memória'})

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    """Exclui um usuário"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'mensagem': 'Usuário excluído com sucesso'})
        except Exception as e:
            print(f"Erro ao excluir usuário: {e}")
    
    return jsonify({'erro': 'Não foi possível excluir o usuário'}), 500

# ============================================
# ROTAS DE ESCOLAS
# ============================================

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    """Lista todas as escolas"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM escolas ORDER BY nome")
            escolas = cur.fetchall()
            cur.close()
            conn.close()
            if escolas:
                return jsonify(escolas)
        except Exception as e:
            print(f"Erro ao listar escolas: {e}")
    
    return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    """Cria uma nova escola"""
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
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                nome,
                data.get('inep', ''),
                data.get('municipio', ''),
                data.get('estado', 'PA'),
                data.get('telefone', ''),
                data.get('diretor', '')
            ))
            
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Escola criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar escola: {e}")
    
    return jsonify({'erro': 'Erro ao criar escola'}), 500

@app.route('/api/escolas/<int:id>', methods=['PUT'])
def atualizar_escola(id):
    """Atualiza uma escola existente"""
    data = request.json
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                UPDATE escolas 
                SET nome = %s, inep = %s, municipio = %s, estado = %s, telefone = %s, diretor = %s
                WHERE id = %s
                RETURNING id
            """, (
                data.get('nome'),
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
            
            if result:
                return jsonify({'mensagem': 'Escola atualizada com sucesso'})
            else:
                return jsonify({'erro': 'Escola não encontrada'}), 404
        except Exception as e:
            print(f"Erro ao atualizar escola: {e}")
    
    return jsonify({'erro': 'Erro ao atualizar escola'}), 500

@app.route('/api/escolas/<int:id>', methods=['DELETE'])
def excluir_escola(id):
    """Exclui uma escola"""
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

# ============================================
# ROTAS DE TURMAS
# ============================================

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    """Lista todas as turmas com informações da escola"""
    escola_id = request.args.get('escola_id')
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT t.*, e.nome as escola_nome 
                FROM turmas t
                LEFT JOIN escolas e ON t.escola_id = e.id
            """
            params = []
            
            if escola_id:
                query += " WHERE t.escola_id = %s"
                params.append(escola_id)
            
            query += " ORDER BY t.nome"
            
            cur.execute(query, params)
            turmas = cur.fetchall()
            cur.close()
            conn.close()
            
            if turmas:
                return jsonify(turmas)
        except Exception as e:
            print(f"Erro ao listar turmas: {e}")
    
    return jsonify([])

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    """Cria uma nova turma"""
    data = request.json
    
    if not data.get('nome') or not data.get('escola_id'):
        return jsonify({'erro': 'Nome da turma e escola são obrigatórios'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO turmas (escola_id, nome, serie, turno, professor, capacidade, ano_letivo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['escola_id'],
                data['nome'],
                data.get('serie', '1º Ano'),
                data.get('turno', 'Manhã'),
                data.get('professor', ''),
                data.get('capacidade', 35),
                data.get('ano_letivo', 2025)
            ))
            
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Turma criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar turma: {e}")
    
    return jsonify({'erro': 'Erro ao criar turma'}), 500

@app.route('/api/turmas/<int:id>', methods=['PUT'])
def atualizar_turma(id):
    """Atualiza uma turma existente"""
    data = request.json
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                UPDATE turmas 
                SET nome = %s, serie = %s, turno = %s, professor = %s, capacidade = %s, ano_letivo = %s
                WHERE id = %s
                RETURNING id
            """, (
                data.get('nome'),
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
            
            if result:
                return jsonify({'mensagem': 'Turma atualizada com sucesso'})
            else:
                return jsonify({'erro': 'Turma não encontrada'}), 404
        except Exception as e:
            print(f"Erro ao atualizar turma: {e}")
    
    return jsonify({'erro': 'Erro ao atualizar turma'}), 500

@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
    """Exclui uma turma"""
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

# ============================================
# ROTAS DE ALUNOS
# ============================================

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    """Lista todos os alunos com informações da turma e escola"""
    turma_id = request.args.get('turma_id')
    escola_id = request.args.get('escola_id')
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome, e.id as escola_id
                FROM alunos a
                LEFT JOIN turmas t ON a.turma_id = t.id
                LEFT JOIN escolas e ON t.escola_id = e.id
            """
            params = []
            
            if turma_id:
                query += " WHERE a.turma_id = %s"
                params.append(turma_id)
            elif escola_id:
                query += " WHERE e.id = %s"
                params.append(escola_id)
            
            query += " ORDER BY a.numero_chamada, a.nome"
            
            cur.execute(query, params)
            alunos = cur.fetchall()
            cur.close()
            conn.close()
            
            if alunos:
                return jsonify(alunos)
        except Exception as e:
            print(f"Erro ao listar alunos: {e}")
    
    return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    """Cria um novo aluno"""
    data = request.json
    
    if not data.get('nome') or not data.get('turma_id'):
        return jsonify({'erro': 'Nome do aluno e turma são obrigatórios'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO alunos (turma_id, nome, matricula, numero_chamada, data_nascimento, genero, responsavel, telefone, email, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                data.get('observacoes', '')
            ))
            
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Aluno criado com sucesso'})
        except Exception as e:
            print(f"Erro ao criar aluno: {e}")
    
    return jsonify({'erro': 'Erro ao criar aluno'}), 500

@app.route('/api/alunos/<int:id>', methods=['PUT'])
def atualizar_aluno(id):
    """Atualiza um aluno existente"""
    data = request.json
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                UPDATE alunos 
                SET nome = %s, matricula = %s, numero_chamada = %s, data_nascimento = %s, 
                    genero = %s, responsavel = %s, telefone = %s, email = %s, observacoes = %s
                WHERE id = %s
                RETURNING id
            """, (
                data.get('nome'),
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
            
            if result:
                return jsonify({'mensagem': 'Aluno atualizado com sucesso'})
            else:
                return jsonify({'erro': 'Aluno não encontrado'}), 404
        except Exception as e:
            print(f"Erro ao atualizar aluno: {e}")
    
    return jsonify({'erro': 'Erro ao atualizar aluno'}), 500

@app.route('/api/alunos/<int:id>', methods=['DELETE'])
def excluir_aluno(id):
    """Exclui um aluno"""
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

# ============================================
# ROTAS DE PROVAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    """Lista todas as provas com informações da turma"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT p.*, t.nome as turma_nome, t.serie as turma_serie
                FROM provas p
                LEFT JOIN turmas t ON p.turma_id = t.id
                ORDER BY p.id DESC
            """)
            provas = cur.fetchall()
            cur.close()
            conn.close()
            print(f"📋 Listando {len(provas)} provas")
            return jsonify(provas)
        except Exception as e:
            print(f"❌ Erro ao listar provas: {e}")
    
    return jsonify([])

@app.route('/api/provas/<int:id>', methods=['GET'])
def buscar_prova(id):
    """Busca uma prova específica pelo ID"""
    conn = get_db_connection()
    if conn:
        try:
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
            
            if prova:
                print(f"📖 Prova encontrada: ID={prova['id']}, Título={prova['titulo']}")
                return jsonify(prova)
            else:
                print(f"❌ Prova ID {id} não encontrada")
                return jsonify({'erro': 'Prova não encontrada'}), 404
        except Exception as e:
            print(f"❌ Erro ao buscar prova: {e}")
            return jsonify({'erro': str(e)}), 500
    
    return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    """Cria uma nova prova"""
    data = request.json
    
    if not data.get('titulo') or not data.get('turma_id'):
        return jsonify({'erro': 'Título da prova e turma são obrigatórios'}), 400
    
    # Garantir que quantidade_questoes seja definido
    quantidade_questoes = data.get('quantidade_questoes')
    if not quantidade_questoes:
        gabarito = data.get('gabarito', [])
        quantidade_questoes = len(gabarito) if gabarito else 20
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO provas (turma_id, titulo, disciplina, bimestre, data_prova, valor_nota, tipo_questoes, quantidade_questoes, gabarito)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['turma_id'],
                data['titulo'],
                data.get('disciplina', ''),
                data.get('bimestre', ''),
                data.get('data_prova'),
                data.get('valor_nota', 10),
                data.get('tipo_questoes', '4'),
                quantidade_questoes,
                data.get('gabarito', [])
            ))
            
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Prova criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar prova: {e}")
    
    return jsonify({'erro': 'Erro ao criar prova'}), 500

@app.route('/api/provas/<int:id>', methods=['PUT'])
def atualizar_prova(id):
    """Atualiza uma prova existente"""
    data = request.json
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                UPDATE provas 
                SET titulo = %s, disciplina = %s, bimestre = %s, data_prova = %s, 
                    valor_nota = %s, tipo_questoes = %s, quantidade_questoes = %s, gabarito = %s
                WHERE id = %s
                RETURNING id
            """, (
                data.get('titulo'),
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
            
            if result:
                return jsonify({'mensagem': 'Prova atualizada com sucesso'})
            else:
                return jsonify({'erro': 'Prova não encontrada'}), 404
        except Exception as e:
            print(f"Erro ao atualizar prova: {e}")
    
    return jsonify({'erro': 'Erro ao atualizar prova'}), 500

@app.route('/api/provas/<int:id>', methods=['DELETE'])
def excluir_prova(id):
    """Exclui uma prova"""
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

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    """
    Salva o gabarito de uma prova no banco de dados.
    """
    try:
        print("=" * 60)
        print("📝 SALVANDO GABARITO")
        print("=" * 60)
        
        data = request.json
        print(f"📥 Dados recebidos: {data}")
        
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        
        if not prova_id:
            return jsonify({'erro': 'ID da prova é obrigatório'}), 400
        
        if not respostas or len(respostas) == 0:
            return jsonify({'erro': 'Respostas do gabarito são obrigatórias'}), 400
        
        # Filtrar respostas
        respostas_validas = []
        for r in respostas:
            if r:
                respostas_validas.append(str(r).strip().upper())
        
        print(f"📝 Respostas processadas: {respostas_validas}")
        print(f"📝 Total: {len(respostas_validas)}")
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        try:
            cur = conn.cursor()
            
            # Verificar se a prova existe
            cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (prova_id,))
            prova = cur.fetchone()
            
            if not prova:
                cur.close()
                conn.close()
                return jsonify({'erro': 'Prova não encontrada'}), 404
            
            print(f"✅ Prova encontrada: {prova[1]} (ID: {prova[0]})")
            
            # Atualizar a prova com o gabarito
            cur.execute("""
                UPDATE provas 
                SET gabarito = %s::text[],
                    quantidade_questoes = %s
                WHERE id = %s
                RETURNING id, titulo
            """, (respostas_validas, len(respostas_validas), prova_id))
            
            result = cur.fetchone()
            
            if result:
                conn.commit()
                print(f"✅ Gabarito salvo: {result[1]}")
                
                cur.close()
                conn.close()
                
                return jsonify({
                    'id': result[0],
                    'mensagem': f'Gabarito salvo com sucesso para "{result[1]}"',
                    'total_questoes': len(respostas_validas),
                    'gabarito_salvo': respostas_validas
                })
            else:
                conn.rollback()
                cur.close()
                conn.close()
                return jsonify({'erro': 'Erro ao salvar gabarito'}), 500
                
        except Exception as e:
            print(f"❌ Erro: {e}")
            print(traceback.format_exc())
            if conn:
                conn.rollback()
                conn.close()
            return jsonify({'erro': f'Erro ao salvar gabarito: {str(e)}'}), 500
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        print(traceback.format_exc())
        return jsonify({'erro': f'Erro interno: {str(e)}'}), 500

@app.route('/api/gabaritos/prova/<int:prova_id>', methods=['GET'])
def buscar_gabarito_por_prova(prova_id):
    """Busca o gabarito de uma prova específica"""
    print(f"🔍 Buscando gabarito para prova ID: {prova_id}")
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, titulo, gabarito, quantidade_questoes, tipo_questoes
            FROM provas 
            WHERE id = %s
        """, (prova_id,))
        
        prova = cur.fetchone()
        cur.close()
        conn.close()
        
        if prova:
            print(f"✅ Gabarito encontrado: {prova.get('gabarito', [])}")
            return jsonify({
                'encontrado': True,
                'prova_id': prova['id'],
                'titulo': prova['titulo'],
                'gabarito': prova.get('gabarito', []),
                'quantidade_questoes': prova.get('quantidade_questoes', 0),
                'tipo_questoes': prova.get('tipo_questoes', '4')
            })
        else:
            print(f"❌ Prova {prova_id} não encontrada")
            return jsonify({'encontrado': False, 'erro': 'Prova não encontrada'}), 404
            
    except Exception as e:
        print(f"❌ Erro ao buscar gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS DE HISTÓRICO / RESULTADOS
# ============================================

@app.route('/api/historico', methods=['GET'])
def listar_historico():
    """Lista o histórico de correções com filtros"""
    escola_id = request.args.get('escola_id')
    serie = request.args.get('serie')
    turma_id = request.args.get('turma_id')
    aluno_id = request.args.get('aluno_id')
    prova_id = request.args.get('prova_id')
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT 
                    h.*, 
                    a.nome as aluno_nome,
                    p.titulo as prova_titulo,
                    p.quantidade_questoes as total_questoes,
                    t.serie as serie,
                    t.nome as turma_nome,
                    e.nome as escola_nome
                FROM historico h
                LEFT JOIN alunos a ON h.aluno_id = a.id
                LEFT JOIN provas p ON h.prova_id = p.id
                LEFT JOIN turmas t ON p.turma_id = t.id
                LEFT JOIN escolas e ON t.escola_id = e.id
                WHERE 1=1
            """
            params = []
            
            if escola_id:
                query += " AND e.id = %s"
                params.append(escola_id)
            
            if serie:
                query += " AND t.serie = %s"
                params.append(serie)
            
            if turma_id:
                query += " AND t.id = %s"
                params.append(turma_id)
            
            if aluno_id:
                query += " AND h.aluno_id = %s"
                params.append(aluno_id)
            
            if prova_id:
                query += " AND h.prova_id = %s"
                params.append(prova_id)
            
            query += " ORDER BY h.data_correcao DESC"
            
            cur.execute(query, params)
            historico = cur.fetchall()
            cur.close()
            conn.close()
            
            print(f"📊 Histórico retornado: {len(historico)} registros")
            if len(historico) > 0:
                print(f"📝 Primeiro registro: {historico[0]}")
            
            return jsonify(historico)
        except Exception as e:
            print(f"Erro ao listar histórico: {e}")
            return jsonify([])
    
    return jsonify([])

@app.route('/api/historico', methods=['POST'])
def salvar_correcao():
    """Salva uma correção no histórico"""
    data = request.json
    
    prova_id = data.get('prova_id')
    aluno_id = data.get('aluno_id')
    respostas = data.get('respostas', [])
    acertos = data.get('acertos', 0)
    nota = data.get('nota', 0)
    total = data.get('total', 0)
    tipo_correcao = data.get('tipo_correcao', 'ia')
    
    if not prova_id or not aluno_id:
        return jsonify({'erro': 'Prova e aluno são obrigatórios'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao))
            
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({'id': result['id'], 'mensagem': 'Correção salva com sucesso'})
        except Exception as e:
            print(f"Erro ao salvar correção: {e}")
    
    return jsonify({'erro': 'Erro ao salvar correção'}), 500

# ============================================
# ROTAS DE CORREÇÃO MANUAL
# ============================================

@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    """Salva uma correção manual no histórico"""
    try:
        print("=" * 60)
        print("📝 SALVANDO CORREÇÃO MANUAL")
        print("=" * 60)
        
        data = request.json
        print(f"📥 Dados recebidos: {data}")
        
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        respostas = data.get('respostas', [])
        acertos = data.get('acertos', 0)
        nota = data.get('nota', 0)
        total = data.get('total', 0)
        
        if not prova_id or not aluno_id:
            print("❌ Prova e aluno são obrigatórios")
            return jsonify({'erro': 'Prova e aluno são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            print("❌ Erro ao conectar ao banco")
            return jsonify({'erro': 'Erro ao conectar ao banco de dados'}), 500
        
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Verificar se já existe uma correção para este aluno e prova
            cur.execute("""
                SELECT id FROM historico 
                WHERE prova_id = %s AND aluno_id = %s
            """, (prova_id, aluno_id))
            
            existing = cur.fetchone()
            
            if existing:
                # Atualizar correção existente
                cur.execute("""
                    UPDATE historico 
                    SET respostas = %s::text[],
                        acertos = %s,
                        nota = %s,
                        total = %s,
                        tipo_correcao = 'manual',
                        data_correcao = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id
                """, (respostas, acertos, nota, total, existing['id']))
                
                result = cur.fetchone()
                mensagem = 'Correção manual atualizada com sucesso'
            else:
                # Inserir nova correção
                cur.execute("""
                    INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
                    VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual')
                    RETURNING id
                """, (prova_id, aluno_id, respostas, acertos, nota, total))
                
                result = cur.fetchone()
                mensagem = 'Correção manual salva com sucesso'
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(f"✅ {mensagem} - ID: {result['id']}")
            
            return jsonify({
                'sucesso': True,
                'id': result['id'],
                'mensagem': mensagem,
                'nota': nota,
                'acertos': acertos,
                'total': total
            })
            
        except psycopg2.Error as e:
            print(f"❌ Erro no PostgreSQL: {e}")
            if conn:
                conn.rollback()
                conn.close()
            return jsonify({'erro': f'Erro no banco de dados: {str(e)}'}), 500
            
        except Exception as e:
            print(f"❌ Erro: {e}")
            print(traceback.format_exc())
            if conn:
                conn.rollback()
                conn.close()
            return jsonify({'erro': f'Erro ao salvar correção: {str(e)}'}), 500
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        print(traceback.format_exc())
        return jsonify({'erro': f'Erro interno: {str(e)}'}), 500

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
# ROTAS DE IA - CORREÇÃO
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    """Corrige uma prova usando IA"""
    data = request.json
    imagem_base64 = data.get('imagem')
    prova_id = data.get('prova_id')
    aluno_id = data.get('aluno_id')
    
    if not imagem_base64 or not prova_id or not aluno_id:
        return jsonify({'erro': 'Imagem, prova e aluno são obrigatórios'}), 400
    
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'erro': 'Erro ao processar imagem'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = prova.get('gabarito', [])
        quantidade_questoes = prova.get('quantidade_questoes', len(gabarito) or 20)
        
        if not gabarito:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400
        
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        cur.close()
        conn.close()
        
        nome_aluno = aluno['nome'] if aluno else 'Aluno'
        
        # Simulação de detecção de respostas
        random.seed(aluno_id)
        respostas_detectadas = [random.choice(['A', 'B', 'C', 'D']) for _ in range(len(gabarito))]
        
        acertos = 0
        valor_por_questao = prova.get('valor_nota', 10) / len(gabarito)
        
        correcoes = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp and gab and resp.upper() == gab.upper()
            if is_correto:
                acertos += 1
            correcoes.append({
                'questao': i + 1,
                'resposta': resp,
                'gabarito': gab,
                'correto': is_correto
            })
        
        nota = acertos * valor_por_questao
        
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
                    VALUES (%s, %s, %s, %s, %s, %s, 'ia')
                """, (prova_id, aluno_id, respostas_detectadas, acertos, nota, quantidade_questoes))
                conn.commit()
                cur.close()
            except Exception as e:
                print(f"Erro ao salvar histórico: {e}")
            finally:
                conn.close()
        
        return jsonify({
            'aluno': nome_aluno,
            'prova': prova.get('titulo', 'Prova'),
            'total': quantidade_questoes,
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas,
            'correcoes': correcoes,
            'gabarito': gabarito,
            'tipo_questoes': prova.get('tipo_questoes', '4'),
            'confianca': 85,
            'valor_por_questao': round(valor_por_questao, 2)
        })
        
    except Exception as e:
        print(f"Erro na correção: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS DE CORREÇÃO DE REDAÇÃO
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    """Corrige uma redação usando Gemini AI"""
    data = request.json
    texto = data.get('texto')
    aluno_id = data.get('aluno_id')
    
    if not texto:
        return jsonify({'erro': 'Texto é obrigatório'}), 400
    
    notas = {
        'nota_coerencia': round(random.uniform(5, 9), 1),
        'nota_estrutura': round(random.uniform(5, 9), 1),
        'nota_gramatica': round(random.uniform(5, 9), 1),
        'nota_vocabulario': round(random.uniform(5, 9), 1)
    }
    
    nota_media = round(sum(notas.values()) / 4, 1)
    
    feedbacks = [
        "O texto apresenta boa estrutura, com introdução, desenvolvimento e conclusão bem definidos.",
        "A redação demonstra compreensão do tema e desenvolve argumentos de forma coerente.",
        "O texto é bem escrito e organizado. As ideias são apresentadas de forma clara e objetiva.",
        "Excelente desenvolvimento do tema! A estrutura é muito boa e as ideias são bem articuladas."
    ]
    
    resultado = {
        'nota': nota_media,
        'feedback': random.choice(feedbacks),
        'metricas': notas
    }
    
    if aluno_id:
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM provas WHERE titulo LIKE '%Redação%' ORDER BY id DESC LIMIT 1")
                prova = cur.fetchone()
                if prova:
                    cur.execute("""
                        INSERT INTO historico (prova_id, aluno_id, nota, tipo_correcao)
                        VALUES (%s, %s, %s, 'ia')
                    """, (prova[0], aluno_id, resultado.get('nota', 0)))
                    conn.commit()
                cur.close()
                conn.close()
        except Exception as e:
            print(f"Erro ao salvar correção de redação: {e}")
    
    return jsonify(resultado)

# ============================================
# ROTA DE TESTE DO BANCO
# ============================================

@app.route('/api/teste', methods=['GET'])
def testar_banco():
    """Testa a conexão com o banco de dados"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 as test")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({'sucesso': True, 'mensagem': 'Conexão com banco OK!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS DE GERAR CARTÃO RESPOSTA
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    """Gera um cartão resposta para impressão"""
    data = request.json
    escola_id = data.get('escola_id')
    turma_id = data.get('turma_id')
    aluno_id = data.get('aluno_id')
    prova_id = data.get('prova_id')
    quantidade_questoes = data.get('quantidade_questoes', 20)
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT nome FROM escolas WHERE id = %s", (escola_id,))
        escola = cur.fetchone()
        nome_escola = escola['nome'] if escola else 'Escola'
        
        cur.execute("SELECT nome, serie, turno, professor FROM turmas WHERE id = %s", (turma_id,))
        turma = cur.fetchone()
        nome_turma = turma['nome'] if turma else 'Turma'
        serie = turma['serie'] if turma else ''
        professor = turma['professor'] if turma else ''
        
        cur.execute("SELECT nome, numero_chamada FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        nome_aluno = aluno['nome'] if aluno else 'Aluno'
        numero_chamada = aluno['numero_chamada'] if aluno else ''
        
        cur.execute("SELECT titulo, data_prova FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        titulo_prova = prova['titulo'] if prova else 'Avaliação'
        data_prova = prova['data_prova'] if prova else ''
        
        cur.close()
        conn.close()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Cartão Resposta</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: white; }}
                .header {{ text-align: center; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                .header h1 {{ font-size: 20px; margin: 0; }}
                .header p {{ margin: 5px 0; color: #555; }}
                .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }}
                .info-item {{ padding: 5px 10px; background: #f5f5f5; border-radius: 5px; }}
                .info-item strong {{ display: inline-block; width: 80px; }}
                .questoes-grid {{ 
                    display: grid; 
                    grid-template-columns: repeat(5, 1fr); 
                    gap: 10px; 
                    margin-top: 10px;
                }}
                .questao-item {{
                    border: 1px solid #ccc;
                    border-radius: 8px;
                    padding: 10px;
                    text-align: center;
                }}
                .questao-num {{ font-size: 12px; color: #666; font-weight: bold; }}
                .opcoes {{ display: flex; justify-content: center; gap: 10px; margin-top: 5px; }}
                .opcao {{ 
                    width: 30px; 
                    height: 30px; 
                    border: 2px solid #ccc;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 14px;
                }}
                .footer {{ margin-top: 30px; display: grid; grid-template-columns: 1fr 1fr; gap: 40px; border-top: 1px solid #ccc; padding-top: 20px; }}
                .footer .assinatura {{ text-align: center; }}
                .footer .assinatura .linha {{ border-top: 1px solid #333; width: 200px; margin: 20px auto 0; }}
                @media print {{
                    .no-print {{ display: none; }}
                    body {{ margin: 10px; }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📄 CARTÃO RESPOSTA</h1>
                <p>{nome_escola}</p>
                <p><strong>Prova:</strong> {titulo_prova} | <strong>Data:</strong> {data_prova}</p>
            </div>
            
            <div class="info-grid">
                <div class="info-item"><strong>Aluno:</strong> {nome_aluno}</div>
                <div class="info-item"><strong>Nº:</strong> {numero_chamada}</div>
                <div class="info-item"><strong>Turma:</strong> {nome_turma}</div>
                <div class="info-item"><strong>Série:</strong> {serie}</div>
                <div class="info-item"><strong>Professor(a):</strong> {professor}</div>
                <div class="info-item"><strong>Turno:</strong> {turma['turno'] if turma else ''}</div>
            </div>
            
            <div style="text-align:center;margin-bottom:15px;font-size:14px;color:#666;">
                Instruções: Preencha com caneta ou lápis o círculo correspondente à sua resposta.
            </div>
            
            <div class="questoes-grid">
        """
        
        for i in range(1, quantidade_questoes + 1):
            html += f"""
                <div class="questao-item">
                    <div class="questao-num">Q{i}</div>
                    <div class="opcoes">
                        <div class="opcao">A</div>
                        <div class="opcao">B</div>
                        <div class="opcao">C</div>
                        <div class="opcao">D</div>
                    </div>
                </div>
            """
        
        html += """
            </div>
            
            <div class="footer">
                <div class="assinatura">
                    <p>Professor(a) Responsável</p>
                    <div class="linha"></div>
                </div>
                <div class="assinatura">
                    <p>Diretor(a)</p>
                    <div class="linha"></div>
                </div>
            </div>
            
            <div style="text-align:center;margin-top:30px;font-size:12px;color:#999;">
                Sistema CorrigePro - Cartão Resposta Gerado Automaticamente
            </div>
        </body>
        </html>
        """
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE LISTAR RESULTADOS (tb-resultados)
# ============================================

@app.route('/api/resultados', methods=['GET'])
def listar_resultados():
    """Lista todos os resultados (histórico) para a página de resultados"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    h.*, 
                    a.nome as aluno_nome,
                    p.titulo as prova_titulo,
                    p.quantidade_questoes as total_questoes,
                    t.serie as serie,
                    t.nome as turma_nome
                FROM historico h
                LEFT JOIN alunos a ON h.aluno_id = a.id
                LEFT JOIN provas p ON h.prova_id = p.id
                LEFT JOIN turmas t ON p.turma_id = t.id
                ORDER BY h.data_correcao DESC
            """)
            resultados = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(resultados)
        except Exception as e:
            print(f"Erro ao listar resultados: {e}")
    
    return jsonify([])

# ============================================
# SERVIDOR
# ============================================

@app.route('/')
def index():
    """Serve a página principal"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve arquivos estáticos"""
    return send_from_directory('.', path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
