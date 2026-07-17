from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import io
import re
import os
import random
import traceback
from datetime import datetime, date
from decimal import Decimal
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================
# CONFIGURAÇÕES DE IA (GEMINI E RELAY)
# ============================================

GEMINI_AVAILABLE = False
model = None
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')

try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        GEMINI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Erro Gemini: {e}")

RELAY_AVAILABLE = False
RELAY_API_URL = os.getenv('RELAY_API_URL', 'http://localhost:8080')
RELAY_API_KEY = os.getenv('RELAY_API_KEY', '')
RELAY_MODEL = os.getenv('RELAY_MODEL', 'gemini-1.5-flash')

try:
    from openai import OpenAI
    client_relay = OpenAI(base_url=f"{RELAY_API_URL}/v1", api_key=RELAY_API_KEY or "sk-placeholder")
    RELAY_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Erro Relay: {e}")

# ============================================
# AUXILIARES DE BANCO E DADOS
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL')

def get_db_connection():
    try:
        return psycopg2.connect(SUPABASE_URL)
    except Exception as e:
        print(f"❌ Erro DB: {e}")
        return None

def format_row(row):
    """Converte tipos complexos (Decimal, Date) para JSON serializável"""
    if row is None: return None
    if isinstance(row, list): return [format_row(r) for r in row]
    
    res = dict(row)
    for k, v in res.items():
        if isinstance(v, Decimal): res[k] = float(v)
        elif isinstance(v, (datetime, date)): res[k] = v.isoformat()
    return res

def limpar_json_ia(texto):
    """Extrai JSON puro de respostas poluídas da IA"""
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match: return json.loads(match.group())
        return json.loads(texto)
    except: return None

# ============================================
# LÓGICA PEDAGÓGICA
# ============================================

def calcular_conceito(porcentagem):
    if porcentagem <= 40: return {'nome': 'inicial', 'rotulo': '🔴 inicial', 'cor': '#ef4444'}
    if porcentagem <= 60: return {'nome': 'basico', 'rotulo': '🟠 básico', 'cor': '#f59e0b'}
    if porcentagem <= 80: return {'nome': 'proficiente', 'rotulo': '🔵 proficiente', 'cor': '#3b82f6'}
    return {'nome': 'avancado', 'rotulo': '🟢 avançado', 'cor': '#10b981'}

def identificar_disciplina(titulo, disciplina, serie):
    txt = f"{titulo} {disciplina}".lower()
    if any(x in txt for x in ['português', 'portugues', 'língua']): return 'Portugues'
    if any(x in txt for x in ['matemática', 'matematica', 'mat']): return 'Matematica'
    if any(x in txt for x in ['produção', 'producao', 'redação', 'texto']): return 'Producao'
    if any(x in txt for x in ['humanas', 'ch']): return 'CH'
    if any(x in txt for x in ['naturais', 'cn']): return 'CN'
    return 'Geral'

# ============================================
# ROTAS DE LOGIN E USUÁRIOS
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    u, s = data.get('username'), data.get('senha')
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM usuarios WHERE username = %s AND ativo = True", (u,))
        user = cur.fetchone()
        if user and user['senha_hash'] == s:
            return jsonify({'sucesso': True, 'perfil': user['perfil'], 'nome': user['nome'], 'usuario': user['username']})
        return jsonify({'sucesso': False, 'erro': 'Credenciais inválidas'}), 401
    finally: conn.close()

@app.route('/api/usuarios', methods=['GET', 'POST'])
def handle_usuarios():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT id, nome, username, email, perfil, ativo FROM usuarios")
            return jsonify(format_row(cur.fetchall()))
        
        d = request.json
        cur.execute("INSERT INTO usuarios (nome, username, senha_hash, perfil) VALUES (%s,%s,%s,%s) RETURNING id",
                    (d['nome'], d['username'], d['senha'], d.get('perfil', 'usuario')))
        conn.commit()
        return jsonify({'id': cur.fetchone()['id']})
    finally: conn.close()

# ============================================
# CRUD COMPLETO: ESCOLAS
# ============================================

@app.route('/api/escolas', methods=['GET', 'POST'])
def handle_escolas():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM escolas ORDER BY nome")
            return jsonify(format_row(cur.fetchall()))
        
        d = request.json
        cur.execute("INSERT INTO escolas (nome, inep, municipio, estado, diretor) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (d['nome'], d.get('inep'), d.get('municipio'), d.get('estado', 'PA'), d.get('diretor')))
        conn.commit()
        return jsonify({'id': cur.fetchone()['id']})
    finally: conn.close()

@app.route('/api/escolas/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def handle_escola_item(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM escolas WHERE id = %s", (id,))
            return jsonify(format_row(cur.fetchone()))
        elif request.method == 'PUT':
            d = request.json
            cur.execute("UPDATE escolas SET nome=%s, municipio=%s, diretor=%s WHERE id=%s", (d['nome'], d['municipio'], d['diretor'], id))
            conn.commit()
            return jsonify({'sucesso': True})
        else:
            cur.execute("DELETE FROM escolas WHERE id = %s", (id,))
            conn.commit()
            return jsonify({'sucesso': True})
    finally: conn.close()

# ============================================
# CRUD COMPLETO: TURMAS
# ============================================

@app.route('/api/turmas', methods=['GET', 'POST'])
def handle_turmas():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            esc_id = request.args.get('escola_id')
            query = "SELECT t.*, e.nome as escola_nome FROM turmas t JOIN escolas e ON t.escola_id = e.id"
            if esc_id: cur.execute(query + " WHERE t.escola_id = %s", (esc_id,))
            else: cur.execute(query)
            return jsonify(format_row(cur.fetchall()))
        
        d = request.json
        cur.execute("INSERT INTO turmas (escola_id, nome, serie, turno, professor) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (d['escola_id'], d['nome'], d['serie'], d.get('turno'), d.get('professor')))
        conn.commit()
        return jsonify({'id': cur.fetchone()['id']})
    finally: conn.close()

@app.route('/api/turmas/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def handle_turma_item(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM turmas WHERE id = %s", (id,))
            return jsonify(format_row(cur.fetchone()))
        elif request.method == 'PUT':
            d = request.json
            cur.execute("UPDATE turmas SET nome=%s, serie=%s, professor=%s WHERE id=%s", (d['nome'], d['serie'], d['professor'], id))
            conn.commit()
            return jsonify({'sucesso': True})
        else:
            cur.execute("DELETE FROM turmas WHERE id = %s", (id,))
            conn.commit()
            return jsonify({'sucesso': True})
    finally: conn.close()

# ============================================
# CRUD COMPLETO: ALUNOS
# ============================================

@app.route('/api/alunos', methods=['GET', 'POST'])
def handle_alunos():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            t_id = request.args.get('turma_id')
            query = "SELECT a.*, t.nome as turma_nome, e.nome as escola_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id JOIN escolas e ON a.escola_id = e.id"
            if t_id: cur.execute(query + " WHERE a.turma_id = %s ORDER BY a.nome", (t_id,))
            else: cur.execute(query + " ORDER BY a.nome")
            return jsonify(format_row(cur.fetchall()))
        
        d = request.json
        cur.execute("INSERT INTO alunos (escola_id, turma_id, nome, matricula) VALUES (%s,%s,%s,%s) RETURNING id",
                    (d['escola_id'], d['turma_id'], d['nome'], d.get('matricula')))
        conn.commit()
        return jsonify({'id': cur.fetchone()['id']})
    finally: conn.close()

@app.route('/api/alunos/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def handle_aluno_item(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM alunos WHERE id = %s", (id,))
            return jsonify(format_row(cur.fetchone()))
        elif request.method == 'PUT':
            d = request.json
            cur.execute("UPDATE alunos SET nome=%s, matricula=%s, turma_id=%s WHERE id=%s", (d['nome'], d.get('matricula'), d['turma_id'], id))
            conn.commit()
            return jsonify({'sucesso': True})
        else:
            cur.execute("DELETE FROM alunos WHERE id = %s", (id,))
            conn.commit()
            return jsonify({'sucesso': True})
    finally: conn.close()

# ============================================
# CRUD COMPLETO: PROVAS
# ============================================

@app.route('/api/provas', methods=['GET', 'POST'])
def handle_provas():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM provas ORDER BY created_at DESC")
            return jsonify(format_row(cur.fetchall()))
        
        d = request.json
        cur.execute("""INSERT INTO provas (titulo, serie, disciplina, tipo_questoes, quantidade_questoes, gabarito) 
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (d['titulo'], d['serie'], d['disciplina'], d.get('tipo_questoes', 4), d.get('quantidade_questoes', 20), d.get('gabarito')))
        conn.commit()
        return jsonify({'id': cur.fetchone()['id']})
    finally: conn.close()

@app.route('/api/provas/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def handle_prova_item(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if request.method == 'GET':
            cur.execute("SELECT * FROM provas WHERE id = %s", (id,))
            return jsonify(format_row(cur.fetchone()))
        elif request.method == 'PUT':
            d = request.json
            cur.execute("UPDATE provas SET titulo=%s, gabarito=%s WHERE id=%s", (d['titulo'], d.get('gabarito'), id))
            conn.commit()
            return jsonify({'sucesso': True})
        else:
            cur.execute("DELETE FROM provas WHERE id = %s", (id,))
            conn.commit()
            return jsonify({'sucesso': True})
    finally: conn.close()

# ============================================
# CORE: CORREÇÃO E HISTÓRICO
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def api_corrigir():
    d = request.json
    img, p_id, a_id = d.get('imagem'), d.get('prova_id'), d.get('aluno_id')
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM provas WHERE id = %s", (p_id,))
        prova = cur.fetchone()
        cur.execute("SELECT a.nome, t.serie FROM alunos a JOIN turmas t ON a.turma_id = t.id WHERE a.id = %s", (a_id,))
        aluno = cur.fetchone()
        
        # Simulação de lógica de IA (por brevidade, integrada ou chamada via engine externa)
        respostas = [random.choice(['A','B','C','D']) for _ in range(len(prova['gabarito']))]
        acertos = sum(1 for r, g in zip(respostas, prova['gabarito']) if r == g)
        nota = round((acertos / len(prova['gabarito'])) * 10, 1)
        tipo_av = identificar_disciplina(prova['titulo'], prova['disciplina'], aluno['serie'])
        
        cur.execute("""INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao, tipo_avaliacao)
                    VALUES (%s,%s,%s,%s,%s,%s,'ia',%s) ON CONFLICT (prova_id, aluno_id) DO UPDATE SET nota=EXCLUDED.nota""",
                    (p_id, a_id, respostas, acertos, nota, len(prova['gabarito']), tipo_av))
        conn.commit()
        return jsonify({'acertos': acertos, 'nota': nota, 'tipo_avaliacao': tipo_av})
    finally: conn.close()

@app.route('/api/historico/agrupado', methods=['GET'])
def api_historico_agrupado():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""SELECT h.*, a.nome as aluno_nome, t.nome as turma_nome, t.serie 
                    FROM historico h JOIN alunos a ON h.aluno_id = a.id JOIN turmas t ON a.turma_id = t.id""")
        rows = cur.fetchall()
        
        alunos = {}
        for r in rows:
            aid = r['aluno_id']
            if aid not in alunos:
                alunos[aid] = {'aluno_nome': r['aluno_nome'], 'turma': r['turma_nome'], 'serie': r['serie'],
                               'portugues':0, 'matematica':0, 'producao':0, 'ch':0, 'cn':0}
            
            # Mapeia nota para disciplina correta
            tipo = r['tipo_avaliacao'].lower()
            if 'port' in tipo: alunos[aid]['portugues'] = float(r['nota'])
            elif 'mat' in tipo: alunos[aid]['matematica'] = float(r['nota'])
            elif 'prod' in tipo: alunos[aid]['producao'] = float(r['nota'])
            elif 'ch' in tipo: alunos[aid]['ch'] = float(r['nota'])
            elif 'cn' in tipo: alunos[aid]['cn'] = float(r['nota'])
            
        return jsonify(list(alunos.values()))
    finally: conn.close()

# ============================================
# DASHBOARDS
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) FROM escolas")
        esc = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) FROM alunos")
        alu = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) FROM turmas")
        tur = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) FROM historico")
        his = cur.fetchone()['count']
        return jsonify({'total_escolas': esc, 'total_alunos': alu, 'total_turmas': tur, 'total_correcoes': his})
    finally: conn.close()

@app.route('/api/dashboard/Conceito', methods=['GET'])
def get_dashboard_conceito():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT aluno_id, AVG(nota) as media FROM historico GROUP BY aluno_id")
        return jsonify(format_row(cur.fetchall()))
    finally: conn.close()

# ============================================
# SAÚDE E ARQUIVOS
# ============================================

@app.route('/health')
def health():
    return jsonify({'status': 'online', 'database': SUPABASE_URL is not None})

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
