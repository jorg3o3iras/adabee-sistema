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
import re

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
    """Retorna conexão com o MySQL"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"❌ Erro MySQL: {e}")
        return None

def log_sistema(tipo, mensagem, ip=None):
    """Registra logs no sistema"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO logs (tipo, mensagem, ip) VALUES (%s, %s, %s)",
                (tipo, mensagem, ip)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except:
            pass

# ============================================
# RECONHECIMENTO DE BOLINHAS COM OPENCV
# ============================================
def detectar_bolinhas(imagem_base64):
    """
    Detecta bolinhas marcadas no gabarito usando OpenCV
    Retorna lista de respostas encontradas (ex: ['A', 'B', 'C', 'D', 'A'])
    """
    try:
        # Limpar o base64 se necessário
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        # Decodificar imagem
        imagem_bytes = base64.b64decode(imagem_base64)
        np_arr = np.frombuffer(imagem_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return []
        
        # Redimensionar se muito grande (otimização)
        altura, largura = img.shape[:2]
        if altura > 1000:
            escala = 1000 / altura
            nova_largura = int(largura * escala)
            img = cv2.resize(img, (nova_largura, 1000))
        
        # 1. Converter para escala de cinza
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 2. Melhorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cinza = clahe.apply(cinza)
        
        # 3. Aplicar blur para reduzir ruído
        blur = cv2.GaussianBlur(cinza, (5, 5), 0)
        
        # 4. Binarização adaptativa
        binaria = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # 5. Operações morfológicas para limpar
        kernel = np.ones((3, 3), np.uint8)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel)
        
        # 6. Detectar círculos (Hough Circle Transform)
        circles = cv2.HoughCircles(
            binaria,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=25,
            param1=50,
            param2=35,
            minRadius=8,
            maxRadius=45
        )
        
        respostas = []
        
        if circles is not None:
            circles = np.round(circles[0, :]).astype(int)
            # Ordenar por posição Y (questão) e depois X (alternativa)
            circles = sorted(circles, key=lambda c: (c[1], c[0]))
            
            altura_img, largura_img = img.shape[:2]
            regiao = largura_img / 4  # Divide em A, B, C, D
            
            for (x, y, r) in circles:
                if x < regiao:
                    respostas.append('A')
                elif x < regiao * 2:
                    respostas.append('B')
                elif x < regiao * 3:
                    respostas.append('C')
                else:
                    respostas.append('D')
        
        # 7. Fallback: Detecção por contornos
        if len(respostas) == 0:
            contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            bolinhas = []
            for contorno in contornos:
                area = cv2.contourArea(contorno)
                # Filtrar por área (tamanho típico de bolinha)
                if 80 < area < 1500:
                    x, y, w, h = cv2.boundingRect(contorno)
                    # Verificar se é aproximadamente circular
                    raio = (w + h) / 4
                    circularidade = area / (np.pi * raio * raio)
                    if 0.6 < circularidade < 1.4:
                        bolinhas.append((x, y, w, h))
            
            bolinhas = sorted(bolinhas, key=lambda b: (b[1], b[0]))
            
            if bolinhas:
                altura_img, largura_img = img.shape[:2]
                regiao = largura_img / 4
                
                for (x, y, w, h) in bolinhas:
                    centro_x = x + w/2
                    if centro_x < regiao:
                        respostas.append('A')
                    elif centro_x < regiao * 2:
                        respostas.append('B')
                    elif centro_x < regiao * 3:
                        respostas.append('C')
                    else:
                        respostas.append('D')
        
        log_sistema('INFO', f'Detectadas {len(respostas)} respostas via OpenCV')
        return respostas
        
    except Exception as e:
        log_sistema('ERRO', f'Erro na detecção: {str(e)}')
        return []

# ============================================
# ENDPOINTS DA API
# ============================================

@app.route('/')
def index():
    """Página principal"""
    return send_from_directory('.', 'index.html')

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    """Estatísticas do dashboard"""
    conn = get_db_connection()
    if not conn:
        return jsonify({
            'total_escolas': 0,
            'total_turmas': 0,
            'total_alunos': 0,
            'total_provas': 0,
            'total_correcoes': 0,
            'media_geral': 0
        })
    
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
        
        cursor.execute("SELECT COUNT(*) as total, AVG(nota) as media FROM correcoes")
        row = cursor.fetchone()
        stats['total_correcoes'] = row['total'] if row['total'] else 0
        stats['media_geral'] = round(row['media'], 1) if row['media'] else 0
        
        cursor.close()
        conn.close()
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    """Lista todas as escolas"""
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM escolas ORDER BY nome")
        escolas = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(escolas)
    except Exception as e:
        return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    """Cria uma nova escola"""
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Sem conexão com banco'}), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO escolas (nome, endereco, telefone, email) VALUES (%s, %s, %s, %s)",
            (dados.get('nome'), dados.get('endereco'), dados.get('telefone'), dados.get('email'))
        )
        conn.commit()
        escola_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return jsonify({'id': escola_id, 'mensagem': 'Escola criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    """Lista todas as turmas"""
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(dictionary=True)
        if escola_id:
            cursor.execute("SELECT * FROM turmas WHERE escola_id = %s ORDER BY nome", (escola_id,))
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
    """Cria uma nova turma"""
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Sem conexão com banco'}), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO turmas (escola_id, nome, ano, turno) VALUES (%s, %s, %s, %s)",
            (dados.get('escola_id'), dados.get('nome'), dados.get('ano'), dados.get('turno'))
        )
        conn.commit()
        turma_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return jsonify({'id': turma_id, 'mensagem': 'Turma criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    """Lista todos os alunos"""
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(dictionary=True)
        if turma_id:
            cursor.execute("SELECT a.*, t.nome as turma_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id WHERE a.turma_id = %s ORDER BY a.nome", (turma_id,))
        else:
            cursor.execute("SELECT a.*, t.nome as turma_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id ORDER BY a.nome")
        alunos = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(alunos)
    except Exception as e:
        return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    """Cria um novo aluno"""
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Sem conexão com banco'}), 500
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO alunos (turma_id, nome, matricula, data_nascimento, responsavel) VALUES (%s, %s, %s, %s, %s)",
            (dados.get('turma_id'), dados.get('nome'), dados.get('matricula'), dados.get('data_nascimento'), dados.get('responsavel'))
        )
        conn.commit()
        aluno_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return jsonify({'id': aluno_id, 'mensagem': 'Aluno cadastrado com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    """Lista todas as provas"""
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(dictionary=True)
        if turma_id:
            cursor.execute("""
                SELECT p.*, t.nome as turma_nome 
                FROM provas p 
                JOIN turmas t ON p.turma_id = t.id 
                WHERE p.turma_id = %s 
                ORDER BY p.data_prova DESC
            """, (turma_id,))
        else:
            cursor.execute("""
                SELECT p.*, t.nome as turma_nome 
                FROM provas p 
                JOIN turmas t ON p.turma_id = t.id 
                ORDER BY p.data_prova DESC
            """)
        provas = cursor.fetchall()
        
        # Decodificar gabarito JSON
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
    """Cria uma nova prova"""
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Sem conexão com banco'}), 500
    
    try:
        cursor = conn.cursor()
        gabarito_json = json.dumps(dados.get('gabarito', []))
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            dados.get('turma_id'),
            dados.get('titulo'),
            dados.get('descricao'),
            gabarito_json,
            len(dados.get('gabarito', [])),
            dados.get('data_prova'),
            dados.get('valor_nota', 10)
        ))
        conn.commit()
        prova_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        log_sistema('INFO', f'Prova criada: ID {prova_id} - {dados.get("titulo")}')
        return jsonify({'id': prova_id, 'mensagem': 'Prova criada com sucesso'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/corrigir', methods=['POST'])
def corrigir_prova():
    """Corrige uma prova com reconhecimento de bolinhas"""
    try:
        dados = request.json
        imagem = dados.get('imagem')
        prova_id = dados.get('prova_id')
        aluno_id = dados.get('aluno_id')
        
        if not imagem:
            return jsonify({'erro': 'Nenhuma imagem enviada'}), 400
        
        if not prova_id:
            return jsonify({'erro': 'Prova não informada'}), 400
        
        # Buscar gabarito do banco
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Sem conexão com banco'}), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT gabarito, titulo FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            cursor.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova['gabarito']) if prova['gabarito'] else []
        
        if not gabarito:
            cursor.close()
            conn.close()
            return jsonify({'erro': 'Gabarito não encontrado'}), 400
        
        # 🔥 RECONHECIMENTO REAL DAS BOLINHAS
        respostas_encontradas = detectar_bolinhas(imagem)
        
        if len(respostas_encontradas) == 0:
            cursor.close()
            conn.close()
            return jsonify({
                'erro': 'Não foi possível detectar as bolinhas. Tente uma foto com melhor iluminação e contraste.'
            }), 400
        
        # Corrigir a prova
        acertos = 0
        correcoes = []
        
        for i, resposta in enumerate(respostas_encontradas):
            if i < len(gabarito):
                correta = resposta == gabarito[i]
                if correta:
                    acertos += 1
                correcoes.append({
                    'questao': i + 1,
                    'resposta': resposta,
                    'gabarito': gabarito[i],
                    'correta': correta
                })
        
        nota = (acertos / len(gabarito)) * 10
        percentual = (acertos / len(gabarito)) * 100
        
        # Salvar correção no banco
        aluno_nome = None
        if aluno_id:
            try:
                respostas_json = json.dumps(respostas_encontradas)
                correcoes_json = json.dumps(correcoes)
                cursor.execute("""
                    INSERT INTO correcoes (prova_id, aluno_id, respostas, respostas_detectadas, acertos, nota, data_correcao)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (prova_id, aluno_id, respostas_json, correcoes_json, acertos, round(nota, 2), datetime.now()))
                conn.commit()
                
                # Buscar nome do aluno
                cursor.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
                aluno = cursor.fetchone()
                aluno_nome = aluno['nome'] if aluno else 'Aluno'
                
            except Exception as e:
                print(f"Erro ao salvar correção: {e}")
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome or 'Aluno',
            'respostas_detectadas': respostas_encontradas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round(percentual, 1),
            'correcoes': correcoes
        })
        
    except Exception as e:
        log_sistema('ERRO', f'Erro na correção: {str(e)}')
        return jsonify({'erro': f'Erro interno: {str(e)}'}), 500

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    """Retorna estatísticas de uma prova"""
    prova_id = request.args.get('prova_id')
    
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'geral': {'total_corrigidas': 0, 'media_nota': 0, 'maior_nota': 0, 'menor_nota': 0}})
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_corrigidas,
                AVG(nota) as media_nota,
                MAX(nota) as maior_nota,
                MIN(nota) as menor_nota,
                AVG(acertos) as media_acertos,
                STDDEV(nota) as desvio_padrao
            FROM correcoes 
            WHERE prova_id = %s
        """, (prova_id,))
        geral = cursor.fetchone()
        
        # Distribuição de notas
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN nota >= 9 THEN '9-10'
                    WHEN nota >= 7 THEN '7-8.9'
                    WHEN nota >= 5 THEN '5-6.9'
                    WHEN nota >= 3 THEN '3-4.9'
                    ELSE '0-2.9'
                END as faixa,
                COUNT(*) as quantidade,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM correcoes WHERE prova_id = %s), 1) as percentual
            FROM correcoes 
            WHERE prova_id = %s
            GROUP BY faixa
            ORDER BY 
                CASE faixa
                    WHEN '9-10' THEN 1
                    WHEN '7-8.9' THEN 2
                    WHEN '5-6.9' THEN 3
                    WHEN '3-4.9' THEN 4
                    ELSE 5
                END
        """, (prova_id, prova_id))
        distribuicao = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'geral': geral,
            'distribuicao': distribuicao
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/historico', methods=['GET'])
def historico():
    """Retorna histórico de correções"""
    aluno_id = request.args.get('aluno_id')
    prova_id = request.args.get('prova_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT c.*, a.nome as aluno_nome, p.titulo as prova_titulo, p.data_prova
            FROM correcoes c
            JOIN alunos a ON c.aluno_id = a.id
            JOIN provas p ON c.prova_id = p.id
            WHERE 1=1
        """
        params = []
        
        if aluno_id:
            query += " AND c.aluno_id = %s"
            params.append(aluno_id)
        if prova_id:
            query += " AND c.prova_id = %s"
            params.append(prova_id)
        
        query += " ORDER BY c.data_correcao DESC LIMIT 100"
        
        cursor.execute(query, params)
        historico = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(historico)
    except Exception as e:
        return jsonify([])

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    """Exporta resultados para CSV"""
    prova_id = request.args.get('prova_id')
    
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Sem conexão com banco'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                a.nome as aluno,
                a.matricula,
                t.nome as turma,
                c.acertos,
                c.nota,
                c.data_correcao,
                c.respostas
            FROM correcoes c
            JOIN alunos a ON c.aluno_id = a.id
            JOIN turmas t ON a.turma_id = t.id
            WHERE c.prova_id = %s
            ORDER BY c.nota DESC
        """, (prova_id,))
        
        resultados = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Gerar CSV
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Cabeçalho
        writer.writerow(['Aluno', 'Matrícula', 'Turma', 'Acertos', 'Nota', 'Data da Correção', 'Respostas'])
        
        # Dados
        for r in resultados:
            respostas = json.loads(r['respostas']) if r['respostas'] else []
            data_str = r['data_correcao'].strftime('%d/%m/%Y %H:%M') if r['data_correcao'] else ''
            writer.writerow([
                r['aluno'],
                r.get('matricula', ''),
                r.get('turma', ''),
                r['acertos'],
                r['nota'],
                data_str,
                ','.join(respostas)
            ])
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': f'attachment; filename=prova_{prova_id}_resultados_{datetime.now().strftime("%Y%m%d")}.csv'
        }
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)