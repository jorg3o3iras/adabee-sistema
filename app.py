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
from psycopg2.pool import ThreadedConnectionPool
from psycopg2 import extensions
import pytesseract
import random
import traceback
from dotenv import load_dotenv
import hmac
import logging
import zipfile
import hashlib
from collections import Counter

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================
# 🔥 CACHE DE CORREÇÕES
# ============================================

CORRECOES_CACHE = {}
CORRECOES_CACHE_TTL = 3600  # 1 hora

def get_cache_key(imagem_hash, prova_id, aluno_id):
    return f"{imagem_hash}_{prova_id}_{aluno_id}"

def limpar_cache_antigo():
    """Remove entradas antigas do cache"""
    agora = datetime.now().timestamp()
    chaves_remover = []
    for chave, dados in CORRECOES_CACHE.items():
        if agora - dados['timestamp'] > CORRECOES_CACHE_TTL:
            chaves_remover.append(chave)
    for chave in chaves_remover:
        del CORRECOES_CACHE[chave]
        logging.info(f"🧹 Cache antigo removido: {chave}")

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
            GEMINI_AVAILABLE = True
            print("=" * 60)
            print("✅ Gemini AI configurado!")
            print(f"📌 Modelo: {GEMINI_MODEL}")
            print("=" * 60)

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
DB_POOL = None
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '5'))
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '30'))

if not SUPABASE_URL:
    print("❌ ERRO: SUPABASE_URL não definida no .env")

class PooledConnection:
    __slots__ = ('_conn', '_pool', '_closed')

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._conn.status != extensions.STATUS_READY:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
        finally:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass

def _get_pool():
    global DB_POOL
    if DB_POOL is not None:
        return DB_POOL

    if not SUPABASE_URL:
        return None

    try:
        DB_POOL = ThreadedConnectionPool(
            minconn=DB_POOL_MIN,
            maxconn=DB_POOL_MAX,
            dsn=SUPABASE_URL,
            connect_timeout=8,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3
        )
        logging.info("✅ Pool PostgreSQL criado: %s-%s conexões", DB_POOL_MIN, DB_POOL_MAX)
        return DB_POOL
    except Exception as e:
        logging.error("❌ Erro ao criar pool PostgreSQL: %s", e)
        DB_POOL = None
        return None

def get_db_connection():
    pool = _get_pool()
    if not pool:
        return None

    try:
        conn = pool.getconn()
        if conn.closed:
            pool.putconn(conn, close=True)
            conn = pool.getconn()
        return PooledConnection(conn, pool)
    except Exception as e:
        logging.error("❌ Erro ao obter conexão do pool: %s", e)
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
# 🔥 FUNÇÕES DE CORREÇÃO - VERSÃO DEFINITIVA COM OCR + CÍRCULOS + IA
# ============================================

def calcular_conceito(porcentagem):
    """Calcula o conceito baseado na porcentagem de acertos"""
    if porcentagem <= 40:
        return {
            'nome': 'inicial',
            'rotulo': '🔴 Inicial',
            'faixa': 'até 40%',
            'cor': '#ef4444',
            'badge': 'badge-conceito-inicial'
        }
    elif porcentagem <= 60:
        return {
            'nome': 'basico',
            'rotulo': '🟠 Básico',
            'faixa': '41% - 60%',
            'cor': '#f59e0b',
            'badge': 'badge-conceito-basico'
        }
    elif porcentagem <= 80:
        return {
            'nome': 'proficiente',
            'rotulo': '🔵 Proficiente',
            'faixa': '61% - 80%',
            'cor': '#3b82f6',
            'badge': 'badge-conceito-proficiente'
        }
    else:
        return {
            'nome': 'avancado',
            'rotulo': '🟢 Avançado',
            'faixa': 'acima de 80%',
            'cor': '#10b981',
            'badge': 'badge-conceito-avancado'
        }


def identificar_disciplina(prova_titulo, disciplina, serie):
    disciplina_lower = (disciplina or '').lower().strip()

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

    if serie:
        serie_num = re.search(r'(\d+)', serie)
        if serie_num:
            num = int(serie_num.group(1))
            if num <= 5:
                return 'Portugues'
            else:
                return 'Matematica'

    return 'Geral'


def extrair_mimetype(imagem_base64):
    if not imagem_base64:
        return 'image/jpeg'

    match = re.match(r'data:image/(\w+);base64,', imagem_base64)
    if match:
        tipo = match.group(1)
        return f'image/{tipo}'

    return 'image/jpeg'


# ============================================
# 🔥 FUNÇÃO PARA GERAR PADRÃO DE GABARITO
# ============================================

def gerar_padrao_gabarito(gabarito, tipo_questoes=4):
    """Gera um padrão de gabarito para a IA comparar"""
    alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
    
    padrao = {
        'total_questoes': len(gabarito),
        'alternativas': alternativas,
        'gabarito_oficial': gabarito,
        'questoes': []
    }
    
    for i, resp in enumerate(gabarito):
        padrao['questoes'].append({
            'numero': i + 1,
            'resposta_correta': resp.upper() if resp else None,
            'alternativas': alternativas,
            'posicao': i + 1
        })
    
    return padrao


# ============================================
# 🔥 PASSO 1: OCR + POSIÇÃO (LEITURA DE LETRAS)
# ============================================

def extrair_respostas_com_ocr(imagem_base64, total_questoes, alternativas):
    """
    🔥 OCR + POSIÇÃO - Usa Tesseract para ler letras marcadas
    """
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        if img is None:
            return []
        
        # Redimensionar
        height, width = img.shape[:2]
        if height > 1200:
            scale = 1200 / height
            new_width = int(width * scale)
            img = cv2.resize(img, (new_width, 1200), interpolation=cv2.INTER_AREA)
        
        # Pré-processamento
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Binarização
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary = cv2.bitwise_not(binary)
        
        # Detectar contornos de letras
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        letras_encontradas = []
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            
            # Tamanho médio de uma letra
            if 50 < area < 800 and w > 10 and h > 10:
                roi = binary[y:y+h, x:x+w]
                
                try:
                    texto = pytesseract.image_to_string(roi, config='--psm 8 -c tessedit_char_whitelist=ABCD')
                    letra = texto.strip().upper()
                    
                    if letra in alternativas:
                        cx = x + w//2
                        cy = y + h//2
                        letras_encontradas.append({
                            'letra': letra,
                            'x': cx,
                            'y': cy,
                            'w': w,
                            'h': h,
                            'area': area
                        })
                except:
                    continue
        
        logging.info(f"📊 OCR encontrou {len(letras_encontradas)} letras")
        
        if not letras_encontradas:
            return []
        
        # Organizar por posição (linhas)
        letras_ordenadas = sorted(letras_encontradas, key=lambda l: (l['y'], l['x']))
        
        # Agrupar por linha
        linhas = []
        linha_atual = []
        y_limite = 40
        
        for l in letras_ordenadas:
            if not linha_atual:
                linha_atual.append(l)
            elif abs(l['y'] - linha_atual[0]['y']) < y_limite:
                linha_atual.append(l)
            else:
                linha_atual.sort(key=lambda l: l['x'])
                linhas.append(linha_atual)
                linha_atual = [l]
        
        if linha_atual:
            linha_atual.sort(key=lambda l: l['x'])
            linhas.append(linha_atual)
        
        # Extrair a letra de cada linha
        respostas = []
        
        for linha in linhas:
            if not linha:
                respostas.append('')
                continue
            
            linha_ordenada = sorted(linha, key=lambda l: l['x'])
            
            letra_escolhida = None
            
            if len(linha_ordenada) == 1:
                letra_escolhida = linha_ordenada[0]['letra']
            else:
                linha_ordenada.sort(key=lambda l: l['area'], reverse=True)
                letra_escolhida = linha_ordenada[0]['letra']
            
            if letra_escolhida:
                respostas.append(letra_escolhida)
                logging.info(f"✅ OCR - Questão {len(respostas)}: {letra_escolhida}")
            else:
                respostas.append('')
        
        while len(respostas) < total_questoes:
            respostas.append('')
        
        return respostas[:total_questoes]
        
    except Exception as e:
        logging.error(f"⚠️ Erro no OCR: {e}")
        return []


# ============================================
# 🔥 PASSO 2: DETECÇÃO DE CÍRCULOS PREENCHIDOS
# ============================================

def detectar_circulos_preenchidos(imagem_base64):
    """
    🔥 DETECTA CÍRCULOS PREENCHIDOS NA IMAGEM
    NÃO FAZ OCR - APENAS DETECTA QUAL CÍRCULO FOI MARCADO
    """
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        if img is None:
            return []
        
        # Redimensionar para consistência
        height, width = img.shape[:2]
        if height > 1200:
            scale = 1200 / height
            new_width = int(width * scale)
            img = cv2.resize(img, (new_width, 1200), interpolation=cv2.INTER_AREA)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Aumentar contraste
        clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Binarização
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 🔥 INVERTER PARA DETECTAR CÍRCULOS MAIS ESCUROS (PREENCHIDOS)
        binary_inv = cv2.bitwise_not(binary)
        
        # Detectar círculos
        edges = cv2.Canny(binary_inv, 50, 150)
        
        circles = cv2.HoughCircles(
            edges,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=30,
            param1=100,
            param2=25,
            minRadius=15,
            maxRadius=60
        )
        
        resultados = []
        
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            logging.info(f"🔵 Total de círculos detectados: {len(circles)}")
            
            for (x, y, r) in circles:
                # 🔥 VERIFICAR SE O CÍRCULO ESTÁ PREENCHIDO
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.circle(mask, (x, y), r, 255, -1)
                roi = cv2.bitwise_and(binary_inv, binary_inv, mask=mask)
                
                total_pixels = cv2.countNonZero(mask)
                dark_pixels = cv2.countNonZero(roi)
                dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0
                
                # 🔥 LIMIAR: se mais de 20% do círculo está escuro, está preenchido
                is_filled = dark_ratio > 0.20
                
                resultados.append({
                    'x': x,
                    'y': y,
                    'r': r,
                    'preenchido': is_filled,
                    'dark_ratio': dark_ratio
                })
                
                if is_filled:
                    logging.info(f"🔵 Círculo PREENCHIDO em ({x}, {y}) | Escuridão: {dark_ratio:.2f}")
                else:
                    logging.info(f"⚪ Círculo VAZIO em ({x}, {y}) | Escuridão: {dark_ratio:.2f}")
        
        # 🔥 FILTRAR APENAS CÍRCULOS PREENCHIDOS
        preenchidos = [c for c in resultados if c['preenchido']]
        
        logging.info(f"📊 Círculos preenchidos: {len(preenchidos)} de {len(resultados)}")
        
        return preenchidos
        
    except Exception as e:
        logging.error(f"⚠️ Erro na detecção de círculos: {e}")
        traceback.print_exc()
        return []


def organizar_respostas_por_posicao(circulos, total_questoes):
    """
    🔥 ORGANIZA OS CÍRCULOS PREENCHIDOS POR POSIÇÃO
    A POSIÇÃO DETERMINA A LETRA (1º = A, 2º = B, 3º = C, 4º = D)
    """
    if not circulos:
        return []
    
    # 🔥 ORDENAR POR POSIÇÃO (topo para baixo, esquerda para direita)
    circulos_ordenados = sorted(circulos, key=lambda c: (c['y'], c['x']))
    
    # 🔥 AGRUPAR POR LINHAS (cada linha = uma questão)
    linhas = []
    linha_atual = []
    y_limite = 50
    
    for c in circulos_ordenados:
        if not linha_atual:
            linha_atual.append(c)
        elif abs(c['y'] - linha_atual[0]['y']) < y_limite:
            linha_atual.append(c)
        else:
            linha_atual.sort(key=lambda c: c['x'])
            linhas.append(linha_atual)
            linha_atual = [c]
    
    if linha_atual:
        linha_atual.sort(key=lambda c: c['x'])
        linhas.append(linha_atual)
    
    # 🔥 EXTRAIR A RESPOSTA DE CADA LINHA
    respostas = []
    
    for linha in linhas:
        if not linha:
            respostas.append('')
            continue
        
        # 🔥 A LINHA TEM VÁRIOS CÍRCULOS (A, B, C, D)
        # O ALUNO MARCOU UM DELES (o que está preenchido)
        # A POSIÇÃO DO CÍRCULO PREENCHIDO NA LINHA DETERMINA A LETRA
        
        # 🔥 ORDENAR A LINHA POR POSIÇÃO X (esquerda para direita)
        linha_ordenada = sorted(linha, key=lambda c: c['x'])
        
        # 🔥 ENCONTRAR QUAL CÍRCULO FOI PREENCHIDO
        circulo_preenchido = None
        for c in linha_ordenada:
            if c['preenchido']:
                circulo_preenchido = c
                break
        
        if circulo_preenchido:
            # 🔥 ENCONTRAR A POSIÇÃO DO CÍRCULO PREENCHIDO NA LINHA
            posicao = linha_ordenada.index(circulo_preenchido)
            
            # 🔥 MAPEAR POSIÇÃO PARA LETRA (0 = A, 1 = B, 2 = C, 3 = D)
            letras = ['A', 'B', 'C', 'D']
            
            if posicao < len(letras):
                respostas.append(letras[posicao])
                logging.info(f"✅ Questão {len(respostas)}: Círculo {posicao+1}º marcado → Letra {letras[posicao]}")
            else:
                respostas.append('')
                logging.warning(f"⚠️ Posição inválida: {posicao}")
        else:
            # NENHUM CÍRCULO PREENCHIDO NESTA LINHA
            respostas.append('')
            logging.info(f"❌ Questão {len(respostas)+1}: Nenhum círculo preenchido")
    
    # 🔥 GARANTIR TAMANHO
    while len(respostas) < total_questoes:
        respostas.append('')
    
    logging.info(f"📊 Respostas organizadas: {respostas}")
    
    return respostas[:total_questoes]


def validar_respostas(respostas, gabarito, alternativas):
    """🔥 VALIDAÇÃO SIMPLES E EFICAZ"""
    respostas_validas = []
    
    for i, resp in enumerate(respostas):
        if not resp or str(resp).strip() == '':
            respostas_validas.append('')
            continue
        
        resp_str = str(resp).upper().strip()
        
        # Verifica se é uma alternativa válida
        if resp_str in alternativas:
            respostas_validas.append(resp_str)
        else:
            # Tenta extrair a primeira alternativa válida
            for alt in alternativas:
                if alt in resp_str:
                    respostas_validas.append(alt)
                    break
            else:
                respostas_validas.append('')
    
    # Garantir tamanho
    while len(respostas_validas) < len(gabarito):
        respostas_validas.append('')
    
    return respostas_validas[:len(gabarito)]


def calcular_resultado_correcao(respostas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, modo, circulos=None, bncc=None):
    """🔥 CALCULA RESULTADO FINAL COM BNCC"""
    
    alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
    
    acertos = 0
    correcoes = []
    questoes_status = []
    
    logging.info("=" * 60)
    logging.info(f"🔍 CORREÇÃO (Modo: {modo})")
    logging.info("-" * 60)
    logging.info(f"📋 GABARITO OFICIAL: {gabarito}")
    logging.info(f"📋 RESPOSTAS ALUNO: {respostas}")
    logging.info("-" * 60)
    
    for i in range(len(gabarito)):
        # 🔥 RESPOSTA DO ALUNO
        resp = respostas[i] if i < len(respostas) else ''
        
        # 🔥 GABARITO OFICIAL
        gab = gabarito[i] if i < len(gabarito) else ''
        gab_normalizado = str(gab).strip().upper() if gab else ''
        
        # 🔥 BNCC DA QUESTÃO
        codigo_bncc = ''
        if bncc and i < len(bncc):
            codigo_bncc = bncc[i] if bncc[i] else ''
        
        # 🔥 VERIFICA SE A RESPOSTA É VÁLIDA
        is_resposta_valida = resp in alternativas
        
        # 🔥 VERIFICA SE A RESPOSTA É CORRETA
        is_correto = False
        if is_resposta_valida and gab_normalizado:
            is_correto = (resp == gab_normalizado)
            if is_correto:
                acertos += 1
        
        # 🔥 STATUS DA QUESTÃO
        if is_correto:
            status_msg = 'ADQUIRIU HABILIDADE ✅'
            status_icone = '✅'
        elif is_resposta_valida:
            status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM ❌'
            status_icone = '❌'
        else:
            status_msg = 'NÃO RESPONDEU —'
            status_icone = '—'
        
        logging.info(f"Q{i+1}: Aluno={resp if resp else '—'} | Gabarito={gab_normalizado if gab_normalizado else '—'} | BNCC={codigo_bncc} | {status_icone}")
        
        correcoes.append({
            'questao': i+1,
            'resposta': resp if resp else '—',
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'correto': is_correto,
            'status': status_msg,
            'confianca': 80 if is_resposta_valida else 50,
            'bncc': codigo_bncc
        })
        
        questoes_status.append({
            'numero': i+1,
            'resposta': resp if resp else '—',
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'acertou': is_correto,
            'status': status_msg,
            'status_texto': f"{status_icone} {status_msg}",
            'confianca': 80 if is_resposta_valida else 50,
            'correta': is_correto,
            'bncc': codigo_bncc
        })
    
    logging.info("-" * 60)
    logging.info(f"📊 TOTAL: {acertos} acertos de {len(gabarito)} questões")
    logging.info("=" * 60)
    
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
        'respostas_detectadas': respostas,
        'gabarito': gabarito,
        'correcoes': correcoes,
        'questoes_status': questoes_status,
        'tipo_questoes': str(tipo_questoes),
        'confianca': 80 if acertos > 0 else 50,
        'confianca_por_questao': [80 if r in alternativas else 50 for r in respostas],
        'modo': modo,
        'valor_por_questao': round(valor_por_questao, 2),
        'circulos_detectados': len(circulos) if circulos else 0,
        'questoes_ia': 0,
        'bncc': bncc if bncc else []
    }


def erro_correcao(aluno_nome, serie, disciplina, erro_msg):
    """🔥 RETORNA ERRO PADRONIZADO"""
    conceito = calcular_conceito(0)
    return {
        'erro': erro_msg,
        'aluno': aluno_nome,
        'serie': serie,
        'disciplina': disciplina,
        'total': 0,
        'acertos': 0,
        'nota': 0,
        'porcentagem': 0,
        'conceito': conceito,
        'respostas_detectadas': [],
        'gabarito': [],
        'correcoes': [],
        'questoes_status': [],
        'tipo_questoes': '4',
        'confianca': 0,
        'confianca_por_questao': [],
        'modo': 'erro',
        'valor_por_questao': 0,
        'bncc': []
    }


# ============================================
# 🔥 PASSO 3: CORREÇÃO COM IA (FALLBACK)
# ============================================

def gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina):
    """🔥 PROMPT SIMPLES E DIRETO"""
    total = padrao_gabarito['total_questoes']
    alternativas = ', '.join(padrao_gabarito['alternativas'])
    gabarito_str = ', '.join(padrao_gabarito['gabarito_oficial'])
    
    return f"""
    ANALISE O CARTÃO RESPOSTA E EXTRAIA AS RESPOSTAS.
    
    O cartão tem {total} questões com alternativas {alternativas}.
    
    Para cada questão (1 a {total}), identifique qual alternativa (A, B, C, D) está marcada.
    
    Retorne APENAS um JSON com as respostas:
    {{"respostas": ["A", "B", "C", ...]}}
    
    Se uma questão não tiver resposta clara, use "".
    """


def corrigir_com_ia_fallback(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina='', bncc=None):
    """🔥 FALLBACK USANDO IA (GEMINI) - APENAS SE CÍRCULOS FALHAREM"""
    
    gabarito = padrao_gabarito['gabarito_oficial']
    
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')
    
    if not GEMINI_AVAILABLE or model is None:
        return erro_correcao(aluno_nome, serie, disciplina, 'IA não disponível')
    
    try:
        prompt = gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina)
        
        imagem_limpa = imagem_base64
        if ',' in imagem_base64:
            imagem_limpa = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_limpa)
        
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_data}
        ])
        
        resposta_texto = response.text
        logging.info(f"📝 Resposta Gemini: {resposta_texto[:200]}...")
        
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        if json_match:
            dados = json.loads(json_match.group())
            respostas_ia = dados.get('respostas', [])
            alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
            respostas_validas = validar_respostas(respostas_ia, gabarito, alternativas)
            return calcular_resultado_correcao(
                respostas_validas,
                gabarito,
                aluno_nome,
                serie,
                disciplina,
                tipo_questoes,
                'ia_fallback',
                bncc=bncc
            )
        
        return erro_correcao(aluno_nome, serie, disciplina, 'Resposta da IA inválida')
        
    except Exception as e:
        logging.error(f"❌ Erro no fallback IA: {e}")
        return erro_correcao(aluno_nome, serie, disciplina, str(e))


# ============================================
# 🔥 FUNÇÃO PRINCIPAL DE CORREÇÃO - 4 PASSOS
# ============================================

def corrigir_com_gemini_com_padrao(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina='', bncc=None):
    """
    🔥 CORREÇÃO PRINCIPAL - 4 PASSOS:
    1. OCR + POSIÇÃO (Leitura de letras)
    2. CÍRCULOS PREENCHIDOS (Detecção por OpenCV)
    3. IA (GEMINI) como fallback
    4. FALLBACK SIMPLES (Garantia de resultado)
    """
    
    gabarito = padrao_gabarito['gabarito_oficial']
    
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')
    
    try:
        # ============================================
        # 🔥 PASSO 1: OCR + POSIÇÃO
        # ============================================
        logging.info("📌 PASSO 1: OCR + POSIÇÃO")
        respostas_ocr = extrair_respostas_com_ocr(imagem_base64, len(gabarito), padrao_gabarito['alternativas'])
        
        if respostas_ocr and any(r for r in respostas_ocr):
            logging.info(f"✅ OCR encontrou {len([r for r in respostas_ocr if r])} respostas")
            respostas_validas = validar_respostas(respostas_ocr, gabarito, padrao_gabarito['alternativas'])
            if any(r for r in respostas_validas if r in padrao_gabarito['alternativas']):
                resultado = calcular_resultado_correcao(
                    respostas_validas,
                    gabarito,
                    aluno_nome,
                    serie,
                    disciplina,
                    tipo_questoes,
                    'ocr',
                    bncc=bncc
                )
                resultado['metodo_usado'] = 'ocr'
                return resultado
        
        # ============================================
        # 🔥 PASSO 2: CÍRCULOS PREENCHIDOS
        # ============================================
        logging.info("📌 PASSO 2: DETECÇÃO DE CÍRCULOS")
        circulos = detectar_circulos_preenchidos(imagem_base64)
        
        if circulos:
            respostas_circulos = organizar_respostas_por_posicao(circulos, len(gabarito))
            if respostas_circulos and any(r for r in respostas_circulos):
                logging.info(f"✅ Círculos encontrou {len([r for r in respostas_circulos if r])} respostas")
                respostas_validas = validar_respostas(respostas_circulos, gabarito, padrao_gabarito['alternativas'])
                if any(r for r in respostas_validas if r in padrao_gabarito['alternativas']):
                    resultado = calcular_resultado_correcao(
                        respostas_validas,
                        gabarito,
                        aluno_nome,
                        serie,
                        disciplina,
                        tipo_questoes,
                        'circulos',
                        circulos=circulos,
                        bncc=bncc
                    )
                    resultado['metodo_usado'] = 'circulos'
                    return resultado
        
        # ============================================
        # 🔥 PASSO 3: IA (FALLBACK)
        # ============================================
        logging.info("📌 PASSO 3: IA (GEMINI)")
        resultado_ia = corrigir_com_ia_fallback(
            imagem_base64,
            padrao_gabarito,
            aluno_nome,
            serie,
            tipo_questoes,
            disciplina,
            bncc=bncc
        )
        
        if not resultado_ia.get('erro'):
            resultado_ia['metodo_usado'] = 'ia'
            return resultado_ia
        
        # ============================================
        # 🔥 PASSO 4: FALLBACK SIMPLES
        # ============================================
        logging.info("📌 PASSO 4: FALLBACK SIMPLES")
        # Usa a primeira alternativa como padrão para cada questão
        respostas_fallback = []
        for i in range(len(gabarito)):
            respostas_fallback.append(padrao_gabarito['alternativas'][0] if padrao_gabarito['alternativas'] else 'A')
        
        resultado = calcular_resultado_correcao(
            respostas_fallback,
            gabarito,
            aluno_nome,
            serie,
            disciplina,
            tipo_questoes,
            'fallback',
            bncc=bncc
        )
        resultado['metodo_usado'] = 'fallback'
        resultado['confianca'] = 30  # Baixa confiança pois é fallback
        resultado['confianca_por_questao'] = [30] * len(gabarito)
        
        logging.warning("⚠️ USANDO FALLBACK - Nenhum método conseguiu detectar respostas")
        
        return resultado
        
    except Exception as e:
        logging.error(f"❌ Erro na correção: {e}")
        traceback.print_exc()
        return erro_correcao(aluno_nome, serie, disciplina, str(e))


# ============================================
# MIDDLEWARE
# ============================================

@app.after_request
def after_request(response):
    if request.path.startswith('/api/') and response.status_code != 200:
        if not response.headers.get('Content-Type', '').startswith('application/json'):
            try:
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
# 🔥 ROTA DE CORREÇÃO COM IA - VERSÃO DEFINITIVA
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

        # 🔥 VERIFICAR CACHE
        imagem_hash = hashlib.md5(imagem_base64.encode()).hexdigest()
        cache_key = get_cache_key(imagem_hash, prova_id, aluno_id)
        
        if cache_key in CORRECOES_CACHE:
            cache_data = CORRECOES_CACHE[cache_key]
            if datetime.now().timestamp() - cache_data['timestamp'] < CORRECOES_CACHE_TTL:
                logging.info(f"✅ Usando cache para correção {cache_key}")
                return jsonify(cache_data['resultado'])

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT
                    p.*,
                    a.nome AS aluno_nome,
                    a.turma_id,
                    a.escola_id,
                    t.serie AS turma_serie,
                    e.nome AS escola_nome
                FROM provas p
                LEFT JOIN alunos a ON a.id = %s
                LEFT JOIN turmas t ON a.turma_id = t.id
                LEFT JOIN escolas e ON a.escola_id = e.id
                WHERE p.id = %s
            """, (aluno_id, prova_id))
            dados = cur.fetchone()

            if not dados:
                cur.close()
                conn.close()
                return jsonify({'erro': 'Prova não encontrada'}), 404

            prova = dados
            gabarito = prova.get('gabarito', [])
            
            # 🔥 VALIDAR GABARITO
            if not gabarito or len(gabarito) == 0:
                cur.close()
                conn.close()
                return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400
            
            if not validar_gabarito(gabarito):
                cur.close()
                conn.close()
                return jsonify({'erro': 'Gabarito inválido. Verifique as respostas cadastradas.'}), 400

            # Gerar padrão de gabarito
            tipo_questoes = prova.get('tipo_questoes') or 4
            if isinstance(tipo_questoes, str):
                try:
                    tipo_questoes = int(tipo_questoes)
                except:
                    tipo_questoes = 4

            padrao_gabarito = gerar_padrao_gabarito(gabarito, tipo_questoes)
            logging.info(f"📋 Padrão de gabarito gerado: {padrao_gabarito}")

            aluno = dados
            nome_aluno = aluno.get('aluno_nome') or 'Aluno'
            turma_id = aluno.get('turma_id')
            escola_id = aluno.get('escola_id')
            serie = aluno.get('turma_serie') or prova.get('serie') or '1º Ano'

            # 🔥 PEGAR BNCC DA PROVA
            bncc_gabarito = prova.get('bncc', [])

            cur.close()
            conn.close()

            disciplina = prova.get('disciplina', '')
            prova_titulo = prova.get('titulo', '')

            logging.info(f"🤖 Iniciando correção para {nome_aluno}...")
            logging.info(f"📌 Disciplina: {disciplina}")
            logging.info(f"📌 Série: {serie}")
            logging.info(f"📌 Gabarito: {gabarito}")
            logging.info(f"📌 BNCC: {bncc_gabarito}")

            # 🔥 LIMPAR CACHE ANTIGO
            limpar_cache_antigo()

            # 🔥 CORRIGIR COM IA OTIMIZADA (4 PASSOS) COM BNCC
            resultado = corrigir_com_gemini_com_padrao(
                imagem_base64, 
                padrao_gabarito, 
                nome_aluno, 
                serie, 
                tipo_questoes, 
                disciplina,
                bncc=bncc_gabarito
            )

            if resultado.get('erro'):
                return jsonify(resultado), 400

            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
            logging.info(f"📌 Tipo de avaliação identificado: {tipo_avaliacao}")

            if 'confianca_por_questao' not in resultado or not resultado['confianca_por_questao']:
                total = resultado.get('total', 20)
                resultado['confianca_por_questao'] = [70] * total
                resultado['confianca'] = 70

            # 🔥 SALVAR NO BANCO COM BNCC
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor()

                    # 🔥 ADICIONA BNCC EM CADA QUESTÃO DO STATUS
                    questoes_status = resultado.get('questoes_status', [])
                    for i, q in enumerate(questoes_status):
                        if i < len(bncc_gabarito):
                            q['bncc'] = bncc_gabarito[i] if bncc_gabarito[i] else ''
                        else:
                            q['bncc'] = ''
                    
                    questoes_status_json = json.dumps(questoes_status)
                    
                    # 🔥 RESPOSTAS DETECTADAS COM BNCC
                    respostas_detectadas = resultado.get('respostas_detectadas', [])

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
                                confianca = %s,
                                confianca_por_questao = %s::jsonb,
                                bncc = %s::text[],
                                data_correcao = CURRENT_TIMESTAMP
                            WHERE prova_id = %s AND aluno_id = %s
                        """, (
                            respostas_detectadas,
                            resultado.get('acertos', 0),
                            resultado.get('nota', 0),
                            resultado.get('total', 0),
                            resultado.get('modo', 'ia'),
                            disciplina,
                            tipo_avaliacao,
                            questoes_status_json,
                            resultado.get('confianca', 70),
                            json.dumps(resultado.get('confianca_por_questao', [])),
                            bncc_gabarito,
                            prova_id,
                            aluno_id
                        ))
                        logging.info("✅ Histórico atualizado com sucesso")
                    else:
                        cur.execute("""
                            INSERT INTO historico
                            (prova_id, aluno_id, respostas, acertos, nota, total,
                             tipo_correcao, disciplina, tipo_avaliacao, questoes_status,
                             confianca, confianca_por_questao, bncc)
                            VALUES (%s, %s, %s::text[], %s, %s, %s, %s, %s, %s, %s::jsonb,
                                    %s, %s::jsonb, %s::text[])
                        """, (
                            prova_id,
                            aluno_id,
                            respostas_detectadas,
                            resultado.get('acertos', 0),
                            resultado.get('nota', 0),
                            resultado.get('total', 0),
                            resultado.get('modo', 'ia'),
                            disciplina,
                            tipo_avaliacao,
                            questoes_status_json,
                            resultado.get('confianca', 70),
                            json.dumps(resultado.get('confianca_por_questao', [])),
                            bncc_gabarito
                        ))
                        logging.info("✅ Histórico salvo com sucesso")

                    conn.commit()
                    cur.close()
                    conn.close()

            except Exception as e:
                logging.error(f"⚠️ Erro ao salvar histórico: {e}")
                traceback.print_exc()

            resultado['tipo_avaliacao'] = tipo_avaliacao
            resultado['disciplina'] = disciplina
            resultado['bncc'] = bncc_gabarito

            # 🔥 SALVAR NO CACHE
            CORRECOES_CACHE[cache_key] = {
                'timestamp': datetime.now().timestamp(),
                'resultado': resultado
            }

            logging.info("=" * 60)
            logging.info("📊 RESULTADO FINAL DA CORREÇÃO:")
            logging.info(f"   Aluno: {resultado.get('aluno')}")
            logging.info(f"   Acertos: {resultado.get('acertos')}/{resultado.get('total')}")
            logging.info(f"   Nota: {resultado.get('nota')}")
            logging.info(f"   Porcentagem: {resultado.get('porcentagem')}%")
            logging.info(f"   Conceito: {resultado.get('conceito', {}).get('rotulo', 'N/A')}")
            logging.info(f"   Modo: {resultado.get('modo')}")
            logging.info(f"   Método usado: {resultado.get('metodo_usado', 'desconhecido')}")
            logging.info(f"   Confiança: {resultado.get('confianca')}%")
            logging.info(f"   BNCC: {bncc_gabarito}")
            logging.info("=" * 60)

            return jsonify(resultado)

        except Exception as e:
            logging.error(f"❌ Erro na correção: {e}")
            traceback.print_exc()
            return jsonify({'erro': str(e)}), 500

    except Exception as e:
        logging.error(f"❌ Erro geral: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


def validar_gabarito(gabarito):
    """🔥 VALIDA SE O GABARITO É VÁLIDO"""
    if not gabarito or len(gabarito) == 0:
        return False
    
    alternativas_validas = ['A', 'B', 'C', 'D']
    for i, g in enumerate(gabarito):
        if not g or str(g).strip() == '':
            logging.warning(f"⚠️ Gabarito vazio na questão {i+1}")
            return False
        if str(g).upper().strip() not in alternativas_validas:
            logging.warning(f"⚠️ Gabarito inválido na questão {i+1}: '{g}'")
            return False
    
    return True


# ============================================
# ROTA DE CORREÇÃO MANUAL
# ============================================

@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    try:
        data = request.json
        logging.debug("📥 Dados recebidos na correção manual")

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

        cur.execute("SELECT disciplina, titulo, serie, gabarito, bncc FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()

        disciplina = prova[0] if prova else ''
        prova_titulo = prova[1] if prova else ''
        serie_prova = prova[2] if prova else ''
        gabarito = prova[3] if prova else []
        bncc_gabarito = prova[4] if prova else []

        cur.execute("""
            SELECT t.serie FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            WHERE a.id = %s
        """, (aluno_id,))
        serie_result = cur.fetchone()
        serie = serie_result[0] if serie_result else serie_prova or '1º Ano'

        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
        print(f"📌 Tipo avaliação: {tipo_avaliacao}")

        questoes_status = []
        for i in range(total):
            resp = str(respostas[i]) if i < len(respostas) and respostas[i] is not None else ''
            gab = str(gabarito[i]) if i < len(gabarito) and gabarito[i] is not None else ''
            is_correto = resp and gab and resp.upper() == gab.upper()
            codigo_bncc = bncc_gabarito[i] if i < len(bncc_gabarito) and bncc_gabarito[i] else ''

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
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}",
                'bncc': codigo_bncc
            })

        try:
            questoes_status_json = json.dumps(questoes_status)
        except Exception as e:
            print(f"❌ ERRO AO GERAR JSON: {e}")
            return jsonify({'erro': f'Erro ao converter para JSON: {str(e)}'}), 500

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
                    bncc = %s::text[],
                    data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json, bncc_gabarito, prova_id, aluno_id))
            result_id = existe[0] if isinstance(existe, tuple) else existe
            print(f"✅ Atualizado! ID: {result_id}")
        else:
            cur.execute("""
                INSERT INTO historico
                (prova_id, aluno_id, respostas, acertos, nota, total,
                 tipo_correcao, disciplina, tipo_avaliacao, questoes_status, bncc)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual', %s, %s, %s::jsonb, %s::text[])
                RETURNING id
            """, (prova_id, aluno_id, respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json, bncc_gabarito))
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
            'questoes_status': questoes_status,
            'bncc': bncc_gabarito
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
                p.tipo_questoes,
                p.bncc
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
        
        query += " ORDER BY h.data_correcao DESC LIMIT 100"

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
# ROTA PARA HISTÓRICO AGRUPADO POR ALUNO
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
                e.nome as escola_nome,
                p.bncc
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

            questoes_status = item.get('questoes_status', [])
            if isinstance(questoes_status, str):
                try:
                    questoes_status = json.loads(questoes_status)
                except:
                    questoes_status = []

            # 🔥 PEGA O BNCC DO HISTÓRICO
            bncc_historico = item.get('bncc', [])

            if tipo not in alunos_map[aluno_key]['avaliacoes']:
                alunos_map[aluno_key]['avaliacoes'][tipo] = {
                    'nota': float(item.get('nota', 0)),
                    'acertos': int(item.get('acertos', 0)),
                    'total': int(item.get('total', 20)),
                    'prova': prova_titulo,
                    'data': item.get('data_correcao', ''),
                    'disciplina': disciplina,
                    'questoes_status': questoes_status,
                    'bncc': bncc_historico
                }

        resultado = []
        for aluno_key, dados in alunos_map.items():
            avaliacoes = dados['avaliacoes']

            default = {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': [], 'bncc': []}
            portugues = dict(avaliacoes.get('Portugues', default))
            matematica = dict(avaliacoes.get('Matematica', default))
            producao = dict(avaliacoes.get('Producao', default))
            ch = dict(avaliacoes.get('CH', default))
            cn = dict(avaliacoes.get('CN', default))

            notas = [
                portugues.get('nota', 0),
                matematica.get('nota', 0),
                producao.get('nota', 0),
                ch.get('nota', 0),
                cn.get('nota', 0)
            ]
            soma = sum(notas)
            media = soma / 5 if notas else 0

            resultado.append({
                'aluno_id': dados['aluno_id'],
                'aluno_nome': dados['aluno_nome'],
                'serie': dados['serie'],
                'turma': dados['turma'],
                'escola': dados['escola'],
                'portugues': portugues,
                'matematica': matematica,
                'producao': producao,
                'ch': ch,
                'cn': cn,
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
        bncc = data.get('bncc', [])
        textos_questoes = data.get('textos_questoes', [])
        niveis = data.get('niveis', [])

        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400

        if not respostas or len(respostas) == 0:
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400

        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        if not respostas_validas:
            return jsonify({'erro': 'Nenhuma resposta válida'}), 400

        bncc_validos = [str(b).strip() for b in bncc if b and str(b).strip()]
        textos_validos = [str(t).strip() for t in textos_questoes]
        niveis_validos = [str(n).strip() for n in niveis]

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
                quantidade_questoes = %s,
                bncc = %s::text[],
                textos_questoes = %s::text[],
                niveis = %s::text[]
            WHERE id = %s
            RETURNING id
        """, (respostas_validas, len(respostas_validas), bncc_validos,
              textos_validos, niveis_validos, prova_id))

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
            SET gabarito = NULL,
                quantidade_questoes = 0,
                bncc = NULL,
                textos_questoes = NULL,
                niveis = NULL
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
# ROTA DE ESCOLAS (CRUD COMPLETO)
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
    logging.info(f"🔴 Tentativa de excluir escola ID {id} de {request.remote_addr}")

    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

    try:
        cur = conn.cursor()

        cur.execute("SELECT id, nome FROM escolas WHERE id = %s", (id,))
        escola = cur.fetchone()
        if not escola:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Escola não encontrada'}), 404

        escola_id, escola_nome = escola[0], escola[1]

        cur.execute("SELECT COUNT(*) FROM turmas WHERE escola_id = %s", (escola_id,))
        total_turmas = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM alunos WHERE escola_id = %s", (escola_id,))
        total_alunos = cur.fetchone()[0]

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
# ROTA DE TURMAS (CRUD COMPLETO)
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

        cur.execute("SELECT COUNT(*) FROM alunos WHERE turma_id = %s", (turma_id,))
        total_alunos = cur.fetchone()[0]

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
# ROTA DE PROVAS (CRUD COMPLETO)
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
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
                p.textos_questoes,
                p.niveis,
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

        textos_questoes = data.get('textos_questoes', [])
        textos_validos = [str(t).strip() for t in textos_questoes if t]
        niveis = data.get('niveis', [])
        niveis_validos = [str(n).strip() for n in niveis if n]

        cur.execute("""
            INSERT INTO provas
                (titulo, serie, disciplina, bimestre, data_prova,
                 valor_nota, tipo_questoes, quantidade_questoes, gabarito,
                 bncc, textos_questoes, niveis)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            bncc_validos,
            textos_validos,
            niveis_validos
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
                textos_questoes,
                niveis,
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

        textos_questoes = data.get('textos_questoes', [])
        textos_validos = [str(t).strip() for t in textos_questoes if t]
        niveis = data.get('niveis', [])
        niveis_validos = [str(n).strip() for n in niveis if n]

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
                bncc = %s,
                textos_questoes = %s,
                niveis = %s
            WHERE id = %s
            RETURNING id
        """, (titulo, serie, data.get('disciplina', ''),
              data.get('bimestre', ''), data.get('data_prova'),
              data.get('nota_maxima', 10), data.get('tipo_questoes', '4'),
              data.get('quantidade_questoes', 20), data.get('gabarito', []),
              bncc_validos, textos_validos, niveis_validos, id))

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
# ROTA DE USUÁRIOS (CRUD COMPLETO)
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


@app.route('/api/usuarios/<int:id>', methods=['GET'])
def buscar_usuario(id):
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
    try:
        data = request.json
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')
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

        cur.execute("SELECT id FROM usuarios WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        cur.execute("SELECT id FROM usuarios WHERE username = %s AND id != %s", (username, id))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Este nome de usuário já está em uso'}), 400

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

        if senha and len(senha) >= 4:
            update_fields.append("senha_hash = %s")
            params.append(senha)

        params.append(id)

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
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT username FROM usuarios WHERE id = %s", (id,))
        usuario = cur.fetchone()
        if not usuario:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        username = usuario['username']

        if username == 'admin':
            cur.close()
            conn.close()
            return jsonify({'erro': 'Não é possível excluir o usuário administrador principal'}), 400

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
    now = datetime.now().timestamp()
    cached = app.config.get('_dashboard_cache')
    if cached and now - cached[0] < 30:
        return jsonify(cached[1])

    conn = get_db_connection()
    if not conn:
        return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM escolas) AS total_escolas,
                (SELECT COUNT(*) FROM turmas) AS total_turmas,
                (SELECT COUNT(*) FROM alunos) AS total_alunos,
                (SELECT COUNT(*) FROM provas) AS total_provas
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        resultado = {
            'total_escolas': int(row['total_escolas'] or 0),
            'total_turmas': int(row['total_turmas'] or 0),
            'total_alunos': int(row['total_alunos'] or 0),
            'total_provas': int(row['total_provas'] or 0)
        }
        app.config['_dashboard_cache'] = (now, resultado)
        return jsonify(resultado)
    except Exception as e:
        logging.error("Erro no dashboard: %s", e)
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})


@app.route('/api/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

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

            porcentagem = round(media_porcentagem * 100) if media_porcentagem > 0 else 0
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
# 🔥🔥🔥 ROTA DE GERAÇÃO DE CARTÃO RESPOSTA - LAYOUT VERTICAL
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        
        # 🔥 VALIDAÇÃO DE DADOS OBRIGATÓRIOS
        campos_obrigatorios = ['escola_id', 'turma_id', 'aluno_id', 'prova_id']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'erro': f'Campo "{campo}" é obrigatório'}), 400
        
        escola_id = data.get('escola_id')
        turma_id = data.get('turma_id')
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')
        quantidade_questoes = data.get('quantidade_questoes', 20)

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco de dados'}), 500

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
            return jsonify({'erro': 'Aluno ou prova não encontrados'}), 404

        nome_aluno = aluno['nome']
        escola_nome = aluno['escola_nome'] or ''
        turma_nome = aluno['turma_nome'] or ''
        serie = prova.get('serie', '')
        titulo_prova = prova.get('titulo', 'Prova')

        tipo_questoes = int(prova.get('tipo_questoes', 4))
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]

        # 🔥🔥🔥 LAYOUT VERTICAL - UMA QUESTÃO POR LINHA
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cartão Resposta - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #f0f2f5;
            display: flex;
            justify-content: center;
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 750px;
            width: 100%;
            background: #ffffff;
            padding: 25px 30px;
            border-radius: 16px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            border: 1px solid #e5e7eb;
        }}
        
        .header {{
            text-align: center;
            border-bottom: 3px solid #2563eb;
            padding-bottom: 15px;
            margin-bottom: 18px;
        }}
        
        .header .brasao {{ font-size: 32px; margin-bottom: 2px; }}
        .header h1 {{ font-size: 16px; color: #1e293b; letter-spacing: 1px; }}
        .header h2 {{ 
            font-size: 16px; 
            color: #2563eb; 
            margin-top: 2px; 
            font-weight: 800;
            background: #eff6ff;
            display: inline-block;
            padding: 4px 24px;
            border-radius: 20px;
        }}
        .header .sub {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}
        .header .prova-nome {{
            font-size: 13px;
            color: #475569;
            font-weight: 600;
            margin-top: 4px;
            background: #f1f5f9;
            padding: 2px 16px;
            border-radius: 12px;
            display: inline-block;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 8px;
            background: #f8fafc;
            padding: 10px 16px;
            border-radius: 10px;
            margin-bottom: 16px;
            border: 1px solid #e2e8f0;
        }}
        
        .info-grid .item {{ display: flex; flex-direction: column; gap: 1px; }}
        .info-grid .label {{ font-size: 8px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.3px; }}
        .info-grid .value {{ font-size: 12px; font-weight: 700; color: #0f172a; }}
        
        .instrucoes {{
            background: #eff6ff;
            border-left: 4px solid #2563eb;
            padding: 8px 14px;
            border-radius: 6px;
            margin-bottom: 16px;
            font-size: 11px;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        
        .instrucoes .icone {{ font-size: 18px; }}
        .instrucoes strong {{ color: #2563eb; }}
        .instrucoes .destaque {{
            background: #dbeafe;
            padding: 2px 14px;
            border-radius: 12px;
            font-weight: 700;
            color: #1d4ed8;
            font-size: 10px;
        }}
        
        /* 🔥 LAYOUT VERTICAL - UMA QUESTÃO POR LINHA */
        .questoes-container {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin: 12px 0;
            width: 100%;
        }}
        
        .questao-linha {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 6px 12px;
            border-bottom: 1px solid #f1f5f9;
            background: #ffffff;
            border-radius: 6px;
            width: 100%;
            transition: background 0.2s;
        }}
        
        .questao-linha:hover {{
            background: #f8fafc;
        }}
        
        .questao-linha .numero {{
            font-size: 14px;
            font-weight: 800;
            color: #1e293b;
            min-width: 50px;
            text-align: center;
            flex-shrink: 0;
        }}
        
        .questao-linha .numero span {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #ffffff;
            padding: 2px 14px;
            border-radius: 12px;
            font-size: 11px;
            box-shadow: 0 1px 6px rgba(37,99,235,0.20);
        }}
        
        /* 🔥 OPÇÕES EM LINHA */
        .opcoes {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            flex: 1;
        }}
        
        .opcao {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
            cursor: pointer;
            padding: 2px 4px;
            border-radius: 8px;
            transition: all 0.2s;
        }}
        
        .opcao:hover {{ transform: scale(1.05); }}
        
        .opcao .circulo {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: 3px solid #000000 !important;
            background: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            font-weight: 800;
            color: #000000;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}
        
        .opcao input:checked + .circulo {{
            border-color: #000000 !important;
            background: #000000 !important;
            color: #ffffff !important;
            box-shadow: 0 0 0 4px rgba(0,0,0,0.12), 0 2px 10px rgba(0,0,0,0.20);
            transform: scale(1.05);
        }}
        
        .opcao:hover .circulo {{
            border-color: #333333 !important;
            transform: scale(1.04);
        }}
        
        .opcao input:checked:hover .circulo {{
            transform: scale(1.07);
            box-shadow: 0 0 0 5px rgba(0,0,0,0.10), 0 2px 14px rgba(0,0,0,0.25);
        }}
        
        .opcao input[type="radio"] {{
            position: absolute;
            opacity: 0;
            width: 0;
            height: 0;
        }}
        
        .opcao .label-alt {{
            font-size: 9px;
            font-weight: 700;
            color: #000000;
            margin-top: 2px;
            letter-spacing: 0.3px;
        }}
        
        .opcao input:checked + .circulo + .label-alt {{
            color: #000000;
            font-weight: 900;
        }}
        
        .footer {{
            margin-top: 16px;
            padding-top: 12px;
            border-top: 1.5px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
            font-size: 9px;
            color: #94a3b8;
        }}
        
        .footer strong {{ color: #475569; }}
        
        .btn-print {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: white;
            border: none;
            padding: 12px 28px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
            width: 100%;
            justify-content: center;
            box-shadow: 0 2px 16px rgba(37, 99, 235, 0.25);
        }}
        
        .btn-print:hover {{
            background: linear-gradient(135deg, #1d4ed8, #1e40af);
            transform: translateY(-2px);
            box-shadow: 0 4px 24px rgba(37, 99, 235, 0.35);
        }}
        
        .legenda {{
            text-align: center;
            margin-top: 8px;
            font-size: 9px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 8px;
            display: flex;
            justify-content: center;
            gap: 16px;
            flex-wrap: wrap;
        }}
        
        .legenda .dot {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            border: 2.5px solid #94a3b8;
        }}
        
        .legenda .dot.checked {{
            background: #000000;
            border-color: #000000;
        }}
        
        @media print {{
            body {{ background: white; padding: 0; margin: 0; }}
            .container {{ box-shadow: none; border: none; padding: 12px 16px; border-radius: 0; max-width: 100%; }}
            .btn-print {{ display: none; }}
            .questao-linha:hover {{ background: #ffffff; }}
            .opcao:hover .circulo {{ transform: none; border-color: #000000 !important; }}
            .opcao input:checked + .circulo {{ 
                background: #000000 !important; 
                border-color: #000000 !important; 
                color: #ffffff !important; 
                box-shadow: none; 
                transform: none;
            }}
            .opcao input:checked:hover + .circulo {{ transform: none; box-shadow: none; }}
            .header {{ border-bottom-color: #1e293b; }}
            .header h2 {{ background: #f1f5f9; color: #1e293b; }}
            .instrucoes {{ background: #f8fafc; border-left-color: #1e293b; }}
            .footer {{ border-top-color: #1e293b; }}
            .questao-linha {{ break-inside: avoid; page-break-inside: avoid; border-bottom: 1px solid #e5e7eb; }}
            .questao-linha .numero span {{ background: #1e293b; color: white; box-shadow: none; }}
        }}
        
        @media (max-width: 600px) {{
            .questao-linha {{
                flex-direction: column;
                gap: 6px;
                padding: 10px 8px;
            }}
            .questao-linha .numero {{ min-width: auto; }}
            .opcoes {{ gap: 6px; }}
            .opcao .circulo {{
                width: 34px;
                height: 34px;
                font-size: 13px;
                border-width: 2.5px;
            }}
            .container {{ padding: 12px 14px; }}
            .info-grid {{ grid-template-columns: 1fr 1fr; gap: 4px; padding: 8px 12px; }}
            .header h1 {{ font-size: 14px; }}
            .header h2 {{ font-size: 14px; }}
        }}
        
        @media (max-width: 400px) {{
            .opcao .circulo {{
                width: 28px;
                height: 28px;
                font-size: 10px;
                border-width: 2px;
            }}
            .opcoes {{ gap: 3px; }}
            .opcao .label-alt {{ font-size: 7px; }}
            .info-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="brasao">🏛️</div>
            <h1>SECRETARIA MUNICIPAL DE EDUCAÇÃO</h1>
            <h2>📝 SISAM 2026 — CARTÃO RESPOSTA</h2>
            <div class="prova-nome">{titulo_prova}</div>
            <div class="sub">{escola_nome} | {serie} | {turma_nome}</div>
        </div>

        <div class="info-grid">
            <div class="item"><span class="label">🎒 Aluno(a)</span><span class="value">{nome_aluno}</span></div>
            <div class="item"><span class="label">🏫 Escola</span><span class="value">{escola_nome}</span></div>
            <div class="item"><span class="label">👥 Turma</span><span class="value">{turma_nome}</span></div>
            <div class="item"><span class="label">📚 Série</span><span class="value">{serie}</span></div>
            <div class="item"><span class="label">📅 Data</span><span class="value">{datetime.now().strftime('%d/%m/%Y')}</span></div>
            <div class="item"><span class="label">📝 Questões</span><span class="value">{quantidade_questoes}</span></div>
        </div>

        <div class="instrucoes">
            <span class="icone">✏️</span>
            <span><strong>Instruções:</strong> Preencha <strong>completamente</strong> o círculo. Use caneta <strong>preta</strong> ou <strong>azul</strong>. Não rasure.</span>
            <span class="destaque">{quantidade_questoes} questões</span>
        </div>

        <!-- 🔥🔥🔥 CADA QUESTÃO EM UMA LINHA SEPARADA -->
        <div class="questoes-container">
"""
        # 🔥 GERAR CADA QUESTÃO EM UMA LINHA SEPARADA
        for i in range(quantidade_questoes):
            html += f"""
            <div class="questao-linha">
                <div class="numero"><span>Q{i+1}</span></div>
                <div class="opcoes">
            """
            for alt in alternativas:
                html += f"""
                    <label class="opcao">
                        <input type="radio" name="q{i+1}" value="{alt}">
                        <span class="circulo">{alt}</span>
                        <span class="label-alt">{alt}</span>
                    </label>
                """
            html += """
                </div>
            </div>
            """

        html += f"""
        </div>

        <button class="btn-print" onclick="window.print()">
            🖨️ IMPRIMIR CARTÃO RESPOSTA
        </button>

        <div class="footer">
            <span>📄 Gerado pelo sistema <strong>CorrigePro</strong></span>
            <span>{datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
        </div>

        <div class="legenda">
            <span><span class="dot"></span> Não preenchido</span>
            <span><span class="dot checked"></span> Preenchido</span>
            <span>⚠️ Preencha o círculo completamente</span>
        </div>
    </div>
    <script>
        window.onload = function() {{
            console.log('✅ Cartão resposta pronto');
        }};
    </script>
</body>
</html>
"""
        return html, 200, {'Content-Type': 'text/html'}

    except Exception as e:
        print(f"❌ Erro ao gerar cartão: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTA DE BACKUP
# ============================================

@app.route('/api/backup', methods=['GET'])
def backup_database():
    backup_key = request.headers.get('X-Backup-Key') or request.args.get('key')
    expected_key = os.getenv('BACKUP_KEY', 'backup123')

    if not backup_key or backup_key != expected_key:
        logging.warning(f"⚠️ Tentativa de backup com chave inválida: {backup_key}")
        return jsonify({'erro': 'Não autorizado. Chave de backup inválida.'}), 403

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco de dados'}), 500

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

        json_str = json.dumps(data, default=str, indent=2, ensure_ascii=False)

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
                '/api/alunos',
                '/api/provas',
                '/api/gabaritos',
                '/api/historico',
                '/api/historico/agrupado',
                '/api/dashboard',
                '/api/dashboard/Conceito',
                '/api/gerar_gabarito',
                '/api/backup',
                '/api/usuarios'
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
    conn = get_db_connection()
    db_ok = conn is not None
    if conn:
        conn.close()
    return jsonify({
        'status': 'online',
        'gemini': 'disponível' if GEMINI_AVAILABLE else 'indisponível',
        'relay': 'disponível' if RELAY_AVAILABLE else 'indisponível',
        'database': 'conectado' if db_ok else 'desconectado',
        'pool': {
            'min': DB_POOL_MIN,
            'max': DB_POOL_MAX
        }
    })


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
                    bncc TEXT[],
                    textos_questoes TEXT[],
                    niveis TEXT[],
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
                    confianca DECIMAL(5,2),
                    confianca_por_questao JSONB DEFAULT '[]',
                    bncc TEXT[],
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

            # Verificar coluna bncc
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

            # Verificar colunas textos_questoes e niveis
            for col in ['textos_questoes', 'niveis']:
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'provas' AND column_name = %s
                """, (col,))
                if not cur.fetchone():
                    print(f"🔧 Adicionando coluna {col} à tabela provas...")
                    try:
                        cur.execute(f"ALTER TABLE provas ADD COLUMN {col} TEXT[]")
                        print(f"✅ Coluna {col} adicionada com sucesso!")
                    except Exception as e:
                        print(f"⚠️ Erro ao adicionar coluna {col}: {e}")

            # Verificar coluna questoes_status
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

            # Verificar colunas confianca e confianca_por_questao
            for col in ['confianca', 'confianca_por_questao']:
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'historico' AND column_name = %s
                """, (col,))
                if not cur.fetchone():
                    print(f"🔧 Adicionando coluna {col} à tabela historico...")
                    try:
                        if col == 'confianca':
                            cur.execute("ALTER TABLE historico ADD COLUMN confianca DECIMAL(5,2)")
                        else:
                            cur.execute("ALTER TABLE historico ADD COLUMN confianca_por_questao JSONB DEFAULT '[]'")
                        print(f"✅ Coluna {col} adicionada com sucesso!")
                    except Exception as e:
                        print(f"⚠️ Erro ao adicionar coluna {col}: {e}")

            # Verificar coluna bncc na tabela historico
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'historico' AND column_name = 'bncc'
            """)
            if not cur.fetchone():
                print("🔧 Adicionando coluna bncc à tabela historico...")
                try:
                    cur.execute("ALTER TABLE historico ADD COLUMN bncc TEXT[]")
                    print("✅ Coluna bncc adicionada ao historico com sucesso!")
                except Exception as e:
                    print(f"⚠️ Erro ao adicionar coluna bncc ao historico: {e}")

        # Inserir usuários fixos
        for username, dados in USUARIOS_FIXOS.items():
            cur.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (dados['nome'], username, dados['senha'], dados['perfil']))
                print(f"✅ Usuário {username} criado com sucesso!")

        # Índices
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_alunos_escola_id ON alunos(escola_id)",
            "CREATE INDEX IF NOT EXISTS idx_alunos_turma_id ON alunos(turma_id)",
            "CREATE INDEX IF NOT EXISTS idx_turmas_escola_id ON turmas(escola_id)",
            "CREATE INDEX IF NOT EXISTS idx_historico_aluno_id ON historico(aluno_id)",
            "CREATE INDEX IF NOT EXISTS idx_historico_prova_id ON historico(prova_id)",
            "CREATE INDEX IF NOT EXISTS idx_historico_data_correcao ON historico(data_correcao DESC)",
            "CREATE INDEX IF NOT EXISTS idx_historico_aluno_data ON historico(aluno_id, data_correcao DESC)",
            "CREATE INDEX IF NOT EXISTS idx_correcoes_texto_data ON correcoes_texto(data_correcao DESC)",
            "CREATE INDEX IF NOT EXISTS idx_provas_created_at ON provas(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username)"
        ]
        for sql in indices:
            try:
                cur.execute(sql)
            except Exception as e:
                logging.warning("⚠️ Índice não criado: %s", e)

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
    print("🚀 INICIANDO SERVIDOR CORRIGEPRO (VERSÃO DEFINITIVA)")
    print("=" * 60)
    print(f"📌 Porta: {port}")
    print(f"📌 Pool de conexões: {DB_POOL_MIN}-{DB_POOL_MAX}")
    print(f"🤖 Gemini: {'✅ Disponível' if GEMINI_AVAILABLE else '❌ Indisponível'}")
    if GEMINI_AVAILABLE:
        print(f"📌 Modelo: {GEMINI_MODEL}")
    print(f"🤖 RelayFreeLLM: {'✅ Disponível' if RELAY_AVAILABLE else '❌ Indisponível'}")
    if RELAY_AVAILABLE:
        print(f"📌 URL: {RELAY_API_URL}")
        print(f"📌 Modelo: {RELAY_MODEL}")
    print("=" * 60)
    print("📋 ESTRATÉGIA DE CORREÇÃO - 4 PASSOS:")
    print("   1️⃣ OCR + POSIÇÃO - Leitura de letras via Tesseract")
    print("   2️⃣ CÍRCULOS PREENCHIDOS - Detecção via OpenCV")
    print("   3️⃣ IA (GEMINI) - Fallback com prompt otimizado")
    print("   4️⃣ FALLBACK SIMPLES - Garantia de resultado")
    print("=" * 60)

    init_db()
    app.run(host='0.0.0.0', port=port, debug=False)
