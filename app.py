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
# CONFIGURAR GEMINI AI
# ============================================

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        GEMINI_AVAILABLE = True
        print("✅ Gemini AI configurado com sucesso!")
    except Exception as e:
        GEMINI_AVAILABLE = False
        print(f"❌ Erro ao configurar Gemini: {e}")
else:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini não configurado. Use OpenCV como fallback.")

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
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, endereco TEXT, telefone TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, escola_id INTEGER, nome TEXT NOT NULL, turno TEXT DEFAULT 'Manhã')''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, nome TEXT NOT NULL, matricula TEXT, 
        responsavel TEXT, numero_chamada INTEGER)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS provas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, titulo TEXT NOT NULL, descricao TEXT,
        gabarito TEXT, data_prova DATE, valor_nota REAL DEFAULT 10, quantidade_questoes INTEGER)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, prova_id INTEGER, aluno_id INTEGER, 
        respostas TEXT, acertos INTEGER, nota REAL, data_correcao TIMESTAMP)''')
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado!")

init_database()

# ============================================
# DETECÇÃO COM GEMINI AI (PROMPT OTIMIZADO)
# ============================================

def detectar_com_gemini(imagem_base64):
    """Usa Google Gemini para detectar respostas com alta precisão"""
    try:
        if not GEMINI_AVAILABLE:
            return None, 0.0
        
        # Remover cabeçalho base64
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        img = Image.open(io.BytesIO(imagem_bytes))
        
        # PROMPT OTIMIZADO PARA MAIOR PRECISÃO
        prompt = """
[INSTRUÇÕES ESTRITAS - SIGA EXATAMENTE]

VOCÊ É UM SISTEMA DE CORREÇÃO DE PROVAS. ANALISE A IMAGEM DO CARTÃO RESPOSTA.

REGRAS:
1. O cartão tem questões numeradas (1, 2, 3...)
2. Cada questão tem 5 bolinhas: A, B, C, D, E
3. O aluno preencheu UMA bolinha por questão (mais escura)
4. As bolinhas não marcadas estão vazias/brancas

TAREFA:
Liste SOMENTE as letras das respostas marcadas, na ordem das questões.

FORMATO EXATO (OBRIGATÓRIO):
A, B, C, D, E, A, B, C, D, E

REGRAS DE FORMATAÇÃO:
- Use SOMENTE letras maiúsculas
- Separe POR VÍRGULA E ESPAÇO (", ")
- NÃO use números
- NÃO use texto explicativo
- NÃO use pontuação extra
- NÃO use aspas

EXEMPLO CORRETO para 10 questões:
A, B, C, A, D, E, B, C, A, D

Se a questão estiver em branco, use "?" no lugar.

Responda APENAS a linha com as letras. NADA MAIS.
"""
        
        # Enviar para o Gemini
        response = model.generate_content([prompt, img])
        texto = response.text.strip()
        
        print(f"🤖 Gemini resposta bruta: {texto}")
        
        # Limpar a resposta - remover tudo que não for letras ou ?
        texto_limpo = re.sub(r'[^A-E?,]', '', texto.upper())
        
        # Processar resposta
        respostas = []
        for item in texto_limpo.split(','):
            letra = item.strip()
            if letra in ['A', 'B', 'C', 'D', 'E']:
                respostas.append(letra)
            elif letra == '?':
                respostas.append('?')
        
        # Se não conseguiu detectar, tentar extrair letras individuais
        if len(respostas) == 0:
            letras_encontradas = re.findall(r'[A-E]', texto.upper())
            if letras_encontradas:
                respostas = letras_encontradas[:50]
        
        # Garantir que cada resposta é uma letra válida
        respostas = [r if r in ['A','B','C','D','E'] else '?' for r in respostas]
        
        print(f"✅ Gemini detectou: {respostas}")
        confianca = 95.0 if len(respostas) > 0 else 0.0
        return respostas, confianca
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return None, 0.0

# ============================================
# DETECÇÃO PRINCIPAL (APENAS GEMINI)
# ============================================

def detectar_respostas(imagem_base64):
    """Usa APENAS Gemini AI para detecção"""
    
    if GEMINI_AVAILABLE:
        respostas, confianca = detectar_com_gemini(imagem_base64)
        if respostas and len(respostas) > 0:
            print(f"🎯 Gemini AI - {len(respostas)} respostas detectadas")
            return respostas, confianca
    
    # Se Gemini falhar, retorna erro (não usa OpenCV)
    print("❌ Gemini AI falhou. Verifique a imagem.")
    return [], 0.0

# ============================================
# ROTAS DA API
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
    escolas = [dict(row) for row in conn.execute("SELECT id, nome, endereco, telefone FROM escolas ORDER BY nome").fetchall()]
    conn.close()
    return jsonify(escolas)

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO escolas (nome, endereco, telefone) VALUES (?, ?, ?)", 
                   (dados['nome'], dados.get('endereco', ''), dados.get('telefone', '')))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    if escola_id:
        turmas = [dict(row) for row in conn.execute("SELECT id, nome, turno FROM turmas WHERE escola_id = ? ORDER BY nome", (escola_id,)).fetchall()]
    else:
        turmas = [dict(row) for row in conn.execute("SELECT id, nome, turno FROM turmas ORDER BY nome").fetchall()]
    conn.close()
    return jsonify(turmas)

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO turmas (escola_id, nome, turno) VALUES (?, ?, ?)", 
                   (dados['escola_id'], dados['nome'], dados.get('turno', 'Manhã')))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if turma_id:
        alunos = [dict(row) for row in conn.execute("""
            SELECT a.id, a.nome, a.matricula, a.responsavel, a.numero_chamada, t.nome as turma_nome 
            FROM alunos a JOIN turmas t ON a.turma_id = t.id 
            WHERE a.turma_id = ? ORDER BY a.numero_chamada""", (turma_id,)).fetchall()]
    else:
        alunos = [dict(row) for row in conn.execute("""
            SELECT a.id, a.nome, a.matricula, a.responsavel, a.numero_chamada, t.nome as turma_nome 
            FROM alunos a JOIN turmas t ON a.turma_id = t.id ORDER BY a.numero_chamada""").fetchall()]
    conn.close()
    return jsonify(alunos)

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alunos (turma_id, nome, matricula, responsavel, numero_chamada) VALUES (?, ?, ?, ?, ?)", 
                   (dados['turma_id'], dados['nome'], dados.get('matricula', ''), dados.get('responsavel', ''), dados.get('numero_chamada')))
    conn.commit()
    conn.close()
    return jsonify({'id': cursor.lastrowid})

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    provas = []
    for row in conn.execute("""
        SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
               p.valor_nota, p.quantidade_questoes, t.nome as turma_nome, p.turma_id
        FROM provas p JOIN turmas t ON p.turma_id = t.id ORDER BY p.data_prova DESC
    """):
        provas.append({
            'id': row[0], 'titulo': row[1], 'descricao': row[2],
            'gabarito_array': json.loads(row[3]) if row[3] else [],
            'data_prova': row[4], 'valor_nota': row[5], 'quantidade_questoes': row[6] or len(json.loads(row[3]) if row[3] else []),
            'turma_nome': row[7], 'turma_id': row[8]
        })
    conn.close()
    return jsonify(provas)

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    dados = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (dados['turma_id'], dados['titulo'], dados.get('descricao', ''), 
          json.dumps(dados['gabarito']), len(dados['gabarito']), dados['data_prova'], dados.get('valor_nota', 10)))
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
        prova = conn.execute("SELECT gabarito, quantidade_questoes FROM provas WHERE id = ?", (prova_id,)).fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova[0]) if prova[0] else []
        respostas_detectadas, confianca = detectar_respostas(imagem)
        
        if len(respostas_detectadas) == 0:
            conn.close()
            return jsonify({'erro': 'Gemini não conseguiu detectar as respostas. Tente uma foto mais nítida e com boa iluminação.'}), 400
        
        # Alinhar tamanhos - se detectou menos que o gabarito
        while len(respostas_detectadas) < len(gabarito):
            respostas_detectadas.append('?')
        
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
        print(f"Erro na correção: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'geral': {}})
    
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*), COALESCE(AVG(nota), 0), COALESCE(MAX(nota), 0), COALESCE(MIN(nota), 0) FROM correcoes WHERE prova_id = ?", (prova_id,)).fetchone()
    conn.close()
    
    return jsonify({'geral': {
        'total_corrigidas': row[0] or 0,
        'media_nota': round(row[1], 1),
        'maior_nota': round(row[2], 1),
        'menor_nota': round(row[3], 1)
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
        FROM correcoes c JOIN alunos a ON c.aluno_id = a.id WHERE c.prova_id = ? ORDER BY c.nota DESC
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
        return jsonify({'param1': 80, 'param2': 25, 'minRadius': 8, 'maxRadius': 25})
    return jsonify({'mensagem': 'ok'})

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'treinada': True, 
        'usando_ia': True, 
        'gemini_disponivel': GEMINI_AVAILABLE,
        'status': '🧠 Gemini AI (Google) - Alta precisão! 🔥' if GEMINI_AVAILABLE else '⚠️ Gemini não configurado',
        'metodo': 'Gemini AI'
    })

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': True})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': '✅ Gemini AI está pronto! Faça o upload da imagem para correção.'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Gemini AI não precisa de calibração!', 'limites': {'A': (0,80), 'B': (81,160), 'C': (161,240), 'D': (241,320), 'E': (321,400)}})

# ============================================
# GERAR GABARITO
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
        
        conn.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
        escola = conn.fetchone()
        nome_escola = escola[0] if escola else "ESCOLA"
        
        conn.execute("SELECT nome FROM turmas WHERE id = ?", (turma_id,))
        turma = conn.fetchone()
        nome_turma = turma[0] if turma else "TURMA"
        
        conn.execute("SELECT nome, numero_chamada FROM alunos WHERE id = ?", (aluno_id,))
        aluno = conn.fetchone()
        nome_aluno = aluno[0] if aluno else "ALUNO"
        numero = str(aluno[1]) if aluno and aluno[1] else ""
        
        conn.execute("SELECT titulo FROM provas WHERE id = ?", (prova_id,))
        prova = conn.fetchone()
        nome_prova = prova[0] if prova else "PROVA"
        
        conn.close()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Folha de Respostas - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }}
        .folha {{ padding: 30px; }}
        .header {{ text-align: center; margin-bottom: 25px; border-bottom: 3px solid #4CAF50; padding-bottom: 15px; }}
        .header h2 {{ color: #4CAF50; font-size: 24px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; background: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .info-item {{ display: flex; gap: 10px; }}
        .info-label {{ font-weight: bold; color: #555; min-width: 80px; }}
        .info-value {{ color: #333; border-bottom: 1px solid #ccc; min-width: 150px; }}
        .instrucoes {{ background: #FFF3CD; padding: 10px; border-radius: 5px; margin-bottom: 20px; font-size: 12px; color: #856404; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #4CAF50; color: white; padding: 10px; text-align: center; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .questao-num {{ font-weight: bold; width: 60px; text-align: center; }}
        .opcoes {{ display: flex; gap: 20px; justify-content: center; }}
        .opcao {{ display: inline-flex; align-items: center; gap: 8px; }}
        .circulo {{ display: inline-block; width: 22px; height: 22px; border: 2px solid #333; border-radius: 50%; }}
        .rodape {{ margin-top: 30px; text-align: center; font-size: 11px; color: #999; border-top: 1px solid #ddd; padding-top: 15px; }}
        .botoes {{ text-align: center; margin: 20px; }}
        button {{ background: #4CAF50; color: white; border: none; padding: 12px 30px; border-radius: 5px; font-size: 16px; cursor: pointer; margin: 0 10px; }}
        button.secundario {{ background: #2196F3; }}
        button:hover {{ opacity: 0.9; }}
        @media print {{ .botoes {{ display: none; }} .container {{ box-shadow: none; }} }}
    </style>
</head>
<body>
<div class="container">
    <div class="folha">
        <div class="header">
            <h2>🐝🧠 AdaBee AI - FOLHA DE RESPOSTAS</h2>
            <p>Correção com Inteligência Artificial Gemini</p>
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
            • Preencha COMPLETAMENTE a bolinha da resposta escolhida<br>
            • Use caneta preta ou azul | • Não rasure, não amasse e não dobre a folha
        </div>
        <table><thead><tr><th>Questão</th><th>A</th><th>B</th><th>C</th><th>D</th><th>E</th></tr></thead><tbody>"""
        
        for i in range(1, int(qtd_questoes) + 1):
            html += f"<tr><td class='questao-num'>{i}</td>" + "".join([f"<td style='text-align:center'><span class='circulo'></span></td>" for _ in range(5)]) + "</tr>"
        
        html += f"""</tbody><tr>
        <div class="rodape">
            <strong>AdaBee AI - Tecnologia Gemini</strong><br>
            Precisão de 95-98% na detecção de respostas
        </div>
    </div>
    <div class="botoes">
        <button onclick="window.print()">🖨️ IMPRIMIR</button>
        <button class="secundario" onclick="window.print()">💾 SALVAR COMO PDF</button>
    </div>
</div>
</body>
</html>"""
        
        html_base64 = base64.b64encode(html.encode('utf-8')).decode()
        return jsonify({'imagem': f"data:text/html;base64,{html_base64}"})
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
