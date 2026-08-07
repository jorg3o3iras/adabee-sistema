from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import json
import os
from datetime import datetime
import traceback
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import urllib.parse as urlparse
import logging
import random
import re

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS - POOL DE CONEXÕES
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL')
db_pool = None

if SUPABASE_URL:
    try:
        result = urlparse.urlparse(SUPABASE_URL)
        dbname = result.path[1:]
        user = result.username
        password = result.password
        host = result.hostname
        port = result.port

        db_pool = psycopg2.pool.SimpleConnectionPool(
            2, 20,
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        print("✅ Pool de conexões criado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao criar pool: {e}")
        db_pool = None

def get_db_connection():
    if not db_pool:
        return None
    try:
        return db_pool.getconn()
    except Exception as e:
        print(f"❌ Erro ao obter conexão: {e}")
        return None

def release_db_connection(conn):
    if conn and db_pool:
        try:
            db_pool.putconn(conn)
        except Exception as e:
            print(f"❌ Erro ao devolver conexão: {e}")

# ============================================
# USUÁRIOS FIXOS
# ============================================

USUARIOS_FIXOS = {
    'admin': {'senha': 'admin', 'perfil': 'admin', 'nome': 'Administrador'},
    'usuario': {'senha': '123', 'perfil': 'usuario', 'nome': 'Usuário'},
    'professor1': {'senha': '123', 'perfil': 'usuario', 'nome': 'Professor 1'}
}

# ============================================
# FUNÇÃO PARA CALCULAR CONCEITO
# ============================================

def calcular_conceito(porcentagem):
    if porcentagem <= 40:
        return {'nome': 'inicial', 'rotulo': '🔴 inicial', 'faixa': 'até 40%', 'cor': '#ef4444', 'badge': 'badge-conceito-inicial'}
    elif porcentagem <= 60:
        return {'nome': 'basico', 'rotulo': '🟠 básico', 'faixa': '41% - 60%', 'cor': '#f59e0b', 'badge': 'badge-conceito-basico'}
    elif porcentagem <= 80:
        return {'nome': 'proficiente', 'rotulo': '🔵 proficiente', 'faixa': '61% - 80%', 'cor': '#3b82f6', 'badge': 'badge-conceito-proficiente'}
    else:
        return {'nome': 'avancado', 'rotulo': '🟢 avançado', 'faixa': 'acima de 80%', 'cor': '#10b981', 'badge': 'badge-conceito-avancado'}

# ============================================
# ROTA DE LOGIN
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        senha = data.get('senha')

        if not username or not senha:
            return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("SELECT id, nome, username, senha_hash, perfil, ativo FROM usuarios WHERE username = %s", (username,))
                usuario = cur.fetchone()
                cur.close()
                release_db_connection(conn)

                if usuario and usuario['ativo'] and str(usuario['senha_hash']) == str(senha):
                    return jsonify({
                        'sucesso': True,
                        'perfil': usuario['perfil'],
                        'usuario': usuario['username'],
                        'nome': usuario['nome']
                    })
            except Exception as e:
                print(f"❌ Erro no banco: {e}")
                release_db_connection(conn)

        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if str(dados['senha']) == str(senha):
                return jsonify({
                    'sucesso': True,
                    'perfil': dados['perfil'],
                    'usuario': username,
                    'nome': dados['nome']
                })

        return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401
    except Exception as e:
        print(f"❌ Erro no login: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE ESCOLAS
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
            release_db_connection(conn)
            return jsonify(escolas if escolas else [])
        except Exception as e:
            print(f"❌ Erro ao listar escolas: {e}")
            release_db_connection(conn)
    return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    try:
        data = request.json
        nome = data.get('nome')
        if not nome:
            return jsonify({'erro': 'Nome é obrigatório'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO escolas (nome, inep, municipio, estado, telefone, diretor)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (nome, data.get('inep', ''), data.get('municipio', ''),
              data.get('estado', 'PA'), data.get('telefone', ''), data.get('diretor', '')))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)
        return jsonify({'id': result['id'], 'mensagem': 'Escola criada com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao criar escola: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:id>', methods=['GET'])
def buscar_escola(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        cur.close()
        release_db_connection(conn)

        if not escola:
            return jsonify({'erro': 'Escola não encontrada'}), 404

        return jsonify(escola)
    except Exception as e:
        print(f"❌ Erro ao buscar escola: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:id>', methods=['PUT'])
def editar_escola(id):
    try:
        data = request.json
        nome = data.get('nome')

        if not nome:
            return jsonify({'erro': 'Nome é obrigatório'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM escolas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Escola não encontrada'}), 404

        cur.execute("""
            UPDATE escolas SET nome = %s, inep = %s, municipio = %s, estado = %s, telefone = %s, diretor = %s
            WHERE id = %s RETURNING id
        """, (nome, data.get('inep', ''), data.get('municipio', ''),
              data.get('estado', 'PA'), data.get('telefone', ''), data.get('diretor', ''), id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Escola atualizada com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao editar escola: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:id>', methods=['DELETE'])
def excluir_escola(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        if not escola:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Escola não encontrada'}), 404

        escola_nome = escola[1]
        cur.execute("DELETE FROM escolas WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'mensagem': f'Escola "{escola_nome}" excluída com sucesso!'})
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao excluir escola: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE TURMAS
# ============================================

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    try:
        escola_id = request.args.get('escola_id')
        conn = get_db_connection()
        if not conn:
            return jsonify([])

        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT t.*, e.nome as escola_nome, COUNT(a.id) as total_alunos
            FROM turmas t
            LEFT JOIN escolas e ON t.escola_id = e.id
            LEFT JOIN alunos a ON a.turma_id = t.id
        """
        params = []

        if escola_id and escola_id != '':
            try:
                query += " WHERE t.escola_id = %s"
                params.append(int(escola_id))
            except ValueError:
                pass

        query += " GROUP BY t.id, e.nome ORDER BY t.nome"

        cur.execute(query, params)
        turmas = cur.fetchall()
        cur.close()
        release_db_connection(conn)

        return jsonify(turmas if turmas else [])
    except Exception as e:
        print(f"❌ Erro ao listar turmas: {e}")
        return jsonify([])

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    try:
        data = request.json
        if not data.get('nome') or not data.get('escola_id'):
            return jsonify({'erro': 'Nome e escola são obrigatórios'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

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
        release_db_connection(conn)
        return jsonify({'id': result['id'], 'mensagem': 'Turma criada com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao criar turma: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>', methods=['GET'])
def buscar_turma(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM turmas WHERE id = %s", (id,))
        turma = cur.fetchone()
        cur.close()
        release_db_connection(conn)

        if not turma:
            return jsonify({'erro': 'Turma não encontrada'}), 404

        return jsonify(turma)
    except Exception as e:
        print(f"❌ Erro ao buscar turma: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>', methods=['PUT'])
def editar_turma(id):
    try:
        data = request.json

        if not data.get('nome') or not data.get('escola_id'):
            return jsonify({'erro': 'Nome e escola são obrigatórios'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM turmas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Turma não encontrada'}), 404

        cur.execute("""
            UPDATE turmas SET escola_id = %s, nome = %s, serie = %s, turno = %s, professor = %s, capacidade = %s, ano_letivo = %s
            WHERE id = %s RETURNING id
        """, (data['escola_id'], data['nome'], data.get('serie', '1º Ano'),
              data.get('turno', 'Manhã'), data.get('professor', ''),
              data.get('capacidade', 35), data.get('ano_letivo', 2025), id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Turma atualizada com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao editar turma: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM turmas WHERE id = %s", (id,))
        turma = cur.fetchone()
        if not turma:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Turma não encontrada'}), 404

        turma_nome = turma[1]
        cur.execute("DELETE FROM turmas WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'mensagem': f'Turma "{turma_nome}" excluída com sucesso!'})
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao excluir turma: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE ALUNOS
# ============================================

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    try:
        escola_id = request.args.get('escola_id')
        turma_id = request.args.get('turma_id')
        serie = request.args.get('serie')

        conn = get_db_connection()
        if not conn:
            return jsonify([])

        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            WHERE 1=1
        """
        params = []

        if escola_id and escola_id != '':
            try:
                query += " AND a.escola_id = %s"
                params.append(int(escola_id))
            except ValueError:
                pass

        if turma_id and turma_id != '':
            try:
                query += " AND a.turma_id = %s"
                params.append(int(turma_id))
            except ValueError:
                pass

        if serie and serie != '':
            query += " AND t.serie = %s"
            params.append(serie)

        query += " ORDER BY a.numero_chamada NULLS LAST, a.nome"

        cur.execute(query, params)
        alunos = cur.fetchall()
        cur.close()
        release_db_connection(conn)

        return jsonify(alunos if alunos else [])
    except Exception as e:
        print(f"❌ Erro ao listar alunos: {e}")
        return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    try:
        data = request.json

        if not data.get('nome'):
            return jsonify({'erro': 'Nome é obrigatório'}), 400

        if not data.get('escola_id'):
            return jsonify({'erro': 'Escola é obrigatória'}), 400

        if not data.get('turma_id'):
            return jsonify({'erro': 'Turma é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM escolas WHERE id = %s", (data['escola_id'],))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Escola não encontrada'}), 404

        cur.execute("SELECT id FROM turmas WHERE id = %s", (data['turma_id'],))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Turma não encontrada'}), 404

        cur.execute("""
            INSERT INTO alunos (escola_id, turma_id, nome, matricula, numero_chamada, data_nascimento,
             genero, responsavel, telefone, email, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (data['escola_id'], data['turma_id'], data['nome'], data.get('matricula', ''),
              data.get('numero_chamada'), data.get('data_nascimento'), data.get('genero', 'Masculino'),
              data.get('responsavel', ''), data.get('telefone', ''), data.get('email', ''),
              data.get('observacoes', '')))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'id': result['id'], 'mensagem': 'Aluno criado com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao criar aluno: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['GET'])
def buscar_aluno(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT a.*, t.nome as turma_nome, e.nome as escola_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id LEFT JOIN escolas e ON a.escola_id = e.id WHERE a.id = %s", (id,))
        aluno = cur.fetchone()
        cur.close()
        release_db_connection(conn)

        if not aluno:
            return jsonify({'erro': 'Aluno não encontrado'}), 404

        return jsonify(aluno)
    except Exception as e:
        print(f"❌ Erro ao buscar aluno: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['PUT'])
def editar_aluno(id):
    try:
        data = request.json

        if not data.get('nome'):
            return jsonify({'erro': 'Nome é obrigatório'}), 400

        if not data.get('escola_id'):
            return jsonify({'erro': 'Escola é obrigatória'}), 400

        if not data.get('turma_id'):
            return jsonify({'erro': 'Turma é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM alunos WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Aluno não encontrado'}), 404

        cur.execute("""
            UPDATE alunos SET escola_id = %s, turma_id = %s, nome = %s, matricula = %s,
             numero_chamada = %s, data_nascimento = %s, genero = %s, responsavel = %s,
             telefone = %s, email = %s, observacoes = %s
            WHERE id = %s RETURNING id
        """, (data['escola_id'], data['turma_id'], data['nome'], data.get('matricula', ''),
              data.get('numero_chamada'), data.get('data_nascimento'), data.get('genero', 'Masculino'),
              data.get('responsavel', ''), data.get('telefone', ''), data.get('email', ''),
              data.get('observacoes', ''), id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Aluno atualizado com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao editar aluno: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['DELETE'])
def excluir_aluno(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nome FROM alunos WHERE id = %s", (id,))
        aluno = cur.fetchone()
        if not aluno:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Aluno não encontrado'}), 404

        aluno_nome = aluno[1]
        cur.execute("DELETE FROM alunos WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'mensagem': f'Aluno "{aluno_nome}" excluído com sucesso!'})
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao excluir aluno: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE PROVAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, titulo, serie, disciplina, bimestre, data_prova, valor_nota,
             tipo_questoes, quantidade_questoes, gabarito, bncc, textos_questoes, niveis, created_at
            FROM provas ORDER BY created_at DESC
        """)
        provas = cur.fetchall()
        cur.close()
        release_db_connection(conn)

        return jsonify(provas if provas else [])
    except Exception as e:
        print(f"❌ Erro ao listar provas: {e}")
        return jsonify([])

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        data = request.json
        titulo = data.get('titulo')
        serie = data.get('serie')

        if not titulo:
            return jsonify({'erro': 'Título é obrigatório'}), 400
        if not serie:
            return jsonify({'erro': 'Série é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            INSERT INTO provas (titulo, serie, disciplina, bimestre, data_prova, valor_nota, tipo_questoes, quantidade_questoes, gabarito, bncc, textos_questoes, niveis)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (titulo, serie, data.get('disciplina', ''), data.get('bimestre', ''),
              data.get('data_prova'), data.get('nota_maxima', 10), data.get('tipo_questoes', '4'),
              data.get('quantidade_questoes', 20), data.get('gabarito', []), data.get('bncc', []),
              data.get('textos_questoes', []), data.get('niveis', [])))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'id': result['id'], 'mensagem': f'Prova "{titulo}" criada com sucesso!'})
    except Exception as e:
        print(f"❌ Erro ao criar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['GET'])
def buscar_prova(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        cur.close()
        release_db_connection(conn)

        if not prova:
            return jsonify({'erro': 'Prova não encontrada'}), 404

        return jsonify(prova)
    except Exception as e:
        print(f"❌ Erro ao buscar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['PUT'])
def editar_prova(id):
    try:
        data = request.json
        titulo = data.get('titulo')
        serie = data.get('serie')

        if not titulo:
            return jsonify({'erro': 'Título é obrigatório'}), 400

        if not serie:
            return jsonify({'erro': 'Série é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM provas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Prova não encontrada'}), 404

        cur.execute("""
            UPDATE provas SET titulo = %s, serie = %s, disciplina = %s, bimestre = %s,
             data_prova = %s, valor_nota = %s, tipo_questoes = %s, quantidade_questoes = %s,
             gabarito = %s, bncc = %s, textos_questoes = %s, niveis = %s
            WHERE id = %s RETURNING id
        """, (titulo, serie, data.get('disciplina', ''), data.get('bimestre', ''),
              data.get('data_prova'), data.get('nota_maxima', 10), data.get('tipo_questoes', '4'),
              data.get('quantidade_questoes', 20), data.get('gabarito', []), data.get('bncc', []),
              data.get('textos_questoes', []), data.get('niveis', []), id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Prova atualizada com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao editar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['DELETE'])
def excluir_prova(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        if not prova:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Prova não encontrada'}), 404

        prova_titulo = prova[1]
        cur.execute("DELETE FROM provas WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'mensagem': f'Prova "{prova_titulo}" excluída com sucesso!'})
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao excluir prova: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE GABARITOS
# ============================================

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        bncc = data.get('bncc', [])

        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400

        if not respostas or len(respostas) == 0:
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor()
        cur.execute("SELECT id FROM provas WHERE id = %s", (prova_id,))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Prova não encontrada'}), 404

        cur.execute("""
            UPDATE provas SET gabarito = %s::text[], quantidade_questoes = %s, bncc = %s::text[]
            WHERE id = %s RETURNING id
        """, (respostas, len(respostas), bncc, prova_id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'id': result[0], 'mensagem': 'Gabarito salvo com sucesso', 'total_questoes': len(respostas)})
    except Exception as e:
        print(f"❌ Erro ao salvar gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/gabaritos/<int:id>', methods=['DELETE'])
def excluir_gabarito(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor()

        cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        if not prova:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Prova não encontrada'}), 404

        cur.execute("UPDATE provas SET gabarito = NULL, quantidade_questoes = 0, bncc = NULL WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'mensagem': f'Gabarito da prova "{prova[1]}" removido com sucesso!'})
    except Exception as e:
        print(f"❌ Erro ao excluir gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE HISTÓRICO
# ============================================

@app.route('/api/historico', methods=['GET'])
def listar_historico():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT h.*, a.nome as aluno_nome, p.titulo as prova_titulo, p.disciplina,
             t.serie, t.nome as turma_nome, e.nome as escola_nome
            FROM historico h
            LEFT JOIN alunos a ON h.aluno_id = a.id
            LEFT JOIN provas p ON h.prova_id = p.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            ORDER BY h.data_correcao DESC
        """)
        historico = cur.fetchall()
        cur.close()
        release_db_connection(conn)

        for item in historico:
            total = item.get('total', 20)
            acertos = item.get('acertos', 0)
            porcentagem = round((acertos / total) * 100) if total > 0 else 0
            conceito = calcular_conceito(porcentagem)
            item['conceito'] = conceito['nome']
            item['conceito_rotulo'] = conceito['rotulo']
            item['porcentagem'] = porcentagem

        return jsonify(historico if historico else [])
    except Exception as e:
        print(f"❌ Erro ao listar histórico: {e}")
        return jsonify([])

@app.route('/api/historico/agrupado', methods=['GET'])
def historico_agrupado():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT h.*, a.nome as aluno_nome, p.titulo as prova_titulo, p.disciplina,
             t.serie, t.nome as turma_nome, e.nome as escola_nome
            FROM historico h
            LEFT JOIN alunos a ON h.aluno_id = a.id
            LEFT JOIN provas p ON h.prova_id = p.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            ORDER BY a.nome, h.data_correcao DESC
        """)
        historico = cur.fetchall()
        cur.close()
        release_db_connection(conn)

        alunos_map = {}
        for item in historico:
            aluno_key = item.get('aluno_id') or item.get('aluno_nome')
            if not aluno_key:
                continue

            if aluno_key not in alunos_map:
                alunos_map[aluno_key] = {
                    'aluno_id': item.get('aluno_id'),
                    'aluno_nome': item.get('aluno_nome', 'Aluno'),
                    'serie': item.get('serie', ''),
                    'turma': item.get('turma_nome', ''),
                    'escola': item.get('escola_nome', ''),
                    'avaliacoes': {}
                }

            disciplina = item.get('disciplina', '')
            prova_titulo = item.get('prova_titulo', '')
            serie_aluno = item.get('serie', '')
            tipo = 'Portugues'

            if 'matemática' in disciplina.lower() or 'matematica' in disciplina.lower():
                tipo = 'Matematica'
            elif 'produção' in disciplina.lower() or 'producao' in disciplina.lower() or 'texto' in disciplina.lower():
                tipo = 'Producao'
            elif 'ciências humanas' in disciplina.lower() or 'ch' in disciplina.lower():
                tipo = 'CH'
            elif 'ciências naturais' in disciplina.lower() or 'cn' in disciplina.lower():
                tipo = 'CN'

            if tipo not in alunos_map[aluno_key]['avaliacoes']:
                alunos_map[aluno_key]['avaliacoes'][tipo] = {
                    'nota': float(item.get('nota', 0)),
                    'acertos': int(item.get('acertos', 0)),
                    'total': int(item.get('total', 20)),
                    'prova': prova_titulo,
                    'data': item.get('data_correcao', ''),
                    'disciplina': disciplina
                }

        resultado = []
        for aluno_key, dados in alunos_map.items():
            avaliacoes = dados['avaliacoes']

            default = {'nota': 0, 'acertos': 0, 'total': 20}
            portugues = dict(avaliacoes.get('Portugues', default))
            matematica = dict(avaliacoes.get('Matematica', default))
            producao = dict(avaliacoes.get('Producao', default))
            ch = dict(avaliacoes.get('CH', default))
            cn = dict(avaliacoes.get('CN', default))

            notas = [portugues.get('nota', 0), matematica.get('nota', 0),
                     producao.get('nota', 0), ch.get('nota', 0), cn.get('nota', 0)]
            soma = sum(notas)
            media = soma / 5 if notas else 0

            resultado.append({
                'aluno_id': dados['aluno_id'],
                'aluno_nome': dados['aluno_nome'],
                'serie': dados['serie'],
                'turma': dados['turma'],
                'escola': dados['escola'],
                'portugues': portugues,
                'matematica': matematica,
                'producao': producao,
                'ch': ch,
                'cn': cn,
                'soma': round(soma, 1),
                'media': round(media, 1)
            })

        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Erro ao buscar histórico agrupado: {e}")
        return jsonify([])

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
            release_db_connection(conn)
            return jsonify({
                'total_escolas': total_escolas,
                'total_turmas': total_turmas,
                'total_alunos': total_alunos,
                'total_provas': total_provas
            })
        except Exception as e:
            print(f"❌ Erro no dashboard: {e}")
            release_db_connection(conn)
    return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})

@app.route('/api/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT t.id as turma_id, t.nome as turma_nome, t.serie,
             COUNT(DISTINCT a.id) as total_alunos,
             COALESCE(AVG(h.acertos * 1.0 / NULLIF(h.total, 0)), 0) as media_porcentagem,
             COALESCE(SUM(CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END), 0) as total_correcoes
            FROM turmas t
            LEFT JOIN alunos a ON a.turma_id = t.id
            LEFT JOIN historico h ON h.aluno_id = a.id
            GROUP BY t.id, t.nome, t.serie
            HAVING COUNT(DISTINCT a.id) > 0
            ORDER BY t.nome
        """)

        turmas = cur.fetchall()
        cur.close()
        release_db_connection(conn)

        resultado = []
        for turma in turmas:
            media_porcentagem = float(turma['media_porcentagem'] or 0)
            porcentagem = round(media_porcentagem * 100) if media_porcentagem > 0 else 0
            conceito = calcular_conceito(porcentagem)

            resultado.append({
                'id': turma['turma_id'],
                'nome': turma['turma_nome'] or f"Turma {turma['turma_id']}",
                'serie': turma['serie'],
                'total_alunos': turma['total_alunos'],
                'porcentagem': porcentagem,
                'total_correcoes': turma['total_correcoes'],
                'conceito': conceito
            })

        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Erro em /api/dashboard/Conceito: {e}")
        return jsonify([])

# ============================================
# ROTA DE CORREÇÃO
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')

        if not prova_id or not aluno_id:
            return jsonify({'erro': 'Prova e aluno são obrigatórios'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()

        if not prova:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Prova não encontrada'}), 404

        cur.execute("SELECT * FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        cur.close()
        release_db_connection(conn)

        gabarito = prova.get('gabarito', [])
        if not gabarito or len(gabarito) == 0:
            return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400

        # Simulação de correção
        alternativas = ['A', 'B', 'C', 'D']
        total = len(gabarito)
        respostas_detectadas = []

        # Gera respostas simuladas (80% de chance de acertar)
        for gab in gabarito:
            if random.random() < 0.8:
                respostas_detectadas.append(gab)
            else:
                erradas = [a for a in alternativas if a != gab]
                respostas_detectadas.append(random.choice(erradas) if erradas else gab)

        acertos = sum(1 for r, g in zip(respostas_detectadas, gabarito) if r == g)
        valor_por_questao = 10 / total if total > 0 else 0
        nota = acertos * valor_por_questao
        porcentagem = round((acertos / total) * 100) if total > 0 else 0
        conceito = calcular_conceito(porcentagem)

        questoes_status = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp == gab if resp else False
            status_msg = 'ADQUIRIU HABILIDADE' if is_correto else ('RECOMPOSIÇÃO DE APRENDIZAGEM' if resp else 'NÃO RESPONDEU')
            questoes_status.append({
                'numero': i+1,
                'resposta': resp or '—',
                'gabarito': gab or '—',
                'acertou': is_correto,
                'status': status_msg,
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}"
            })

        resultado = {
            'aluno': aluno['nome'] if aluno else 'Aluno',
            'prova': prova['titulo'],
            'disciplina': prova.get('disciplina', ''),
            'serie': prova.get('serie', ''),
            'total': total,
            'acertos': acertos,
            'nota': round(nota, 1),
            'porcentagem': porcentagem,
            'conceito': conceito,
            'respostas_detectadas': respostas_detectadas,
            'gabarito': gabarito,
            'questoes_status': questoes_status,
            'confianca': 85,
            'modo': 'simulado',
            'valor_por_questao': round(valor_por_questao, 2)
        }

        # Salva no histórico
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                questoes_status_json = json.dumps(questoes_status)

                cur.execute("""
                    SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s
                """, (prova_id, aluno_id))
                existe = cur.fetchone()

                if existe:
                    cur.execute("""
                        UPDATE historico SET respostas = %s::text[], acertos = %s, nota = %s,
                         total = %s, tipo_correcao = 'ia', disciplina = %s,
                         questoes_status = %s::jsonb, data_correcao = CURRENT_TIMESTAMP
                        WHERE prova_id = %s AND aluno_id = %s
                    """, (respostas_detectadas, acertos, nota, total, prova.get('disciplina', ''),
                          questoes_status_json, prova_id, aluno_id))
                else:
                    cur.execute("""
                        INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total,
                         tipo_correcao, disciplina, questoes_status)
                        VALUES (%s, %s, %s::text[], %s, %s, %s, 'ia', %s, %s::jsonb)
                    """, (prova_id, aluno_id, respostas_detectadas, acertos, nota, total,
                          prova.get('disciplina', ''), questoes_status_json))

                conn.commit()
                cur.close()
                release_db_connection(conn)
        except Exception as e:
            print(f"⚠️ Erro ao salvar histórico: {e}")

        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Erro na correção: {e}")
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

        cur.execute("SELECT disciplina, titulo, gabarito FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        disciplina = prova[0] if prova else ''
        gabarito = prova[2] if prova else []

        questoes_status = []
        for i in range(total):
            resp = str(respostas[i]) if i < len(respostas) and respostas[i] is not None else ''
            gab = str(gabarito[i]) if i < len(gabarito) and gabarito[i] is not None else ''
            is_correto = resp and gab and resp.upper() == gab.upper()

            status_msg = 'ADQUIRIU HABILIDADE' if is_correto else ('RECOMPOSIÇÃO DE APRENDIZAGEM' if resp else 'NÃO RESPONDEU')
            questoes_status.append({
                'numero': i+1,
                'resposta': resp or '—',
                'gabarito': gab or '—',
                'acertou': is_correto,
                'status': status_msg,
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}"
            })

        questoes_status_json = json.dumps(questoes_status)

        cur.execute("""
            SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s
        """, (prova_id, aluno_id))
        existe = cur.fetchone()

        if existe:
            cur.execute("""
                UPDATE historico SET respostas = %s::text[], acertos = %s, nota = %s,
                 total = %s, tipo_correcao = 'manual', disciplina = %s,
                 questoes_status = %s::jsonb, data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, questoes_status_json, prova_id, aluno_id))
        else:
            cur.execute("""
                INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total,
                 tipo_correcao, disciplina, questoes_status)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual', %s, %s::jsonb)
            """, (prova_id, aluno_id, respostas, acertos, nota, total, disciplina, questoes_status_json))

        conn.commit()
        cur.close()
        release_db_connection(conn)

        porcentagem = round((acertos / total) * 100) if total > 0 else 0
        conceito = calcular_conceito(porcentagem)

        return jsonify({
            'sucesso': True,
            'mensagem': 'Correção manual salva com sucesso',
            'conceito': conceito,
            'porcentagem': porcentagem,
            'questoes_status': questoes_status
        })
    except Exception as e:
        print(f"❌ Erro na correção manual: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE CORREÇÃO DE REDAÇÃO
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        data = request.json
        texto = data.get('texto')

        if not texto:
            return jsonify({'erro': 'Texto é obrigatório'}), 400

        # Simulação de avaliação
        palavras = len(texto.split())
        nota = min(10, max(0, (palavras / 30) * 10))

        return jsonify({
            'nota': round(nota, 1),
            'metricas': {
                'nota_coerencia': round(nota * 0.9, 1),
                'nota_estrutura': round(nota * 0.8, 1),
                'nota_gramatica': round(nota * 0.85, 1),
                'nota_vocabulario': round(nota * 0.75, 1)
            },
            'feedback': 'Texto avaliado com sucesso!',
            'modo': 'simulado'
        })
    except Exception as e:
        print(f"❌ Erro na correção de redação: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE USUÁRIOS
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
            release_db_connection(conn)
            return jsonify(usuarios if usuarios else [])
        except Exception as e:
            print(f"❌ Erro ao listar usuários: {e}")
            release_db_connection(conn)

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
            release_db_connection(conn)
            return jsonify({'erro': 'Usuário já existe'}), 400

        cur.execute("""
            INSERT INTO usuarios (nome, username, senha_hash, email, perfil, ativo)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (nome, username, senha, email, perfil, ativo))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'id': result['id'], 'mensagem': 'Usuário criado com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao criar usuário: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['GET'])
def buscar_usuario(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nome, username, email, perfil, ativo, criado_em FROM usuarios WHERE id = %s", (id,))
        usuario = cur.fetchone()
        cur.close()
        release_db_connection(conn)

        if not usuario:
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        return jsonify(usuario)
    except Exception as e:
        print(f"❌ Erro ao buscar usuário: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def atualizar_usuario(id):
    try:
        data = request.json
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)

        if not nome or not username:
            return jsonify({'erro': 'Nome e usuário são obrigatórios'}), 400

        if len(username) < 3:
            return jsonify({'erro': 'Usuário deve ter pelo menos 3 caracteres'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM usuarios WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        cur.execute("SELECT id FROM usuarios WHERE username = %s AND id != %s", (username, id))
        if cur.fetchone():
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Este nome de usuário já está em uso'}), 400

        update_fields = []
        params = []

        update_fields.append("nome = %s")
        params.append(nome)

        update_fields.append("username = %s")
        params.append(username)

        update_fields.append("email = %s")
        params.append(email)

        update_fields.append("perfil = %s")
        params.append(perfil)

        update_fields.append("ativo = %s")
        params.append(ativo)

        if senha and len(senha) >= 4:
            update_fields.append("senha_hash = %s")
            params.append(senha)

        params.append(id)

        query = f"UPDATE usuarios SET {', '.join(update_fields)} WHERE id = %s RETURNING id"

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Usuário atualizado com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao atualizar usuário: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT username FROM usuarios WHERE id = %s", (id,))
        usuario = cur.fetchone()
        if not usuario:
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        username = usuario['username']

        if username == 'admin':
            cur.close()
            release_db_connection(conn)
            return jsonify({'erro': 'Não é possível excluir o usuário administrador principal'}), 400

        cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        release_db_connection(conn)

        return jsonify({'sucesso': True, 'mensagem': f'Usuário "{username}" excluído com sucesso'})
    except Exception as e:
        print(f"❌ Erro ao excluir usuário: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE BACKUP
# ============================================

@app.route('/api/backup', methods=['GET'])
def backup_database():
    return jsonify({'mensagem': 'Backup disponível em breve'})

# ============================================
# ROTA DE SAÚDE
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'online',
        'database': 'conectado' if db_pool else 'desconectado'
    })

# ============================================
# ROTA PRINCIPAL
# ============================================

@app.route('/')
def index():
    try:
        return send_from_directory('.', 'index.html')
    except:
        return jsonify({'mensagem': 'CorrigePro API', 'status': 'online'})

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('.', path)
    except:
        return jsonify({'erro': 'Arquivo não encontrado'}), 404

# ============================================
# INICIALIZAÇÃO DO BANCO
# ============================================

def init_db():
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível")
        return

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'escolas'
            )
        """)
        tabela_existe = cur.fetchone()[0]

        if not tabela_existe:
            print("🔧 Criando tabelas do banco de dados...")

            cur.execute("""
                CREATE TABLE escolas (
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
                CREATE TABLE turmas (
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
                CREATE TABLE alunos (
                    id SERIAL PRIMARY KEY,
                    escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
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

            cur.execute("""
                CREATE TABLE provas (
                    id SERIAL PRIMARY KEY,
                    titulo TEXT NOT NULL,
                    serie TEXT NOT NULL,
                    disciplina TEXT,
                    bimestre TEXT,
                    data_prova DATE,
                    valor_nota DECIMAL(5,2) DEFAULT 10,
                    tipo_questoes TEXT DEFAULT '4',
                    quantidade_questoes INTEGER DEFAULT 20,
                    gabarito TEXT[],
                    bncc TEXT[],
                    textos_questoes TEXT[],
                    niveis TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE historico (
                    id SERIAL PRIMARY KEY,
                    prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                    aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                    respostas TEXT[],
                    acertos INTEGER,
                    nota DECIMAL(5,2),
                    total INTEGER,
                    tipo_correcao TEXT DEFAULT 'ia',
                    disciplina TEXT,
                    tipo_avaliacao TEXT,
                    questoes_status JSONB DEFAULT '[]',
                    data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE usuarios (
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

            cur.execute("""
                CREATE TABLE correcoes_texto (
                    id SERIAL PRIMARY KEY,
                    aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                    prova_id INTEGER REFERENCES provas(id) ON DELETE SET NULL,
                    texto TEXT NOT NULL,
                    nota DECIMAL(5,2),
                    metrica_coerencia DECIMAL(5,2),
                    metrica_estrutura DECIMAL(5,2),
                    metrica_gramatica DECIMAL(5,2),
                    metrica_vocabulario DECIMAL(5,2),
                    feedback TEXT,
                    tipo_correcao TEXT DEFAULT 'ia',
                    data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            print("✅ Tabelas criadas com sucesso!")

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
        release_db_connection(conn)
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")
        traceback.print_exc()

# ============================================
# INICIALIZAÇÃO DO SERVIDOR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 INICIANDO SERVIDOR CORRIGEPRO")
    print("=" * 60)
    print(f"📌 Porta: {port}")
    print(f"🗄️ Banco: {'✅ Conectado' if db_pool else '❌ Desconectado'}")
    print("=" * 60)

    init_db()

    app.run(host='0.0.0.0', port=port, debug=False)
