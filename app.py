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

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAR GEMINI AI - MODELOS CORRETOS (2025)
# ============================================

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        # MODELOS QUE REALMENTE FUNCIONAM (baseado na lista disponível)
        modelos_tentar = [
            'models/gemini-2.0-flash',      # ✅ Estável e rápido
            'models/gemini-2.5-flash',      # ✅ Mais novo
            'models/gemini-2.5-pro',        # ✅ Mais potente
            'models/gemini-flash-latest',   # ✅ Última versão
            'models/gemini-pro-latest',     # ✅ Pro latest
        ]
        
        model = None
        modelo_usado = None
        for modelo_nome in modelos_tentar:
            try:
                model = genai.GenerativeModel(modelo_nome)
                modelo_usado = modelo_nome
                print(f"✅ Modelo carregado: {modelo_nome}")
                break
            except Exception as e:
                print(f"⚠️ Falha em {modelo_nome}: {e}")
                continue
        
        if model is None:
            raise Exception("Nenhum modelo disponível")
        
        GEMINI_AVAILABLE = True
        print(f"✅ Gemini AI configurado! Modelo: {modelo_usado}")
    except Exception as e:
        GEMINI_AVAILABLE = False
        print(f"❌ Erro ao configurar Gemini: {e}")
else:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini não configurado.")

# ============================================
# BANCO DE DADOS SQLITE
# ============================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'adabee.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS escolas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, escola_id INTEGER, nome TEXT NOT NULL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, nome TEXT NOT NULL, 
        matricula TEXT, numero_chamada INTEGER)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS provas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, titulo TEXT NOT NULL,
        gabarito TEXT, data_prova DATE, quantidade_questoes INTEGER)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, prova_id INTEGER, aluno_id INTEGER, 
        respostas TEXT, acertos INTEGER, nota REAL, data_correcao TIMESTAMP)''')
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado!")

init_database()

# ============================================
# DETECÇÃO COM GEMINI AI - VERSÃO OTIMIZADA
# ============================================

def detectar_com_gemini(imagem_base64):
    """Usa Google Gemini para detectar respostas"""
    try:
        if not GEMINI_AVAILABLE:
            return None, 0.0
        
        # Limpar base64
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        img = Image.open(io.BytesIO(imagem_bytes))
        
        # Reduzir tamanho para processamento mais rápido
        img.thumbnail((1024, 1024))
        
        # Prompt otimizado para detecção
        prompt = """[SISTEMA DE CORREÇÃO DE PROVAS]

ANALISE ESTA IMAGEM:
- É uma folha de respostas com questões numeradas
- Cada questão tem 5 bolinhas: A, B, C, D, E
- O aluno marcou UMA bolinha por questão (a mais escura)

TAREFA:
Liste APENAS as letras das bolinhas marcadas, na ordem das questões (da 1 até o final)

FORMATO OBRIGATÓRIO:
A, B, C, D, A, B, C, D, E, A

REGRAS:
- Use SOMENTE letras maiúsculas
- Separe por vírgula e espaço
- NÃO adicione explicações
- NÃO adicione números
- Se não conseguir ver, responda: NENHUMA

Responda SOMENTE a lista de letras."""
        
        response = model.generate_content([prompt, img])
        texto = response.text.strip().upper()
        
        print(f"🤖 Gemini respondeu: {texto[:200]}")
        
        # Extrair letras A-E
        respostas = re.findall(r'[A-E]', texto)
        
        if len(respostas) >= 5:
            print(f"✅ Detectadas {len(respostas)} respostas")
            return respostas, 90.0
        elif len(respostas) > 0:
            print(f"⚠️ Apenas {len(respostas)} respostas detectadas")
            return respostas, 70.0
        
        print("❌ Nenhuma letra detectada")
        return None, 0.0
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return None, 0.0

def detectar_respostas(imagem_base64):
    """Detecta respostas usando Gemini"""
    if GEMINI_AVAILABLE:
        respostas, confianca = detectar_com_gemini(imagem_base64)
        if respostas and len(respostas) > 0:
            return respostas, confianca
    return [], 0.0

# ============================================
# ROTA DE TESTE PARA DIAGNÓSTICO
# ============================================

@app.route('/api/testar_gemini', methods=['POST'])
def testar_gemini():
    """Endpoint para diagnosticar o Gemini"""
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
        
        return jsonify({
            'resposta_bruta': response.text,
            'sucesso': True
        })
    except Exception as e:
        return jsonify({'erro': str(e), 'sucesso': False}), 500

# ============================================
# ROTA PARA LISTAR MODELOS DISPONÍVEIS
# ============================================

@app.route('/api/listar_modelos', methods=['GET'])
def listar_modelos():
    """Lista os modelos Gemini disponíveis"""
    try:
        if not GEMINI_AVAILABLE:
            return jsonify({'erro': 'Gemini não configurado'}), 400
        
        modelos = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos.append(m.name)
        
        return jsonify({'modelos_disponiveis': modelos})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS PRINCIPAIS DA API
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

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

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    escolas = [dict(row) for row in conn.execute("SELECT id, nome FROM escolas ORDER BY nome").fetchall()]
    conn.close()
    return jsonify(escolas)

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO escolas (nome) VALUES (?)", (dados['nome'],))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    if escola_id:
        turmas = [dict(row) for row in conn.execute("SELECT id, nome FROM turmas WHERE escola_id = ? ORDER BY nome", (escola_id,)).fetchall()]
    else:
        turmas = [dict(row) for row in conn.execute("SELECT id, nome FROM turmas ORDER BY nome").fetchall()]
    conn.close()
    return jsonify(turmas)

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO turmas (escola_id, nome) VALUES (?, ?)", (dados['escola_id'], dados['nome']))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if turma_id:
        alunos = [dict(row) for row in conn.execute("SELECT id, nome, numero_chamada FROM alunos WHERE turma_id = ? ORDER BY numero_chamada", (turma_id,)).fetchall()]
    else:
        alunos = [dict(row) for row in conn.execute("SELECT id, nome, numero_chamada FROM alunos ORDER BY numero_chamada").fetchall()]
    conn.close()
    return jsonify(alunos)

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alunos (turma_id, nome, numero_chamada) VALUES (?, ?, ?)", 
                   (dados['turma_id'], dados['nome'], dados.get('numero_chamada')))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    provas = []
    for row in conn.execute("""
        SELECT p.id, p.titulo, p.gabarito, p.data_prova, p.quantidade_questoes, t.nome as turma_nome, p.turma_id
        FROM provas p JOIN turmas t ON p.turma_id = t.id ORDER BY p.data_prova DESC
    """):
        provas.append({
            'id': row[0], 'titulo': row[1],
            'gabarito_array': json.loads(row[2]) if row[2] else [],
            'data_prova': row[3], 'quantidade_questoes': row[4],
            'turma_nome': row[5], 'turma_id': row[6]
        })
    conn.close()
    return jsonify(provas)

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO provas (turma_id, titulo, gabarito, quantidade_questoes, data_prova)
        VALUES (?, ?, ?, ?, ?)
    """, (dados['turma_id'], dados['titulo'], json.dumps(dados['gabarito']), len(dados['gabarito']), dados['data_prova']))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM correcoes WHERE prova_id = ?", (prova_id,))
    conn.execute("DELETE FROM provas WHERE id = ?", (prova_id,))
    conn.commit()
    conn.close()
    return jsonify({'mensagem': 'ok'})

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
        prova = conn.execute("SELECT gabarito FROM provas WHERE id = ?", (prova_id,)).fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova[0]) if prova[0] else []
        respostas_detectadas, confianca = detectar_respostas(imagem)
        
        if len(respostas_detectadas) == 0:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as respostas. Tente uma foto mais nítida.'}), 400
        
        # Alinhar tamanhos
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
            'metodo': 'Gemini AI',
            'usando_ia': True
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'geral': {}})
    
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*), COALESCE(AVG(nota), 0) FROM correcoes WHERE prova_id = ?", (prova_id,)).fetchone()
    conn.close()
    
    return jsonify({'geral': {
        'total_corrigidas': row[0] or 0,
        'media_nota': round(row[1], 1) if row[1] else 0
    }})

@app.route('/api/historico', methods=['GET'])
def historico():
    conn = get_db_connection()
    historico = []
    for row in conn.execute("""
        SELECT c.id, a.nome, p.titulo, c.acertos, c.nota, c.data_correcao
        FROM correcoes c JOIN alunos a ON c.aluno_id = a.id JOIN provas p ON c.prova_id = p.id
        ORDER BY c.data_correcao DESC LIMIT 50
    """):
        historico.append({'id': row[0], 'aluno_nome': row[1], 'prova_titulo': row[2], 
                          'acertos': row[3], 'nota': round(row[4], 1), 'data_correcao': row[5]})
    conn.close()
    return jsonify(historico)

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

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'treinada': True, 
        'usando_ia': True, 
        'gemini_disponivel': GEMINI_AVAILABLE,
        'status': '🧠 Gemini AI ativo!' if GEMINI_AVAILABLE else '⚠️ Gemini não configurado',
        'metodo': 'Gemini AI'
    })

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': True})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': '✅ Gemini AI está pronto!'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Gemini AI não precisa de calibração!'})

# ============================================
# GERAR GABARITO - VERSÃO MELHORADA (COM BOLINHAS MAIORES E INSTRUÇÕES)
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
        
        # Buscar dados do banco
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
        escola = cursor.fetchone()
        nome_escola = escola[0] if escola else "ESCOLA"
        
        cursor.execute("SELECT nome FROM turmas WHERE id = ?", (turma_id,))
        turma = cursor.fetchone()
        nome_turma = turma[0] if turma else "TURMA"
        
        cursor.execute("SELECT nome, numero_chamada FROM alunos WHERE id = ?", (aluno_id,))
        aluno = cursor.fetchone()
        nome_aluno = aluno[0] if aluno else "ALUNO"
        numero = str(aluno[1]) if aluno and aluno[1] else ""
        
        cursor.execute("SELECT titulo FROM provas WHERE id = ?", (prova_id,))
        prova = cursor.fetchone()
        nome_prova = prova[0] if prova else "PROVA"
        
        conn.close()
        
        # HTML melhorado com círculos maiores e mais visíveis
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Folha de Respostas - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: #f0f2f5;
            padding: 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            border-radius: 10px;
        }}
        .folha {{
            padding: 30px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 25px;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 15px;
        }}
        .header h2 {{
            color: #4CAF50;
            font-size: 24px;
        }}
        .header p {{
            color: #666;
            font-size: 12px;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 25px;
            background: #f9f9f9;
            padding: 15px;
            border-radius: 8px;
        }}
        .info-item {{
            display: flex;
            gap: 10px;
        }}
        .info-label {{
            font-weight: bold;
            color: #555;
            min-width: 80px;
        }}
        .info-value {{
            color: #333;
            border-bottom: 1px solid #ccc;
            min-width: 150px;
            padding: 0 5px;
        }}
        .instrucoes {{
            background: #FFF3CD;
            padding: 12px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 13px;
            color: #856404;
            text-align: center;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            background: #4CAF50;
            color: white;
            padding: 12px;
            text-align: center;
            font-weight: bold;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        .questao-num {{
            font-weight: bold;
            width: 70px;
            text-align: center;
            font-size: 16px;
        }}
        .opcoes {{
            display: flex;
            gap: 35px;
            justify-content: center;
            flex-wrap: wrap;
        }}
        .opcao {{
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
            cursor: pointer;
            min-width: 55px;
        }}
        .circulo {{
            display: inline-block;
            width: 32px;
            height: 32px;
            border: 3px solid #333;
            border-radius: 50%;
            background: white;
            transition: all 0.2s;
        }}
        .opcao span:last-child {{
            font-weight: bold;
            font-size: 16px;
        }}
        .rodape {{
            margin-top: 30px;
            text-align: center;
            font-size: 11px;
            color: #999;
            border-top: 1px solid #ddd;
            padding-top: 15px;
        }}
        .botoes {{
            text-align: center;
            margin: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        button {{
            background: #4CAF50;
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin: 0 10px;
        }}
        button:hover {{
            background: #45a049;
        }}
        button.secundario {{
            background: #2196F3;
        }}
        button.secundario:hover {{
            background: #0b7dda;
        }}
        @media print {{
            body {{
                background: white;
                padding: 0;
                margin: 0;
            }}
            .container {{
                box-shadow: none;
                margin: 0;
                padding: 0;
            }}
            .botoes {{
                display: none;
            }}
            .info-value {{
                border-bottom: none;
            }}
            .circulo {{
                border: 2px solid #000;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="folha">
            <div class="header">
                <h2>🐝🧠 AdaBee AI - FOLHA DE RESPOSTAS</h2>
                <p>Sistema de Correção Inteligente - Marque APENAS uma bolinha por questão</p>
            </div>
            
            <div class="info-grid">
                <div class="info-item"><span class="info-label">ESCOLA:</span><span class="info-value">{nome_escola}</span></div>
                <div class="info-item"><span class="info-label">TURMA:</span><span class="info-value">{nome_turma}</span></div>
                <div class="info-item"><span class="info-label">ALUNO(A):</span><span class="info-value">{nome_aluno}</span></div>
                <div class="info-item"><span class="info-label">Nº:</span><span class="info-value">{numero}</span></div>
                <div class="info-item"><span class="info-label">PROVA:</span><span class="info-value">{nome_prova}</span></div>
                <div class="info-item"><span class="info-label">DATA:</span><span class="info-value">___/___/______</span></div>
            </div>
            
            <div class="instrucoes">
                <strong>📌 INSTRUÇÕES IMPORTANTES:</strong><br>
                • Preencha COMPLETAMENTE a bolinha da resposta escolhida (deixe toda PRETA)<br>
                • Use caneta PRETA ou AZUL ESCURA<br>
                • Não rasure, não amasse e não dobre a folha<br>
                • Cada questão tem apenas UMA resposta correta (A, B, C, D ou E)
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Questão</th>
                        <th colspan="5">Respostas (A, B, C, D, E)</th>
                    </tr>
                </thead>
                <tbody>"""
        
        for i in range(1, int(qtd_questoes) + 1):
            html += f"""
                    <tr>
                        <td class="questao-num">{i}</td>
                        <td colspan="5" style="text-align:center">
                            <div class="opcoes">
                                <label class="opcao">
                                    <span class="circulo"></span>
                                    <span>A</span>
                                </label>
                                <label class="opcao">
                                    <span class="circulo"></span>
                                    <span>B</span>
                                </label>
                                <label class="opcao">
                                    <span class="circulo"></span>
                                    <span>C</span>
                                </label>
                                <label class="opcao">
                                    <span class="circulo"></span>
                                    <span>D</span>
                                </label>
                                <label class="opcao">
                                    <span class="circulo"></span>
                                    <span>E</span>
                                </label>
                            </div>
                        </td>
                    </tr>"""
        
        html += f"""
                </tbody>
            </table>
            
            <div class="rodape">
                <strong>AdaBee AI - Corretor Inteligente</strong><br>
                Certifique-se de preencher completamente a bolinha escolhida
            </div>
        </div>
        <div class="botoes">
            <button onclick="window.print()">🖨️ IMPRIMIR</button>
            <button class="secundario" onclick="baixarPDF()">💾 SALVAR COMO PDF</button>
        </div>
    </div>
    <script>
        function baixarPDF() {{
            window.print();
        }}
        
        // Permitir marcar apenas uma opção por linha
        document.querySelectorAll('.opcoes').forEach(grupo => {{
            const opcoes = grupo.querySelectorAll('.opcao');
            opcoes.forEach(opcao => {{
                opcao.addEventListener('click', function() {{
                    // Limpar todas da mesma linha
                    opcoes.forEach(opt => {{
                        const circulo = opt.querySelector('.circulo');
                        circulo.style.backgroundColor = 'white';
                        circulo.style.border = '3px solid #333';
                    }});
                    // Marcar esta
                    const circulo = this.querySelector('.circulo');
                    circulo.style.backgroundColor = 'black';
                    circulo.style.border = '3px solid black';
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
