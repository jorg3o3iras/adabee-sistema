from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import sqlite3
from datetime import datetime
import os
import io
import csv
import re
from PIL import Image
import google.generativeai as genai
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAR BANCO DE DADOS (PostgreSQL ou SQLite)
# ============================================

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_db_connection():
    """Retorna conexão com o banco de dados (PostgreSQL ou SQLite)"""
    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            print(f"⚠️ PostgreSQL indisponível: {e}")
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'adabee.db')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS escolas (
        id SERIAL PRIMARY KEY, nome TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (
        id SERIAL PRIMARY KEY, escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        nome TEXT NOT NULL, serie TEXT DEFAULT '1º Ano', criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (
        id SERIAL PRIMARY KEY, turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
        nome TEXT NOT NULL, matricula TEXT, numero_chamada INTEGER, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS provas (
        id SERIAL PRIMARY KEY, turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
        titulo TEXT NOT NULL, descricao TEXT, gabarito TEXT, data_prova DATE,
        valor_nota REAL DEFAULT 10, quantidade_questoes INTEGER, tipo_questoes TEXT DEFAULT '4',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes (
        id SERIAL PRIMARY KEY, prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        respostas TEXT, acertos INTEGER, nota REAL, data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes_redacao (
        id SERIAL PRIMARY KEY, prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        texto TEXT, nota REAL, feedback TEXT, data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado!")

init_database()

# ============================================
# CONFIGURAR GEMINI AI
# ============================================

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        modelos_tentar = [
            'models/gemini-2.0-flash',
            'models/gemini-2.5-flash',
            'models/gemini-2.5-pro',
            'models/gemini-flash-latest',
        ]
        
        model = None
        for modelo_nome in modelos_tentar:
            try:
                model = genai.GenerativeModel(modelo_nome)
                print(f"✅ Modelo carregado: {modelo_nome}")
                break
            except Exception as e:
                print(f"⚠️ Falha em {modelo_nome}: {e}")
                continue
        
        if model is None:
            raise Exception("Nenhum modelo disponível")
        
        GEMINI_AVAILABLE = True
        print("✅ Gemini AI configurado!")
    except Exception as e:
        GEMINI_AVAILABLE = False
        print(f"❌ Erro ao configurar Gemini: {e}")
else:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini não configurado.")

# ============================================
# DETECÇÃO DE RESPOSTAS COM GEMINI
# ============================================

def detectar_respostas_gemini(imagem_base64, num_opcoes=4):
    try:
        if not GEMINI_AVAILABLE:
            return [], 0.0
        
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        img = Image.open(io.BytesIO(imagem_bytes))
        img.thumbnail((1024, 1024))
        
        opcoes = 'ABCDE'[:num_opcoes]
        opcoes_str = ', '.join(list(opcoes))
        
        prompt = f"""[SISTEMA DE CORREÇÃO DE PROVAS]

ANALISE ESTA IMAGEM:
- É uma folha de respostas com questões numeradas
- Cada questão tem {num_opcoes} bolinhas: {opcoes_str}
- O aluno marcou UMA bolinha por questão (a mais escura)

TAREFA:
Liste APENAS as letras das bolinhas marcadas, na ordem das questões.

FORMATO OBRIGATÓRIO (exemplo para 10 questões):
A, B, C, A, B, C, A, B, C, D

REGRAS:
- Use SOMENTE letras maiúsculas ({opcoes_str})
- Separe por vírgula e espaço
- NÃO adicione explicações
- Se não conseguir ver, responda: NENHUMA

Responda SOMENTE a lista de letras."""
        
        response = model.generate_content([prompt, img])
        texto = response.text.strip().upper()
        
        print(f"🤖 Gemini respondeu: {texto[:200]}")
        
        letras_validas = set(opcoes)
        respostas = [c for c in texto if c in letras_validas]
        
        if len(respostas) >= 3:
            print(f"✅ Detectadas {len(respostas)} respostas")
            return respostas, 90.0
        elif len(respostas) > 0:
            return respostas, 70.0
        
        return None, 0.0
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return None, 0.0

# ============================================
# CORREÇÃO DE REDAÇÃO POR IMAGEM OU TEXTO
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao_api():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        texto = dados.get('texto')
        prova_id = dados.get('prova_id')
        aluno_id = dados.get('aluno_id')
        
        if not GEMINI_AVAILABLE:
            return jsonify({'erro': 'Gemini AI não disponível'}), 400
        
        # CORREÇÃO POR IMAGEM (FOTO DA REDAÇÃO)
        if imagem:
            if ',' in imagem:
                imagem = imagem.split(',')[1]
            
            imagem_bytes = base64.b64decode(imagem)
            img = Image.open(io.BytesIO(imagem_bytes))
            img.thumbnail((1024, 1024))
            
            prompt = """[SISTEMA DE CORREÇÃO DE REDAÇÃO]

ANALISE ESTA IMAGEM DE UMA REDAÇÃO ESCRITA À MÃO.

CRITÉRIOS DE AVALIAÇÃO:
1. Estrutura e organização do texto
2. Coerência e coesão
3. Ortografia e gramática
4. Desenvolvimento do tema
5. Criatividade e originalidade

TAREFA:
Analise a redação da imagem e forneça:
1. NOTA: (0 a 10)
2. CONCEITO: (Excelente, Bom, Regular, Insuficiente)
3. FEEDBACK: (Pontos fortes e fracos)
4. SUGESTÕES: (Melhorias)

Formato de resposta:
NOTA: [nota]
CONCEITO: [conceito]
FEEDBACK: [feedback detalhado]
SUGESTÕES: [sugestões]
"""
            
            response = model.generate_content([prompt, img])
            resultado = response.text.strip()
            
            # Extrair nota
            nota_match = re.search(r'NOTA:\s*(\d+(?:\.\d+)?)', resultado)
            nota = float(nota_match.group(1)) if nota_match else 0.0
            nota = min(10, max(0, nota))
            
            # Extrair conceito
            conceito_match = re.search(r'CONCEITO:\s*([A-Za-záéíóúãõç]+)', resultado)
            conceito = conceito_match.group(1) if conceito_match else "Não avaliado"
            
            # Salvar no banco
            if prova_id and aluno_id:
                conn = get_db_connection()
                conn.execute("INSERT INTO correcoes_redacao (prova_id, aluno_id, nota, feedback, data_correcao) VALUES (?, ?, ?, ?, ?)",
                             (prova_id, aluno_id, nota, resultado, datetime.now()))
                conn.commit()
                conn.close()
            
            return jsonify({
                'nota': round(nota, 1),
                'conceito': conceito,
                'feedback': resultado,
                'sucesso': True,
                'metodo': 'Imagem'
            })
        
        # CORREÇÃO POR TEXTO (FALLBACK)
        elif texto and len(texto.strip()) > 5:
            prompt = f"""Corrija a seguinte redação:

"{texto}"

CRITÉRIOS: Estrutura, Coerência, Ortografia, Desenvolvimento do tema.

Responda:
NOTA: (0 a 10)
CONCEITO: (Excelente/Bom/Regular/Insuficiente)
FEEDBACK: (pontos fortes e fracos)
SUGESTÕES: (melhorias)
"""
            
            response = model.generate_content(prompt)
            resultado = response.text.strip()
            
            nota_match = re.search(r'NOTA:\s*(\d+(?:\.\d+)?)', resultado)
            nota = float(nota_match.group(1)) if nota_match else 0.0
            nota = min(10, max(0, nota))
            
            conceito_match = re.search(r'CONCEITO:\s*([A-Za-záéíóúãõç]+)', resultado)
            conceito = conceito_match.group(1) if conceito_match else "Não avaliado"
            
            if prova_id and aluno_id:
                conn = get_db_connection()
                conn.execute("INSERT INTO correcoes_redacao (prova_id, aluno_id, texto, nota, feedback, data_correcao) VALUES (?, ?, ?, ?, ?, ?)",
                             (prova_id, aluno_id, texto, nota, resultado, datetime.now()))
                conn.commit()
                conn.close()
            
            return jsonify({
                'nota': round(nota, 1),
                'conceito': conceito,
                'feedback': resultado,
                'sucesso': True,
                'metodo': 'Texto'
            })
        
        return jsonify({'erro': 'Forneça uma imagem ou texto para correção'}), 400
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# DEMAIS ROTAS (ESCOLAS, TURMAS, ALUNOS, PROVAS, CORREÇÃO)
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ---------- ESCOLAS ----------
@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    if 'psycopg2' in str(type(conn)):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT id, nome FROM escolas ORDER BY nome")
        escolas = cursor.fetchall()
    else:
        escolas = [dict(row) for row in conn.execute("SELECT id, nome FROM escolas ORDER BY nome").fetchall()]
    conn.close()
    return jsonify(escolas)

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'psycopg2' in str(type(conn)):
        cursor.execute("INSERT INTO escolas (nome) VALUES (%s) RETURNING id", (dados['nome'],))
    else:
        cursor.execute("INSERT INTO escolas (nome) VALUES (?)", (dados['nome'],))
    conn.commit()
    escola_id = cursor.fetchone()[0] if hasattr(cursor, 'fetchone') else cursor.lastrowid
    conn.close()
    return jsonify({'id': escola_id})

# ---------- TURMAS ----------
@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    if 'psycopg2' in str(type(conn)):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if escola_id:
            cursor.execute("SELECT id, nome, serie FROM turmas WHERE escola_id = %s ORDER BY nome", (escola_id,))
        else:
            cursor.execute("SELECT id, nome, serie FROM turmas ORDER BY nome")
        turmas = cursor.fetchall()
    else:
        if escola_id:
            turmas = [dict(row) for row in conn.execute("SELECT id, nome, serie FROM turmas WHERE escola_id = ? ORDER BY nome", (escola_id,)).fetchall()]
        else:
            turmas = [dict(row) for row in conn.execute("SELECT id, nome, serie FROM turmas ORDER BY nome").fetchall()]
    conn.close()
    return jsonify(turmas)

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'psycopg2' in str(type(conn)):
        cursor.execute("INSERT INTO turmas (escola_id, nome, serie) VALUES (%s, %s, %s) RETURNING id", 
                       (dados['escola_id'], dados['nome'], dados.get('serie', '1º Ano')))
    else:
        cursor.execute("INSERT INTO turmas (escola_id, nome, serie) VALUES (?, ?, ?)", 
                       (dados['escola_id'], dados['nome'], dados.get('serie', '1º Ano')))
    conn.commit()
    turma_id = cursor.fetchone()[0] if hasattr(cursor, 'fetchone') else cursor.lastrowid
    conn.close()
    return jsonify({'id': turma_id})

# ---------- ALUNOS ----------
@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if 'psycopg2' in str(type(conn)):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if turma_id:
            cursor.execute("SELECT id, nome, matricula, numero_chamada FROM alunos WHERE turma_id = %s ORDER BY numero_chamada", (turma_id,))
        else:
            cursor.execute("SELECT id, nome, matricula, numero_chamada FROM alunos ORDER BY numero_chamada")
        alunos = cursor.fetchall()
    else:
        if turma_id:
            alunos = [dict(row) for row in conn.execute("SELECT id, nome, matricula, numero_chamada FROM alunos WHERE turma_id = ? ORDER BY numero_chamada", (turma_id,)).fetchall()]
        else:
            alunos = [dict(row) for row in conn.execute("SELECT id, nome, matricula, numero_chamada FROM alunos ORDER BY numero_chamada").fetchall()]
    conn.close()
    return jsonify(alunos)

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'psycopg2' in str(type(conn)):
        cursor.execute("INSERT INTO alunos (turma_id, nome, matricula, numero_chamada) VALUES (%s, %s, %s, %s) RETURNING id",
                       (dados['turma_id'], dados['nome'], dados.get('matricula', ''), dados.get('numero_chamada')))
    else:
        cursor.execute("INSERT INTO alunos (turma_id, nome, matricula, numero_chamada) VALUES (?, ?, ?, ?)",
                       (dados['turma_id'], dados['nome'], dados.get('matricula', ''), dados.get('numero_chamada')))
    conn.commit()
    aluno_id = cursor.fetchone()[0] if hasattr(cursor, 'fetchone') else cursor.lastrowid
    conn.close()
    return jsonify({'id': aluno_id})

# ---------- PROVAS ----------
@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    if 'psycopg2' in str(type(conn)):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
                   p.valor_nota, p.quantidade_questoes, p.tipo_questoes, 
                   t.nome as turma_nome, p.turma_id
            FROM provas p JOIN turmas t ON p.turma_id = t.id 
            ORDER BY p.data_prova DESC
        """)
        provas = cursor.fetchall()
    else:
        provas = []
        for row in conn.execute("""
            SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
                   p.valor_nota, p.quantidade_questoes, p.tipo_questoes,
                   t.nome as turma_nome, p.turma_id
            FROM provas p JOIN turmas t ON p.turma_id = t.id 
            ORDER BY p.data_prova DESC
        """):
            provas.append({
                'id': row[0], 'titulo': row[1], 'descricao': row[2],
                'gabarito_array': json.loads(row[3]) if row[3] else [],
                'data_prova': row[4], 'valor_nota': row[5],
                'quantidade_questoes': row[6] or len(json.loads(row[3]) if row[3] else []),
                'tipo_questoes': row[7] or '4',
                'turma_nome': row[8], 'turma_id': row[9]
            })
    conn.close()
    return jsonify(provas)

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'psycopg2' in str(type(conn)):
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota, tipo_questoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            dados['turma_id'], dados['titulo'], dados.get('descricao', ''),
            json.dumps(dados['gabarito']), len(dados['gabarito']),
            dados['data_prova'], dados.get('valor_nota', 10),
            dados.get('tipo_questoes', '4')
        ))
    else:
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota, tipo_questoes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dados['turma_id'], dados['titulo'], dados.get('descricao', ''),
            json.dumps(dados['gabarito']), len(dados['gabarito']),
            dados['data_prova'], dados.get('valor_nota', 10),
            dados.get('tipo_questoes', '4')
        ))
    conn.commit()
    prova_id = cursor.fetchone()[0] if hasattr(cursor, 'fetchone') else cursor.lastrowid
    conn.close()
    return jsonify({'id': prova_id})

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM correcoes WHERE prova_id = %s", (prova_id,))
    cursor.execute("DELETE FROM provas WHERE id = %s", (prova_id,))
    conn.commit()
    conn.close()
    return jsonify({'mensagem': 'ok'})

# ---------- CORREÇÃO DE MÚLTIPLA ESCOLHA ----------
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
        prova = conn.execute("SELECT gabarito, tipo_questoes FROM provas WHERE id = ?", (prova_id,)).fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova[0]) if prova[0] else []
        tipo_questoes = int(prova[1] or 4)
        
        respostas_detectadas, confianca = detectar_respostas_gemini(imagem, tipo_questoes)
        
        if not respostas_detectadas:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as respostas.'}), 400
        
        while len(respostas_detectadas) < len(gabarito):
            respostas_detectadas.append('?')
        
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
        
        aluno = conn.execute("SELECT nome FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
        aluno_nome = aluno[0] if aluno else 'Aluno'
        
        conn.execute("INSERT INTO correcoes (prova_id, aluno_id, respostas, acertos, nota, data_correcao) VALUES (?, ?, ?, ?, ?, ?)",
                     (prova_id, aluno_id, json.dumps(respostas_detectadas), acertos, nota, datetime.now()))
        conn.commit()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round((acertos / len(gabarito)) * 100, 1),
            'correcoes': correcoes,
            'confianca_media': round(confianca, 1),
            'tipo_questoes': tipo_questoes,
            'metodo': 'Gemini AI'
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ---------- GERAR GABARITO ----------
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
        cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
        escola = cursor.fetchone()
        nome_escola = escola[0] if escola else "ESCOLA"
        
        cursor.execute("SELECT nome, serie FROM turmas WHERE id = ?", (turma_id,))
        turma = cursor.fetchone()
        nome_turma = turma[0] if turma else "TURMA"
        serie = turma[1] if turma and turma[1] else "1º Ano"
        
        cursor.execute("SELECT nome, numero_chamada FROM alunos WHERE id = ?", (aluno_id,))
        aluno = cursor.fetchone()
        nome_aluno = aluno[0] if aluno else "ALUNO"
        numero = str(aluno[1]) if aluno and aluno[1] else ""
        
        cursor.execute("SELECT titulo FROM provas WHERE id = ?", (prova_id,))
        prova = cursor.fetchone()
        nome_prova = prova[0] if prova else "PROVA"
        
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
        .circulo {{ display: inline-block; width: 22px; height: 22px; border: 2px solid #333; border-radius: 50%; background: white; }}
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
                                    <span class="circulo"></span>
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
            <button class="secundario" onclick="baixarPDF()">💾 SALVAR PDF</button>
        </div>
    </div>
    <script>
        function baixarPDF() {{ window.print(); }}
        document.querySelectorAll('.opcoes').forEach(grupo => {{
            const opcoes = grupo.querySelectorAll('.opcao');
            opcoes.forEach(opcao => {{
                opcao.addEventListener('click', function() {{
                    opcoes.forEach(opt => {{
                        opt.querySelector('.circulo').style.backgroundColor = 'white';
                        opt.querySelector('.circulo').style.border = '2px solid #333';
                    }});
                    this.querySelector('.circulo').style.backgroundColor = 'black';
                    this.querySelector('.circulo').style.border = '2px solid black';
                }});
            }});
        }});
    </script>
</body>
</html>"""
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        print(f"Erro: {e}")
        return f"<h3>Erro: {str(e)}</h3>", 500

# ---------- DEMAIS ROTAS ----------
@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    try:
        conn = get_db_connection()
        total_escolas = conn.execute("SELECT COUNT(*) FROM escolas").fetchone()[0]
        total_turmas = conn.execute("SELECT COUNT(*) FROM turmas").fetchone()[0]
        total_alunos = conn.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
        total_provas = conn.execute("SELECT COUNT(*) FROM provas").fetchone()[0]
        row = conn.execute("SELECT COUNT(*), COALESCE(AVG(nota), 0) FROM correcoes").fetchone()
        conn.close()
        return jsonify({
            'total_escolas': total_escolas,
            'total_turmas': total_turmas,
            'total_alunos': total_alunos,
            'total_provas': total_provas,
            'total_correcoes': row[0] or 0,
            'media_geral': round(row[1], 1) if row[1] else 0
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/historico', methods=['GET'])
def historico():
    try:
        conn = get_db_connection()
        historico = []
        for row in conn.execute("""
            SELECT c.id, a.nome, p.titulo, c.acertos, c.nota, c.data_correcao
            FROM correcoes c JOIN alunos a ON c.aluno_id = a.id JOIN provas p ON c.prova_id = p.id
            ORDER BY c.data_correcao DESC LIMIT 50
        """):
            historico.append({
                'id': row[0], 'aluno_nome': row[1], 'prova_titulo': row[2],
                'acertos': row[3], 'nota': round(row[4], 1), 'data_correcao': row[5]
            })
        conn.close()
        return jsonify(historico)
    except Exception as e:
        return jsonify([])

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'treinada': True,
        'usando_ia': True,
        'gemini_disponivel': GEMINI_AVAILABLE,
        'status': '🧠 Gemini AI ativo!' if GEMINI_AVAILABLE else '⚠️ Gemini não configurado',
        'metodo': 'Gemini AI',
        'banco': 'PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite'
    })

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    conn = get_db_connection()
    resultados = conn.execute("""
        SELECT a.nome, a.matricula, c.acertos, c.nota, c.data_correcao
        FROM correcoes c JOIN alunos a ON c.aluno_id = a.id WHERE c.prova_id = ?
    """, (prova_id,)).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Aluno', 'Matrícula', 'Acertos', 'Nota', 'Data'])
    for r in resultados:
        writer.writerow([r[0], r[1] or '', r[2], r[3], r[4]])
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': f'attachment; filename=prova_{prova_id}_resultados.csv'
    }

@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    return jsonify({'ip': 'render.com', 'porta': 10000, 'url': 'https://adabee-sistema-3.onrender.com'})

@app.route('/api/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if request.method == 'GET':
        return jsonify({'param1': 80, 'param2': 25})
    return jsonify({'mensagem': 'ok'})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': True})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': '✅ Gemini AI está pronto!'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Gemini AI não precisa de calibração!'})

@app.route('/api/testar_gemini', methods=['POST'])
def testar_gemini():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        if not imagem:
            return jsonify({'erro': 'Imagem não fornecida'}), 400
        if ',' in imagem:
            imagem = imagem.split(',')[1]
        imagem_bytes = base64.b64decode(imagem)
        img = Image.open(io.BytesIO(imagem_bytes))
        img.thumbnail((800, 800))
        prompt = "Descreva o que você vê nesta imagem. Liste as letras A, B, C, D, E se aparecerem."
        response = model.generate_content([prompt, img])
        return jsonify({'resposta_bruta': response.text, 'sucesso': True})
    except Exception as e:
        return jsonify({'erro': str(e), 'sucesso': False}), 500

# ============================================
# ROTA DE TESTE E FALLBACK PARA ERROR 404
# ============================================

@app.route('/api/teste', methods=['GET'])
def teste():
    """Rota simples para testar se o servidor está rodando"""
    return jsonify({
        'mensagem': 'Servidor funcionando!',
        'status': 'ok',
        'banco': 'PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite',
        'gemini': GEMINI_AVAILABLE,
        'timestamp': datetime.now().isoformat()
    })

@app.errorhandler(404)
def not_found(e):
    """Retorna erro 404 em JSON"""
    return jsonify({
        'erro': 'Rota não encontrada',
        'mensagem': 'Verifique se a URL está correta'
    }), 404

@app.errorhandler(500)
def internal_error(e):
    """Retorna erro 500 em JSON"""
    return jsonify({
        'erro': 'Erro interno do servidor',
        'mensagem': str(e)
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
