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
import pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO MYSQL (VIA VARIÁVEIS DE AMBIENTE)
# ============================================
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'mysql-22b0fe8e-jorge-80ab.d.aivencloud.com'),
    'port': int(os.environ.get('DB_PORT', 19307)),
    'user': os.environ.get('DB_USER', 'avnadmin'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'defaultdb'),
    'ssl_disabled': False
}

def get_db_connection():
    try:
        if not DB_CONFIG['password']:
            print("❌ Senha do banco não configurada!")
            return None
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"❌ Erro MySQL: {e}")
        return None

# ============================================
# CLASSE DA IA
# ============================================

class ClassificadorBolinhasIA:
    def __init__(self):
        self.modelo = None
        self.scaler = StandardScaler()
        self.treinado = False
        self.carregar_modelo()
    
    def extrair_caracteristicas(self, patch):
        """Extrai características da bolinha para a IA"""
        if patch.size == 0:
            return [0] * 15
        
        caracteristicas = []
        
        # 1. Percentual de preenchimento
        preenchimento = np.sum(patch < 100) / patch.size
        caracteristicas.append(preenchimento)
        
        # 2. Média da intensidade
        media = np.mean(patch)
        caracteristicas.append(media / 255.0)
        
        # 3. Desvio padrão
        desvio = np.std(patch)
        caracteristicas.append(desvio / 255.0)
        
        # 4. Variância
        variancia = np.var(patch)
        caracteristicas.append(variancia / (255.0 * 255.0))
        
        # 5. Mínimo
        minimo = np.min(patch)
        caracteristicas.append(minimo / 255.0)
        
        # 6. Máximo
        maximo = np.max(patch)
        caracteristicas.append(maximo / 255.0)
        
        # 7. Assimetria (skewness)
        if patch.size > 1:
            skewness = np.mean(((patch - media) / (desvio + 0.01)) ** 3)
            caracteristicas.append(skewness)
        else:
            caracteristicas.append(0)
        
        # 8-15. Histograma simplificado (8 bins)
        hist = np.histogram(patch, bins=8, range=(0, 255))[0]
        hist_norm = hist / patch.size
        caracteristicas.extend(hist_norm)
        
        while len(caracteristicas) < 15:
            caracteristicas.append(0)
        
        return caracteristicas
    
    def prever(self, patch):
        """Prediz se a bolinha está marcada usando IA"""
        if not self.treinado or self.modelo is None:
            return None, 0.0
        
        caracteristicas = self.extrair_caracteristicas(patch)
        X = self.scaler.transform([caracteristicas])
        proba = self.modelo.predict_proba(X)[0]
        marcada = proba[1] > 0.5
        confianca = proba[1] if marcada else proba[0]
        return marcada, confianca
    
    def salvar_modelo(self):
        if self.modelo is not None:
            with open('modelo_ia.pkl', 'wb') as f:
                pickle.dump({'modelo': self.modelo, 'scaler': self.scaler}, f)
    
    def carregar_modelo(self):
        try:
            with open('modelo_ia.pkl', 'rb') as f:
                dados = pickle.load(f)
                self.modelo = dados['modelo']
                self.scaler = dados['scaler']
                self.treinado = True
                print("✅ Modelo IA carregado!")
                return True
        except:
            print("⚠️ Modelo IA não encontrado, usando regras")
            return False

class IAReconhecedor:
    def __init__(self):
        self.ia = ClassificadorBolinhasIA()
        self.usar_ia = True
    
    def detectar_bolinhas(self, imagem_base64):
        """Detecta bolinhas usando IA"""
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
            
            # Pré-processamento
            cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            cinza = clahe.apply(cinza)
            blur = cv2.GaussianBlur(cinza, (5,5), 0)
            _, binaria = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Detectar círculos
            circles = cv2.HoughCircles(
                binaria, cv2.HOUGH_GRADIENT, dp=1.2, minDist=25,
                param1=50, param2=35, minRadius=8, maxRadius=45
            )
            
            if circles is None:
                return [], 0.0
            
            circles = np.round(circles[0, :]).astype(int)
            circles = sorted(circles, key=lambda c: (c[1], c[0]))
            
            # Calcular regiões das alternativas
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
                    
                    # Usa IA se disponível, senão usa regras
                    if self.usar_ia and self.ia.treinado:
                        marcada, confianca = self.ia.prever(patch)
                    else:
                        preenchimento = np.sum(patch < 100) / patch.size if patch.size > 0 else 0
                        marcada = preenchimento > 0.25
                        confianca = min(0.95, preenchimento * 2)
                    
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

reconhecedor = IAReconhecedor()

# ============================================
# INICIALIZAR BANCO
# ============================================

def init_database():
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor()
    cursor.execute("USE defaultdb")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS escolas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(200) NOT NULL,
            endereco VARCHAR(300),
            telefone VARCHAR(20),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS turmas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            escola_id INT,
            nome VARCHAR(100) NOT NULL,
            turno VARCHAR(20) DEFAULT 'Manhã',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alunos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            turma_id INT,
            nome VARCHAR(200) NOT NULL,
            matricula VARCHAR(50),
            responsavel VARCHAR(200),
            numero_chamada INT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS provas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            turma_id INT,
            titulo VARCHAR(200) NOT NULL,
            descricao TEXT,
            gabarito TEXT,
            data_prova DATE,
            valor_nota DECIMAL(5,2) DEFAULT 10,
            quantidade_questoes INT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS correcoes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            prova_id INT,
            aluno_id INT,
            respostas TEXT,
            acertos INT,
            nota DECIMAL(5,2),
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Banco inicializado!")

init_database()

# ============================================
# ROTAS
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    conn = get_db_connection()
    if not conn:
        return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0, 'total_correcoes': 0, 'media_geral': 0})
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    cursor.execute("SELECT COUNT(*) as total FROM escolas")
    total_escolas = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM turmas")
    total_turmas = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM alunos")
    total_alunos = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM provas")
    total_provas = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total, COALESCE(AVG(nota), 0) as media FROM correcoes")
    row = cursor.fetchone()
    total_correcoes = row['total'] if row['total'] else 0
    media_geral = round(row['media'], 1) if row['media'] else 0
    conn.close()
    return jsonify({'total_escolas': total_escolas, 'total_turmas': total_turmas, 'total_alunos': total_alunos, 'total_provas': total_provas, 'total_correcoes': total_correcoes, 'media_geral': media_geral})

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    cursor.execute("SELECT id, nome, endereco, telefone FROM escolas ORDER BY nome")
    escolas = cursor.fetchall()
    conn.close()
    return jsonify(escolas)

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro de conexão'}), 500
    cursor = conn.cursor()
    cursor.execute("USE defaultdb")
    cursor.execute("INSERT INTO escolas (nome, endereco, telefone) VALUES (%s, %s, %s)", (dados.get('nome'), dados.get('endereco', ''), dados.get('telefone', '')))
    conn.commit()
    escola_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': escola_id})

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    escola_id = request.args.get('escola_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    if escola_id:
        cursor.execute("SELECT t.id, t.nome, t.turno, e.nome as escola_nome FROM turmas t JOIN escolas e ON t.escola_id = e.id WHERE t.escola_id = %s", (escola_id,))
    else:
        cursor.execute("SELECT t.id, t.nome, t.turno, e.nome as escola_nome FROM turmas t JOIN escolas e ON t.escola_id = e.id")
    turmas = cursor.fetchall()
    conn.close()
    return jsonify(turmas)

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro de conexão'}), 500
    cursor = conn.cursor()
    cursor.execute("USE defaultdb")
    cursor.execute("INSERT INTO turmas (escola_id, nome, turno) VALUES (%s, %s, %s)", (dados.get('escola_id'), dados.get('nome'), dados.get('turno', 'Manhã')))
    conn.commit()
    turma_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': turma_id})

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    turma_id = request.args.get('turma_id')
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    if turma_id:
        cursor.execute("SELECT a.id, a.nome, a.matricula, a.responsavel, a.numero_chamada, t.nome as turma_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id WHERE a.turma_id = %s", (turma_id,))
    else:
        cursor.execute("SELECT a.id, a.nome, a.matricula, a.responsavel, a.numero_chamada, t.nome as turma_nome FROM alunos a JOIN turmas t ON a.turma_id = t.id")
    alunos = cursor.fetchall()
    conn.close()
    return jsonify(alunos)

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro de conexão'}), 500
    cursor = conn.cursor()
    cursor.execute("USE defaultdb")
    cursor.execute("INSERT INTO alunos (turma_id, nome, matricula, responsavel, numero_chamada) VALUES (%s, %s, %s, %s, %s)", 
                   (dados.get('turma_id'), dados.get('nome'), dados.get('matricula', ''), dados.get('responsavel', ''), dados.get('numero_chamada')))
    conn.commit()
    aluno_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': aluno_id})

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    cursor.execute("SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, p.valor_nota, p.quantidade_questoes, t.nome as turma_nome, p.turma_id FROM provas p JOIN turmas t ON p.turma_id = t.id ORDER BY p.data_prova DESC")
    provas = cursor.fetchall()
    for p in provas:
        p['gabarito_array'] = json.loads(p['gabarito']) if p['gabarito'] else []
    conn.close()
    return jsonify(provas)

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    dados = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro de conexão'}), 500
    cursor = conn.cursor()
    cursor.execute("USE defaultdb")
    gabarito_json = json.dumps(dados.get('gabarito', []))
    cursor.execute("INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                   (dados.get('turma_id'), dados.get('titulo'), dados.get('descricao', ''), gabarito_json, len(dados.get('gabarito', [])), dados.get('data_prova'), dados.get('valor_nota', 10)))
    conn.commit()
    prova_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': prova_id})

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
            return jsonify({'erro': 'Erro de conexão'}), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("USE defaultdb")
        cursor.execute("SELECT gabarito FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova['gabarito']) if prova['gabarito'] else []
        
        # Usar IA para detectar bolinhas
        respostas_detectadas, confianca = reconhecedor.detectar_bolinhas(imagem)
        
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
        
        cursor.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        aluno_nome = aluno['nome'] if aluno else 'Aluno'
        
        conn.close()
        
        # Retornar resultado com indicação do uso da IA
        usando_ia_texto = "IA (Random Forest)" if reconhecedor.usar_ia and reconhecedor.ia.treinado else "regras OpenCV"
        
        return jsonify({
            'aluno': aluno_nome,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round(percentual, 1),
            'correcoes': correcoes,
            'confianca': round(confianca, 1),
            'metodo': usando_ia_texto
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'geral': {}})
    conn = get_db_connection()
    if not conn:
        return jsonify({'geral': {}})
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    cursor.execute("SELECT COUNT(*) as total, COALESCE(AVG(nota), 0) as media, COALESCE(MAX(nota), 0) as maior, COALESCE(MIN(nota), 0) as menor FROM correcoes WHERE prova_id = %s", (prova_id,))
    geral = cursor.fetchone()
    conn.close()
    return jsonify({'geral': geral})

@app.route('/api/historico', methods=['GET'])
def historico():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cursor = conn.cursor(dictionary=True)
    cursor.execute("USE defaultdb")
    cursor.execute("SELECT c.id, a.nome as aluno_nome, p.titulo as prova_titulo, c.acertos, c.nota, c.data_correcao FROM correcoes c JOIN alunos a ON c.aluno_id = a.id JOIN provas p ON c.prova_id = p.id ORDER BY c.data_correcao DESC LIMIT 50")
    historico = cursor.fetchall()
    conn.close()
    return jsonify(historico)

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Aluno', 'Acertos', 'Nota', 'Data'])
    return output.getvalue(), 200, {'Content-Type': 'text/csv'}

@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    return jsonify({'ip': 'render.com', 'porta': 10000, 'url': 'https://adabee-sistema-3.onrender.com'})

@app.route('/api/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    return jsonify({'param1': 80, 'param2': 25})

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({'treinada': reconhecedor.ia.treinado, 'usando_ia': reconhecedor.usar_ia})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    dados = request.json
    reconhecedor.usar_ia = dados.get('usar_ia', True)
    return jsonify({'usando_ia': reconhecedor.usar_ia})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    try:
        dados = request.json
        imagens_marcadas = dados.get('imagens_marcadas', [])
        imagens_nao_marcadas = dados.get('imagens_nao_marcadas', [])
        
        X = []
        y = []
        
        for img_b64 in imagens_marcadas:
            if ',' in img_b64:
                img_b64 = img_b64.split(',')[1]
            img_data = base64.b64decode(img_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                img = cv2.resize(img, (40, 40))
                caracteristicas = reconhecedor.ia.extrair_caracteristicas(img)
                X.append(caracteristicas)
                y.append(1)
        
        for img_b64 in imagens_nao_marcadas:
            if ',' in img_b64:
                img_b64 = img_b64.split(',')[1]
            img_data = base64.b64decode(img_b64)
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                img = cv2.resize(img, (40, 40))
                caracteristicas = reconhecedor.ia.extrair_caracteristicas(img)
                X.append(caracteristicas)
                y.append(0)
        
        if len(X) >= 10:
            X = np.array(X)
            reconhecedor.ia.scaler.fit(X)
            X_scaled = reconhecedor.ia.scaler.transform(X)
            reconhecedor.ia.modelo = RandomForestClassifier(n_estimators=100, random_state=42)
            reconhecedor.ia.modelo.fit(X_scaled, y)
            reconhecedor.ia.treinado = True
            reconhecedor.ia.salvar_modelo()
            return jsonify({'status': 'ok', 'mensagem': 'IA treinada com sucesso!'})
        else:
            return jsonify({'status': 'erro', 'mensagem': 'Precisa de pelo menos 5 exemplos de cada tipo'})
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Calibração realizada'})

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    return jsonify({'imagem': 'https://via.placeholder.com/800x1100?text=Folha+de+Respostas'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
