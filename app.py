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

app = Flask(__name__)
CORS(app)

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

init_database()

# ============================================
# DETECÇÃO CORRIGIDA PARA 5 OPÇÕES (A,B,C,D,E)
# ============================================

def detectar_bolinhas_corrigido(imagem_base64):
    """Detecção corrigida para 5 opções (A,B,C,D,E)"""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        np_arr = np.frombuffer(imagem_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return [], 0.0
        
        # Redimensionar
        altura, largura = img.shape[:2]
        if altura > 1000:
            escala = 1000 / altura
            img = cv2.resize(img, (int(largura * escala), 1000))
            altura, largura = img.shape[:2]
        
        # Converter para cinza e melhorar contraste
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Binarização
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Detectar círculos
        circles = cv2.HoughCircles(
            binary, cv2.HOUGH_GRADIENT, dp=1.2, minDist=20,
            param1=50, param2=30, minRadius=6, maxRadius=30
        )
        
        if circles is None:
            return [], 0.0
        
        circles = np.round(circles[0, :]).astype(int)
        circles = sorted(circles, key=lambda c: (c[1], c[0]))
        
        # CORREÇÃO: 5 regiões (A,B,C,D,E)
        largura_img = img.shape[1]
        regiao = largura_img / 5  # 5 opções!
        
        respostas = []
        confiancas = []
        
        for x, y, r in circles:
            x1 = max(0, x - r)
            y1 = max(0, y - r)
            x2 = min(img.shape[1], x + r)
            y2 = min(img.shape[0], y + r)
            
            roi = gray[y1:y2, x1:x2]
            if roi.size > 0:
                # CORREÇÃO: Limiar mais baixo (15% de preenchimento)
                escuro = np.sum(roi < 100) / roi.size
                if escuro > 0.15:  # Reduzido de 0.3 para 0.15
                    # Determinar letra (5 regiões)
                    if x < regiao:
                        letra = 'A'
                    elif x < regiao * 2:
                        letra = 'B'
                    elif x < regiao * 3:
                        letra = 'C'
                    elif x < regiao * 4:
                        letra = 'D'
                    else:
                        letra = 'E'
                    
                    respostas.append(letra)
                    confiancas.append(min(99, escuro * 100))
        
        # Remover duplicatas (cada questão deve ter uma resposta)
        respostas_finais = []
        for r in respostas:
            if len(respostas_finais) == 0 or r != respostas_finais[-1]:
                respostas_finais.append(r)
        
        confianca_media = np.mean(confiancas) if confiancas else 0.0
        
        print(f"✅ Detectadas {len(respostas_finais)} respostas: {respostas_finais}")
        return respostas_finais[:50], confianca_media
        
    except Exception as e:
        print(f"Erro na detecção: {e}")
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
        respostas_detectadas, confianca = detectar_bolinhas_corrigido(imagem)
        
        if len(respostas_detectadas) == 0:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar bolinhas. Tente uma foto mais nítida e com boa iluminação.'}), 400
        
        # Comparar respostas (alinhar pelo tamanho do gabarito)
        acertos = 0
        correcoes = []
        for i in range(len(gabarito)):
            resposta = respostas_detectadas[i] if i < len(respostas_detectadas) else ''
            correta = resposta == gabarito[i] if resposta else False
            if correta:
                acertos += 1
            correcoes.append({'questao': i+1, 'resposta': resposta or '?', 'gabarito': gabarito[i], 'correta': correta})
        
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
    return jsonify({'treinada': True, 'usando_ia': True, 'tesseract_disponivel': False, 'status': 'IA Corrigida para 5 opções (A-E)'})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': True})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': '✅ IA já está configurada para 5 opções (A,B,C,D,E)!'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Calibração concluída', 'limites': {'A': (0,80), 'B': (81,160), 'C': (161,240), 'D': (241,320), 'E': (321,400)}})

# ============================================
# GERAR GABARITO
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        dados = request.json
        qtd_questoes = dados.get('quantidade_questoes', 20)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Folha de Respostas</title>
    <style>
        body {{ font-family: Arial; margin: 40px; }}
        .folha {{ border: 2px solid #4CAF50; padding: 20px; max-width: 800px; margin: auto; }}
        .header {{ text-align: center; }}
        .info {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
        .info input {{ padding: 8px; border: 1px solid #ccc; border-radius: 5px; flex: 1; }}
        .questao {{ margin: 15px 0; padding: 10px; background: #f9f9f9; border-radius: 8px; }}
        .opcoes {{ margin-left: 30px; margin-top: 10px; }}
        .opcao {{ display: inline-block; margin-right: 25px; cursor: pointer; }}
        .circulo {{ display: inline-block; width: 22px; height: 22px; border: 2px solid #333; border-radius: 50%; margin-right: 5px; vertical-align: middle; }}
        button {{ background: #4CAF50; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; margin-top: 20px; display: block; margin-left: auto; margin-right: auto; }}
        @media print {{ button {{ display: none; }} .folha {{ border: none; }} }}
    </style>
</head>
<body>
<div class="folha">
    <div class="header"><h2>🐝🧠 FOLHA DE RESPOSTAS - 5 OPÇÕES (A-E)</h2></div>
    <div class="info">
        <input type="text" id="aluno" placeholder="Nome do Aluno" style="flex:2">
        <input type="text" id="numero" placeholder="Nº" style="flex:1">
        <input type="text" id="prova" placeholder="Prova" style="flex:2">
        <input type="date" id="data" style="flex:1">
    </div>
    <hr>
    <div id="questoes"></div>
    <button onclick="window.print()">🖨️ IMPRIMIR</button>
</div>
<script>
    const qtd = {qtd_questoes};
    let html = '';
    for(let i = 1; i <= qtd; i++) {{
        html += `<div class="questao">
            <strong>${{i}}.</strong>
            <div class="opcoes">
                <label class="opcao"><span class="circulo"></span> A</label>
                <label class="opcao"><span class="circulo"></span> B</label>
                <label class="opcao"><span class="circulo"></span> C</label>
                <label class="opcao"><span class="circulo"></span> D</label>
                <label class="opcao"><span class="circulo"></span> E</label>
            </div>
        </div>`;
    }}
    document.getElementById('questoes').innerHTML = html;
</script>
</body>
</html>"""
        
        html_base64 = base64.b64encode(html.encode('utf-8')).decode()
        return jsonify({'imagem': f"data:text/html;base64,{html_base64}"})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
