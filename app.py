from flask import Flask, request, jsonify, send_from_directory, send_file
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
import hmac
import logging
import zipfile

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
# Configurar CORS para aceitar requisições de qualquer origem
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
RELAY_API_URL = os.getenv('RELAY_API_URL', '')
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

SUPABASE_URL = os.getenv('SUPABASE_URL')
if not SUPABASE_URL:
    print("❌ ERRO: SUPABASE_URL não definida no .env")
    print("⚠️ O servidor não conseguirá conectar ao banco de dados!")
    print("⚠️ Configure a variável SUPABASE_URL no arquivo .env")

def get_db_connection():
    if not SUPABASE_URL:
        print("❌ SUPABASE_URL não configurada")
        return None
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
# FUNÇÃO PARA IDENTIFICAR DISCIPLINA (CORRIGIDA COM \b)
# ============================================

def identificar_disciplina(prova_titulo, disciplina, serie):
    """
    Identifica o tipo de avaliação com base no título, disciplina e série
    Retorna: 'Portugues', 'Matematica', 'Producao', 'CH', 'CN' ou 'Geral'
    Usa \b (word boundary) para evitar falsos positivos
    """
    # PRIMEIRO: verificar a disciplina informada (mais confiável)
    disciplina_lower = (disciplina or '').lower().strip()

    # Usa word boundaries para evitar falsos positivos
    if re.search(r'\bportugu[êe]s\b', disciplina_lower) or 'língua' in disciplina_lower:
        return 'Portugues'
    if re.search(r'\bmatem[áa]tica\b', disciplina_lower):
        return 'Matematica'
    if re.search(r'\bprodu[cç][ãa]o\b', disciplina_lower) or 'texto' in disciplina_lower or 'redação' in disciplina_lower or 'redacao' in disciplina_lower:
        return 'Producao'
    if re.search(r'\bch\b', disciplina_lower) or 'ciencias humanas' in disciplina_lower:
        return 'CH'
    if re.search(r'\bcn\b', disciplina_lower) or 'ciencias naturais' in disciplina_lower:
        return 'CN'

    # SEGUNDO: verificar o título da prova
    texto = f"{prova_titulo or ''}".lower()

    if re.search(r'\bportugu[êe]s\b', texto) or 'língua' in texto:
        return 'Portugues'
    if re.search(r'\bmatem[áa]tica\b', texto) or re.search(r'\bmat\b', texto):
        return 'Matematica'
    if re.search(r'\bprodu[cç][ãa]o\b', texto) or 'texto' in texto or 'redação' in texto or 'redacao' in texto:
        return 'Producao'
    if re.search(r'\bch\b', texto) or 'ciencias humanas' in texto:
        return 'CH'
    if re.search(r'\bcn\b', texto) or 'ciencias naturais' in texto:
        return 'CN'

    # TERCEIRO: fallback baseado na série
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
# FUNÇÃO PARA EXTRAIR MIMETYPE DA IMAGEM
# ============================================

def extrair_mimetype(imagem_base64):
    """Extrai o mimetype real do prefixo data:image/...;base64"""
    if not imagem_base64:
        return 'image/jpeg'

    match = re.match(r'data:image/(\w+);base64,', imagem_base64)
    if match:
        tipo = match.group(1)
        return f'image/{tipo}'

    return 'image/jpeg'

# ============================================
# FUNÇÃO DE CORREÇÃO COM GEMINI (COM QUESTÕES_STATUS)
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

                # Extrair o mimetype real da imagem
                mimetype = extrair_mimetype(imagem_base64)

                imagem_limpa = imagem_base64
                if ',' in imagem_base64:
                    imagem_limpa = imagem_base64.split(',')[1]

                alternativas = "A, B, C, D" if tipo_questoes == 4 else "A, B, C"

                # Montar mensagem com imagem no formato multimodal
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

                # Usar a API OpenAI com suporte a multimodal
                try:
                    # Tentar usar a API com suporte a imagens
                    if hasattr(openai, 'ChatCompletion') and hasattr(openai.ChatCompletion, 'create'):
                        response = openai.ChatCompletion.create(
                            model=RELAY_MODEL,
                            messages=[
                                {"role": "system", "content": "Você é um assistente especializado em correção de provas."},
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": f"data:{mimetype};base64,{imagem_limpa}"}}
                                    ]
                                }
                            ],
                            max_tokens=500,
                            temperature=0.3
                        )
                        resposta_texto = response.choices[0].message.content
                    else:
                        # Fallback: enviar apenas texto
                        print("⚠️ API não suporta multimodal, enviando apenas texto")
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
                except Exception as e:
                    print(f"⚠️ Erro na API multimodal: {e}")
                    # Tentar fallback sem imagem
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
# MIDDLEWARE PARA GARANTIR RESPOSTAS JSON
# ============================================

@app.after_request
def after_request(response):
    """Garante que todas as respostas da API sejam JSON"""
    if request.path.startswith('/api/') and response.status_code != 200:
        # Se não for JSON, converte para JSON
        if not response.headers.get('Content-Type', '').startswith('application/json'):
            try:
                # Se for HTML, converte para JSON de erro
                if 'text/html' in response.headers.get('Content-Type', ''):
                    response = jsonify({
                        'erro': 'Erro interno do servidor',
                        'status': response.status_code,
                        'detalhes': 'A requisição retornou HTML em vez de JSON'
                    })
                    response.status_code = 500
            except:
                pass
    return response

# ============================================
# ROTA DE LOGIN (COM hmac.compare_digest)
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

                    # Usar hmac.compare_digest para comparação segura
                    if hmac.compare_digest(str(usuario['senha_hash'] or ''), str(senha)) and usuario['ativo'] == True:
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

        # Verificar usuários fixos com comparação segura
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if hmac.compare_digest(str(dados['senha']), str(senha)):
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
            escola_id = aluno['escola_id'] if aluno else None

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

            # CORREÇÃO: usar or 4 para tratar None
            tipo_questoes = prova.get('tipo_questoes') or 4
            if isinstance(tipo_questoes, str):
                try:
                    tipo_questoes = int(tipo_questoes)
                except:
                    tipo_questoes = 4

            disciplina = prova.get('disciplina', '')
            prova_titulo = prova.get('titulo', '')

            print(f"🤖 Iniciando correção para {nome_aluno}...")
            print(f"📌 Disciplina: {disciplina}")
            print(f"📌 Série: {serie}")

            resultado = corrigir_com_gemini(imagem_base64, gabarito, nome_aluno, serie, tipo_questoes, disciplina)

            if resultado.get('erro'):
                return jsonify(resultado), 400

            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
            print(f"📌 Tipo de avaliação identificado: {tipo_avaliacao}")

            # Salvar no banco com questoes_status
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
# ROTA DE CORREÇÃO MANUAL (COM str() ANTES DE .upper())
# ============================================

@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    try:
        data = request.json
        print("=" * 60)
        print("📥 DADOS RECEBIDOS NA CORREÇÃO MANUAL:")
        print(json.dumps(data, indent=2, default=str))
        print("=" * 60)

        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        respostas = data.get('respostas', [])
        acertos = data.get('acertos', 0)
        nota = data.get('nota', 0)
        total = data.get('total', 0)

        print(f"📌 prova_id: {prova_id} (tipo: {type(prova_id)})")
        print(f"📌 aluno_id: {aluno_id} (tipo: {type(aluno_id)})")
        print(f"📌 respostas: {respostas} (tipo: {type(respostas)})")
        print(f"📌 acertos: {acertos} (tipo: {type(acertos)})")
        print(f"📌 nota: {nota} (tipo: {type(nota)})")
        print(f"📌 total: {total} (tipo: {type(total)})")

        if not prova_id or not aluno_id:
            return jsonify({'erro': 'Prova e aluno são obrigatórios'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro no banco'}), 500

        cur = conn.cursor()

        cur.execute("SELECT disciplina, titulo, serie, gabarito FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        print(f"📌 Prova encontrada: {prova}")

        disciplina = prova[0] if prova else ''
        prova_titulo = prova[1] if prova else ''
        serie_prova = prova[2] if prova else ''
        gabarito = prova[3] if prova else []
        print(f"📌 Gabarito: {gabarito} (tipo: {type(gabarito)})")

        cur.execute("""
            SELECT t.serie FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE a.id = %s
        """, (aluno_id,))
        serie_result = cur.fetchone()
        serie = serie_result[0] if serie_result else serie_prova or '1º Ano'

        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
        print(f"📌 Tipo avaliação: {tipo_avaliacao}")

        # Gerar questoes_status - NORMALIZAÇÃO COM str() ANTES DE .upper()
        questoes_status = []
        for i in range(total):
            resp = str(respostas[i]) if i < len(respostas) and respostas[i] is not None else ''
            gab = str(gabarito[i]) if i < len(gabarito) and gabarito[i] is not None else ''
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

        print(f"📌 questoes_status gerado: {questoes_status}")

        try:
            questoes_status_json = json.dumps(questoes_status)
            print(f"📌 JSON gerado: {questoes_status_json[:100]}...")
        except Exception as e:
            print(f"❌ ERRO AO GERAR JSON: {e}")
            return jsonify({'erro': f'Erro ao converter para JSON: {str(e)}'}), 500

        cur.execute("""
            SELECT id FROM historico
            WHERE prova_id = %s AND aluno_id = %s
        """, (prova_id, aluno_id))
        existe = cur.fetchone()
        print(f"📌 Registro existe? {existe}")

        if existe:
            print("📌 Atualizando registro existente...")
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
            result_id = existe[0] if isinstance(existe, tuple) else existe
            print(f"✅ Atualizado! ID: {result_id}")
        else:
            print("📌 Criando novo registro...")
            cur.execute("""
                INSERT INTO historico
                (prova_id, aluno_id, respostas, acertos, nota, total,
                 tipo_correcao, disciplina, tipo_avaliacao, questoes_status)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual', %s, %s, %s::jsonb)
                RETURNING id
            """, (prova_id, aluno_id, respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json))
            result = cur.fetchone()
            result_id = result[0] if result else None
            print(f"✅ Criado! ID: {result_id}")

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
        print("=" * 60)
        print("❌ ERRO NA CORREÇÃO MANUAL:")
        print(f"❌ Tipo: {type(e)}")
        print(f"❌ Mensagem: {str(e)}")
        print("❌ Traceback completo:")
        traceback.print_exc()
        print("=" * 60)
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
# ROTA DE HISTÓRICO - VERSÃO COM 5 AVALIAÇÕES (INCLUINDO CH E CN)
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
# ROTA PARA HISTÓRICO AGRUPADO POR ALUNO (5 AVALIAÇÕES - COM CH E CN)
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
                    'avaliacoes': {}
                }

            disciplina = item.get('disciplina', '')
            prova_titulo = item.get('prova_titulo', '')
            serie_aluno = item.get('serie', '')
            tipo = identificar_disciplina(prova_titulo, disciplina, serie_aluno)

            # Extrair questoes_status
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

            # Agora com 5 disciplinas: Portugues, Matematica, Producao, CH, CN
            notas = []
            for tipo in ['Portugues', 'Matematica', 'Producao', 'CH', 'CN']:
                if tipo in avaliacoes:
                    notas.append(avaliacoes[tipo]['nota'])
                else:
                    notas.append(0)

            soma = sum(notas)
            media = soma / 5 if notas else 0

            resultado.append({
                'aluno_id': dados['aluno_id'],
                'aluno_nome': dados['aluno_nome'],
                'serie': dados['serie'],
                'turma': dados['turma'],
                'escola': dados['escola'],
                'portugues': avaliacoes.get('Portugues', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'matematica': avaliacoes.get('Matematica', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'producao': avaliacoes.get('Producao', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'ch': avaliacoes.get('CH', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
                'cn': avaliacoes.get('CN', {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}),
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
# ROTA DE GABARITOS (COM BNCC)
# ============================================

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        bncc = data.get('bncc', [])          # <-- recebe o array de BNCC

        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400

        if not respostas or len(respostas) == 0:
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400

        # Normaliza respostas
        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        if not respostas_validas:
            return jsonify({'erro': 'Nenhuma resposta válida'}), 400

        # Normaliza BNCC (mantém apenas strings não vazias)
        bncc_validos = [str(b).strip() for b in bncc if b and str(b).strip()]

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor()
        cur.execute("SELECT id FROM provas WHERE id = %s", (prova_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404

        # Atualiza gabarito e bncc
        cur.execute("""
            UPDATE provas
            SET gabarito = %s::text[],
                quantidade_questoes = %s,
                bncc = %s::text[]
            WHERE id = %s
            RETURNING id
        """, (respostas_validas, len(respostas_validas), bncc_validos, prova_id))

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
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE GABARITOS - DELETE
# ============================================

@app.route('/api/gabaritos/<int:id>', methods=['DELETE'])
def excluir_gabarito(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor()

        cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404

        cur.execute("""
            UPDATE provas
            SET gabarito = NULL, quantidade_questoes = 0, bncc = NULL
            WHERE id = %s
        """, (id,))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'sucesso': True,
            'mensagem': f'Gabarito da prova "{prova[1]}" removido com sucesso!'
        })

    except Exception as e:
        print(f"❌ Erro ao excluir gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE ESCOLAS (CRUD COMPLETO) - CORRIGIDA
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
    """
    Exclui a escola, suas turmas e alunos (em cascata via banco).
    NÃO EXCLUI PROVAS em hipótese alguma.
    """
    logging.info(f"🔴 Tentativa de excluir escola ID {id} de {request.remote_addr}")

    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()

        # Verifica se a escola existe
        cur.execute("SELECT id, nome FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        if not escola:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404

        escola_id, escola_nome = escola[0], escola[1]

        # Conta turmas e alunos para estatísticas (opcional)
        cur.execute("SELECT COUNT(*) FROM turmas WHERE escola_id = %s", (escola_id,))
        total_turmas = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM alunos WHERE escola_id = %s", (escola_id,))
        total_alunos = cur.fetchone()[0]

        # NÃO EXCLUIMOS PROVAS - NENHUMA CONSULTA OU DELETE NA TABELA provas!

        # Exclui a escola (em cascata, turmas e alunos serão excluídos automaticamente)
        cur.execute("DELETE FROM escolas WHERE id = %s", (escola_id,))

        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"✅ Escola '{escola_nome}' (ID {escola_id}) excluída com sucesso. Turmas: {total_turmas}, Alunos: {total_alunos}")

        return jsonify({
            'sucesso': True,
            'mensagem': f'Escola "{escola_nome}" excluída com sucesso!',
            'detalhes': {
                'turmas_excluidas': total_turmas,
                'alunos_excluidos': total_alunos
            }
        })

    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Erro ao excluir escola ID {id}: {str(e)}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE TURMAS (CRUD COMPLETO) - CORRIGIDA
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
                e.nome as escola_nome
            FROM turmas t
            LEFT JOIN escolas e ON t.escola_id = e.id
            WHERE t.id = %s
        """, (id,))
        turma = cur.fetchone()
        cur.close()
        conn.close()

        if not turma:
            return jsonify({'erro': 'Turma não encontrada'}), 404

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

@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
    """
    Exclui a turma e seus alunos (em cascata via banco).
    NÃO EXCLUI PROVAS.
    """
    logging.info(f"🔴 Tentativa de excluir turma ID {id} de {request.remote_addr}")

    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()

        cur.execute("SELECT id, nome, serie FROM turmas WHERE id = %s", (id,))
        turma = cur.fetchone()
        if not turma:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404

        turma_id, turma_nome, turma_serie = turma[0], turma[1], turma[2]

        # Contar alunos para estatísticas
        cur.execute("SELECT COUNT(*) FROM alunos WHERE turma_id = %s", (turma_id,))
        total_alunos = cur.fetchone()[0]

        # NÃO EXCLUIMOS PROVAS - NENHUMA CONSULTA OU DELETE NA TABELA provas!

        # Excluir turma (em cascata, alunos serão excluídos automaticamente)
        cur.execute("DELETE FROM turmas WHERE id = %s", (turma_id,))

        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"✅ Turma '{turma_nome}' (ID {turma_id}) excluída com sucesso. Alunos: {total_alunos}")

        return jsonify({
            'sucesso': True,
            'mensagem': f'Turma "{turma_nome}" excluída com sucesso!',
            'detalhes': {
                'alunos_excluidos': total_alunos
            }
        })

    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Erro ao excluir turma ID {id}: {str(e)}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE ALUNOS (CRUD COMPLETO)
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
                a.escola_id,
                t.nome as turma_nome,
                t.serie as turma_serie,
                t.turno as turma_turno,
                e.nome as escola_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            WHERE 1=1
        """
        params = []

        if escola_id and escola_id != '' and escola_id != 'null' and escola_id != 'undefined':
            try:
                escola_id_int = int(escola_id)
                query += " AND a.escola_id = %s"
                params.append(escola_id_int)
            except ValueError:
                pass

        if turma_id and turma_id != '' and turma_id != 'null' and turma_id != 'undefined':
            try:
                turma_id_int = int(turma_id)
                query += " AND a.turma_id = %s"
                params.append(turma_id_int)
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
    try:
        data = request.json

        if not data.get('nome'):
            return jsonify({'erro': 'Nome é obrigatório'}), 400

        if not data.get('escola_id'):
            return jsonify({'erro': 'Escola é obrigatória'}), 400

        if not data.get('turma_id'):
            return jsonify({'erro': 'Turma é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM escolas WHERE id = %s", (data['escola_id'],))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404

        cur.execute("SELECT id FROM turmas WHERE id = %s", (data['turma_id'],))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404

        cur.execute("""
            INSERT INTO alunos
            (escola_id, turma_id, nome, matricula, numero_chamada, data_nascimento,
             genero, responsavel, telefone, email, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['escola_id'],
            data['turma_id'],
            data['nome'],
            data.get('matricula', ''),
            data.get('numero_chamada'),
            data.get('data_nascimento'),
            data.get('genero', 'Masculino'),
            data.get('responsavel', ''),
            data.get('telefone', ''),
            data.get('email', ''),
            data.get('observacoes', '')
        ))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'id': result['id'],
            'mensagem': 'Aluno criado com sucesso'
        })

    except Exception as e:
        print(f"❌ Erro ao criar aluno: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:id>', methods=['GET'])
def buscar_aluno(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                a.*,
                t.nome as turma_nome,
                t.serie as turma_serie,
                e.nome as escola_nome,
                e.id as escola_id
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
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

        if not data.get('nome'):
            return jsonify({'erro': 'Nome é obrigatório'}), 400

        if not data.get('escola_id'):
            return jsonify({'erro': 'Escola é obrigatória'}), 400

        if not data.get('turma_id'):
            return jsonify({'erro': 'Turma é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM alunos WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Aluno não encontrado'}), 404

        cur.execute("SELECT id FROM escolas WHERE id = %s", (data['escola_id'],))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404

        cur.execute("SELECT id FROM turmas WHERE id = %s", (data['turma_id'],))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Turma não encontrada'}), 404

        cur.execute("""
            UPDATE alunos
            SET escola_id = %s,
                turma_id = %s,
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
        """, (
            data['escola_id'],
            data['turma_id'],
            data['nome'],
            data.get('matricula', ''),
            data.get('numero_chamada'),
            data.get('data_nascimento'),
            data.get('genero', 'Masculino'),
            data.get('responsavel', ''),
            data.get('telefone', ''),
            data.get('email', ''),
            data.get('observacoes', ''),
            id
        ))

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
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()

        cur.execute("SELECT id, nome FROM alunos WHERE id = %s", (id,))
        aluno = cur.fetchone()
        if not aluno:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Aluno não encontrado'}), 404

        aluno_nome = aluno[1]

        cur.execute("DELETE FROM historico WHERE aluno_id = %s", (id,))
        cur.execute("DELETE FROM correcoes_texto WHERE aluno_id = %s", (id,))
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
# ROTA DE PROVAS (CRUD COMPLETO COM BNCC)
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    # Ignora qualquer parâmetro escola_id – provas não estão vinculadas a escolas
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                p.id,
                p.titulo,
                p.serie,
                p.disciplina,
                p.bimestre,
                p.data_prova,
                p.valor_nota,
                p.tipo_questoes,
                p.quantidade_questoes,
                p.gabarito,
                p.bncc,
                p.created_at
            FROM provas p
            ORDER BY p.created_at DESC
        """)
        provas = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify(provas)

    except Exception as e:
        print(f"❌ Erro ao listar provas: {e}")
        traceback.print_exc()
        return jsonify([])

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        data = request.json
        titulo = data.get('titulo')
        serie = data.get('serie')

        if not titulo:
            return jsonify({'erro': 'Título é obrigatório'}), 400
        if not serie:
            return jsonify({'erro': 'Série é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Verifica duplicata
        cur.execute("""
            SELECT id FROM provas
            WHERE titulo = %s AND serie = %s
        """, (titulo, serie))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Já existe uma prova com este título para esta série'}), 400

        bncc = data.get('bncc', [])
        bncc_validos = [str(b).strip() for b in bncc if b and str(b).strip()]

        cur.execute("""
            INSERT INTO provas
                (titulo, serie, disciplina, bimestre, data_prova,
                 valor_nota, tipo_questoes, quantidade_questoes, gabarito, bncc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            titulo,
            serie,
            data.get('disciplina', ''),
            data.get('bimestre', ''),
            data.get('data_prova'),
            data.get('nota_maxima', 10),
            data.get('tipo_questoes', '4'),
            data.get('quantidade_questoes', 20),
            data.get('gabarito', []),
            bncc_validos
        ))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'id': result['id'],
            'mensagem': f'Prova "{titulo}" criada com sucesso para a série {serie}!',
            'serie': serie
        })

    except Exception as e:
        print(f"❌ Erro ao criar prova: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:id>', methods=['GET'])
def buscar_prova(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                id,
                titulo,
                serie,
                disciplina,
                bimestre,
                data_prova,
                valor_nota,
                tipo_questoes,
                quantidade_questoes,
                gabarito,
                bncc,
                created_at
            FROM provas
            WHERE id = %s
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
        titulo = data.get('titulo')
        serie = data.get('serie')

        if not titulo:
            return jsonify({'erro': 'Título é obrigatório'}), 400

        if not serie:
            return jsonify({'erro': 'Série é obrigatória'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM provas WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404

        bncc = data.get('bncc', [])
        bncc_validos = [str(b).strip() for b in bncc if b and str(b).strip()]

        cur.execute("""
            UPDATE provas
            SET titulo = %s,
                serie = %s,
                disciplina = %s,
                bimestre = %s,
                data_prova = %s,
                valor_nota = %s,
                tipo_questoes = %s,
                quantidade_questoes = %s,
                gabarito = %s,
                bncc = %s
            WHERE id = %s
            RETURNING id
        """, (titulo, serie, data.get('disciplina', ''),
              data.get('bimestre', ''), data.get('data_prova'),
              data.get('nota_maxima', 10), data.get('tipo_questoes', '4'),
              data.get('quantidade_questoes', 20), data.get('gabarito', []),
              bncc_validos, id))

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
    """
    Exclui uma prova específica (apenas quando o usuário seleciona para excluir).
    """
    logging.info(f"🔴 Tentativa de excluir prova ID {id} de {request.remote_addr}")

    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()

        cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404

        prova_titulo = prova[1]

        # Remove registros associados (histórico e correções de texto)
        cur.execute("DELETE FROM historico WHERE prova_id = %s", (id,))
        cur.execute("DELETE FROM correcoes_texto WHERE prova_id = %s", (id,))
        cur.execute("DELETE FROM provas WHERE id = %s", (id,))

        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"✅ Prova '{prova_titulo}' (ID {id}) excluída com sucesso.")

        return jsonify({
            'sucesso': True,
            'mensagem': f'Prova "{prova_titulo}" excluída com sucesso!'
        })

    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Erro ao excluir prova ID {id}: {str(e)}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTA DE USUÁRIOS (CRUD COMPLETO) - CORRIGIDO
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

# ============================================
# ROTAS ADICIONAIS PARA USUÁRIOS (GET, PUT, DELETE)
# ============================================

@app.route('/api/usuarios/<int:id>', methods=['GET'])
def buscar_usuario(id):
    """Busca um usuário específico pelo ID."""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, nome, username, email, perfil, ativo, criado_em
            FROM usuarios
            WHERE id = %s
        """, (id,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if not usuario:
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        return jsonify(usuario)

    except Exception as e:
        print(f"❌ Erro ao buscar usuário: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def atualizar_usuario(id):
    """Atualiza os dados de um usuário existente."""
    try:
        data = request.json
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')          # pode vir vazio
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)

        if not nome or not username:
            return jsonify({'erro': 'Nome e usuário são obrigatórios'}), 400

        if len(username) < 3:
            return jsonify({'erro': 'Usuário deve ter pelo menos 3 caracteres'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Verifica se o usuário existe
        cur.execute("SELECT id FROM usuarios WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        # Verifica se o novo username já está em uso por outro usuário
        cur.execute("SELECT id FROM usuarios WHERE username = %s AND id != %s", (username, id))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Este nome de usuário já está em uso'}), 400

        # Monta a query de atualização dinamicamente
        update_fields = []
        params = []

        update_fields.append("nome = %s")
        params.append(nome)

        update_fields.append("username = %s")
        params.append(username)

        update_fields.append("email = %s")
        params.append(email)

        update_fields.append("perfil = %s")
        params.append(perfil)

        update_fields.append("ativo = %s")
        params.append(ativo)

        # Se a senha foi fornecida (não vazia), atualiza
        if senha and len(senha) >= 4:
            update_fields.append("senha_hash = %s")
            params.append(senha)

        params.append(id)  # para o WHERE

        query = f"""
            UPDATE usuarios
            SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING id
        """

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'sucesso': True,
            'id': result['id'],
            'mensagem': 'Usuário atualizado com sucesso'
        })

    except Exception as e:
        print(f"❌ Erro ao atualizar usuário: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    """Exclui um usuário (apenas se não for o admin principal)."""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Busca o usuário
        cur.execute("SELECT username FROM usuarios WHERE id = %s", (id,))
        usuario = cur.fetchone()
        if not usuario:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        username = usuario['username']

        # Impede exclusão do admin principal
        if username == 'admin':
            cur.close()
            conn.close()
            return jsonify({'erro': 'Não é possível excluir o usuário administrador principal'}), 400

        # Exclui o usuário
        cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'sucesso': True,
            'mensagem': f'Usuário "{username}" excluído com sucesso'
        })

    except Exception as e:
        print(f"❌ Erro ao excluir usuário: {e}")
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

@app.route('/api/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Agrupa por turma, calcula média de acertos e total de correções
        cur.execute("""
            SELECT
                t.id as turma_id,
                t.nome as turma_nome,
                t.serie,
                COUNT(DISTINCT a.id) as total_alunos,
                COALESCE(AVG(h.acertos * 1.0 / NULLIF(h.total, 0)), 0) as media_porcentagem,
                COALESCE(SUM(CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END), 0) as total_correcoes
            FROM turmas t
            LEFT JOIN alunos a ON a.turma_id = t.id
            LEFT JOIN historico h ON h.aluno_id = a.id
            GROUP BY t.id, t.nome, t.serie
            HAVING COUNT(DISTINCT a.id) > 0
            ORDER BY t.nome
        """)

        turmas = cur.fetchall()
        cur.close()
        conn.close()

        resultado = []
        for turma in turmas:
            media_porcentagem = float(turma['media_porcentagem'] or 0)
            total_correcoes = int(turma['total_correcoes'] or 0)

            # Converte média de acertos para porcentagem (0-100)
            porcentagem = round(media_porcentagem * 100) if media_porcentagem > 0 else 0

            # Calcula conceito (opcional)
            conceito = calcular_conceito(porcentagem)

            resultado.append({
                'id': turma['turma_id'],
                'nome': turma['turma_nome'] or f"Turma {turma['turma_id']}",
                'serie': turma['serie'],
                'total_alunos': turma['total_alunos'],
                'porcentagem': porcentagem,
                'total_correcoes': total_correcoes,
                'conceito': conceito
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
# ══ ROTA DE BACKUP DO BANCO DE DADOS ══
# ============================================

@app.route('/api/backup', methods=['GET'])
def backup_database():
    """
    Exporta todas as tabelas do banco para um arquivo ZIP contendo um JSON.
    Requer uma chave de segurança (BACKUP_KEY) para evitar acesso indevido.
    """
    # Verifica a chave de segurança (pode ser passada como query string ou cabeçalho)
    backup_key = request.headers.get('X-Backup-Key') or request.args.get('key')
    expected_key = os.getenv('BACKUP_KEY', 'backup123')

    if not backup_key or backup_key != expected_key:
        logging.warning(f"⚠️ Tentativa de backup com chave inválida: {backup_key}")
        return jsonify({'erro': 'Não autorizado. Chave de backup inválida.'}), 403

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco de dados'}), 500

        # Lista de tabelas a serem exportadas (ordem respeita dependências)
        tables = ['escolas', 'turmas', 'alunos', 'provas', 'historico', 'usuarios', 'correcoes_texto']
        data = {}

        cur = conn.cursor(cursor_factory=RealDictCursor)

        for table in tables:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                data[table] = rows
                logging.info(f"📦 Tabela '{table}': {len(rows)} registros exportados.")
            except Exception as e:
                logging.warning(f"⚠️ Tabela '{table}' não encontrada ou erro: {e}")
                data[table] = []

        cur.close()
        conn.close()

        # Converte para JSON com tratamento de datas (default=str)
        json_str = json.dumps(data, default=str, indent=2, ensure_ascii=False)

        # Cria um arquivo ZIP em memória
        memory_file = io.BytesIO()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"backup_{timestamp}.json"
        zip_filename = f"backup_{timestamp}.zip"

        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(json_filename, json_str.encode('utf-8'))

        memory_file.seek(0)

        logging.info(f"✅ Backup gerado com sucesso: {zip_filename}")

        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )

    except Exception as e:
        logging.error(f"❌ Erro ao gerar backup: {str(e)}")
        traceback.print_exc()
        return jsonify({'erro': f'Erro ao gerar backup: {str(e)}'}), 500

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
                '/api/gerar_gabarito',
                '/api/backup'
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

        # Verifica se a tabela escolas existe (para saber se o banco já foi criado)
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
                    bncc TEXT[],
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

            # Verificar se a coluna bncc existe na tabela provas
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'provas' AND column_name = 'bncc'
            """)
            if not cur.fetchone():
                print("🔧 Adicionando coluna bncc à tabela provas...")
                try:
                    cur.execute("ALTER TABLE provas ADD COLUMN bncc TEXT[]")
                    print("✅ Coluna bncc adicionada com sucesso!")
                except Exception as e:
                    print(f"⚠️ Erro ao adicionar coluna bncc: {e}")

            # Verificar se a coluna questoes_status existe
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

        # Inserir usuários fixos se não existirem
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
    print("📋 Disciplinas suportadas:")
    print("   - Português")
    print("   - Matemática")
    print("   - Produção de Texto")
    print("   - Ciências Humanas (CH)")
    print("   - Ciências Naturais (CN)")
    print("=" * 60)
    print("📋 Endpoints disponíveis:")
    print("   - /health")
    print("   - /api/login")
    print("   - /api/corrigir")
    print("   - /api/corrigir_manual")
    print("   - /api/corrigir_redacao")
    print("   - /api/salvar_correcao_texto")
    print("   - /api/correcoes_texto")
    print("   - /api/escolas")
    print("   - /api/turmas")
    print("   - /api/alunos")
    print("   - /api/provas")
    print("   - /api/gabaritos")
    print("   - /api/historico")
    print("   - /api/historico/agrupado")
    print("   - /api/dashboard")
    print("   - /api/dashboard/Conceito")
    print("   - /api/gerar_gabarito")
    print("   - /api/backup")
    print("   - /api/usuarios (GET, POST)")
    print("   - /api/usuarios/<id> (GET, PUT, DELETE)  ✅ NOVO")
    print("=" * 60)

    # Inicializar banco
    init_db()

    app.run(host='0.0.0.0', port=port, debug=False)
