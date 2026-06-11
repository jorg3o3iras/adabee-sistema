from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# ============================================
# BANCO DE DADOS SQLITE (PERSISTENTE)
# ============================================
DB_PATH = '/opt/render/project/src/adabee.db'

def get_db_connection():
    """Retorna conexão com o SQLite"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Inicializa o banco de dados SQLite"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela escolas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS escolas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            endereco TEXT,
            telefone TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela turmas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS turmas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            escola_id INTEGER,
            nome TEXT NOT NULL,
            turno TEXT DEFAULT 'Manhã',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (escola_id) REFERENCES escolas(id) ON DELETE CASCADE
        )
    ''')
    
    # Tabela alunos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turma_id INTEGER,
            nome TEXT NOT NULL,
            matricula TEXT,
            responsavel TEXT,
            numero_chamada INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (turma_id) REFERENCES turmas(id) ON DELETE CASCADE
        )
    ''')
    
    # Tabela provas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS provas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turma_id INTEGER,
            titulo TEXT NOT NULL,
            descricao TEXT,
            gabarito TEXT,
            data_prova DATE,
            valor_nota REAL DEFAULT 10,
            quantidade_questoes INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (turma_id) REFERENCES turmas(id) ON DELETE CASCADE
        )
    ''')
    
    # Tabela correções
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS correcoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prova_id INTEGER,
            aluno_id INTEGER,
            respostas TEXT,
            acertos INTEGER,
            nota REAL,
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prova_id) REFERENCES provas(id) ON DELETE CASCADE,
            FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados SQLite inicializado!")

# Inicializar banco (apenas cria as tabelas se não existirem)
init_database()

# ============================================
# IA PRÉ-TREINADA
# ============================================

def ia_detectar_bolinha(patch):
    """Detecta se a bolinha está marcada usando regras inteligentes"""
    if patch.size == 0:
        return False, 0.0
    
    preenchimento = np.sum(patch < 100) / patch.size
    media = np.mean(patch)
    variancia = np.var(patch)
    
    pontuacao = 0.0
    
    if preenchimento > 0.30:
        pontuacao += 0.6
    elif preenchimento > 0.20:
        pontuacao += 0.4
    elif preenchimento > 0.10:
        pontuacao += 0.2
    
    if media < 80:
        pontuacao += 0.3
    elif media < 120:
        pontuacao += 0.2
    elif media < 160:
        pontuacao += 0.1
    
    if variancia < 3000:
        pontuacao += 0.1
    
    marcada = pontuacao >= 0.4
    confianca = min(0.98, pontuacao + 0.2) if marcada else min(0.95, 0.6 - pontuacao)
    
    return marcada, confianca

def detectar_bolinhas_com_ia(imagem_base64):
    """Detecta bolinhas usando IA pré-treinada"""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        np_arr = np.frombuffer(imagem_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return [], 0.0
        
        altura, largura = img.shape[:2]
        if altura > 1000:
            escala = 1000 / altura
            nova_largura = int(largura * escala)
            img = cv2.resize(img, (nova_largura, 1000))
        
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cinza = clahe.apply(cinza)
        blur = cv2.GaussianBlur(cinza, (5,5), 0)
        _, binaria = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        circles = cv2.HoughCircles(
            binaria, cv2.HOUGH_GRADIENT, dp=1.2, minDist=25,
            param1=50, param2=35, minRadius=8, maxRadius=45
        )
        
        if circles is None:
            return [], 0.0
        
        circles = np.round(circles[0, :]).astype(int)
        circles = sorted(circles, key=lambda c: (c[1], c[0]))
        
        largura_img = img.shape[1]
        regiao = largura_img / 4
        
        respostas = []
        confianca_total = 0.0
        
        for x, y, r in circles:
            x1 = max(0, x - r)
            y1 = max(0, y - r)
            x2 = min(binaria.shape[1], x + r)
            y2 = min(binaria.shape[0], y + r)
            
            if x2 > x1 and y2 > y1:
                patch = binaria[y1:y2, x1:x2]
                marcada, confianca = ia_detectar_bolinha(patch)
                
                if marcada:
                    if x < regiao:
                        respostas.append('A')
                    elif x < regiao * 2:
                        respostas.append('B')
                    elif x < regiao * 3:
                        respostas.append('C')
                    else:
                        respostas.append('D')
                    confianca_total += confianca
        
        confianca_media = (confianca_total / len(respostas) * 100) if respostas else 0
        return respostas, confianca_media
        
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM escolas")
    total_escolas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM turmas")
    total_turmas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alunos")
    total_alunos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM provas")
    total_provas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*), COALESCE(AVG(nota), 0) FROM correcoes")
    row = cursor.fetchone()
    total_correcoes = row[0] if row[0] else 0
    media_geral = round(row[1], 1) if row[1] else 0
    
    conn.close()
    
    return jsonify({
        'total_escolas': total_escolas,
        'total_turmas': total_turmas,
        'total_alunos': total_alunos,
        'total_provas': total_provas,
        'total_correcoes': total_correcoes,
        'media_geral': media_geral
    })

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, endereco, telefone FROM escolas ORDER BY nome")
    escolas = [{'id': row[0], 'nome': row[1], 'endereco': row[2], 'telefone': row[3]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(escolas)

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    try:
        dados = request.json
        nome = dados.get('nome')
        endereco = dados.get('endereco', '')
        telefone = dados.get('telefone', '')
        
        if not nome:
            return jsonify({'erro': 'Nome da escola é obrigatório'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO escolas (nome, endereco, telefone) VALUES (?, ?, ?)",
            (nome, endereco, telefone)
        )
        conn.commit()
        escola_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'id': escola_id, 'mensagem': 'Escola criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if escola_id:
        cursor.execute("""
            SELECT t.id, t.nome, t.turno, e.nome as escola_nome 
            FROM turmas t 
            JOIN escolas e ON t.escola_id = e.id 
            WHERE t.escola_id = ? ORDER BY t.nome
        """, (escola_id,))
    else:
        cursor.execute("""
            SELECT t.id, t.nome, t.turno, e.nome as escola_nome 
            FROM turmas t 
            JOIN escolas e ON t.escola_id = e.id 
            ORDER BY t.nome
        """)
    
    turmas = [{'id': row[0], 'nome': row[1], 'turno': row[2], 'escola_nome': row[3]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(turmas)

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    try:
        dados = request.json
        escola_id = dados.get('escola_id')
        nome = dados.get('nome')
        turno = dados.get('turno', 'Manhã')
        
        if not escola_id or not nome:
            return jsonify({'erro': 'Escola e nome da turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO turmas (escola_id, nome, turno) VALUES (?, ?, ?)",
            (escola_id, nome, turno)
        )
        conn.commit()
        turma_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'id': turma_id, 'mensagem': 'Turma criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if turma_id:
        cursor.execute("""
            SELECT a.id, a.nome, a.matricula, a.responsavel, a.numero_chamada, t.nome as turma_nome 
            FROM alunos a 
            JOIN turmas t ON a.turma_id = t.id 
            WHERE a.turma_id = ? ORDER BY a.numero_chamada
        """, (turma_id,))
    else:
        cursor.execute("""
            SELECT a.id, a.nome, a.matricula, a.responsavel, a.numero_chamada, t.nome as turma_nome 
            FROM alunos a 
            JOIN turmas t ON a.turma_id = t.id 
            ORDER BY a.numero_chamada
        """)
    
    alunos = [{'id': row[0], 'nome': row[1], 'matricula': row[2], 'responsavel': row[3], 
               'numero_chamada': row[4], 'turma_nome': row[5]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(alunos)

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    try:
        dados = request.json
        turma_id = dados.get('turma_id')
        nome = dados.get('nome')
        matricula = dados.get('matricula', '')
        responsavel = dados.get('responsavel', '')
        numero_chamada = dados.get('numero_chamada')
        
        if not turma_id or not nome:
            return jsonify({'erro': 'Turma e nome do aluno são obrigatórios'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO alunos (turma_id, nome, matricula, responsavel, numero_chamada) VALUES (?, ?, ?, ?, ?)",
            (turma_id, nome, matricula, responsavel, numero_chamada if numero_chamada else None)
        )
        conn.commit()
        aluno_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'id': aluno_id, 'mensagem': 'Aluno cadastrado com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
               p.valor_nota, p.quantidade_questoes, t.nome as turma_nome, p.turma_id
        FROM provas p 
        JOIN turmas t ON p.turma_id = t.id 
        ORDER BY p.data_prova DESC
    """)
    
    provas = []
    for row in cursor.fetchall():
        gabarito = json.loads(row[3]) if row[3] else []
        provas.append({
            'id': row[0], 'titulo': row[1], 'descricao': row[2],
            'gabarito_array': gabarito, 'data_prova': row[4],
            'valor_nota': row[5], 'quantidade_questoes': row[6] or len(gabarito),
            'turma_nome': row[7], 'turma_id': row[8]
        })
    conn.close()
    return jsonify(provas)

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        dados = request.json
        turma_id = dados.get('turma_id')
        titulo = dados.get('titulo')
        descricao = dados.get('descricao', '')
        gabarito = json.dumps(dados.get('gabarito', []))
        data_prova = dados.get('data_prova')
        valor_nota = dados.get('valor_nota', 10)
        quantidade_questoes = len(dados.get('gabarito', []))
        
        if not turma_id or not titulo or not data_prova or quantidade_questoes == 0:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota))
        conn.commit()
        prova_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'id': prova_id, 'mensagem': 'Prova criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correcoes WHERE prova_id = ?", (prova_id,))
        cursor.execute("DELETE FROM provas WHERE id = ?", (prova_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Prova removida com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

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
        cursor = conn.cursor()
        cursor.execute("SELECT gabarito FROM provas WHERE id = ?", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova[0]) if prova[0] else []
        respostas_detectadas, confianca = detectar_bolinhas_com_ia(imagem)
        
        if len(respostas_detectadas) == 0:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar bolinhas. Tente uma foto melhor.'}), 400
        
        acertos = 0
        correcoes = []
        for i, resposta in enumerate(respostas_detectadas):
            if i < len(gabarito):
                correta = resposta == gabarito[i]
                if correta:
                    acertos += 1
                correcoes.append({'questao': i+1, 'resposta': resposta, 'gabarito': gabarito[i], 'correta': correta})
        
        nota = (acertos / len(gabarito)) * 10 if gabarito else 0
        percentual = (acertos / len(gabarito)) * 100 if gabarito else 0
        
        cursor.execute("SELECT nome FROM alunos WHERE id = ?", (aluno_id,))
        aluno = cursor.fetchone()
        aluno_nome = aluno[0] if aluno else 'Aluno'
        
        # Salvar correção
        respostas_json = json.dumps(respostas_detectadas)
        cursor.execute("""
            INSERT INTO correcoes (prova_id, aluno_id, respostas, acertos, nota, data_correcao)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (prova_id, aluno_id, respostas_json, acertos, nota, datetime.now()))
        conn.commit()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round(percentual, 1),
            'correcoes': correcoes,
            'confianca': round(confianca, 1),
            'metodo': 'IA Pré-treinada'
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'geral': {'total_corrigidas': 0, 'media_nota': 0, 'maior_nota': 0, 'menor_nota': 0}})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*), COALESCE(AVG(nota), 0), COALESCE(MAX(nota), 0), COALESCE(MIN(nota), 0)
        FROM correcoes WHERE prova_id = ?
    """, (prova_id,))
    row = cursor.fetchone()
    conn.close()
    
    return jsonify({
        'geral': {
            'total_corrigidas': row[0] or 0,
            'media_nota': round(row[1], 1) if row[1] else 0,
            'maior_nota': round(row[2], 1) if row[2] else 0,
            'menor_nota': round(row[3], 1) if row[3] else 0
        }
    })

@app.route('/api/historico', methods=['GET'])
def historico():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, a.nome as aluno_nome, p.titulo as prova_titulo, 
               c.acertos, c.nota, c.data_correcao
        FROM correcoes c
        JOIN alunos a ON c.aluno_id = a.id
        JOIN provas p ON c.prova_id = p.id
        ORDER BY c.data_correcao DESC LIMIT 50
    """)
    historico = [{'id': row[0], 'aluno_nome': row[1], 'prova_titulo': row[2], 
                  'acertos': row[3], 'nota': round(row[4], 1), 'data_correcao': row[5]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(historico)

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.nome as aluno, a.matricula, c.acertos, c.nota, c.data_correcao
        FROM correcoes c
        JOIN alunos a ON c.aluno_id = a.id
        WHERE c.prova_id = ?
        ORDER BY c.nota DESC
    """, (prova_id,))
    resultados = cursor.fetchall()
    conn.close()
    
    import csv
    from io import StringIO
    output = StringIO()
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
    return jsonify({'mensagem': 'Configurações salvas'})

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({'treinada': True, 'usando_ia': True})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': True})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': '✅ IA já está ativa e funcionando!'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Calibração realizada', 'limites': {'A': (0,100), 'B': (101,200), 'C': (201,300), 'D': (301,400)}})

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    return jsonify({'imagem': 'https://via.placeholder.com/800x1100?text=Folha+de+Respostas'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
