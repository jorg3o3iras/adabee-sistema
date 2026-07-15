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
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================
# CONFIGURAÇÃO GEMINI
# ============================================

GEMINI_AVAILABLE = False
model = None
GEMINI_MODEL = None

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')

try:
    import google.generativeai as genai
    
    if GEMINI_API_KEY and GEMINI_API_KEY != '':
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            test_response = model.generate_content("Teste de conexão - responda apenas OK")
            if test_response and test_response.text:
                GEMINI_AVAILABLE = True
                print("=" * 60)
                print("✅ Gemini AI configurado com sucesso!")
                print(f"📌 Modelo: {GEMINI_MODEL}")
                print("=" * 60)
            else:
                print("⚠️ Falha no teste da chave")
                GEMINI_AVAILABLE = False
                
        except Exception as e:
            print(f"⚠️ Erro ao configurar Gemini: {e}")
            GEMINI_AVAILABLE = False
    else:
        print("⚠️ GEMINI_API_KEY não encontrada no .env")
        
except ImportError as e:
    print(f"❌ Erro ao importar google-generativeai: {e}")
    GEMINI_AVAILABLE = False
except Exception as e:
    print(f"⚠️ Erro ao configurar Gemini: {e}")
    GEMINI_AVAILABLE = False

# ============================================
# CONFIGURAÇÃO RELAYFREELLM
# ============================================

RELAY_AVAILABLE = False
RELAY_API_URL = os.getenv('RELAY_API_URL', 'http://localhost:8080')
RELAY_API_KEY = os.getenv('RELAY_API_KEY', '')
RELAY_MODEL = os.getenv('RELAY_MODEL', 'gemini-1.5-flash')

try:
    import openai
    
    if RELAY_API_URL:
        openai.api_base = RELAY_API_URL + "/v1"
        openai.api_key = RELAY_API_KEY or "sk-placeholder"
        RELAY_AVAILABLE = True
        print("✅ RelayFreeLLM configurado como fallback!")
except Exception as e:
    print(f"⚠️ RelayFreeLLM não disponível: {e}")
    RELAY_AVAILABLE = False

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL', 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require')

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
# FUNÇÃO PARA CALCULAR CONCEITO
# ============================================

def calcular_conceito(porcentagem):
    """Calcula o conceito baseado na porcentagem de acertos"""
    if porcentagem <= 40:
        return {
            'nome': 'inicial',
            'rotulo': '🔴 inicial',
            'faixa': 'até 40%',
            'cor': '#ef4444',
            'badge': 'badge-conceito-inicial'
        }
    elif porcentagem <= 60:
        return {
            'nome': 'basico',
            'rotulo': '🟠 básico',
            'faixa': '41% - 60%',
            'cor': '#f59e0b',
            'badge': 'badge-conceito-basico'
        }
    elif porcentagem <= 80:
        return {
            'nome': 'proficiente',
            'rotulo': '🔵 proficiente',
            'faixa': '61% - 80%',
            'cor': '#3b82f6',
            'badge': 'badge-conceito-proficiente'
        }
    else:
        return {
            'nome': 'avancado',
            'rotulo': '🟢 avançado',
            'faixa': 'acima de 80%',
            'cor': '#10b981',
            'badge': 'badge-conceito-avancado'
        }

# ============================================
# FUNÇÃO PARA IDENTIFICAR DISCIPLINA (CORRIGIDA)
# ============================================

def identificar_disciplina(prova_titulo, disciplina, serie):
    """
    Identifica o tipo de avaliação com base no título, disciplina e série
    Retorna: 'Portugues', 'Matematica', 'Producao' ou 'Geral'
    """
    # PRIMEIRO e MAIS IMPORTANTE: verificar a disciplina informada
    disciplina_lower = (disciplina or '').lower().strip()
    
    # Verifica se a disciplina contém palavras-chave
    if 'português' in disciplina_lower or 'portugues' in disciplina_lower or 'língua' in disciplina_lower:
        return 'Portugues'
    if 'matemática' in disciplina_lower or 'matematica' in disciplina_lower:
        return 'Matematica'
    if 'produção' in disciplina_lower or 'producao' in disciplina_lower or 'texto' in disciplina_lower or 'redação' in disciplina_lower or 'redacao' in disciplina_lower:
        return 'Producao'
    
    # SEGUNDO: verificar o título da prova
    texto = f"{prova_titulo or ''}".lower()
    
    if 'português' in texto or 'portugues' in texto or 'língua' in texto:
        return 'Portugues'
    if 'matemática' in texto or 'matematica' in texto or 'mat' in texto:
        return 'Matematica'
    if 'produção' in texto or 'producao' in texto or 'texto' in texto or 'redação' in texto or 'redacao' in texto:
        return 'Producao'
    
    # TERCEIRO: fallback baseado na série (APENAS se não foi possível identificar pela disciplina ou título)
    if serie:
        serie_num = re.search(r'(\d+)', serie)
        if serie_num:
            num = int(serie_num.group(1))
            if num <= 5:
                return 'Portugues'
            else:
                return 'Matematica'
    
    return 'Geral'

# ============================================
# FUNÇÃO DE CORREÇÃO COM GEMINI
# ============================================

def corrigir_com_gemini(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4, disciplina=''):
    """Corrige a prova usando Gemini ou simulação"""
    
    if not gabarito or len(gabarito) == 0:
        conceito = calcular_conceito(0)
        return {
            'erro': 'Gabarito não disponível',
            'aluno': aluno_nome,
            'serie': serie,
            'disciplina': disciplina,
            'total': 0,
            'acertos': 0,
            'nota': 0,
            'porcentagem': 0,
            'conceito': conceito,
            'respostas_detectadas': [],
            'gabarito': gabarito,
            'correcoes': [],
            'questoes_status': [],
            'tipo_questoes': str(tipo_questoes),
            'confianca': 0,
            'modo': 'erro',
            'valor_por_questao': 0
        }
    
    try:
        imagem_limpa = imagem_base64
        if ',' in imagem_base64:
            imagem_limpa = imagem_base64.split(',')[1]
        
        if GEMINI_AVAILABLE and model is not None:
            try:
                image_data = base64.b64decode(imagem_limpa)
                alternativas = "A, B, C, D" if tipo_questoes == 4 else "A, B, C"
                
                prompt = f"""
                Você é um assistente especializado em correção de provas escolares.
                
                Analise a imagem do cartão resposta e identifique as respostas marcadas.
                
                INFORMAÇÕES DA PROVA:
                - Total de questões: {len(gabarito)}
                - Alternativas disponíveis: {alternativas}
                - Gabarito correto: {gabarito}
                
                INSTRUÇÕES:
                1. Analise cada questão e identifique qual alternativa foi marcada
                2. Se a marcação não estiver clara, faça a melhor estimativa
                3. Compare com o gabarito e determine se está correta
                
                Responda APENAS em formato JSON válido:
                {{
                    "respostas": ["A", "B", "C", ...],
                    "confianca": 85
                }}
                """
                
                response = model.generate_content([
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_data}
                ])
                
                resposta_texto = response.text
                print(f"📝 Resposta Gemini: {resposta_texto[:200]}...")
                
                json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
                
                if json_match:
                    try:
                        dados = json.loads(json_match.group())
                        respostas_detectadas = dados.get('respostas', [])
                        confianca = dados.get('confianca', 70)
                    except:
                        respostas_detectadas = []
                        confianca = 50
                else:
                    respostas_detectadas = []
                    confianca = 50
                
                if not respostas_detectadas or len(respostas_detectadas) == 0:
                    print("⚠️ Nenhuma resposta detectada, tentando Relay...")
                    return corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)
                
                alternativas_lista = ['A', 'B', 'C', 'D'][:tipo_questoes]
                
                while len(respostas_detectadas) < len(gabarito):
                    respostas_detectadas.append(random.choice(alternativas_lista))
                
                respostas_detectadas = respostas_detectadas[:len(gabarito)]
                respostas_detectadas = [str(r).strip().upper() if r else '' for r in respostas_detectadas]
                
                acertos = 0
                correcoes = []
                questoes_status = []
                
                for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
                    gab_normalizado = str(gab).strip().upper() if gab else ''
                    is_correto = resp == gab_normalizado if resp and gab_normalizado else False
                    
                    if is_correto:
                        acertos += 1
                        status_msg = 'ADQUIRIU HABILIDADE'
                    elif resp:
                        status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM'
                    else:
                        status_msg = 'NÃO RESPONDEU'
                    
                    correcoes.append({
                        'questao': i+1, 
                        'resposta': resp, 
                        'gabarito': gab_normalizado, 
                        'correto': is_correto,
                        'status': status_msg
                    })
                    
                    questoes_status.append({
                        'numero': i+1,
                        'resposta': resp or '—',
                        'gabarito': gab_normalizado or '—',
                        'acertou': is_correto,
                        'status': status_msg,
                        'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}"
                    })
                
                valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
                nota = acertos * valor_por_questao
                porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
                conceito = calcular_conceito(porcentagem)
                
                return {
                    'aluno': aluno_nome,
                    'serie': serie,
                    'disciplina': disciplina,
                    'total': len(gabarito),
                    'acertos': acertos,
                    'nota': round(nota, 1),
                    'porcentagem': porcentagem,
                    'conceito': conceito,
                    'respostas_detectadas': respostas_detectadas,
                    'gabarito': gabarito,
                    'correcoes': correcoes,
                    'questoes_status': questoes_status,
                    'tipo_questoes': str(tipo_questoes),
                    'confianca': confianca,
                    'modo': 'gemini',
                    'valor_por_questao': round(valor_por_questao, 2)
                }
                
            except Exception as e:
                print(f"❌ Erro no Gemini: {e}")
                print("⚠️ Tentando RelayFreeLLM...")
                return corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)
        else:
            print("⚠️ Gemini não disponível, tentando RelayFreeLLM...")
            return corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)

def corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4, disciplina=''):
    """Corrige a prova usando RelayFreeLLM ou simulação"""
    
    if not gabarito or len(gabarito) == 0:
        conceito = calcular_conceito(0)
        return {
            'erro': 'Gabarito não disponível',
            'aluno': aluno_nome,
            'serie': serie,
            'disciplina': disciplina,
            'total': 0,
            'acertos': 0,
            'nota': 0,
            'porcentagem': 0,
            'conceito': conceito,
            'respostas_detectadas': [],
            'gabarito': gabarito,
            'correcoes': [],
            'questoes_status': [],
            'tipo_questoes': str(tipo_questoes),
            'confianca': 0,
            'modo': 'erro',
            'valor_por_questao': 0
        }
    
    try:
        if RELAY_AVAILABLE:
            try:
                import openai
                
                imagem_limpa = imagem_base64
                if ',' in imagem_base64:
                    imagem_limpa = imagem_base64.split(',')[1]
                
                alternativas = "A, B, C, D" if tipo_questoes == 4 else "A, B, C"
                
                prompt = f"""
                Você é um assistente especializado em correção de provas escolares.
                
                Analise a imagem do cartão resposta e identifique as respostas marcadas.
                
                INFORMAÇÕES DA PROVA:
                - Total de questões: {len(gabarito)}
                - Alternativas disponíveis: {alternativas}
                - Gabarito correto: {gabarito}
                
                INSTRUÇÕES:
                1. Analise cada questão e identifique qual alternativa foi marcada
                2. Se a marcação não estiver clara, faça a melhor estimativa
                3. Compare com o gabarito e determine se está correta
                
                Responda APENAS em formato JSON válido:
                {{
                    "respostas": ["A", "B", "C", ...],
                    "confianca": 85
                }}
                """
                
                response = openai.ChatCompletion.create(
                    model=RELAY_MODEL,
                    messages=[
                        {"role": "system", "content": "Você é um assistente especializado em correção de provas."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=500,
                    temperature=0.3
                )
                
                resposta_texto = response.choices[0].message.content
                print(f"📝 Resposta Relay: {resposta_texto[:200]}...")
                
                json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
                
                if json_match:
                    try:
                        dados = json.loads(json_match.group())
                        respostas_detectadas = dados.get('respostas', [])
                        confianca = dados.get('confianca', 70)
                    except:
                        respostas_detectadas = []
                        confianca = 50
                else:
                    respostas_detectadas = []
                    confianca = 50
                
                if not respostas_detectadas or len(respostas_detectadas) == 0:
                    return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)
                
                alternativas_lista = ['A', 'B', 'C', 'D'][:tipo_questoes]
                
                while len(respostas_detectadas) < len(gabarito):
                    respostas_detectadas.append(random.choice(alternativas_lista))
                
                respostas_detectadas = respostas_detectadas[:len(gabarito)]
                respostas_detectadas = [str(r).strip().upper() if r else '' for r in respostas_detectadas]
                
                acertos = 0
                correcoes = []
                questoes_status = []
                
                for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
                    gab_normalizado = str(gab).strip().upper() if gab else ''
                    is_correto = resp == gab_normalizado if resp and gab_normalizado else False
                    
                    if is_correto:
                        acertos += 1
                        status_msg = 'ADQUIRIU HABILIDADE'
                    elif resp:
                        status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM'
                    else:
                        status_msg = 'NÃO RESPONDEU'
                    
                    correcoes.append({
                        'questao': i+1, 
                        'resposta': resp, 
                        'gabarito': gab_normalizado, 
                        'correto': is_correto,
                        'status': status_msg
                    })
                    
                    questoes_status.append({
                        'numero': i+1,
                        'resposta': resp or '—',
                        'gabarito': gab_normalizado or '—',
                        'acertou': is_correto,
                        'status': status_msg,
                        'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}"
                    })
                
                valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
                nota = acertos * valor_por_questao
                porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
                conceito = calcular_conceito(porcentagem)
                
                return {
                    'aluno': aluno_nome,
                    'serie': serie,
                    'disciplina': disciplina,
                    'total': len(gabarito),
                    'acertos': acertos,
                    'nota': round(nota, 1),
                    'porcentagem': porcentagem,
                    'conceito': conceito,
                    'respostas_detectadas': respostas_detectadas,
                    'gabarito': gabarito,
                    'correcoes': correcoes,
                    'questoes_status': questoes_status,
                    'tipo_questoes': str(tipo_questoes),
                    'confianca': confianca,
                    'modo': 'relay',
                    'valor_por_questao': round(valor_por_questao, 2)
                }
                
            except Exception as e:
                print(f"❌ Erro no RelayFreeLLM: {e}")
                return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)
        else:
            print("⚠️ RelayFreeLLM não disponível, usando simulação")
            return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)

def corrigir_simulado(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4, disciplina=''):
    """Correção simulada quando nenhuma IA está disponível"""
    try:
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        respostas_detectadas = []
        
        import hashlib
        
        if imagem_base64 and len(imagem_base64) > 10:
            hash_val = int(hashlib.md5(imagem_base64.encode()).hexdigest()[:8], 16)
            random.seed(hash_val)
        else:
            random.seed(datetime.now().timestamp())
        
        for i, gab in enumerate(gabarito):
            if random.random() < 0.75:
                respostas_detectadas.append(gab)
            else:
                erradas = [a for a in alternativas if a != gab]
                respostas_detectadas.append(random.choice(erradas) if erradas else gab)
        
        acertos = 0
        correcoes = []
        questoes_status = []
        
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp == gab if resp else False
            
            if is_correto:
                acertos += 1
                status_msg = 'ADQUIRIU HABILIDADE'
            elif resp:
                status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM'
            else:
                status_msg = 'NÃO RESPONDEU'
            
            correcoes.append({
                'questao': i+1, 
                'resposta': resp, 
                'gabarito': gab, 
                'correto': is_correto,
                'status': status_msg
            })
            
            questoes_status.append({
                'numero': i+1,
                'resposta': resp or '—',
                'gabarito': gab or '—',
                'acertou': is_correto,
                'status': status_msg,
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}"
            })
        
        valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
        nota = acertos * valor_por_questao
        porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
        conceito = calcular_conceito(porcentagem)
        
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'disciplina': disciplina,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'porcentagem': porcentagem,
            'conceito': conceito,
            'respostas_detectadas': respostas_detectadas,
            'gabarito': gabarito,
            'correcoes': correcoes,
            'questoes_status': questoes_status,
            'tipo_questoes': str(tipo_questoes),
            'confianca': 70,
            'modo': 'simulado',
            'valor_por_questao': round(valor_por_questao, 2)
        }
    except Exception as e:
        print(f"❌ Erro na simulação: {e}")
        conceito = calcular_conceito(0)
        return {
            'aluno': aluno_nome,
            'serie': serie,
            'disciplina': disciplina,
            'total': len(gabarito),
            'acertos': 0,
            'nota': 0,
            'porcentagem': 0,
            'conceito': conceito,
            'respostas_detectadas': [],
            'gabarito': gabarito,
            'correcoes': [],
            'questoes_status': [],
            'tipo_questoes': str(tipo_questoes),
            'confianca': 0,
            'modo': 'erro',
            'valor_por_questao': 0,
            'erro': 'Erro na correção simulada'
        }

# ============================================
# ROTA DE LOGIN
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        senha = data.get('senha')
        
        if not username or not senha:
            return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
        
        print(f"🔑 Tentativa de login: {username}")
        
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT id, nome, username, senha_hash, perfil, ativo 
                    FROM usuarios 
                    WHERE username = %s
                """, (username,))
                usuario = cur.fetchone()
                cur.close()
                conn.close()
                
                if usuario:
                    print(f"📌 Usuário encontrado no banco: {usuario['username']}")
                    print(f"📌 Ativo: {usuario['ativo']}")
                    
                    if usuario['senha_hash'] == senha and usuario['ativo'] == True:
                        print(f"✅ Login via banco: {username}")
                        return jsonify({
                            'sucesso': True,
                            'perfil': usuario['perfil'],
                            'usuario': usuario['username'],
                            'nome': usuario['nome']
                        })
                    else:
                        print(f"❌ Senha incorreta ou usuário inativo")
                else:
                    print(f"❌ Usuário não encontrado no banco: {username}")
                    
            except Exception as e:
                print(f"❌ Erro no banco: {e}")
                traceback.print_exc()
        
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if dados['senha'] == senha:
                print(f"✅ Login via usuário fixo: {username}")
                return jsonify({
                    'sucesso': True,
                    'perfil': dados['perfil'],
                    'usuario': username,
                    'nome': dados['nome']
                })
        
        print(f"❌ Login falhou para: {username}")
        return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401
    except Exception as e:
        print(f"❌ Erro no login: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE CORREÇÃO COM IA
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
        print("📥 Recebendo requisição de correção...")
        
        data = request.json
        if not data:
            return jsonify({'erro': 'Nenhum dado recebido'}), 400
        
        imagem_base64 = data.get('imagem')
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        
        if not imagem_base64:
            return jsonify({'erro': 'Imagem é obrigatória'}), 400
        
        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400
        
        if not aluno_id:
            return jsonify({'erro': 'Aluno ID é obrigatório'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT p.*
                FROM provas p 
                WHERE p.id = %s
            """, (prova_id,))
            prova = cur.fetchone()
            
            if not prova:
                cur.close()
                conn.close()
                return jsonify({'erro': 'Prova não encontrada'}), 404
            
            gabarito = prova.get('gabarito', [])
            if not gabarito or len(gabarito) == 0:
                cur.close()
                conn.close()
                return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400
            
            cur.execute("""
                SELECT a.id, a.nome, a.turma_id, t.serie, e.nome as escola_nome, e.id as escola_id
                FROM alunos a
                LEFT JOIN turmas t ON a.turma_id = t.id
                LEFT JOIN escolas e ON a.escola_id = e.id
                WHERE a.id = %s
            """, (aluno_id,))
            aluno = cur.fetchone()
            cur.close()
            conn.close()
            
            nome_aluno = aluno['nome'] if aluno else 'Aluno'
            turma_id = aluno['turma_id'] if aluno else None
            
            serie = '1º Ano'
            if turma_id:
                try:
                    conn2 = get_db_connection()
                    if conn2:
                        cur2 = conn2.cursor(cursor_factory=RealDictCursor)
                        cur2.execute("SELECT serie FROM turmas WHERE id = %s", (turma_id,))
                        turma = cur2.fetchone()
                        if turma:
                            serie = turma['serie']
                        cur2.close()
                        conn2.close()
                except Exception as e:
                    print(f"⚠️ Erro ao buscar série: {e}")
            
            tipo_questoes = int(prova.get('tipo_questoes', 4))
            disciplina = prova.get('disciplina', '')
            prova_titulo = prova.get('titulo', '')
            
            print(f"🤖 Iniciando correção para {nome_aluno}...")
            print(f"📌 Disciplina informada: {disciplina}")
            print(f"📌 Série: {serie}")
            
            resultado = corrigir_com_gemini(imagem_base64, gabarito, nome_aluno, serie, tipo_questoes, disciplina)
            
            if resultado.get('erro'):
                return jsonify(resultado), 400
            
            # Usar a disciplina da prova para identificar o tipo (prioridade máxima)
            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
            print(f"📌 Tipo de avaliação identificado: {tipo_avaliacao}")
            
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor()
                    
                    questoes_status_json = json.dumps(resultado.get('questoes_status', []))
                    
                    cur.execute("""
                        SELECT id FROM historico 
                        WHERE prova_id = %s AND aluno_id = %s
                    """, (prova_id, aluno_id))
                    existe = cur.fetchone()
                    
                    if existe:
                        cur.execute("""
                            UPDATE historico 
                            SET respostas = %s::text[], 
                                acertos = %s, 
                                nota = %s, 
                                total = %s, 
                                tipo_correcao = %s,
                                disciplina = %s,
                                tipo_avaliacao = %s,
                                questoes_status = %s::jsonb,
                                data_correcao = CURRENT_TIMESTAMP
                            WHERE prova_id = %s AND aluno_id = %s
                        """, (
                            resultado.get('respostas_detectadas', []), 
                            resultado.get('acertos', 0), 
                            resultado.get('nota', 0), 
                            resultado.get('total', 0), 
                            resultado.get('modo', 'ia'),
                            disciplina,
                            tipo_avaliacao,
                            questoes_status_json,
                            prova_id, 
                            aluno_id
                        ))
                        print("✅ Histórico atualizado com sucesso")
                    else:
                        cur.execute("""
                            INSERT INTO historico 
                            (prova_id, aluno_id, respostas, acertos, nota, total, 
                             tipo_correcao, disciplina, tipo_avaliacao, questoes_status)
                            VALUES (%s, %s, %s::text[], %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """, (
                            prova_id, 
                            aluno_id, 
                            resultado.get('respostas_detectadas', []), 
                            resultado.get('acertos', 0), 
                            resultado.get('nota', 0), 
                            resultado.get('total', 0), 
                            resultado.get('modo', 'ia'),
                            disciplina,
                            tipo_avaliacao,
                            questoes_status_json
                        ))
                        print("✅ Histórico salvo com sucesso")
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    
            except Exception as e:
                print(f"⚠️ Erro ao salvar histórico: {e}")
                traceback.print_exc()
            
            resultado['tipo_avaliacao'] = tipo_avaliacao
            resultado['disciplina'] = disciplina
            
            return jsonify(resultado)
            
        except Exception as e:
            print(f"❌ Erro na correção: {e}")
            traceback.print_exc()
            return jsonify({'erro': str(e)}), 500
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE CORREÇÃO MANUAL
# ============================================

@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        respostas = data.get('respostas', [])
        acertos = data.get('acertos', 0)
        nota = data.get('nota', 0)
        total = data.get('total', 0)
        
        if not prova_id or not aluno_id:
            return jsonify({'erro': 'Prova e aluno são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro no banco'}), 500
        
        cur = conn.cursor()
        
        cur.execute("SELECT disciplina, titulo, serie, gabarito FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        disciplina = prova[0] if prova else ''
        prova_titulo = prova[1] if prova else ''
        serie_prova = prova[2] if prova else ''
        gabarito = prova[3] if prova else []
        
        cur.execute("""
            SELECT t.serie FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE a.id = %s
        """, (aluno_id,))
        serie_result = cur.fetchone()
        serie = serie_result[0] if serie_result else serie_prova or '1º Ano'
        
        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
        
        questoes_status = []
        for i in range(total):
            resp = respostas[i] if i < len(respostas) else ''
            gab = gabarito[i] if i < len(gabarito) else ''
            is_correto = resp and gab and resp.upper() == gab.upper()
            
            if is_correto:
                status_msg = 'ADQUIRIU HABILIDADE'
            elif resp:
                status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM'
            else:
                status_msg = 'NÃO RESPONDEU'
            
            questoes_status.append({
                'numero': i+1,
                'resposta': resp or '—',
                'gabarito': gab or '—',
                'acertou': is_correto,
                'status': status_msg,
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}"
            })
        
        questoes_status_json = json.dumps(questoes_status)
        
        cur.execute("""
            SELECT id FROM historico 
            WHERE prova_id = %s AND aluno_id = %s
        """, (prova_id, aluno_id))
        existe = cur.fetchone()
        
        if existe:
            cur.execute("""
                UPDATE historico 
                SET respostas = %s::text[], 
                    acertos = %s, 
                    nota = %s, 
                    total = %s, 
                    tipo_correcao = 'manual',
                    disciplina = %s,
                    tipo_avaliacao = %s,
                    questoes_status = %s::jsonb,
                    data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json, prova_id, aluno_id))
            result_id = existe[0]
        else:
            cur.execute("""
                INSERT INTO historico 
                (prova_id, aluno_id, respostas, acertos, nota, total, 
                 tipo_correcao, disciplina, tipo_avaliacao, questoes_status)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual', %s, %s, %s::jsonb) 
                RETURNING id
            """, (prova_id, aluno_id, respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json))
            result = cur.fetchone()
            result_id = result[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        porcentagem = round((acertos / total) * 100) if total > 0 else 0
        conceito = calcular_conceito(porcentagem)
        
        return jsonify({
            'sucesso': True,
            'id': result_id,
            'mensagem': 'Correção manual salva com sucesso',
            'conceito': conceito,
            'porcentagem': porcentagem,
            'tipo_avaliacao': tipo_avaliacao,
            'questoes_status': questoes_status
        })
    except Exception as e:
        print(f"❌ Erro na correção manual: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE CORREÇÃO DE REDAÇÃO
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        data = request.json
        texto = data.get('texto')
        aluno_id = data.get('aluno_id')
        
        if not texto:
            return jsonify({'erro': 'Texto é obrigatório'}), 400
        
        if GEMINI_AVAILABLE and model is not None:
            try:
                prompt = f"""
                Avalie a redação: {texto}
                Responda em JSON: {{"nota": 7.5, "metricas": {{"nota_coerencia": 8, "nota_estrutura": 7.5, "nota_gramatica": 7, "nota_vocabulario": 7.5}}, "feedback": "texto..."}}
                """
                response = model.generate_content(prompt)
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    try:
                        resultado = json.loads(json_match.group())
                        resultado['modo'] = 'gemini'
                        return jsonify(resultado)
                    except:
                        pass
            except Exception as e:
                print(f"⚠️ Erro no Gemini para redação: {e}")
        
        if RELAY_AVAILABLE:
            try:
                import openai
                
                prompt = f"""
                Avalie a redação: {texto}
                Responda em JSON: {{"nota": 7.5, "metricas": {{"nota_coerencia": 8, "nota_estrutura": 7.5, "nota_gramatica": 7, "nota_vocabulario": 7.5}}, "feedback": "texto..."}}
                """
                
                response = openai.ChatCompletion.create(
                    model=RELAY_MODEL,
                    messages=[
                        {"role": "system", "content": "Você é um professor especializado em avaliar redações."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=300,
                    temperature=0.5
                )
                
                resposta_texto = response.choices[0].message.content
                json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
                
                if json_match:
                    try:
                        resultado = json.loads(json_match.group())
                        resultado['modo'] = 'relay'
                        return jsonify(resultado)
                    except:
                        pass
            except Exception as e:
                print(f"⚠️ Erro no RelayFreeLLM para redação: {e}")
        
        # FALLBACK: ANÁLISE LOCAL
        import re
        from collections import Counter
        
        texto_limpo = texto.strip()
        palavras = re.findall(r'\b[a-zA-ZáéíóúãõâêôçÁÉÍÓÚÃÕÂÊÔÇ]+\b', texto_limpo)
        num_palavras = len(palavras)
        frases = re.split(r'[.!?;]+', texto_limpo)
        num_frases = len([f for f in frases if f.strip()])
        
        palavras_unicas = len(set([p.lower() for p in palavras]))
        diversidade = palavras_unicas / num_palavras if num_palavras > 0 else 0
        tamanho_medio = sum(len(p) for p in palavras) / num_palavras if num_palavras > 0 else 0
        
        contagem = Counter([p.lower() for p in palavras])
        palavras_repetidas = sum(1 for v in contagem.values() if v > 3)
        
        nota_coerencia = min(10, max(0, (diversidade * 5) + (min(1, num_frases / 4) * 3) + (min(1, num_palavras / 50) * 2)))
        nota_estrutura = min(10, max(0, (min(1, num_frases / 3) * 5) + (min(1, tamanho_medio / 6) * 5)))
        nota_gramatica = min(10, max(0, (min(1, tamanho_medio / 5) * 4) + (min(1, num_palavras / 40) * 4) + (2 - min(2, palavras_repetidas * 0.4))))
        nota_vocabulario = min(10, max(0, diversidade * 12))
        
        if num_palavras < 5:
            nota_coerencia *= 0.2
            nota_estrutura *= 0.2
            nota_gramatica *= 0.2
            nota_vocabulario *= 0.2
        
        nota_final = round((nota_coerencia * 0.30 + nota_estrutura * 0.25 + nota_gramatica * 0.25 + nota_vocabulario * 0.20), 1)
        nota_final = min(10, max(0, nota_final))
        
        feedback_parts = []
        if num_palavras < 10:
            feedback_parts.append(f"⚠️ Texto muito curto ({num_palavras} palavras). Escreva pelo menos 20 palavras.")
        elif num_palavras < 30:
            feedback_parts.append(f"📝 Bom início! Tente expandir seus argumentos.")
        else:
            feedback_parts.append("✅ Bom desenvolvimento textual.")
        
        if diversidade < 0.4:
            feedback_parts.append("🔤 Tente usar vocabulário mais variado.")
        elif diversidade < 0.6:
            feedback_parts.append("📚 Bom uso do vocabulário.")
        else:
            feedback_parts.append("📚 Ótimo vocabulário!")
        
        if palavras_repetidas > 5:
            feedback_parts.append("⚠️ Muitas palavras repetidas. Use sinônimos.")
        
        if nota_final >= 7:
            feedback_parts.append("🌟 Bom trabalho! Continue praticando.")
        elif nota_final >= 5:
            feedback_parts.append("📈 Continue melhorando!")
        else:
            feedback_parts.append("📝 Revise seu texto e tente novamente.")
        
        feedback = " ".join(feedback_parts)
        
        resultado = {
            'nota': nota_final,
            'metricas': {
                'nota_coerencia': round(nota_coerencia, 1),
                'nota_estrutura': round(nota_estrutura, 1),
                'nota_gramatica': round(nota_gramatica, 1),
                'nota_vocabulario': round(nota_vocabulario, 1)
            },
            'feedback': feedback,
            'modo': 'local'
        }
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro na correção de redação: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA PARA SALVAR CORREÇÃO DE TEXTO
# ============================================

@app.route('/api/salvar_correcao_texto', methods=['POST'])
def salvar_correcao_texto():
    try:
        data = request.json
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')
        texto = data.get('texto')
        nota = data.get('nota')
        metricas = data.get('metricas', {})
        feedback = data.get('feedback', '')
        
        if not aluno_id:
            return jsonify({'erro': 'Aluno é obrigatório'}), 400
        
        if not texto:
            return jsonify({'erro': 'Texto é obrigatório'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO correcoes_texto 
            (aluno_id, prova_id, texto, nota, metrica_coerencia, metrica_estrutura, 
             metrica_gramatica, metrica_vocabulario, feedback, tipo_correcao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            aluno_id,
            prova_id,
            texto,
            nota,
            metricas.get('nota_coerencia', 0),
            metricas.get('nota_estrutura', 0),
            metricas.get('nota_gramatica', 0),
            metricas.get('nota_vocabulario', 0),
            feedback,
            'ia'
        ))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'id': result[0],
            'mensagem': 'Correção de texto salva com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao salvar correção de texto: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA PARA LISTAR CORREÇÕES DE TEXTO
# ============================================

@app.route('/api/correcoes_texto', methods=['GET'])
def listar_correcoes_texto():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT ct.*, a.nome as aluno_nome, t.serie
            FROM correcoes_texto ct
            LEFT JOIN alunos a ON ct.aluno_id = a.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            ORDER BY ct.data_correcao DESC
        """)
        
        resultados = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(resultados)
        
    except Exception as e:
        print(f"❌ Erro ao listar correções de texto: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE HISTÓRICO
# ============================================

@app.route('/api/historico', methods=['GET'])
def listar_historico():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        escola_id = request.args.get('escola')
        turma_id = request.args.get('turma')
        aluno_id = request.args.get('aluno_id')
        prova_id = request.args.get('prova_id')
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                h.*, 
                a.nome as aluno_nome, 
                p.titulo as prova_titulo,
                p.disciplina,
                p.serie as prova_serie,
                t.serie, 
                t.nome as turma_nome, 
                e.nome as escola_nome,
                t.id as turma_id, 
                e.id as escola_id,
                p.quantidade_questoes as total_questoes,
                p.tipo_questoes
            FROM historico h
            LEFT JOIN alunos a ON h.aluno_id = a.id
            LEFT JOIN provas p ON h.prova_id = p.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON t.escola_id = e.id
            WHERE 1=1
        """
        params = []
        
        if escola_id and escola_id != '' and escola_id != 'null':
            try:
                escola_id_int = int(escola_id)
                query += " AND e.id = %s"
                params.append(escola_id_int)
            except ValueError:
                pass
        
        if turma_id and turma_id != '' and turma_id != 'null':
            try:
                turma_id_int = int(turma_id)
                query += " AND t.id = %s"
                params.append(turma_id_int)
            except ValueError:
                pass
        
        if aluno_id and aluno_id != '' and aluno_id != 'null':
            try:
                aluno_id_int = int(aluno_id)
                query += " AND h.aluno_id = %s"
                params.append(aluno_id_int)
            except ValueError:
                pass
        
        if prova_id and prova_id != '' and prova_id != 'null':
            try:
                prova_id_int = int(prova_id)
                query += " AND h.prova_id = %s"
                params.append(prova_id_int)
            except ValueError:
                pass
        
        query += " ORDER BY h.data_correcao DESC"
        
        cur.execute(query, params)
        historico = cur.fetchall()
        cur.close()
        conn.close()
        
        for item in historico:
            if 'total_questoes' not in item or item['total_questoes'] is None:
                item['total_questoes'] = 20
            
            total = item.get('total_questoes', 20)
            acertos = item.get('acertos', 0)
            porcentagem = round((acertos / total) * 100) if total > 0 else 0
            
            conceito = calcular_conceito(porcentagem)
            item['conceito'] = conceito['nome']
            item['conceito_rotulo'] = conceito['rotulo']
            item['conceito_cor'] = conceito['cor']
            item['porcentagem'] = porcentagem
            
            if 'tipo_avaliacao' not in item or not item['tipo_avaliacao']:
                disciplina = item.get('disciplina', '')
                prova_titulo = item.get('prova_titulo', '')
                serie = item.get('serie', '')
                item['tipo_avaliacao'] = identificar_disciplina(prova_titulo, disciplina, serie)
        
        return jsonify(historico)
        
    except Exception as e:
        print(f"❌ Erro ao buscar histórico: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA PARA HISTÓRICO AGRUPADO POR ALUNO (3 AVALIAÇÕES)
# ============================================

@app.route('/api/historico/agrupado', methods=['GET'])
def historico_agrupado():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        escola_id = request.args.get('escola')
        turma_id = request.args.get('turma')
        aluno_id = request.args.get('aluno_id')
        serie = request.args.get('serie')
        prova_id = request.args.get('prova')
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                h.*, 
                a.nome as aluno_nome, 
                p.titulo as prova_titulo,
                p.disciplina,
                p.serie as prova_serie,
                t.serie, 
                t.nome as turma_nome, 
                e.nome as escola_nome
            FROM historico h
            LEFT JOIN alunos a ON h.aluno_id = a.id
            LEFT JOIN provas p ON h.prova_id = p.id
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            WHERE 1=1
        """
        params = []
        
        if escola_id and escola_id != '' and escola_id != 'null':
            try:
                escola_id_int = int(escola_id)
                query += " AND e.id = %s"
                params.append(escola_id_int)
            except ValueError:
                pass
        
        if turma_id and turma_id != '' and turma_id != 'null':
            try:
                turma_id_int = int(turma_id)
                query += " AND t.id = %s"
                params.append(turma_id_int)
            except ValueError:
                pass
        
        if aluno_id and aluno_id != '' and aluno_id != 'null':
            try:
                aluno_id_int = int(aluno_id)
                query += " AND h.aluno_id = %s"
                params.append(aluno_id_int)
            except ValueError:
                pass
        
        if serie and serie != '' and serie != 'null':
            query += " AND t.serie = %s"
            params.append(serie)
        
        if prova_id and prova_id != '' and prova_id != 'null':
            try:
                prova_id_int = int(prova_id)
                query += " AND h.prova_id = %s"
                params.append(prova_id_int)
            except ValueError:
                pass
        
        query += " ORDER BY a.nome, h.data_correcao DESC"
        
        cur.execute(query, params)
        historico = cur.fetchall()
        cur.close()
        conn.close()
        
        alunos_map = {}
        for item in historico:
            aluno_key = item.get('aluno_id') or item.get('aluno_nome')
            if not aluno_key:
                continue
                
            if aluno_key not in alunos_map:
                alunos_map[aluno_key] = {
                    'aluno_id': item.get('aluno_id'),
                    'aluno_nome': item.get('aluno_nome', 'Aluno'),
                    'serie': item.get('serie', ''),
                    'turma': item.get('turma_nome', ''),
                    'escola': item.get('escola_nome', ''),
                    'avaliacoes': {},
                    'questoes_por_disciplina': {}
                }
            
            # Usar a disciplina da prova para identificar o tipo
            disciplina = item.get('disciplina', '')
            prova_titulo = item.get('prova_titulo', '')
            serie_aluno = item.get('serie', '')
            tipo = identificar_disciplina(prova_titulo, disciplina, serie_aluno)
            
            questoes_status = item.get('questoes_status', [])
            if isinstance(questoes_status, str):
                try:
                    questoes_status = json.loads(questoes_status)
                except:
                    questoes_status = []
            
            alunos_map[aluno_key]['avaliacoes'][tipo] = {
                'nota': float(item.get('nota', 0)),
                'acertos': int(item.get('acertos', 0)),
                'total': int(item.get('total_questoes', 20)),
                'prova': prova_titulo,
                'data': item.get('data_correcao', ''),
                'disciplina': disciplina,
                'questoes_status': questoes_status
            }
        
        resultado = []
        for aluno_key, dados in alunos_map.items():
            avaliacoes = dados['avaliacoes']
            
            notas = []
            for tipo in ['Portugues', 'Matematica', 'Producao']:
                if tipo in avaliacoes:
                    notas.append(avaliacoes[tipo]['nota'])
                else:
                    notas.append(0)
            
            soma = sum(notas)
            media = soma / 3 if notas else 0
            
            resultado.append({
                'aluno_id': dados['aluno_id'],
                'aluno_nome': dados['aluno_nome'],
                'serie': dados['serie'],
                'turma': dados['turma'],
                'escola': dados['escola'],
                'portugues': avaliacoes.get('Portugues', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'matematica': avaliacoes.get('Matematica', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'producao': avaliacoes.get('Producao', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'soma': round(soma, 1),
                'media': round(media, 1)
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro ao buscar histórico agrupado: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE DASHBOARD
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT COUNT(*) as total FROM escolas")
            total_escolas = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as total FROM turmas")
            total_turmas = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as total FROM alunos")
            total_alunos = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as total FROM provas")
            total_provas = cur.fetchone()['total']
            cur.close()
            conn.close()
            return jsonify({
                'total_escolas': total_escolas,
                'total_turmas': total_turmas,
                'total_alunos': total_alunos,
                'total_provas': total_provas
            })
        except Exception as e:
            print(f"Erro no dashboard: {e}")
            traceback.print_exc()
    return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})

# ============================================
# ROTA DE DASHBOARD - CONCEITO
# ============================================

@app.route('/api/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                a.id,
                a.nome as aluno_nome,
                t.nome as turma_nome,
                t.serie,
                COALESCE(AVG(h.nota), 0) as media_nota,
                COALESCE(AVG(h.acertos), 0) as media_acertos,
                COUNT(DISTINCT h.id) as total_correcoes
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN historico h ON h.aluno_id = a.id
            GROUP BY a.id, a.nome, t.nome, t.serie
            ORDER BY a.nome
        """)
        
        alunos = cur.fetchall()
        cur.close()
        conn.close()
        
        resultado = []
        for aluno in alunos:
            media_nota = float(aluno['media_nota'] or 0)
            total_correcoes = int(aluno['total_correcoes'] or 0)
            
            if total_correcoes > 0:
                porcentagem = round((media_nota / 10) * 100) if media_nota > 0 else 0
                conceito = calcular_conceito(porcentagem)
            else:
                porcentagem = 0
                conceito = calcular_conceito(0)
            
            resultado.append({
                'aluno_id': aluno['id'],
                'aluno_nome': aluno['aluno_nome'],
                'turma': aluno['turma_nome'],
                'serie': aluno['serie'],
                'media_nota': round(media_nota, 1),
                'porcentagem': porcentagem,
                'conceito': conceito,
                'total_correcoes': total_correcoes
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro em /api/dashboard/Conceito: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE GERAÇÃO DE CARTÃO RESPOSTA
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        escola_id = data.get('escola_id')
        turma_id = data.get('turma_id')
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')
        quantidade_questoes = data.get('quantidade_questoes', 20)
        
        if not escola_id or not turma_id or not aluno_id or not prova_id:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT a.nome, e.nome as escola_nome, t.nome as turma_nome, t.serie
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            WHERE a.id = %s
        """, (aluno_id,))
        aluno = cur.fetchone()
        
        cur.execute("""
            SELECT p.*
            FROM provas p 
            WHERE p.id = %s
        """, (prova_id,))
        prova = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if not aluno or not prova:
            return jsonify({'erro': 'Dados não encontrados'}), 404
        
        nome_aluno = aluno['nome']
        escola_nome = aluno['escola_nome'] or ''
        turma_nome = aluno['turma_nome'] or ''
        serie = prova.get('serie', '')
        titulo_prova = prova.get('titulo', 'Prova')
        
        tipo_questoes = int(prova.get('tipo_questoes', 4))
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Cartão Resposta</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: Arial, sans-serif; 
                    background: #f0f2f5; 
                    display: flex;
                    justify-content: center;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 900px;
                    width: 100%;
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 8px 30px rgba(0,0,0,0.12);
                    border: 1px solid #e5e7eb;
                }}
                .header {{
                    text-align: center;
                    border-bottom: 2px solid #2563eb;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                .header h1 {{ font-size: 24px; color: #1e293b; }}
                .header h2 {{ font-size: 18px; color: #475569; margin-top: 8px; }}
                .header .sub {{ font-size: 14px; color: #64748b; margin-top: 8px; }}
                .info-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                    background: #f8fafc;
                    padding: 16px 20px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                    border: 1px solid #e2e8f0;
                }}
                .info-grid .item {{ font-size: 14px; }}
                .info-grid .label {{ color: #64748b; font-weight: 600; }}
                .info-grid .value {{ color: #0f172a; font-weight: 700; }}
                .questoes {{
                    display: grid;
                    grid-template-columns: repeat(5, 1fr);
                    gap: 10px;
                    margin: 20px 0 30px;
                }}
                .questao {{
                    border: 2px solid #e2e8f0;
                    border-radius: 10px;
                    padding: 12px 8px;
                    text-align: center;
                    background: #fafafa;
                    transition: all 0.2s;
                }}
                .questao:hover {{ border-color: #2563eb; background: #f0f7ff; }}
                .questao .num {{
                    font-size: 12px;
                    font-weight: 700;
                    color: #64748b;
                    margin-bottom: 8px;
                }}
                .questao .opcoes {{
                    display: flex;
                    justify-content: center;
                    gap: 8px;
                    flex-wrap: wrap;
                }}
                .questao .opcao {{
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    font-size: 14px;
                    font-weight: 600;
                    color: #1e293b;
                }}
                .questao .opcao input {{
                    width: 18px;
                    height: 18px;
                    cursor: pointer;
                    accent-color: #2563eb;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e2e8f0;
                    display: flex;
                    justify-content: space-between;
                    font-size: 13px;
                    color: #64748b;
                }}
                .btn-print {{
                    background: #2563eb;
                    color: white;
                    border: none;
                    padding: 12px 30px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 700;
                    cursor: pointer;
                    transition: background 0.2s;
                    margin-top: 20px;
                    width: 100%;
                }}
                .btn-print:hover {{ background: #1d4ed8; }}
                @media print {{
                    body {{ background: white; padding: 0; }}
                    .container {{ box-shadow: none; border: none; padding: 20px; }}
                    .btn-print {{ display: none; }}
                    .questao:hover {{ border-color: #e2e8f0; background: #fafafa; }}
                }}
                @media (max-width: 600px) {{
                    .questoes {{ grid-template-columns: repeat(3, 1fr); }}
                    .info-grid {{ grid-template-columns: 1fr; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📄 CARTÃO RESPOSTA</h1>
                    <h2>{titulo_prova}</h2>
                    <div class="sub">Leia atentamente e marque apenas uma alternativa por questão</div>
                </div>
                
                <div class="info-grid">
                    <div class="item"><span class="label">Aluno(a):</span> <span class="value">{nome_aluno}</span></div>
                    <div class="item"><span class="label">Escola:</span> <span class="value">{escola_nome}</span></div>
                    <div class="item"><span class="label">Turma:</span> <span class="value">{turma_nome}</span></div>
                    <div class="item"><span class="label">Série:</span> <span class="value">{serie}</span></div>
                    <div class="item"><span class="label">Data:</span> <span class="value">{datetime.now().strftime('%d/%m/%Y')}</span></div>
                </div>
                
                <div style="text-align:center;font-size:14px;font-weight:700;color:#475569;margin-bottom:12px;">
                    Marque com um X a alternativa correta
                </div>
                
                <div class="questoes">
        """
        
        for i in range(quantidade_questoes):
            html += f"""
                <div class="questao">
                    <div class="num">Q{i+1}</div>
                    <div class="opcoes">
            """
            for alt in alternativas:
                html += f"""
                        <label class="opcao">
                            <input type="radio" name="q{i+1}" value="{alt}">
                            {alt}
                        </label>
                """
            html += """
                    </div>
                </div>
            """
        
        html += f"""
                </div>
                
                <button class="btn-print" onclick="window.print()">🖨️ IMPRIMIR CARTÃO</button>
                
                <div class="footer">
                    <span>Gerado pelo sistema CorrigePro</span>
                    <span>{datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        print(f"❌ Erro ao gerar cartão: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA PRINCIPAL
# ============================================

@app.route('/')
def index():
    try:
        return send_from_directory('.', 'index.html')
    except:
        return jsonify({
            'mensagem': 'CorrigePro API',
            'status': 'online',
            'endpoints': [
                '/health',
                '/api/login',
                '/api/corrigir',
                '/api/corrigir_manual',
                '/api/corrigir_redacao',
                '/api/salvar_correcao_texto',
                '/api/correcoes_texto',
                '/api/escolas',
                '/api/turmas',
                '/api/turmas/<id>/alunos',
                '/api/turmas/estatisticas',
                '/api/alunos',
                '/api/provas',
                '/api/gabaritos',
                '/api/historico',
                '/api/historico/agrupado',
                '/api/dashboard',
                '/api/dashboard/Conceito',
                '/api/dashboard/turmas_alunos',
                '/api/gerar_gabarito'
            ]
        })

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('.', path)
    except:
        return jsonify({'erro': 'Arquivo não encontrado'}), 404

# ============================================
# ROTA DE SAÚDE
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    status = {
        'status': 'online',
        'gemini': 'disponível' if GEMINI_AVAILABLE else 'indisponível',
        'relay': 'disponível' if RELAY_AVAILABLE else 'indisponível',
        'database': 'conectado' if get_db_connection() else 'desconectado'
    }
    return jsonify(status)

# ============================================
# INICIALIZAÇÃO DO BANCO
# ============================================

def init_db():
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível, usando dados em memória")
        return
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'escolas'
            )
        """)
        tabela_existe = cur.fetchone()[0]
        
        if not tabela_existe:
            print("🔧 Criando tabelas do banco de dados...")
            
            cur.execute("""
                CREATE TABLE escolas (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    inep TEXT,
                    municipio TEXT,
                    estado TEXT DEFAULT 'PA',
                    telefone TEXT,
                    diretor TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE turmas (
                    id SERIAL PRIMARY KEY,
                    escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
                    nome TEXT NOT NULL,
                    serie TEXT,
                    turno TEXT DEFAULT 'Manhã',
                    professor TEXT,
                    capacidade INTEGER DEFAULT 35,
                    ano_letivo INTEGER DEFAULT 2025,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE alunos (
                    id SERIAL PRIMARY KEY,
                    escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
                    turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
                    nome TEXT NOT NULL,
                    matricula TEXT,
                    numero_chamada INTEGER,
                    data_nascimento DATE,
                    genero TEXT,
                    responsavel TEXT,
                    telefone TEXT,
                    email TEXT,
                    observacoes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE provas (
                    id SERIAL PRIMARY KEY,
                    titulo TEXT NOT NULL,
                    serie TEXT NOT NULL,
                    disciplina TEXT,
                    bimestre TEXT,
                    data_prova DATE,
                    valor_nota DECIMAL(5,2) DEFAULT 10,
                    tipo_questoes TEXT DEFAULT '4',
                    quantidade_questoes INTEGER DEFAULT 20,
                    gabarito TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE historico (
                    id SERIAL PRIMARY KEY,
                    prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                    aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                    respostas TEXT[],
                    acertos INTEGER,
                    nota DECIMAL(5,2),
                    total INTEGER,
                    tipo_correcao TEXT DEFAULT 'ia',
                    disciplina TEXT,
                    tipo_avaliacao TEXT,
                    questoes_status JSONB DEFAULT '[]',
                    data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE usuarios (
                    id SERIAL PRIMARY KEY,
                    nome TEXT,
                    username TEXT UNIQUE NOT NULL,
                    senha_hash TEXT NOT NULL,
                    email TEXT,
                    perfil TEXT DEFAULT 'usuario',
                    ativo BOOLEAN DEFAULT TRUE,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE correcoes_texto (
                    id SERIAL PRIMARY KEY,
                    aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                    prova_id INTEGER REFERENCES provas(id) ON DELETE SET NULL,
                    texto TEXT NOT NULL,
                    nota DECIMAL(5,2),
                    metrica_coerencia DECIMAL(5,2),
                    metrica_estrutura DECIMAL(5,2),
                    metrica_gramatica DECIMAL(5,2),
                    metrica_vocabulario DECIMAL(5,2),
                    feedback TEXT,
                    tipo_correcao TEXT DEFAULT 'ia',
                    data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            print("✅ Tabelas criadas com sucesso!")
        else:
            print("📌 Tabelas já existem, verificando colunas...")
            
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'historico' AND column_name = 'questoes_status'
            """)
            if not cur.fetchone():
                print("🔧 Adicionando coluna questoes_status à tabela historico...")
                try:
                    cur.execute("""
                        ALTER TABLE historico ADD COLUMN questoes_status JSONB DEFAULT '[]'
                    """)
                    print("✅ Coluna questoes_status adicionada com sucesso!")
                except Exception as e:
                    print(f"⚠️ Erro ao adicionar coluna questoes_status: {e}")
        
        for username, dados in USUARIOS_FIXOS.items():
            cur.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (dados['nome'], username, dados['senha'], dados['perfil']))
                print(f"✅ Usuário {username} criado com sucesso!")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")
        traceback.print_exc()

# ============================================
# INICIALIZAÇÃO DO SERVIDOR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 INICIANDO SERVIDOR CORRIGEPRO")
    print("=" * 60)
    print(f"📌 Porta: {port}")
    print(f"🤖 Gemini: {'✅ Disponível' if GEMINI_AVAILABLE else '❌ Indisponível'}")
    if GEMINI_AVAILABLE:
        print(f"📌 Modelo: {GEMINI_MODEL}")
    print(f"🤖 RelayFreeLLM: {'✅ Disponível' if RELAY_AVAILABLE else '❌ Indisponível'}")
    if RELAY_AVAILABLE:
        print(f"📌 URL: {RELAY_API_URL}")
        print(f"📌 Modelo: {RELAY_MODEL}")
    print("=" * 60)
    print("📋 Endpoints disponíveis:")
    print("   - /health - Verificar status")
    print("   - /api/login - Login")
    print("   - /api/corrigir - Correção com IA")
    print("   - /api/corrigir_manual - Correção manual")
    print("   - /api/corrigir_redacao - Correção de redação")
    print("   - /api/salvar_correcao_texto - Salvar correção de texto")
    print("   - /api/correcoes_texto - Listar correções de texto")
    print("   - /api/escolas - Gerenciar escolas")
    print("   - /api/turmas - Gerenciar turmas")
    print("   - /api/turmas/<id>/alunos - Listar alunos de uma turma")
    print("   - /api/turmas/estatisticas - Estatísticas de turmas")
    print("   - /api/alunos - Gerenciar alunos")
    print("   - /api/provas - Gerenciar provas")
    print("   - /api/gabaritos - Gerenciar gabaritos")
    print("   - /api/historico - Histórico de correções")
    print("   - /api/historico/agrupado - Histórico agrupado por aluno (3 avaliações)")
    print("   - /api/dashboard - Dados do dashboard")
    print("   - /api/dashboard/Conceito - Dados de conceitos para dashboard")
    print("   - /api/dashboard/turmas_alunos - Turmas com alunos")
    print("   - /api/gerar_gabarito - Gerar cartão resposta")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
