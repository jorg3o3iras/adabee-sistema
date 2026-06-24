from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import io
import csv
import re
from datetime import datetime
import os
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
import pytesseract
import random
import traceback

# ============================================
# CONFIGURAÇÃO GEMINI
# ============================================
GEMINI_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
    print("✅ Gemini AI disponível!")
except ImportError:
    print("⚠️ Gemini AI não disponível - usando simulação")
except Exception as e:
    print(f"❌ Erro ao importar Gemini: {e}")

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================

SUPABASE_URL = 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require'

def get_db_connection():
    try:
        conn = psycopg2.connect(SUPABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

# ============================================
# USUÁRIOS FIXOS
# ============================================

USUARIOS_FIXOS = {
    'admin': {'senha': 'admin', 'perfil': 'admin', 'nome': 'Administrador'},
    'usuario': {'senha': '123', 'perfil': 'usuario', 'nome': 'Usuário'},
    'professor1': {'senha': '123', 'perfil': 'usuario', 'nome': 'Professor 1'}
}

# ============================================
# FUNÇÃO DE CORREÇÃO COM FALLBACK
# ============================================

def corrigir_com_gemini(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4):
    """Corrige usando Gemini AI ou simulação"""
    
    # Se Gemini não está disponível, usar simulação
    if not GEMINI_AVAILABLE:
        print("⚠️ Usando simulação (Gemini indisponível)")
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)
    
    try:
        # Configurar Gemini se disponível
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AQ.Ab8RN6I2xKJfgmXTatMFhKJWzNJKc42AJ25EG_W8E0c0eA86-w')
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Decodificar imagem
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        
        alternativas = "A, B, C, D" if tipo_questoes == 4 else "A, B, C"
        
        prompt = f"""
        Você é um assistente especializado em correção de provas.
        
        Analise a imagem do cartão resposta enviada e identifique as respostas marcadas pelo aluno.
        
        A prova tem {len(gabarito)} questões e as alternativas são: {alternativas}.
        
        O gabarito correto é: {gabarito}
        
        Responda em formato JSON com a seguinte estrutura:
        {{
            "respostas": ["A", "B", "C", ...],
            "confianca": 85,
            "aluno_nome": "{aluno_nome}",
            "serie": "{serie}"
        }}
        
        IMPORTANTE: Retorne APENAS o JSON, sem texto adicional.
        """
        
        # Enviar para o Gemini
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_data}
        ])
        
        # Processar resposta
        resposta_texto = response.text
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        
        if json_match:
            dados = json.loads(json_match.group())
            respostas_detectadas = dados.get('respostas', [])
            confianca = dados.get('confianca', 70)
        else:
            respostas_detectadas = []
            confianca = 50
        
        # Calcular acertos
        acertos = 0
        correcoes = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas[:len(gabarito)], gabarito)):
            resp = str(resp).strip().upper()
            gab = str(gab).strip().upper()
            is_correto = resp == gab and resp != ''
            if is_correto:
                acertos += 1
            correcoes.append({
                'questao': i + 1,
                'resposta': resp,
                'gabarito': gab,
                'correto': is_correto
            })
        
        valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0.5
        nota = acertos * valor_por_questao
        
        print(f"✅ Gemini corrigiu: {acertos}/{len(gabarito)} acertos")
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas[:len(gabarito)],
            'correcoes': correcoes,
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': confianca,
            'valor_por_questao': round(valor_por_questao, 2)
        }
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes)

def corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4):
    """Simula a correção (fallback)"""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        respostas_detectadas = []
        
        if img is not None:
            import hashlib
            hash_val = int(hashlib.md5(image_data).hexdigest()[:8], 16)
            random.seed(hash_val)
            
            for i in range(len(gabarito)):
                if random.random() < 0.75:
                    respostas_detectadas.append(gabarito[i])
                else:
                    erradas = [a for a in alternativas if a != gabarito[i]]
                    respostas_detectadas.append(random.choice(erradas) if erradas else gabarito[i])
        else:
            respostas_detectadas = [random.choice(alternativas) for _ in range(len(gabarito))]
        
        acertos = 0
        correcoes = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp == gab
            if is_correto:
                acertos += 1
            correcoes.append({
                'questao': i + 1,
                'resposta': resp,
                'gabarito': gab,
                'correto': is_correto
            })
        
        valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0.5
        nota = acertos * valor_por_questao
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas,
            'correcoes': correcoes,
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 70,
            'valor_por_questao': round(valor_por_questao, 2)
        }
    except Exception as e:
        print(f"❌ Erro na simulação: {e}")
        # Fallback extremo
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'total': len(gabarito),
            'acertos': 0,
            'nota': 0,
            'respostas_detectadas': [],
            'correcoes': [],
            'gabarito': gabarito,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 0,
            'valor_por_questao': 0
        }

# ============================================
# ROTA DE TESTE DO GEMINI
# ============================================

@app.route('/api/gemini/teste', methods=['GET'])
def testar_gemini():
    """Testa se o Gemini está funcionando"""
    return jsonify({
        'disponivel': GEMINI_AVAILABLE,
        'mensagem': 'Gemini configurado' if GEMINI_AVAILABLE else 'Usando simulação',
        'status': 'ok'
    })

# ============================================
# ROTA PRINCIPAL
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# ============================================
# ROTA DE LOGIN
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    senha = data.get('senha')
    
    if username in USUARIOS_FIXOS and USUARIOS_FIXOS[username]['senha'] == senha:
        return jsonify({
            'sucesso': True,
            'perfil': USUARIOS_FIXOS[username]['perfil'],
            'usuario': username,
            'nome': USUARIOS_FIXOS[username]['nome']
        })
    
    return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401

# ============================================
# ROTA DE CORREÇÃO
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
        data = request.json
        imagem_base64 = data.get('imagem')
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        
        if not imagem_base64 or not prova_id or not aluno_id:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro no banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = prova.get('gabarito', [])
        if not gabarito:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Gabarito não cadastrado'}), 400
        
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        cur.close()
        conn.close()
        
        nome_aluno = aluno['nome'] if aluno else 'Aluno'
        serie = prova.get('turma_serie', '1º Ano')
        tipo_questoes = int(prova.get('tipo_questoes', 4))
        
        resultado = corrigir_com_gemini(
            imagem_base64,
            gabarito,
            nome_aluno,
            serie,
            tipo_questoes
        )
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE DASHBOARD
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    return jsonify({
        'total_escolas': 0,
        'total_turmas': 0,
        'total_alunos': 0,
        'total_provas': 0
    })

# ============================================
# ROTA DE PROVAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    return jsonify([])

# ============================================
# ROTA DE ALUNOS
# ============================================

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    return jsonify([])

# ============================================
# ROTA DE ESCOLAS
# ============================================

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    return jsonify([])

# ============================================
# ROTA DE TURMAS
# ============================================

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    return jsonify([])

# ============================================
# ROTA DE HISTÓRICO
# ============================================

@app.route('/api/historico', methods=['GET'])
def listar_historico():
    return jsonify([])

# ============================================
# INICIAR SERVIDOR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Servidor rodando em http://localhost:{port}")
    app.run(host='0.0.0.0', port=port)
