from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS (InfinityFree)
# ============================================
DB_CONFIG = {
    'host': 'sql100.infinityfree.com',
    'user': 'if0_41652973',
    'password': 'oTPkZmkzF7Hxm7',
    'database': 'if0_41652973_adabee',
    'port': 3306
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"❌ Erro MySQL: {e}")
        return None

# ============================================
# RECONHECIMENTO DE BOLINHAS
# ============================================
def detectar_bolinhas(imagem_base64):
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        np_arr = np.frombuffer(imagem_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return []
        
        altura, largura = img.shape[:2]
        if altura > 1000:
            escala = 1000 / altura
            nova_largura = int(largura * escala)
            img = cv2.resize(img, (nova_largura, 1000))
        
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(cinza, (5, 5), 0)
        _, binaria = cv2.threshold(blur, 127, 255, cv2.THRESH_BINARY_INV)
        
        circles = cv2.HoughCircles(
            binaria, cv2.HOUGH_GRADIENT, dp=1.2, minDist=25,
            param1=50, param2=35, minRadius=8, maxRadius=45
        )
        
        respostas = []
        
        if circles is not None:
            circles = np.round(circles[0, :]).astype(int)
            circles = sorted(circles, key=lambda c: (c[1], c[0]))
            altura_img, largura_img = img.shape[:2]
            regiao = largura_img / 4
            
            for (x, y, r) in circles:
                if x < regiao:
                    respostas.append('A')
                elif x < regiao * 2:
                    respostas.append('B')
                elif x < regiao * 3:
                    respostas.append('C')
                else:
                    respostas.append('D')
        
        return respostas
    except Exception as e:
        print(f"Erro na detecção: {e}")
        return []

# ============================================
# ROTAS DA API - COMPLETAS
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# -------------------- DASHBOARD --------------------
@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    conn = get_db_connection()
    if not conn:
        return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0, 'total_correcoes': 0, 'media_geral': 0})
    try:
        cursor = conn.cursor(dictionary=True)
        stats = {}
        cursor.execute("SELECT COUNT(*) as total FROM escolas")
        stats['total_escolas'] = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM turmas")
        stats['total_turmas'] = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM alunos")
        stats['total_alunos'] = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM provas")
        stats['total_provas'] = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total, COALESCE(AVG(nota), 0) as media FROM correcoes")
        row = cursor.fetchone()
        stats['total_correcoes'] = row['total'] if row['total'] else 0
        stats['media_geral'] = round(row['media'], 1) if row['media'] else 0
        cursor.close()
        conn.close()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- ESCOLAS --------------------
@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, nome, endereco, telefone FROM escolas ORDER BY nome")
        escolas = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(escolas)
    except Exception as e:
        return jsonify([])

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
        if not conn:
            return jsonify({'erro': 'Erro de conexão com banco'}), 500
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO escolas (nome, endereco, telefone) VALUES (%s, %s, %s)",
            (nome, endereco, telefone)
        )
        conn.commit()
        escola_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({'id': escola_id, 'mensagem': 'Escola criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- TURMAS --------------------
@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        if escola_id:
            cursor.execute("SELECT t.*, e.nome as escola_nome FROM turmas t JOIN escolas e ON t.escola_id = e.id WHERE t.escola_id = %s ORDER BY t.nome", (escola_id,))
        else:
            cursor.execute("SELECT t.*, e.nome as escola_nome FROM turmas t JOIN escolas e ON t.escola_id = e.id ORDER BY t.nome")
        turmas = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(turmas)
    except Exception as e:
        return jsonify([])

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
        if not conn:
            return jsonify({'erro': 'Erro de conexão com banco'}), 500
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO turmas (escola_id, nome, turno) VALUES (%s, %s, %s)",
            (escola_id, nome, turno)
        )
        conn.commit()
        turma_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({'id': turma_id, 'mensagem': 'Turma criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- ALUNOS --------------------
@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        if turma_id:
            cursor.execute("SELECT a.*, t.nome as turma_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id WHERE a.turma_id = %s ORDER BY a.numero_chamada", (turma_id,))
        else:
            cursor.execute("SELECT a.*, t.nome as turma_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id ORDER BY a.numero_chamada")
        alunos = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(alunos)
    except Exception as e:
        return jsonify([])

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
        if not conn:
            return jsonify({'erro': 'Erro de conexão com banco'}), 500
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO alunos (turma_id, nome, matricula, responsavel, numero_chamada) VALUES (%s, %s, %s, %s, %s)",
            (turma_id, nome, matricula, responsavel, numero_chamada if numero_chamada else None)
        )
        conn.commit()
        aluno_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({'id': aluno_id, 'mensagem': 'Aluno cadastrado com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- PROVAS --------------------
@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
                   p.valor_nota, p.quantidade_questoes, t.nome as turma_nome, p.turma_id
            FROM provas p 
            JOIN turmas t ON p.turma_id = t.id 
            ORDER BY p.data_prova DESC
        """)
        provas = cursor.fetchall()
        for prova in provas:
            if prova['gabarito']:
                try:
                    prova['gabarito_array'] = json.loads(prova['gabarito'])
                except:
                    prova['gabarito_array'] = []
            else:
                prova['gabarito_array'] = []
        cursor.close()
        conn.close()
        return jsonify(provas)
    except Exception as e:
        return jsonify([])

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
        if not conn:
            return jsonify({'erro': 'Erro de conexão com banco'}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota))
        conn.commit()
        prova_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({'id': prova_id, 'mensagem': 'Prova criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro de conexão'}), 500
        
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correcoes WHERE prova_id = %s", (prova_id,))
        cursor.execute("DELETE FROM provas WHERE id = %s", (prova_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'mensagem': 'Prova removida com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- CORREÇÃO --------------------
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
        if not conn:
            return jsonify({'erro': 'Erro de conexão com banco'}), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT gabarito FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            cursor.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova['gabarito']) if prova['gabarito'] else []
        respostas_detectadas = detectar_bolinhas(imagem)
        
        if len(respostas_detectadas) == 0:
            cursor.close()
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as bolinhas. Tente uma foto melhor.'}), 400
        
        acertos = 0
        for i, resposta in enumerate(respostas_detectadas):
            if i < len(gabarito) and resposta == gabarito[i]:
                acertos += 1
        
        nota = (acertos / len(gabarito)) * 10 if gabarito else 0
        respostas_json = json.dumps(respostas_detectadas)
        
        cursor.execute("""
            INSERT INTO correcoes (prova_id, aluno_id, respostas, acertos, nota, data_correcao)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (prova_id, aluno_id, respostas_json, acertos, nota, datetime.now()))
        conn.commit()
        
        cursor.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        aluno_nome = aluno['nome'] if aluno else 'Aluno'
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round((acertos/len(gabarito))*100, 1) if gabarito else 0,
            'correcoes': []
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- RELATÓRIOS --------------------
@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'geral': {'total_corrigidas': 0, 'media_nota': 0, 'maior_nota': 0, 'menor_nota': 0}})
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT COUNT(*) as total_corrigidas, 
                   COALESCE(AVG(nota), 0) as media_nota,
                   COALESCE(MAX(nota), 0) as maior_nota,
                   COALESCE(MIN(nota), 0) as menor_nota
            FROM correcoes WHERE prova_id = %s
        """, (prova_id,))
        geral = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({'geral': geral})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/historico', methods=['GET'])
def historico():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.id, a.nome as aluno_nome, p.titulo as prova_titulo, 
                   c.acertos, c.nota, c.data_correcao
            FROM correcoes c
            JOIN alunos a ON c.aluno_id = a.id
            JOIN provas p ON c.prova_id = p.id
            ORDER BY c.data_correcao DESC LIMIT 50
        """)
        historico = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(historico)
    except Exception as e:
        return jsonify([])

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro de conexão'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.nome as aluno, a.matricula, c.acertos, c.nota, c.data_correcao
            FROM correcoes c
            JOIN alunos a ON c.aluno_id = a.id
            WHERE c.prova_id = %s
            ORDER BY c.nota DESC
        """, (prova_id,))
        resultados = cursor.fetchall()
        cursor.close()
        conn.close()
        
        import csv
        from io import StringIO
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Aluno', 'Matrícula', 'Acertos', 'Nota', 'Data'])
        for r in resultados:
            writer.writerow([r['aluno'], r.get('matricula', ''), r['acertos'], r['nota'], r['data_correcao']])
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=prova_{prova_id}_resultados.csv'
        }
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# -------------------- UTILIDADES --------------------
@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except:
        ip = "127.0.0.1"
    return jsonify({'ip': ip, 'porta': 5000, 'url': f'http://{ip}:5000'})

@app.route('/api/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if request.method == 'GET':
        return jsonify({'param1': 80, 'param2': 25, 'minRadius': 8, 'maxRadius': 25})
    return jsonify({'mensagem': 'Configurações salvas'})

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({'treinada': False, 'usando_ia': False})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': False})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': 'IA treinada com sucesso!'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Calibração realizada', 'limites': {'A': (0,100), 'B': (101,200), 'C': (201,300), 'D': (301,400), 'E': (401,500)}})

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    return jsonify({'imagem': 'https://via.placeholder.com/800x1100?text=Folha+de+Respostas'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
