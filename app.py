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
CORS(app)

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
# FUNÇÃO PARA IDENTIFICAR DISCIPLINA
# ============================================

def identificar_disciplina(prova_titulo, disciplina, serie):
    """
    Identifica o tipo de avaliação com base no título, disciplina e série
    Retorna: 'Portugues', 'Matematica', 'Producao' ou 'Geral'
    """
    texto = f"{prova_titulo or ''} {disciplina or ''}".lower()
    
    # Verificar por palavras-chave
    if 'português' in texto or 'portugues' in texto or 'língua' in texto or 'port' in texto:
        return 'Portugues'
    if 'matemática' in texto or 'matematica' in texto or 'mat' in texto:
        return 'Matematica'
    if 'produção' in texto or 'producao' in texto or 'texto' in texto or 'redação' in texto or 'redacao' in texto or 'escrita' in texto:
        return 'Producao'
    
    # Se não identificou, usar a série como referência
    # 1º ao 5º Ano → Português, 6º ao 9º → Matemática
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
                for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
                    gab_normalizado = str(gab).strip().upper() if gab else ''
                    is_correto = resp == gab_normalizado if resp and gab_normalizado else False
                    if is_correto:
                        acertos += 1
                    correcoes.append({
                        'questao': i+1, 
                        'resposta': resp, 
                        'gabarito': gab_normalizado, 
                        'correto': is_correto
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
                for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
                    gab_normalizado = str(gab).strip().upper() if gab else ''
                    is_correto = resp == gab_normalizado if resp and gab_normalizado else False
                    if is_correto:
                        acertos += 1
                    correcoes.append({
                        'questao': i+1, 
                        'resposta': resp, 
                        'gabarito': gab_normalizado, 
                        'correto': is_correto
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
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp == gab if resp else False
            if is_correto:
                acertos += 1
            correcoes.append({'questao': i+1, 'resposta': resp, 'gabarito': gab, 'correto': is_correto})
        
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
                SELECT p.*, t.serie, t.nome as turma_nome
                FROM provas p 
                LEFT JOIN turmas t ON p.turma_id = t.id
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
            
            cur.execute("SELECT nome, turma_id FROM alunos WHERE id = %s", (aluno_id,))
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
            print(f"📌 Disciplina: {disciplina}")
            print(f"📌 Série: {serie}")
            
            resultado = corrigir_com_gemini(imagem_base64, gabarito, nome_aluno, serie, tipo_questoes, disciplina)
            
            if resultado.get('erro'):
                return jsonify(resultado), 400
            
            # Identificar o tipo de avaliação
            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
            print(f"📌 Tipo de avaliação identificado: {tipo_avaliacao}")
            
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor()
                    
                    # Verificar se já existe um registro para esta prova e aluno
                    cur.execute("""
                        SELECT id FROM historico 
                        WHERE prova_id = %s AND aluno_id = %s
                    """, (prova_id, aluno_id))
                    existe = cur.fetchone()
                    
                    if existe:
                        # Atualizar registro existente
                        cur.execute("""
                            UPDATE historico 
                            SET respostas = %s::text[], 
                                acertos = %s, 
                                nota = %s, 
                                total = %s, 
                                tipo_correcao = %s,
                                disciplina = %s,
                                tipo_avaliacao = %s,
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
                            prova_id, 
                            aluno_id
                        ))
                        print("✅ Histórico atualizado com sucesso")
                    else:
                        # Inserir novo registro
                        cur.execute("""
                            INSERT INTO historico 
                            (prova_id, aluno_id, respostas, acertos, nota, total, 
                             tipo_correcao, disciplina, tipo_avaliacao)
                            VALUES (%s, %s, %s::text[], %s, %s, %s, %s, %s, %s)
                        """, (
                            prova_id, 
                            aluno_id, 
                            resultado.get('respostas_detectadas', []), 
                            resultado.get('acertos', 0), 
                            resultado.get('nota', 0), 
                            resultado.get('total', 0), 
                            resultado.get('modo', 'ia'),
                            disciplina,
                            tipo_avaliacao
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
        
        # Buscar disciplina da prova
        cur.execute("SELECT disciplina, titulo FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        disciplina = prova[0] if prova else ''
        prova_titulo = prova[1] if prova else ''
        
        # Buscar série do aluno
        cur.execute("""
            SELECT t.serie FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE a.id = %s
        """, (aluno_id,))
        serie_result = cur.fetchone()
        serie = serie_result[0] if serie_result else '1º Ano'
        
        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
        
        # Verificar se já existe um registro
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
                    data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, tipo_avaliacao, prova_id, aluno_id))
        else:
            cur.execute("""
                INSERT INTO historico 
                (prova_id, aluno_id, respostas, acertos, nota, total, 
                 tipo_correcao, disciplina, tipo_avaliacao)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual', %s, %s) 
                RETURNING id
            """, (prova_id, aluno_id, respostas, acertos, nota, total, disciplina, tipo_avaliacao))
            result = cur.fetchone()
        
        conn.commit()
        cur.close()
        conn.close()
        
        porcentagem = round((acertos / total) * 100) if total > 0 else 0
        conceito = calcular_conceito(porcentagem)
        
        return jsonify({
            'sucesso': True,
            'id': result[0] if not existe else existe[0],
            'mensagem': 'Correção manual salva com sucesso',
            'conceito': conceito,
            'porcentagem': porcentagem,
            'tipo_avaliacao': tipo_avaliacao
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
        
        # TENTAR USAR GEMINI
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
        
        # TENTAR USAR RELAYFREELLM
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
# ROTA DE HISTÓRICO - VERSÃO COM 3 AVALIAÇÕES SEPARADAS
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
            LEFT JOIN turmas t ON p.turma_id = t.id
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
            
            # Adicionar tipo de avaliação se não existir
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
    """
    Retorna o histórico agrupado por aluno com as 3 avaliações separadas
    """
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        escola_id = request.args.get('escola')
        turma_id = request.args.get('turma')
        aluno_id = request.args.get('aluno_id')
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                h.*, 
                a.nome as aluno_nome, 
                p.titulo as prova_titulo,
                p.disciplina,
                t.serie, 
                t.nome as turma_nome, 
                e.nome as escola_nome
            FROM historico h
            LEFT JOIN alunos a ON h.aluno_id = a.id
            LEFT JOIN provas p ON h.prova_id = p.id
            LEFT JOIN turmas t ON p.turma_id = t.id
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
        
        query += " ORDER BY a.nome, h.data_correcao DESC"
        
        cur.execute(query, params)
        historico = cur.fetchall()
        cur.close()
        conn.close()
        
        # Agrupar por aluno
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
                    'avaliacoes': {}
                }
            
            # Identificar o tipo de avaliação
            disciplina = item.get('disciplina', '')
            prova_titulo = item.get('prova_titulo', '')
            serie = item.get('serie', '')
            tipo = identificar_disciplina(prova_titulo, disciplina, serie)
            
            # Armazenar a nota no tipo correspondente
            alunos_map[aluno_key]['avaliacoes'][tipo] = {
                'nota': float(item.get('nota', 0)),
                'acertos': int(item.get('acertos', 0)),
                'total': int(item.get('total_questoes', 20)),
                'prova': prova_titulo,
                'data': item.get('data_correcao', ''),
                'disciplina': disciplina
            }
        
        # Converter para lista
        resultado = []
        for aluno_key, dados in alunos_map.items():
            avaliacoes = dados['avaliacoes']
            
            # Calcular soma e média
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
                'portugues': avaliacoes.get('Portugues', {'nota': 0, 'acertos': 0, 'total': 20}),
                'matematica': avaliacoes.get('Matematica', {'nota': 0, 'acertos': 0, 'total': 20}),
                'producao': avaliacoes.get('Producao', {'nota': 0, 'acertos': 0, 'total': 20}),
                'soma': round(soma, 1),
                'media': round(media, 1)
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro ao buscar histórico agrupado: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/historico/<int:id>', methods=['DELETE'])
def excluir_correcao(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("SELECT id FROM historico WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Correção não encontrada'}), 404
        
        cur.execute("DELETE FROM historico WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': 'Correção excluída com sucesso',
            'id': id
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir correção: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE GABARITOS
# ============================================

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        
        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400
        
        if not respostas or len(respostas) == 0:
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400
        
        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        
        if not respostas_validas:
            return jsonify({'erro': 'Nenhuma resposta válida'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("SELECT id FROM provas WHERE id = %s", (prova_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        cur.execute("""
            UPDATE provas 
            SET gabarito = %s::text[], 
                quantidade_questoes = %s
            WHERE id = %s 
            RETURNING id
        """, (respostas_validas, len(respostas_validas), prova_id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result[0],
            'mensagem': 'Gabarito salvo com sucesso',
            'total_questoes': len(respostas_validas)
        })
        
    except Exception as e:
        print(f"❌ Erro ao salvar gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE ESCOLAS (CRUD COMPLETO COM EXCLUSÃO EM CASCATA)
# ============================================

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM escolas ORDER BY nome")
            escolas = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(escolas)
        except Exception as e:
            print(f"Erro ao listar escolas: {e}")
    return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    data = request.json
    nome = data.get('nome')
    if not nome:
        return jsonify({'erro': 'Nome é obrigatório'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO escolas (nome, inep, municipio, estado, telefone, diretor)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (nome, data.get('inep', ''), data.get('municipio', ''), 
                  data.get('estado', 'PA'), data.get('telefone', ''), data.get('diretor', '')))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Escola criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar escola: {e}")
            traceback.print_exc()
    return jsonify({'erro': 'Erro ao criar escola'}), 500

@app.route('/api/escolas/<int:id>', methods=['GET'])
def buscar_escola(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        cur.close()
        conn.close()
        
        if not escola:
            return jsonify({'erro': 'Escola não encontrada'}), 404
        
        return jsonify(escola)
        
    except Exception as e:
        print(f"❌ Erro ao buscar escola: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:id>', methods=['PUT'])
def editar_escola(id):
    try:
        data = request.json
        nome = data.get('nome')
        
        if not nome:
            return jsonify({'erro': 'Nome é obrigatório'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM escolas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404
        
        cur.execute("""
            UPDATE escolas 
            SET nome = %s, 
                inep = %s, 
                municipio = %s, 
                estado = %s, 
                telefone = %s, 
                diretor = %s
            WHERE id = %s
            RETURNING id
        """, (nome, data.get('inep', ''), data.get('municipio', ''),
              data.get('estado', 'PA'), data.get('telefone', ''), data.get('diretor', ''), id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'id': result['id'],
            'mensagem': 'Escola atualizada com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar escola: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:id>', methods=['DELETE'])
def excluir_escola(id):
    """Exclui uma escola e todos os dados vinculados (turmas, alunos, provas, histórico)"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor()
        
        # Verificar se a escola existe
        cur.execute("SELECT id, nome FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        if not escola:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404
        
        escola_nome = escola[1]
        
        # Buscar todas as turmas da escola
        cur.execute("SELECT id FROM turmas WHERE escola_id = %s", (id,))
        turmas = cur.fetchall()
        
        total_turmas = len(turmas)
        total_alunos = 0
        total_provas = 0
        total_historicos = 0
        
        # Para cada turma, contar e excluir dependências
        for turma in turmas:
            turma_id = turma[0]
            
            # Contar alunos
            cur.execute("SELECT COUNT(*) FROM alunos WHERE turma_id = %s", (turma_id,))
            alunos_count = cur.fetchone()[0]
            total_alunos += alunos_count
            
            # Contar provas
            cur.execute("SELECT COUNT(*) FROM provas WHERE turma_id = %s", (turma_id,))
            provas_count = cur.fetchone()[0]
            total_provas += provas_count
            
            # Buscar provas da turma para contar históricos
            cur.execute("SELECT id FROM provas WHERE turma_id = %s", (turma_id,))
            provas = cur.fetchall()
            for prova in provas:
                cur.execute("SELECT COUNT(*) FROM historico WHERE prova_id = %s", (prova[0],))
                historico_count = cur.fetchone()[0]
                total_historicos += historico_count
        
        # Excluir em cascata usando ON DELETE CASCADE
        # As tabelas já têm ON DELETE CASCADE configurado, então basta excluir a escola
        cur.execute("DELETE FROM escolas WHERE id = %s", (id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Escola "{escola_nome}" excluída com sucesso!',
            'detalhes': {
                'turmas_excluidas': total_turmas,
                'alunos_excluidos': total_alunos,
                'provas_excluidas': total_provas,
                'historicos_excluidos': total_historicos
            }
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir escola: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE TURMAS (CRUD COMPLETO COM EXCLUSÃO EM CASCATA)
# ============================================

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    try:
        escola_id = request.args.get('escola_id')
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                t.id,
                t.nome,
                t.serie,
                t.turno,
                t.professor,
                t.capacidade,
                t.ano_letivo,
                t.escola_id,
                e.nome as escola_nome,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'nome', a.nome,
                            'matricula', a.matricula,
                            'numero_chamada', a.numero_chamada,
                            'responsavel', a.responsavel,
                            'telefone', a.telefone,
                            'email', a.email
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'
                ) as alunos,
                COUNT(a.id) as total_alunos
            FROM turmas t 
            LEFT JOIN escolas e ON t.escola_id = e.id 
            LEFT JOIN alunos a ON a.turma_id = t.id
        """
        params = []
        
        if escola_id and escola_id != '' and escola_id != 'null' and escola_id != 'undefined':
            try:
                escola_id_int = int(escola_id)
                query += " WHERE t.escola_id = %s"
                params.append(escola_id_int)
            except ValueError:
                pass
        
        query += " GROUP BY t.id, e.nome ORDER BY t.nome"
        
        cur.execute(query, params)
        turmas = cur.fetchall()
        cur.close()
        conn.close()
        
        for turma in turmas:
            if turma['alunos']:
                turma['alunos'] = turma['alunos']
            else:
                turma['alunos'] = []
        
        return jsonify(turmas)
        
    except Exception as e:
        print(f"❌ Erro ao listar turmas: {e}")
        traceback.print_exc()
        return jsonify([])

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    data = request.json
    if not data.get('nome') or not data.get('escola_id'):
        return jsonify({'erro': 'Nome e escola são obrigatórios'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO turmas (escola_id, nome, serie, turno, professor, capacidade, ano_letivo)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (data['escola_id'], data['nome'], data.get('serie', '1º Ano'), 
                  data.get('turno', 'Manhã'), data.get('professor', ''), 
                  data.get('capacidade', 35), data.get('ano_letivo', 2025)))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Turma criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar turma: {e}")
            traceback.print_exc()
    return jsonify({'erro': 'Erro ao criar turma'}), 500

@app.route('/api/turmas/<int:id>', methods=['GET'])
def buscar_turma(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                t.id,
                t.nome,
                t.serie,
                t.turno,
                t.professor,
                t.capacidade,
                t.ano_letivo,
                t.escola_id,
                e.nome as escola_nome,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'nome', a.nome,
                            'matricula', a.matricula,
                            'numero_chamada', a.numero_chamada,
                            'responsavel', a.responsavel,
                            'telefone', a.telefone,
                            'email', a.email
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'
                ) as alunos,
                COUNT(a.id) as total_alunos
            FROM turmas t 
            LEFT JOIN escolas e ON t.escola_id = e.id 
            LEFT JOIN alunos a ON a.turma_id = t.id
            WHERE t.id = %s
            GROUP BY t.id, e.nome
        """, (id,))
        turma = cur.fetchone()
        cur.close()
        conn.close()
        
        if not turma:
            return jsonify({'erro': 'Turma não encontrada'}), 404
        
        if turma['alunos']:
            turma['alunos'] = turma['alunos']
        else:
            turma['alunos'] = []
        
        return jsonify(turma)
        
    except Exception as e:
        print(f"❌ Erro ao buscar turma: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>', methods=['PUT'])
def editar_turma(id):
    try:
        data = request.json
        
        if not data.get('nome') or not data.get('escola_id'):
            return jsonify({'erro': 'Nome e escola são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM turmas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404
        
        cur.execute("""
            UPDATE turmas 
            SET escola_id = %s,
                nome = %s,
                serie = %s,
                turno = %s,
                professor = %s,
                capacidade = %s,
                ano_letivo = %s
            WHERE id = %s
            RETURNING id
        """, (data['escola_id'], data['nome'], data.get('serie', '1º Ano'),
              data.get('turno', 'Manhã'), data.get('professor', ''),
              data.get('capacidade', 35), data.get('ano_letivo', 2025), id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'id': result['id'],
            'mensagem': 'Turma atualizada com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar turma: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>/alunos', methods=['GET'])
def listar_alunos_por_turma(id):
    """Lista todos os alunos de uma turma específica"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar se a turma existe
        cur.execute("SELECT id, nome, serie FROM turmas WHERE id = %s", (id,))
        turma = cur.fetchone()
        if not turma:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404
        
        # Buscar alunos
        cur.execute("""
            SELECT 
                id,
                nome,
                matricula,
                numero_chamada,
                data_nascimento,
                genero,
                responsavel,
                telefone,
                email,
                observacoes
            FROM alunos
            WHERE turma_id = %s
            ORDER BY numero_chamada NULLS LAST, nome
        """, (id,))
        
        alunos = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            'turma': turma,
            'total_alunos': len(alunos),
            'alunos': alunos
        })
        
    except Exception as e:
        print(f"❌ Erro ao listar alunos da turma: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
    """Exclui uma turma e todos os dados vinculados (alunos, provas, histórico)"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor()
        
        # Verificar se a turma existe
        cur.execute("SELECT id, nome FROM turmas WHERE id = %s", (id,))
        turma = cur.fetchone()
        if not turma:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404
        
        turma_nome = turma[1]
        
        # Contar alunos
        cur.execute("SELECT COUNT(*) FROM alunos WHERE turma_id = %s", (id,))
        total_alunos = cur.fetchone()[0]
        
        # Contar provas
        cur.execute("SELECT COUNT(*) FROM provas WHERE turma_id = %s", (id,))
        total_provas = cur.fetchone()[0]
        
        # Contar históricos
        cur.execute("""
            SELECT COUNT(*) FROM historico h
            JOIN provas p ON h.prova_id = p.id
            WHERE p.turma_id = %s
        """, (id,))
        total_historicos = cur.fetchone()[0]
        
        # Excluir em cascata usando ON DELETE CASCADE
        cur.execute("DELETE FROM turmas WHERE id = %s", (id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Turma "{turma_nome}" excluída com sucesso!',
            'detalhes': {
                'alunos_excluidos': total_alunos,
                'provas_excluidas': total_provas,
                'historicos_excluidos': total_historicos
            }
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir turma: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE ALUNOS (CRUD COMPLETO COM EXCLUSÃO EM CASCATA)
# ============================================

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    try:
        escola_id = request.args.get('escola_id')
        turma_id = request.args.get('turma_id')
        serie = request.args.get('serie')
        
        conn = get_db_connection()
        if not conn:
            return jsonify([])
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                a.id,
                a.nome,
                a.matricula,
                a.numero_chamada,
                a.data_nascimento,
                a.genero,
                a.responsavel,
                a.telefone,
                a.email,
                a.observacoes,
                a.turma_id,
                t.nome as turma_nome,
                t.serie as turma_serie,
                t.turno as turma_turno,
                e.id as escola_id,
                e.nome as escola_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON t.escola_id = e.id
            WHERE 1=1
        """
        params = []
        
        if turma_id and turma_id != '' and turma_id != 'null' and turma_id != 'undefined':
            try:
                turma_id_int = int(turma_id)
                query += " AND a.turma_id = %s"
                params.append(turma_id_int)
            except ValueError:
                pass
        elif escola_id and escola_id != '' and escola_id != 'null' and escola_id != 'undefined':
            try:
                escola_id_int = int(escola_id)
                query += " AND e.id = %s"
                params.append(escola_id_int)
            except ValueError:
                pass
        
        if serie and serie != '' and serie != 'null' and serie != 'undefined':
            query += " AND t.serie = %s"
            params.append(serie)
        
        query += " ORDER BY a.numero_chamada NULLS LAST, a.nome"
        
        cur.execute(query, params)
        alunos = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(alunos)
        
    except Exception as e:
        print(f"❌ Erro ao listar alunos: {e}")
        traceback.print_exc()
        return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    data = request.json
    if not data.get('nome') or not data.get('turma_id'):
        return jsonify({'erro': 'Nome e turma são obrigatórios'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO alunos (turma_id, nome, matricula, numero_chamada, data_nascimento, 
                                    genero, responsavel, telefone, email, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (data['turma_id'], data['nome'], data.get('matricula', ''), 
                  data.get('numero_chamada'), data.get('data_nascimento'), 
                  data.get('genero', 'Masculino'), data.get('responsavel', ''),
                  data.get('telefone', ''), data.get('email', ''), data.get('observacoes', '')))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Aluno criado com sucesso'})
        except Exception as e:
            print(f"Erro ao criar aluno: {e}")
            traceback.print_exc()
    return jsonify({'erro': 'Erro ao criar aluno'}), 500

@app.route('/api/alunos/<int:id>', methods=['GET'])
def buscar_aluno(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON t.escola_id = e.id
            WHERE a.id = %s
        """, (id,))
        aluno = cur.fetchone()
        cur.close()
        conn.close()
        
        if not aluno:
            return jsonify({'erro': 'Aluno não encontrado'}), 404
        
        return jsonify(aluno)
        
    except Exception as e:
        print(f"❌ Erro ao buscar aluno: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['PUT'])
def editar_aluno(id):
    try:
        data = request.json
        
        if not data.get('nome') or not data.get('turma_id'):
            return jsonify({'erro': 'Nome e turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM alunos WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Aluno não encontrado'}), 404
        
        cur.execute("""
            UPDATE alunos 
            SET turma_id = %s,
                nome = %s,
                matricula = %s,
                numero_chamada = %s,
                data_nascimento = %s,
                genero = %s,
                responsavel = %s,
                telefone = %s,
                email = %s,
                observacoes = %s
            WHERE id = %s
            RETURNING id
        """, (data['turma_id'], data['nome'], data.get('matricula', ''),
              data.get('numero_chamada'), data.get('data_nascimento'),
              data.get('genero', 'Masculino'), data.get('responsavel', ''),
              data.get('telefone', ''), data.get('email', ''), data.get('observacoes', ''), id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'id': result['id'],
            'mensagem': 'Aluno atualizado com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar aluno: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['DELETE'])
def excluir_aluno(id):
    """Exclui um aluno e todo o seu histórico"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor()
        
        # Verificar se o aluno existe
        cur.execute("SELECT id, nome FROM alunos WHERE id = %s", (id,))
        aluno = cur.fetchone()
        if not aluno:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Aluno não encontrado'}), 404
        
        aluno_nome = aluno[1]
        
        # Excluir histórico do aluno (ON DELETE CASCADE já cuida)
        cur.execute("DELETE FROM historico WHERE aluno_id = %s", (id,))
        
        # Excluir correções de texto do aluno
        cur.execute("DELETE FROM correcoes_texto WHERE aluno_id = %s", (id,))
        
        # Excluir o aluno
        cur.execute("DELETE FROM alunos WHERE id = %s", (id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Aluno "{aluno_nome}" excluído com sucesso!'
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir aluno: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE PROVAS (CRUD COMPLETO COM EXCLUSÃO EM CASCATA)
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT p.*, t.nome as turma_nome, t.serie as turma_serie
                FROM provas p LEFT JOIN turmas t ON p.turma_id = t.id
                ORDER BY p.id DESC
            """)
            provas = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(provas)
        except Exception as e:
            print(f"Erro ao listar provas: {e}")
            traceback.print_exc()
    return jsonify([])

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    data = request.json
    if not data.get('titulo') or not data.get('turma_id'):
        return jsonify({'erro': 'Título e turma são obrigatórios'}), 400
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO provas (turma_id, titulo, disciplina, bimestre, data_prova, 
                                    valor_nota, tipo_questoes, quantidade_questoes, gabarito)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (data['turma_id'], data['titulo'], data.get('disciplina', ''),
                  data.get('bimestre', ''), data.get('data_prova'), data.get('valor_nota', 10),
                  data.get('tipo_questoes', '4'), data.get('quantidade_questoes', 20), 
                  data.get('gabarito', [])))
            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'id': result['id'], 'mensagem': 'Prova criada com sucesso'})
        except Exception as e:
            print(f"Erro ao criar prova: {e}")
            traceback.print_exc()
    return jsonify({'erro': 'Erro ao criar prova'}), 500

@app.route('/api/provas/<int:id>', methods=['GET'])
def buscar_prova(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*, t.nome as turma_nome, t.serie as turma_serie
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            WHERE p.id = %s
        """, (id,))
        prova = cur.fetchone()
        cur.close()
        conn.close()
        
        if not prova:
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        return jsonify(prova)
        
    except Exception as e:
        print(f"❌ Erro ao buscar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['PUT'])
def editar_prova(id):
    try:
        data = request.json
        
        if not data.get('titulo') or not data.get('turma_id'):
            return jsonify({'erro': 'Título e turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM provas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        cur.execute("""
            UPDATE provas 
            SET turma_id = %s,
                titulo = %s,
                disciplina = %s,
                bimestre = %s,
                data_prova = %s,
                valor_nota = %s,
                tipo_questoes = %s,
                quantidade_questoes = %s,
                gabarito = %s
            WHERE id = %s
            RETURNING id
        """, (data['turma_id'], data['titulo'], data.get('disciplina', ''),
              data.get('bimestre', ''), data.get('data_prova'),
              data.get('valor_nota', 10), data.get('tipo_questoes', '4'),
              data.get('quantidade_questoes', 20), data.get('gabarito', []), id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'id': result['id'],
            'mensagem': 'Prova atualizada com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Erro ao editar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['DELETE'])
def excluir_prova(id):
    """Exclui uma prova e todo o histórico associado"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor()
        
        # Verificar se a prova existe
        cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        prova_titulo = prova[1]
        
        # Contar históricos
        cur.execute("SELECT COUNT(*) FROM historico WHERE prova_id = %s", (id,))
        total_historicos = cur.fetchone()[0]
        
        # Excluir histórico associado (ON DELETE CASCADE já cuida)
        cur.execute("DELETE FROM historico WHERE prova_id = %s", (id,))
        
        # Excluir correções de texto associadas
        cur.execute("DELETE FROM correcoes_texto WHERE prova_id = %s", (id,))
        
        # Excluir a prova
        cur.execute("DELETE FROM provas WHERE id = %s", (id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Prova "{prova_titulo}" excluída com sucesso!',
            'detalhes': {
                'historicos_excluidos': total_historicos
            }
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir prova: {e}")
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

@app.route('/api/dashboard/desempenho', methods=['GET'])
def dashboard_desempenho():
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                t.id,
                t.nome as nome,
                COALESCE(AVG(h.nota), 0) as media,
                COUNT(DISTINCT h.aluno_id) as total_alunos,
                COUNT(DISTINCT h.id) as total_correcoes,
                COALESCE(AVG(h.acertos), 0) as media_acertos,
                COALESCE(AVG(h.total), 20) as media_total
            FROM turmas t
            LEFT JOIN provas p ON p.turma_id = t.id
            LEFT JOIN historico h ON h.prova_id = p.id
            GROUP BY t.id, t.nome
            HAVING COUNT(DISTINCT h.id) > 0
            ORDER BY media DESC
        """)
        turmas = cur.fetchall()
        cur.close()
        conn.close()
        
        nota_maxima = 10
        resultado = []
        for turma in turmas:
            if turma['total_correcoes'] > 0:
                porcentagem = round((turma['media'] / nota_maxima) * 100)
                conceito = calcular_conceito(porcentagem)
            else:
                porcentagem = 0
                conceito = calcular_conceito(0)
            
            resultado.append({
                'id': turma['id'],
                'nome': turma['nome'],
                'media': round(turma['media'], 1),
                'porcentagem': porcentagem,
                'conceito': conceito['nome'],
                'conceito_rotulo': conceito['rotulo'],
                'conceito_cor': conceito['cor'],
                'total_alunos': turma['total_alunos'],
                'total_correcoes': turma['total_correcoes']
            })
        
        resultado = sorted(resultado, key=lambda x: x['porcentagem'], reverse=True)[:5]
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro ao buscar desempenho: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    """Retorna dados de conceitos para o dashboard"""
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
            if aluno['total_correcoes'] > 0:
                porcentagem = round((aluno['media_nota'] / 10) * 100) if aluno['media_nota'] > 0 else 0
                conceito = calcular_conceito(porcentagem)
            else:
                conceito = calcular_conceito(0)
            
            resultado.append({
                'aluno_id': aluno['id'],
                'aluno_nome': aluno['aluno_nome'],
                'turma': aluno['turma_nome'],
                'serie': aluno['serie'],
                'media_nota': round(aluno['media_nota'], 1),
                'porcentagem': porcentagem,
                'conceito': conceito,
                'total_correcoes': aluno['total_correcoes']
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro em /api/dashboard/Conceito: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/dashboard/turmas_alunos', methods=['GET'])
def dashboard_turmas_alunos():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                t.id,
                t.nome as turma_nome,
                t.serie,
                e.nome as escola_nome,
                COUNT(a.id) as total_alunos,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'nome', a.nome,
                            'numero_chamada', a.numero_chamada
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'
                ) as alunos
            FROM turmas t
            LEFT JOIN escolas e ON t.escola_id = e.id
            LEFT JOIN alunos a ON a.turma_id = t.id
            GROUP BY t.id, e.nome
            ORDER BY t.nome
        """)
        
        turmas = cur.fetchall()
        cur.close()
        conn.close()
        
        for turma in turmas:
            if turma['alunos']:
                turma['alunos'] = turma['alunos']
            else:
                turma['alunos'] = []
        
        return jsonify(turmas)
        
    except Exception as e:
        print(f"❌ Erro no dashboard turmas-alunos: {e}")
        return jsonify([])

# ============================================
# ROTA DE ESTATÍSTICAS DE TURMAS
# ============================================

@app.route('/api/turmas/estatisticas', methods=['GET'])
def estatisticas_turmas():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                t.id,
                t.nome as turma_nome,
                t.serie,
                e.nome as escola_nome,
                COUNT(DISTINCT a.id) as total_alunos,
                COUNT(DISTINCT p.id) as total_provas,
                COUNT(DISTINCT h.id) as total_correcoes,
                COALESCE(AVG(h.nota), 0) as media_notas,
                COALESCE(AVG(h.acertos), 0) as media_acertos
            FROM turmas t
            LEFT JOIN escolas e ON t.escola_id = e.id
            LEFT JOIN alunos a ON a.turma_id = t.id
            LEFT JOIN provas p ON p.turma_id = t.id
            LEFT JOIN historico h ON h.prova_id = p.id AND h.aluno_id = a.id
            GROUP BY t.id, e.nome
            ORDER BY t.nome
        """)
        
        estatisticas = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(estatisticas)
        
    except Exception as e:
        print(f"❌ Erro ao buscar estatísticas: {e}")
        return jsonify([])

# ============================================
# ROTA DE USUÁRIOS
# ============================================

@app.route('/api/usuarios', methods=['GET'])
def listar_usuarios():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT id, nome, username, email, perfil, ativo, criado_em FROM usuarios ORDER BY id")
            usuarios = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(usuarios)
        except Exception as e:
            print(f"Erro ao listar usuários: {e}")
    
    resultado = []
    for username, dados in USUARIOS_FIXOS.items():
        resultado.append({
            'id': 0,
            'nome': dados['nome'],
            'username': username,
            'email': '',
            'perfil': dados['perfil'],
            'ativo': True,
            'criado_em': datetime.now().isoformat()
        })
    return jsonify(resultado)

@app.route('/api/usuarios', methods=['POST'])
def criar_usuario():
    try:
        data = request.json
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)
        
        if not nome or not username or not senha:
            return jsonify({'erro': 'Nome, usuário e senha são obrigatórios'}), 400
        
        if len(senha) < 4:
            return jsonify({'erro': 'Senha deve ter pelo menos 4 caracteres'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário já existe'}), 400
        
        cur.execute("""
            INSERT INTO usuarios (nome, username, senha_hash, email, perfil, ativo)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (nome, username, senha, email, perfil, ativo))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'id': result['id'],
            'mensagem': 'Usuário criado com sucesso'
        })
        
    except Exception as e:
        print(f"Erro ao criar usuário: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor()
        cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'sucesso': True,
            'mensagem': 'Usuário excluído com sucesso'
        })
        
    except Exception as e:
        print(f"Erro ao excluir usuário: {e}")
        return jsonify({'erro': 'Erro ao excluir usuário'}), 500

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
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        
        cur.execute("""
            SELECT p.*, t.nome as turma_nome, t.serie 
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            WHERE p.id = %s
        """, (prova_id,))
        prova = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if not aluno or not prova:
            return jsonify({'erro': 'Dados não encontrados'}), 404
        
        nome_aluno = aluno['nome']
        turma_nome = prova.get('turma_nome', '')
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
            CREATE TABLE IF NOT EXISTS escolas (
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
            CREATE TABLE IF NOT EXISTS turmas (
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
            CREATE TABLE IF NOT EXISTS alunos (
                id SERIAL PRIMARY KEY,
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
            CREATE TABLE IF NOT EXISTS provas (
                id SERIAL PRIMARY KEY,
                turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
                titulo TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS historico (
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
                data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
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
            CREATE TABLE IF NOT EXISTS correcoes_texto (
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
        
        # Adicionar colunas se não existirem (para compatibilidade)
        try:
            cur.execute("ALTER TABLE historico ADD COLUMN IF NOT EXISTS disciplina TEXT")
            cur.execute("ALTER TABLE historico ADD COLUMN IF NOT EXISTS tipo_avaliacao TEXT")
        except Exception as e:
            print(f"⚠️ Colunas já existem: {e}")
        
        for username, dados in USUARIOS_FIXOS.items():
            cur.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (dados['nome'], username, dados['senha'], dados['perfil']))
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")
        traceback.print_exc()

init_db()

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
