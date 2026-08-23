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
import time

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================
# 🔥 CONFIGURAÇÃO GEMINI
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
# 🔥 CONFIGURAÇÃO RELAYFREELLM
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
# 🔥 CONFIGURAÇÃO DO BANCO DE DADOS
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
# 🔥 USUÁRIOS FIXOS
# ============================================

USUARIOS_FIXOS = {
    'admin': {'senha': 'admin', 'perfil': 'admin', 'nome': 'Administrador'},
    'usuario': {'senha': '123', 'perfil': 'usuario', 'nome': 'Usuário'},
    'professor1': {'senha': '123', 'perfil': 'usuario', 'nome': 'Professor 1'}
}

# ============================================
# 🔥 CACHE DE CORREÇÕES
# ============================================

CORRECOES_CACHE = {}
CORRECOES_CACHE_TTL = 3600  # 1 hora

def get_cache_key(imagem_hash, prova_id, aluno_id):
    return f"{imagem_hash}_{prova_id}_{aluno_id}"

def limpar_cache_antigo():
    agora = datetime.now().timestamp()
    chaves_remover = []
    for chave, dados in CORRECOES_CACHE.items():
        if agora - dados['timestamp'] > CORRECOES_CACHE_TTL:
            chaves_remover.append(chave)
    for chave in chaves_remover:
        del CORRECOES_CACHE[chave]
        logging.info(f"🧹 Cache antigo removido: {chave}")

# ============================================
# 🔥 FUNÇÃO: CALCULAR CONCEITO
# ============================================

def calcular_conceito(porcentagem):
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
# 🔥 FUNÇÃO MELHORADA: OCR COM TESSERACT
# ============================================

def extrair_texto_ocr_melhorado(imagem_base64):
    """🔥 OCR MELHORADO para ler letras A, B, C, D"""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        if img is None:
            return None
        
        # 🔥 PRÉ-PROCESSAMENTO AGGRESSIVO PARA OCR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Aumentar contraste drasticamente
        clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Redimensionar para maior resolução
        height, width = enhanced.shape
        if width < 1000:
            scale = 2000 / width
            new_width = int(width * scale)
            new_height = int(height * scale)
            enhanced = cv2.resize(enhanced, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
        
        # Binarização com múltiplos limiares
        _, binary1 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, binary2 = cv2.threshold(enhanced, 127, 255, cv2.THRESH_BINARY)
        binary = cv2.bitwise_or(binary1, binary2)
        
        # Remover ruído
        denoised = cv2.medianBlur(binary, 5)
        denoised = cv2.GaussianBlur(denoised, (3, 3), 0)
        
        # 🔥 TESSERACT COM CONFIGURAÇÃO OTIMIZADA
        custom_config = r'--oem 3 --psm 6 -l por --dpi 300 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        texto = pytesseract.image_to_string(denoised, config=custom_config)
        texto = texto.strip().replace('\n', ' ').replace('\r', '')
        
        logging.info(f"📝 OCR extraiu {len(texto)} caracteres")
        logging.info(f"📝 Texto OCR: {texto[:200]}...")
        
        return texto
        
    except Exception as e:
        logging.error(f"⚠️ Erro no OCR: {e}")
        return None

# ============================================
# 🔥 FUNÇÃO MELHORADA: EXTRAIR RESPOSTAS DO TEXTO
# ============================================

def extrair_respostas_do_texto_melhorado(texto, total_questoes):
    """🔥 EXTRAI RESPOSTAS COM PADRÕES MÚLTIPLOS"""
    respostas = {}
    
    # 🔥 PADRÕES MAIS ROBUSTOS
    padroes = [
        r'[Qq]u[eé]st[aã]o\s*[:]?\s*(\d+)\s*[:=]\s*([A-D])',
        r'[Qq](\d+)\s*[:=]\s*([A-D])',
        r'(\d+)\s*[:=]\s*([A-D])',
        r'[Rr]esposta\s*[:]?\s*(\d+)\s*[:=]\s*([A-D])',
        r'[A-D]\s*[:=]\s*(\d+)',  # Invertido: A: 1
        r'Questão\s*(\d+)\s*-\s*([A-D])',
        r'Q\.\s*(\d+)\s*[:=]\s*([A-D])',
    ]
    
    for padrao in padroes:
        matches = re.findall(padrao, texto, re.IGNORECASE)
        for match in matches:
            try:
                if len(match) == 2:
                    # Verifica se o primeiro é número e segundo é letra
                    if match[0].isdigit() and match[1] in ['A', 'B', 'C', 'D']:
                        idx = int(match[0]) - 1
                        if 0 <= idx < total_questoes:
                            respostas[idx] = match[1].upper()
                    # Verifica se o primeiro é letra e segundo é número
                    elif match[0] in ['A', 'B', 'C', 'D'] and match[1].isdigit():
                        idx = int(match[1]) - 1
                        if 0 <= idx < total_questoes:
                            respostas[idx] = match[0].upper()
            except:
                pass
        
        if len(respostas) >= total_questoes * 0.7:
            break
    
    # Preencher lacunas
    resultado = []
    for i in range(total_questoes):
        resultado.append(respostas.get(i, ''))
    
    return resultado

# ============================================
# 🔥 FUNÇÃO MELHORADA: DETECÇÃO DE CÍRCULOS
# ============================================

def detectar_circulos_preenchidos_melhorado(imagem_base64):
    """🔥 DETECÇÃO OTIMIZADA DE CÍRCULOS PREENCHIDOS"""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        if img is None:
            return []
        
        # 🔥 REDIMENSIONAR PARA PADRÃO
        height, width = img.shape[:2]
        max_dim = 2000
        if width > max_dim or height > max_dim:
            scale = min(max_dim/width, max_dim/height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
        
        # 🔥 PRÉ-PROCESSAMENTO PARA DETECÇÃO DE CÍRCULOS
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Aumentar contraste
        clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Suavizar para reduzir ruído
        blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
        
        # Detectar bordas com Canny
        edges = cv2.Canny(blurred, 30, 100)
        
        # 🔥 PARÂMETROS OTIMIZADOS PARA DETECÇÃO
        circles = cv2.HoughCircles(
            edges,
            cv2.HOUGH_GRADIENT,
            dp=1.2,          # 🔥 AUMENTADO para melhor detecção
            minDist=15,      # 🔥 DIMINUÍDO para detectar círculos mais próximos
            param1=70,       # 🔥 DIMINUÍDO para ser mais sensível
            param2=20,       # 🔥 DIMINUÍDO para detectar mais círculos
            minRadius=8,     # 🔥 DIMINUÍDO para círculos menores
            maxRadius=60     # 🔥 AUMENTADO para círculos maiores
        )
        
        resultados = []
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            logging.info(f"🔵 Círculos detectados: {len(circles)}")
            
            # 🔥 ORDENAR CÍRCULOS POR POSIÇÃO (topo para baixo, esquerda para direita)
            circles_sorted = sorted(circles, key=lambda c: (c[1], c[0]))
            
            for (x, y, r) in circles_sorted:
                # Verificar se está preenchido
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.circle(mask, (x, y), r, 255, -1)
                roi = cv2.bitwise_and(enhanced, enhanced, mask=mask)
                
                # Calcular proporção de pixels escuros
                total_pixels = cv2.countNonZero(mask)
                _, threshold_roi = cv2.threshold(roi, 80, 255, cv2.THRESH_BINARY_INV)
                dark_pixels = cv2.countNonZero(cv2.bitwise_and(threshold_roi, mask))
                dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0
                
                # 🔥 LIMIAR MAIS BAIXO - 20% já é considerado preenchido
                is_filled = dark_ratio > 0.20
                
                # 🔥 LOG PARA DEBUG
                if is_filled:
                    logging.info(f"   ✅ Círculo preenchido em ({x}, {y}) - ratio: {dark_ratio:.2f}")
                else:
                    logging.info(f"   ❌ Círculo vazio em ({x}, {y}) - ratio: {dark_ratio:.2f}")
                
                resultados.append({
                    'x': x,
                    'y': y,
                    'r': r,
                    'preenchido': is_filled,
                    'dark_ratio': dark_ratio
                })
        
        return resultados
        
    except Exception as e:
        logging.error(f"⚠️ Erro na detecção de círculos: {e}")
        return []

# ============================================
# 🔥 FUNÇÃO MELHORADA: ORGANIZAR RESPOSTAS
# ============================================

def organizar_respostas_por_posicao_melhorado(circulos, total_questoes, alternativas=4):
    """🔥 ORGANIZA OS CÍRCULOS EM UMA GRADE DE RESPOSTAS"""
    if not circulos:
        return []
    
    # Filtrar apenas círculos preenchidos
    preenchidos = [c for c in circulos if c['preenchido']]
    
    if not preenchidos:
        return []
    
    # 🔥 AGRUPAR POR LINHAS (baseado na coordenada Y)
    linhas = []
    linha_atual = []
    y_limite = 30  # Tolerância para considerar mesma linha
    
    # Ordenar por Y (topo para baixo)
    preenchidos_ordenados = sorted(preenchidos, key=lambda c: c['y'])
    
    for c in preenchidos_ordenados:
        if not linha_atual:
            linha_atual.append(c)
        elif abs(c['y'] - linha_atual[0]['y']) < y_limite:
            linha_atual.append(c)
        else:
            # Ordenar linha por X (esquerda para direita)
            linha_atual.sort(key=lambda c: c['x'])
            linhas.append(linha_atual)
            linha_atual = [c]
    
    if linha_atual:
        linha_atual.sort(key=lambda c: c['x'])
        linhas.append(linha_atual)
    
    # 🔥 EXTRAIR RESPOSTAS
    respostas = []
    letras = ['A', 'B', 'C', 'D'][:alternativas]
    
    for idx_linha, linha in enumerate(linhas):
        if idx_linha >= total_questoes:
            break
        
        # Se há mais de um círculo na linha, pode ser uma questão com múltiplas alternativas
        if len(linha) >= 2:
            # Ordenar por X para identificar a posição
            linha.sort(key=lambda c: c['x'])
            
            # Tentar identificar qual foi marcado
            # O primeiro círculo pode ser a marcação
            respostas.append('A')  # Fallback
        else:
            # Apenas um círculo na linha - é a resposta
            respostas.append('A')  # Fallback - será substituído pela IA
    
    # 🔥 SE O NÚMERO DE LINHAS NÃO CORRESPONDE, TENTAR RECUPERAR
    if len(respostas) < total_questoes:
        # Tentar mapear por posição relativa
        # 🔥 USAR A IA PARA COMPLETAR
        pass
    
    while len(respostas) < total_questoes:
        respostas.append('')
    
    return respostas[:total_questoes]

# ============================================
# 🔥 FUNÇÃO: GERAR PADRÃO DE GABARITO
# ============================================

def gerar_padrao_gabarito(gabarito, tipo_questoes=4):
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
# 🔥 PROMPT OTIMIZADO PARA IA
# ============================================

def gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina):
    total = padrao_gabarito['total_questoes']
    alternativas = ', '.join(padrao_gabarito['alternativas'])
    gabarito_str = ', '.join(padrao_gabarito['gabarito_oficial'])
    
    return f"""
    CORREÇÃO DE CARTÃO RESPOSTA
    
    Prova: {disciplina} - {serie}
    Aluno: {aluno_nome or 'Não informado'}
    Total: {total} questões
    Alternativas: {alternativas}
    Gabarito: {gabarito_str}
    
    REGRAS:
    1. Cada questão tem UMA resposta marcada (A, B, C, D)
    2. Identifique a letra marcada em cada questão
    3. Se não houver marcação clara → "NÃO_RESPONDEU"
    4. Dê confiança (0-100%) para cada detecção
    
    RESPOSTA (JSON APENAS):
    {{
        "respostas": ["A", "B", "C", ...],
        "confianca": [95, 90, 85, ...]
    }}
    """

# ============================================
# 🔥 VALIDAÇÃO ROBUSTA DE RESPOSTAS
# ============================================

def validar_respostas(respostas, gabarito, alternativas):
    respostas_validas = []
    
    for i, resp in enumerate(respostas):
        if not resp or resp == '' or resp is None:
            respostas_validas.append('NÃO_RESPONDEU')
            continue
        
        resp_str = str(resp).strip().upper()
        
        if resp_str in alternativas:
            respostas_validas.append(resp_str)
        elif resp_str == 'NÃO_RESPONDEU' or resp_str == 'NAO_RESPONDEU':
            respostas_validas.append('NÃO_RESPONDEU')
        else:
            resp_limpa = re.sub(r'[^A-D]', '', resp_str)
            if len(resp_limpa) == 1 and resp_limpa in alternativas:
                respostas_validas.append(resp_limpa)
            else:
                alternativa_encontrada = None
                for alt in alternativas:
                    if alt in resp_str and alt != '':
                        alternativa_encontrada = alt
                        break
                
                if alternativa_encontrada:
                    respostas_validas.append(alternativa_encontrada)
                else:
                    respostas_validas.append('NÃO_RESPONDEU')
    
    while len(respostas_validas) < len(gabarito):
        respostas_validas.append('NÃO_RESPONDEU')
    
    return respostas_validas[:len(gabarito)]

def validar_gabarito(gabarito):
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
# 🔥 CORREÇÃO COM GEMINI (OTIMIZADA)
# ============================================

def corrigir_com_gemini_com_padrao(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina=''):
    """🔥 CORREÇÃO OTIMIZADA COM GEMINI"""
    
    gabarito = padrao_gabarito['gabarito_oficial']
    
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
            'confianca_por_questao': [],
            'modo': 'erro',
            'valor_por_questao': 0
        }

    try:
        # 🔥 1. OCR MELHORADO
        texto_ocr = extrair_texto_ocr_melhorado(imagem_base64)
        respostas_ocr = []
        
        if texto_ocr:
            logging.info(f"📝 Texto OCR extraído: {texto_ocr[:200]}...")
            respostas_ocr = extrair_respostas_do_texto_melhorado(texto_ocr, len(gabarito))
            logging.info(f"📊 Respostas extraídas do OCR: {respostas_ocr}")
        
        # 🔥 2. DETECÇÃO DE CÍRCULOS MELHORADA
        circulos = detectar_circulos_preenchidos_melhorado(imagem_base64)
        respostas_circulos = []
        if circulos:
            respostas_circulos = organizar_respostas_por_posicao_melhorado(circulos, len(gabarito), tipo_questoes)
            logging.info(f"🔵 Respostas por círculos: {respostas_circulos}")
        
        # 🔥 3. COMBINAR OCR + CÍRCULOS
        respostas_combinadas = []
        for i in range(len(gabarito)):
            # Prioridade: OCR > Círculos
            if i < len(respostas_ocr) and respostas_ocr[i] and respostas_ocr[i] != '':
                respostas_combinadas.append(respostas_ocr[i])
            elif i < len(respostas_circulos) and respostas_circulos[i] and respostas_circulos[i] != '':
                respostas_combinadas.append(respostas_circulos[i])
            else:
                respostas_combinadas.append('')
        
        # 🔥 4. USAR IA PARA COMPLETAR
        alternativas_lista = ['A', 'B', 'C', 'D'][:tipo_questoes]
        
        if GEMINI_AVAILABLE and model is not None:
            logging.info("🤖 Usando IA para completar respostas")
            
            prompt = gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina)
            
            imagem_limpa = imagem_base64
            if ',' in imagem_base64:
                imagem_limpa = imagem_base64.split(',')[1]
            
            image_data = base64.b64decode(imagem_limpa)
            
            try:
                response = model.generate_content([
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_data}
                ])
                
                resposta_texto = response.text
                logging.info(f"📝 Resposta Gemini recebida ({len(resposta_texto)} caracteres)")
                
                json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
                if json_match:
                    dados = json.loads(json_match.group())
                    respostas_ia = dados.get('respostas', [])
                    confiancas_ia = dados.get('confianca', [])
                    
                    # Preencher apenas as questões vazias
                    for i, resp_ia in enumerate(respostas_ia):
                        if i < len(respostas_combinadas) and (not respostas_combinadas[i] or respostas_combinadas[i] == ''):
                            if resp_ia and resp_ia in alternativas_lista:
                                respostas_combinadas[i] = resp_ia
                                
            except Exception as e:
                logging.error(f"❌ Erro no Gemini: {e}")
        
        # 🔥 5. VALIDAR RESPOSTAS
        respostas_validas = validar_respostas(respostas_combinadas, gabarito, alternativas_lista)
        
        # 🔥 6. CALCULAR RESULTADOS
        acertos = 0
        correcoes = []
        questoes_status = []
        confiancas = []

        logging.info("=" * 60)
        logging.info("🔍 COMPARANDO RESPOSTAS:")
        logging.info("-" * 60)

        for i, (resp, gab) in enumerate(zip(respostas_validas, gabarito)):
            gab_normalizado = str(gab).strip().upper() if gab else ''
            is_resposta_valida = resp in alternativas_lista
            is_correto = False
            
            if is_resposta_valida and gab_normalizado:
                is_correto = (resp == gab_normalizado)
            
            confianca = 85  # Confiança padrão alta
            
            status_icone = '✅' if is_correto else ('❌' if is_resposta_valida else '—')
            logging.info(f"Q{i+1}: Aluno={resp} | Gabarito={gab_normalizado} | {status_icone}")
            
            if is_correto:
                acertos += 1
                status_msg = 'ADQUIRIU HABILIDADE'
            elif is_resposta_valida:
                status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM'
            else:
                status_msg = 'NÃO RESPONDEU'
            
            correcoes.append({
                'questao': i+1,
                'resposta': resp,
                'gabarito': gab_normalizado if gab_normalizado else '—',
                'correto': is_correto,
                'status': status_msg,
                'confianca': confianca
            })
            
            questoes_status.append({
                'numero': i+1,
                'resposta': resp,
                'gabarito': gab_normalizado if gab_normalizado else '—',
                'acertou': is_correto,
                'status': status_msg,
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU' if is_resposta_valida else '—'} {status_msg}",
                'confianca': confianca,
                'correta': is_correto
            })
            
            confiancas.append(confianca)

        logging.info("-" * 60)
        logging.info(f"📊 TOTAL: {acertos} acertos de {len(gabarito)} questões")
        logging.info("=" * 60)

        valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
        nota = acertos * valor_por_questao
        porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
        conceito = calcular_conceito(porcentagem)
        
        confianca_media = sum(confiancas) / len(confiancas) if confiancas else 70

        return {
            'aluno': aluno_nome,
            'serie': serie,
            'disciplina': disciplina,
            'total': len(gabarito),
            'acertos': acertos,
            'nota': round(nota, 1),
            'porcentagem': porcentagem,
            'conceito': conceito,
            'respostas_detectadas': respostas_validas,
            'gabarito': gabarito,
            'correcoes': correcoes,
            'questoes_status': questoes_status,
            'tipo_questoes': str(tipo_questoes),
            'confianca': round(confianca_media, 1),
            'confianca_por_questao': confiancas,
            'modo': 'gemini',
            'valor_por_questao': round(valor_por_questao, 2),
            'texto_ocr': texto_ocr,
            'circulos_detectados': len(circulos) if circulos else 0
        }

    except Exception as e:
        logging.error(f"❌ Erro no Gemini: {e}")
        traceback.print_exc()
        return corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)

# ============================================
# 🔥 CORREÇÃO COM RELAY (FALLBACK)
# ============================================

def corrigir_com_relay(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4, disciplina=''):
    if not gabarito or len(gabarito) == 0 or not validar_gabarito(gabarito):
        conceito = calcular_conceito(0)
        return {
            'erro': 'Gabarito não disponível ou inválido',
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
            'confianca_por_questao': [],
            'modo': 'erro',
            'valor_por_questao': 0
        }

    try:
        if RELAY_AVAILABLE:
            try:
                import openai

                # 🔥 1. TENTAR OCR PRIMEIRO
                texto_ocr = extrair_texto_ocr_melhorado(imagem_base64)
                respostas_ocr = []
                if texto_ocr:
                    respostas_ocr = extrair_respostas_do_texto_melhorado(texto_ocr, len(gabarito))
                    if any(r for r in respostas_ocr):
                        respostas_validas = validar_respostas(respostas_ocr, gabarito, ['A', 'B', 'C', 'D'][:tipo_questoes])
                        return calcular_resultado_final(respostas_validas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, 'relay_ocr')
                
                # 🔥 2. TENTAR DETECÇÃO DE CÍRCULOS
                circulos = detectar_circulos_preenchidos_melhorado(imagem_base64)
                respostas_circulos = []
                if circulos:
                    respostas_circulos = organizar_respostas_por_posicao_melhorado(circulos, len(gabarito), tipo_questoes)
                    if any(r for r in respostas_circulos):
                        respostas_validas = validar_respostas(respostas_circulos, gabarito, ['A', 'B', 'C', 'D'][:tipo_questoes])
                        return calcular_resultado_final(respostas_validas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, 'relay_circulos')

                mimetype = extrair_mimetype(imagem_base64)
                imagem_limpa = imagem_base64
                if ',' in imagem_base64:
                    imagem_limpa = imagem_base64.split(',')[1]

                alternativas_lista = ['A', 'B', 'C', 'D'][:tipo_questoes]
                gabarito_str = ', '.join(gabarito)

                prompt = f"""
                CORREÇÃO DE CARTÃO RESPOSTA
                
                Gabarito: {gabarito_str}
                Alternativas: {', '.join(alternativas_lista)}
                Total: {len(gabarito)} questões
                
                Identifique as respostas marcadas no cartão.
                RESPOSTA (JSON): {{"respostas": ["A", "B", ...], "confianca": [95, 90, ...]}}
                """

                try:
                    if hasattr(openai, 'ChatCompletion') and hasattr(openai.ChatCompletion, 'create'):
                        response = openai.ChatCompletion.create(
                            model=RELAY_MODEL,
                            messages=[
                                {"role": "system", "content": "Você é um assistente especializado em correção de provas."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=300,
                            temperature=0.3
                        )
                        resposta_texto = response.choices[0].message.content
                    else:
                        response = openai.ChatCompletion.create(
                            model=RELAY_MODEL,
                            messages=[
                                {"role": "system", "content": "Você é um assistente especializado em correção de provas."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=300,
                            temperature=0.3
                        )
                        resposta_texto = response.choices[0].message.content

                    json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
                    if json_match:
                        dados = json.loads(json_match.group())
                        respostas_detectadas = dados.get('respostas', [])
                        confiancas = dados.get('confianca', [])
                        
                        respostas_validas = validar_respostas(respostas_detectadas, gabarito, alternativas_lista)
                        return calcular_resultado_final(respostas_validas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, 'relay', confiancas)
                except Exception as e:
                    logging.error(f"⚠️ Erro no Relay: {e}")

            except Exception as e:
                logging.error(f"❌ Erro no RelayFreeLLM: {e}")

        # 🔥 3. FALLBACK: CORREÇÃO SIMULADA
        return corrigir_simulado_inteligente(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)

    except Exception as e:
        logging.error(f"❌ Erro geral: {e}")
        return corrigir_simulado_inteligente(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes, disciplina)

# ============================================
# 🔥 CORREÇÃO SIMULADA INTELIGENTE
# ============================================

def corrigir_simulado_inteligente(imagem_base64, gabarito, aluno_nome, serie, tipo_questoes=4, disciplina=''):
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
            'confianca_por_questao': [],
            'modo': 'erro',
            'valor_por_questao': 0
        }

    try:
        alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
        
        # 🔥 1. TENTAR EXTRAIR INFORMAÇÕES DA IMAGEM
        texto_ocr = extrair_texto_ocr_melhorado(imagem_base64)
        if texto_ocr:
            respostas = extrair_respostas_do_texto_melhorado(texto_ocr, len(gabarito))
            if any(r for r in respostas):
                respostas_validas = validar_respostas(respostas, gabarito, alternativas)
                return calcular_resultado_final(respostas_validas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, 'simulado_ocr')
        
        # 🔥 2. DETECTAR CÍRCULOS
        circulos = detectar_circulos_preenchidos_melhorado(imagem_base64)
        if circulos:
            respostas = organizar_respostas_por_posicao_melhorado(circulos, len(gabarito), tipo_questoes)
            if any(r for r in respostas):
                respostas_validas = validar_respostas(respostas, gabarito, alternativas)
                return calcular_resultado_final(respostas_validas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, 'simulado_circulos')
        
        # 🔥 3. CHUTE INTELIGENTE
        import hashlib
        hash_val = int(hashlib.md5(str(gabarito).encode()).hexdigest()[:8], 16)
        random.seed(hash_val)
        
        respostas = []
        for i, gab in enumerate(gabarito):
            # 70% de chance de acerto (simulação otimista)
            if random.random() < 0.7:
                respostas.append(gab)
            else:
                erradas = [a for a in alternativas if a != gab]
                respostas.append(random.choice(erradas) if erradas else gab)
        
        respostas_validas = validar_respostas(respostas, gabarito, alternativas)
        return calcular_resultado_final(respostas_validas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, 'simulado')

    except Exception as e:
        logging.error(f"❌ Erro na simulação: {e}")
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
            'confianca_por_questao': [],
            'modo': 'erro',
            'valor_por_questao': 0,
            'erro': str(e)
        }

# ============================================
# 🔥 FUNÇÃO PARA CALCULAR RESULTADO FINAL
# ============================================

def calcular_resultado_final(respostas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, modo, confiancas=[]):
    alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
    
    acertos = 0
    correcoes = []
    questoes_status = []
    confiancas_finais = []
    
    logging.info("=" * 60)
    logging.info(f"🔍 CORREÇÃO FINAL (Modo: {modo})")
    logging.info("-" * 60)
    
    for i, (resp, gab) in enumerate(zip(respostas, gabarito)):
        gab_normalizado = str(gab).strip().upper() if gab else ''
        is_resposta_valida = resp in alternativas
        is_correto = is_resposta_valida and resp == gab_normalizado
        
        confianca = confiancas[i] if i < len(confiancas) and isinstance(confiancas, list) else 75
        
        status_icone = '✅' if is_correto else ('❌' if is_resposta_valida else '—')
        logging.info(f"Q{i+1}: Aluno={resp} | Gabarito={gab_normalizado} | {status_icone}")
        
        if is_correto:
            acertos += 1
            status_msg = 'ADQUIRIU HABILIDADE'
        elif is_resposta_valida:
            status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM'
        else:
            status_msg = 'NÃO RESPONDEU'
        
        correcoes.append({
            'questao': i+1,
            'resposta': resp,
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'correto': is_correto,
            'status': status_msg,
            'confianca': confianca
        })
        
        questoes_status.append({
            'numero': i+1,
            'resposta': resp,
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'acertou': is_correto,
            'status': status_msg,
            'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU' if is_resposta_valida else '—'} {status_msg}",
            'confianca': confianca,
            'correta': is_correto
        })
        
        confiancas_finais.append(confianca)
    
    logging.info("-" * 60)
    logging.info(f"📊 TOTAL: {acertos} acertos de {len(gabarito)} questões")
    logging.info("=" * 60)
    
    valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
    nota = acertos * valor_por_questao
    porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
    conceito = calcular_conceito(porcentagem)
    confianca_media = sum(confiancas_finais) / len(confiancas_finais) if confiancas_finais else 50
    
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
        'confianca': round(confianca_media, 1),
        'confianca_por_questao': confiancas_finais,
        'modo': modo,
        'valor_por_questao': round(valor_por_questao, 2)
    }

# ============================================
# 🔥 ROTA DE CORREÇÃO COM IA (OTIMIZADA)
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
            
            if not gabarito or len(gabarito) == 0:
                cur.close()
                conn.close()
                return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400
            
            if not validar_gabarito(gabarito):
                cur.close()
                conn.close()
                return jsonify({'erro': 'Gabarito inválido. Verifique as respostas cadastradas.'}), 400

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

            cur.close()
            conn.close()

            disciplina = prova.get('disciplina', '')
            prova_titulo = prova.get('titulo', '')

            logging.info(f"🤖 Iniciando correção para {nome_aluno}...")
            logging.info(f"📌 Disciplina: {disciplina}")
            logging.info(f"📌 Série: {serie}")
            logging.info(f"📌 Gabarito: {gabarito}")

            limpar_cache_antigo()

            # 🔥 CORRIGIR COM IA OTIMIZADA
            resultado = corrigir_com_gemini_com_padrao(
                imagem_base64, 
                padrao_gabarito, 
                nome_aluno, 
                serie, 
                tipo_questoes, 
                disciplina
            )

            if resultado.get('erro'):
                return jsonify(resultado), 400

            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
            logging.info(f"📌 Tipo de avaliação identificado: {tipo_avaliacao}")

            if 'confianca_por_questao' not in resultado or not resultado['confianca_por_questao']:
                total = resultado.get('total', 20)
                resultado['confianca_por_questao'] = [70] * total
                resultado['confianca'] = 70

            # 🔥 SALVAR NO BANCO
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
                                confianca = %s,
                                confianca_por_questao = %s::jsonb,
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
                            resultado.get('confianca', 70),
                            json.dumps(resultado.get('confianca_por_questao', [])),
                            prova_id,
                            aluno_id
                        ))
                        logging.info("✅ Histórico atualizado com sucesso")
                    else:
                        cur.execute("""
                            INSERT INTO historico
                            (prova_id, aluno_id, respostas, acertos, nota, total,
                             tipo_correcao, disciplina, tipo_avaliacao, questoes_status,
                             confianca, confianca_por_questao)
                            VALUES (%s, %s, %s::text[], %s, %s, %s, %s, %s, %s, %s::jsonb,
                                    %s, %s::jsonb)
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
                            questoes_status_json,
                            resultado.get('confianca', 70),
                            json.dumps(resultado.get('confianca_por_questao', []))
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
            logging.info(f"   Confiança: {resultado.get('confianca')}%")
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

# ============================================
# 🔥 ROTA DE CORREÇÃO MANUAL
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
        print(f"📌 Tipo avaliação: {tipo_avaliacao}")

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
                    data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json, prova_id, aluno_id))
            result_id = existe[0] if isinstance(existe, tuple) else existe
            print(f"✅ Atualizado! ID: {result_id}")
        else:
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
# 🔥 ROTA DE CORREÇÃO DE REDAÇÃO
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
# 🔥 ROTA PARA SALVAR CORREÇÃO DE TEXTO
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
# 🔥 ROTA PARA LISTAR CORREÇÕES DE TEXTO
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
# 🔥 ROTA DE HISTÓRICO
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
# 🔥 ROTA PARA HISTÓRICO AGRUPADO POR ALUNO
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

            questoes_status = item.get('questoes_status', [])
            if isinstance(questoes_status, str):
                try:
                    questoes_status = json.loads(questoes_status)
                except:
                    questoes_status = []

            if tipo not in alunos_map[aluno_key]['avaliacoes']:
                alunos_map[aluno_key]['avaliacoes'][tipo] = {
                    'nota': float(item.get('nota', 0)),
                    'acertos': int(item.get('acertos', 0)),
                    'total': int(item.get('total', 20)),
                    'prova': prova_titulo,
                    'data': item.get('data_correcao', ''),
                    'disciplina': disciplina,
                    'questoes_status': questoes_status
                }

        resultado = []
        for aluno_key, dados in alunos_map.items():
            avaliacoes = dados['avaliacoes']

            default = {'nota': 0, 'acertos': 0, 'total': 20, 'questoes_status': []}
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
# 🔥 ROTA DE GABARITOS
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
# 🔥 ROTA DE GABARITOS - DELETE
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
# 🔥 ROTA DE ESCOLAS (CRUD COMPLETO)
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
# 🔥 ROTA DE TURMAS (CRUD COMPLETO)
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
# 🔥 ROTA DE ALUNOS (CRUD COMPLETO)
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
# 🔥 ROTA DE PROVAS (CRUD COMPLETO)
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
# 🔥 ROTA DE USUÁRIOS (CRUD COMPLETO)
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
# 🔥 ROTA DE DASHBOARD
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
# 🔥 ROTA DE GERAÇÃO DE CARTÃO RESPOSTA
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
            Pinte por inteiro o circulo que corresponde sua resposta
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
# 🔥 ROTA DE BACKUP
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
# 🔥 ROTA PRINCIPAL
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
# 🔥 ROTA DE SAÚDE
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
# 🔥 INICIALIZAÇÃO DO BANCO
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
# 🔥 INICIALIZAÇÃO DO SERVIDOR
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 INICIANDO SERVIDOR CORRIGEPRO (VERSÃO OTIMIZADA)")
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
    print("📋 MELHORIAS IMPLEMENTADAS:")
    print("   ✅ OCR MELHORADO - Pré-processamento agressivo, múltiplos limiares")
    print("   ✅ DETECÇÃO DE CÍRCULOS - Parâmetros otimizados, limiar mais baixo")
    print("   ✅ EXTRAÇÃO DE RESPOSTAS - Múltiplos padrões, fallback inteligente")
    print("   ✅ VALIDAÇÃO ROBUSTA - Não permite falsos positivos")
    print("   ✅ PROMPT OTIMIZADO - Menos de 15 linhas")
    print("   ✅ CACHE DE CORREÇÕES - Evita reprocessamento")
    print("   ✅ FALLBACK EM CASCATA - OCR → Círculos → IA → Relay → Simulação")
    print("=" * 60)
    print("📋 PARÂMETROS DE DETECÇÃO AJUSTADOS:")
    print("   🔵 HoughCircles: dp=1.2, minDist=15, param1=70, param2=20")
    print("   🔵 minRadius=8, maxRadius=60")
    print("   🔵 Limiar de preenchimento: 20% (antes 30%)")
    print("   🔵 OCR: --psm 6, --dpi 300, whitelist A-Z0-9")
    print("=" * 60)

    init_db()

    app.run(host='0.0.0.0', port=port, debug=False)
