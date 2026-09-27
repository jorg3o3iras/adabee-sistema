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
import random
import traceback
from dotenv import load_dotenv
import hmac
import logging
import zipfile
import hashlib
from collections import Counter

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================
# CACHE DE CORREÇÕES
# ============================================

CORRECOES_CACHE = {}
CORRECOES_CACHE_TTL = 3600

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
# CONFIGURAÇÃO OPENAI
# ============================================

OPENAI_AVAILABLE = False
openai_client = None
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

try:
    from openai import OpenAI
    if OPENAI_API_KEY and OPENAI_API_KEY.startswith('sk-'):
        try:
            openai_client = OpenAI(api_key=OPENAI_API_KEY)
            OPENAI_AVAILABLE = True
            print("=" * 60)
            print("✅ OpenAI (ChatGPT) configurado!")
            print(f"📌 Modelo: {OPENAI_MODEL}")
            print("=" * 60)
        except Exception as e:
            print(f"⚠️ Erro ao configurar OpenAI: {e}")
            OPENAI_AVAILABLE = False
    else:
        print("⚠️ OPENAI_API_KEY não encontrada ou inválida no .env")
except ImportError as e:
    print(f"❌ Erro ao importar openai: {e}")
    print("💡 Execute: pip install openai")
    OPENAI_AVAILABLE = False
except Exception as e:
    print(f"⚠️ Erro ao configurar OpenAI: {e}")
    OPENAI_AVAILABLE = False

# ============================================
# CONFIGURAÇÃO RELAYFREELLM
# ============================================

RELAY_AVAILABLE = False
RELAY_API_URL = os.getenv('RELAY_API_URL', '')
RELAY_API_KEY = os.getenv('RELAY_API_KEY', '')
RELAY_MODEL = os.getenv('RELAY_MODEL', 'gemini-1.5-flash')

try:
    if RELAY_API_URL:
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
# FUNÇÕES AUXILIARES
# ============================================

def calcular_conceito(porcentagem):
    if porcentagem <= 40:
        return {'nome': 'inicial', 'rotulo': '🔴 Inicial', 'faixa': 'até 40%', 'cor': '#ef4444', 'badge': 'badge-conceito-inicial'}
    elif porcentagem <= 60:
        return {'nome': 'basico', 'rotulo': '🟠 Básico', 'faixa': '41% - 60%', 'cor': '#f59e0b', 'badge': 'badge-conceito-basico'}
    elif porcentagem <= 80:
        return {'nome': 'proficiente', 'rotulo': '🔵 Proficiente', 'faixa': '61% - 80%', 'cor': '#3b82f6', 'badge': 'badge-conceito-proficiente'}
    else:
        return {'nome': 'avancado', 'rotulo': '🟢 Avançado', 'faixa': 'acima de 80%', 'cor': '#10b981', 'badge': 'badge-conceito-avancado'}


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


def validar_gabarito(gabarito):
    if not gabarito or len(gabarito) == 0:
        return False
    alternativas_validas = ['A', 'B', 'C', 'D']
    for g in gabarito:
        if not g or str(g).strip() == '':
            return False
        if str(g).upper().strip() not in alternativas_validas:
            return False
    return True


def validar_respostas(respostas, gabarito, alternativas):
    respostas_validas = []
    for i, resp in enumerate(respostas):
        if not resp or str(resp).strip() == '':
            respostas_validas.append('')
            continue
        resp_str = str(resp).upper().strip()
        if resp_str in alternativas:
            respostas_validas.append(resp_str)
        else:
            for alt in alternativas:
                if alt in resp_str:
                    respostas_validas.append(alt)
                    break
            else:
                respostas_validas.append('')
    while len(respostas_validas) < len(gabarito):
        respostas_validas.append('')
    return respostas_validas[:len(gabarito)]


def calcular_resultado_correcao(respostas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, modo, circulos=None, bncc=None, confiancas=None):
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
        resp = respostas[i] if i < len(respostas) else ''
        gab = gabarito[i] if i < len(gabarito) else ''
        gab_normalizado = str(gab).strip().upper() if gab else ''
        
        confianca_q = 80
        if confiancas and i < len(confiancas):
            confianca_q = int(confiancas[i])
        
        codigo_bncc = ''
        if bncc and i < len(bncc):
            codigo_bncc = bncc[i] if bncc[i] else ''
        
        is_resposta_valida = resp in alternativas
        is_correto = False
        if is_resposta_valida and gab_normalizado:
            is_correto = (resp == gab_normalizado)
            if is_correto:
                acertos += 1
        
        if is_correto:
            status_msg = 'ADQUIRIU HABILIDADE ✅'
            status_icone = '✅'
        elif is_resposta_valida:
            status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM ❌'
            status_icone = '❌'
        else:
            status_msg = 'NÃO RESPONDEU —'
            status_icone = '—'
        
        correcoes.append({
            'questao': i + 1, 'resposta': resp if resp else '—',
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'correto': is_correto, 'status': status_msg,
            'confianca': confianca_q if is_resposta_valida else 50, 'bncc': codigo_bncc
        })
        
        questoes_status.append({
            'numero': i + 1, 'resposta': resp if resp else '—',
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'acertou': is_correto, 'status': status_msg,
            'status_texto': f"{status_icone} {status_msg}",
            'confianca': confianca_q if is_resposta_valida else 50,
            'correta': is_correto, 'bncc': codigo_bncc
        })
    
    valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
    nota = acertos * valor_por_questao
    porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
    conceito = calcular_conceito(porcentagem)
    
    confianca_media = 70
    if confiancas:
        confianca_media = int(sum(confiancas) / len(confiancas)) if confiancas else 70
    
    return {
        'aluno': aluno_nome, 'serie': serie, 'disciplina': disciplina,
        'total': len(gabarito), 'acertos': acertos, 'nota': round(nota, 1),
        'porcentagem': porcentagem, 'conceito': conceito,
        'respostas_detectadas': respostas, 'gabarito': gabarito,
        'correcoes': correcoes, 'questoes_status': questoes_status,
        'tipo_questoes': str(tipo_questoes),
        'confianca': confianca_media,
        'confianca_por_questao': confiancas if confiancas else [80 if r in alternativas else 50 for r in respostas],
        'modo': modo, 'valor_por_questao': round(valor_por_questao, 2),
        'circulos_detectados': len(circulos) if circulos else 0,
        'questoes_ia': 0, 'bncc': bncc if bncc else []
    }


def erro_correcao(aluno_nome, serie, disciplina, erro_msg):
    conceito = calcular_conceito(0)
    return {
        'erro': erro_msg, 'aluno': aluno_nome, 'serie': serie,
        'disciplina': disciplina, 'total': 0, 'acertos': 0, 'nota': 0,
        'porcentagem': 0, 'conceito': conceito,
        'respostas_detectadas': [], 'gabarito': [], 'correcoes': [],
        'questoes_status': [], 'tipo_questoes': '4', 'confianca': 0,
        'confianca_por_questao': [], 'modo': 'erro',
        'valor_por_questao': 0, 'bncc': []
    }


# ============================================
# DETECÇÃO DE MARCADORES FIDUCIAIS
# ============================================

def detectar_marcadores_fiduciais(gray):
    """Detecta os 4 marcadores fiduciais nos cantos do cartão"""
    try:
        altura, largura = gray.shape
        
        _, binaria = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidatos = []
        area_min = (largura * altura) * 0.003
        area_max = (largura * altura) * 0.025
        
        for c in contornos:
            x, y, w, h = cv2.boundingRect(c)
            area = w * h
            if area_min < area < area_max:
                aspect = w / float(h)
                if 0.7 < aspect < 1.4:
                    roi = binaria[y:y+h, x:x+w]
                    densidade = cv2.countNonZero(roi) / float(w * h)
                    if densidade > 0.5:
                        candidatos.append((x, y, w, h, area, densidade))
        
        if len(candidatos) < 4:
            logging.warning(f"⚠️ Apenas {len(candidatos)} marcadores fiduciais detectados")
            return None
        
        candidatos.sort(key=lambda c: c[4], reverse=True)
        
        meia_largura = largura / 2
        meia_altura = altura / 2
        
        tl = tr = bl = br = None
        for (x, y, w, h, a, d) in candidatos[:10]:
            cx, cy = x + w//2, y + h//2
            if cx < meia_largura and cy < meia_altura and tl is None:
                tl = (cx, cy)
            elif cx >= meia_largura and cy < meia_altura and tr is None:
                tr = (cx, cy)
            elif cx < meia_largura and cy >= meia_altura and bl is None:
                bl = (cx, cy)
            elif cx >= meia_largura and cy >= meia_altura and br is None:
                br = (cx, cy)
        
        if not all([tl, tr, bl, br]):
            logging.warning("⚠️ Não foi possível classificar os 4 marcadores")
            return None
        
        logging.info(f"✅ 4 marcadores fiduciais detectados")
        return {'tl': tl, 'tr': tr, 'bl': bl, 'br': br}
        
    except Exception as e:
        logging.error(f"❌ Erro ao detectar marcadores: {e}")
        return None


def corrigir_perspectiva(img, marcadores):
    """Corrige a perspectiva da imagem usando os marcadores"""
    try:
        tl = marcadores['tl']
        tr = marcadores['tr']
        bl = marcadores['bl']
        br = marcadores['br']
        
        largura_topo = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        largura_base = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        largura_max = max(int(largura_topo), int(largura_base))
        
        altura_esq = np.sqrt(((bl[0] - tl[0]) ** 2) + ((bl[1] - tl[1]) ** 2))
        altura_dir = np.sqrt(((br[0] - tr[0]) ** 2) + ((br[1] - tr[1]) ** 2))
        altura_max = max(int(altura_esq), int(altura_dir))
        
        margem = 30
        largura_max += margem * 2
        altura_max += margem * 2
        
        origem = np.float32([tl, tr, bl, br])
        destino = np.float32([
            [margem, margem],
            [largura_max - margem, margem],
            [margem, altura_max - margem],
            [largura_max - margem, altura_max - margem]
        ])
        
        matriz = cv2.getPerspectiveTransform(origem, destino)
        img_corrigida = cv2.warpPerspective(img, matriz, (largura_max, altura_max))
        
        logging.info(f"✅ Perspectiva corrigida: {largura_max}x{altura_max}")
        return img_corrigida
        
    except Exception as e:
        logging.error(f"❌ Erro ao corrigir perspectiva: {e}")
        return img


# ============================================
# ✅ DETECÇÃO DE CÍRCULOS - VERSÃO DEFINITIVA
# ============================================

def detectar_circulos_preenchidos(imagem_base64):
    """
    ✅ VERSÃO MELHORADA - Aceita caneta azul e preta, ajustes para scanner
    """
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        if img is None:
            logging.error("❌ Imagem inválida")
            return []
        
        height, width = img.shape[:2]
        logging.info(f"📐 Imagem original: {width}x{height}")
        
        # ✅ AUMENTADO: Processar em resolução maior
        if height > 3000:
            scale = 3000 / height
            new_width = int(width * scale)
            img = cv2.resize(img, (new_width, 3000), interpolation=cv2.INTER_AREA)
            logging.info(f"📐 Redimensionada: {new_width}x3000")
        
        # ✅ CONVERTER PARA HSV - detecta melhor azul e preto
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # ✅ MÁSCARA DE AZUL ESCURO (caneta azul)
        # H: 100-130, S: 50-255, V: 0-150 (escuro)
        mask_azul = cv2.inRange(hsv, (90, 40, 0), (140, 255, 180))
        
        # ✅ MÁSCARA DE PRETO (caneta preta)
        # V muito baixo (escuro), qualquer H/S
        mask_preto = cv2.inRange(hsv, (0, 0, 0), (180, 255, 100))
        
        # Combinar as duas máscaras
        mask_marcacao = cv2.bitwise_or(mask_azul, mask_preto)
        
        logging.info(f"📊 Máscara azul: {cv2.countNonZero(mask_azul)} pixels")
        logging.info(f"📊 Máscara preta: {cv2.countNonZero(mask_preto)} pixels")
        
        # Converter para grayscale da marcação (só o que foi marcado fica branco)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray_enhanced = clahe.apply(gray)
        gray_blur = cv2.GaussianBlur(gray_enhanced, (5, 5), 0)
        
        # Tentar corrigir perspectiva
        marcadores = detectar_marcadores_fiduciais(gray)
        if marcadores:
            img = corrigir_perspectiva(img, marcadores)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Recalcular máscaras após correção
            mask_azul = cv2.inRange(hsv, (90, 40, 0), (140, 255, 180))
            mask_preto = cv2.inRange(hsv, (0, 0, 0), (180, 255, 100))
            mask_marcacao = cv2.bitwise_or(mask_azul, mask_preto)
            
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            gray_enhanced = clahe.apply(gray)
            gray_blur = cv2.GaussianBlur(gray_enhanced, (5, 5), 0)
            logging.info("✅ Perspectiva corrigida")
        
        # ✅ Threshold para detectar círculos vazios (contorno)
        _, binaria = cv2.threshold(gray_blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # ✅ HoughCircles com range MAIOR de raio (para scanner)
        circulos = cv2.HoughCircles(
            gray_blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=25,       # ✅ AUMENTADO para evitar duplicatas
            param1=50,
            param2=22,        # ✅ AUMENTADO para detecção mais confiável
            minRadius=10,     # ✅ AUMENTADO para ignorar letras pequenas
            maxRadius=45      # ✅ AUMENTADO para scanner
        )
        
        if circulos is None:
            logging.warning("⚠️ Nenhum círculo detectado")
            return []
        
        circulos = np.round(circulos[0, :]).astype("int")
        logging.info(f"🔵 HoughCircles: {len(circulos)} candidatos")
        
        # ✅ Filtrar por tamanho (mediana)
        raios = [r for (x, y, r) in circulos]
        if len(raios) >= 8:
            raios_sorted = sorted(raios)
            mediana_r = raios_sorted[len(raios_sorted) // 2]
            r_min = mediana_r * 0.7
            r_max = mediana_r * 1.4
            
            circulos = [(x, y, r) for (x, y, r) in circulos if r_min <= r <= r_max]
            logging.info(f"📐 Mediana raio: {mediana_r}px → {len(circulos)} após filtro")
        
        # ✅ Análise de cada círculo
        resultados = []
        for (x, y, r) in circulos:
            if x < r or y < r or x + r > gray.shape[1] or y + r > gray.shape[0]:
                continue
            
            # ✅ Usar MÁSCARA DE COR (azul+preto) para detectar preenchimento
            mask_circ = np.zeros(gray.shape, dtype=np.uint8)
            cv2.circle(mask_circ, (x, y), int(r * 0.75), 255, -1)
            
            # Verificar quantos pixels de MARCAÇÃO (azul/preto) estão dentro do círculo
            mask_marcacao_roi = cv2.bitwise_and(mask_marcacao, mask_marcacao, mask=mask_circ)
            
            # Também verificar o threshold tradicional (para círculos pretos puros)
            binaria_roi = cv2.bitwise_and(binaria, binaria, mask=mask_circ)
            
            total_pixels = cv2.countNonZero(mask_circ)
            pixels_marcacao = cv2.countNonZero(mask_marcacao_roi)
            pixels_binaria = cv2.countNonZero(binaria_roi)
            
            # ✅ Usar o MAIOR dos dois (aceita azul e preto)
            dark_ratio_cor = pixels_marcacao / total_pixels if total_pixels > 0 else 0
            dark_ratio_bin = pixels_binaria / total_pixels if total_pixels > 0 else 0
            
            dark_ratio = max(dark_ratio_cor, dark_ratio_bin)
            
            resultados.append({
                'x': int(x), 'y': int(y), 'r': int(r),
                'preenchido': False,  # Vai ser definido abaixo
                'dark_ratio': float(dark_ratio)
            })
        
        if not resultados:
            return []
        
        logging.info(f"✅ Candidatos analisados: {len(resultados)}")
        
        # ✅ Remover duplicatas
        unicos = []
        for c in sorted(resultados, key=lambda c: c['dark_ratio'], reverse=True):
            duplicado = False
            for u in unicos:
                dist = np.sqrt((c['x'] - u['x'])**2 + (c['y'] - u['y'])**2)
                if dist < u['r'] * 1.4:
                    duplicado = True
                    break
            if not duplicado:
                unicos.append(c)
        
        logging.info(f"✅ Após remover duplicatas: {len(unicos)} círculos")
        
        # ✅ Threshold adaptativo
        ratios = sorted([c['dark_ratio'] for c in unicos])
        logging.info(f"📊 Ratios: {[f'{r:.3f}' for r in ratios]}")
        
        if len(ratios) >= 8:
            q1_idx = len(ratios) // 4
            q3_idx = (3 * len(ratios)) // 4
            quartil1 = ratios[q1_idx]
            quartil3 = ratios[q3_idx]
            
            if quartil3 - quartil1 > 0.15:
                threshold = (quartil1 + quartil3) / 2
            else:
                mediana = ratios[len(ratios) // 2]
                threshold = max(0.25, mediana * 1.5)
        else:
            threshold = 0.30
        
        # ✅ Threshold MINIMO maior (para evitar falsos positivos)
        threshold = max(0.25, min(threshold, 0.60))
        logging.info(f"📊 Threshold adaptativo: {threshold:.3f}")
        
        preenchidos = []
        for c in unicos:
            if c['dark_ratio'] > threshold:
                c['preenchido'] = True
                preenchidos.append(c)
        
        logging.info(f"📊 RESULTADO: {len(unicos)} círculos, {len(preenchidos)} preenchidos")
        
        for c in preenchidos[:20]:
            logging.info(f"   ⭕ ({c['x']},{c['y']}) r={c['r']} ratio={c['dark_ratio']:.3f}")
        
        return preenchidos
        
    except Exception as e:
        logging.error(f"⚠️ Erro na detecção: {e}")
        traceback.print_exc()
        return []


# ============================================
# ✅ ORGANIZAÇÃO DE RESPOSTAS - VERSÃO DEFINITIVA
# ============================================

def organizar_respostas_por_posicao(circulos, total_questoes):
    """
    ✅ VERSÃO CORRIGIDA - não usa mais 'preenchido' (já foram filtrados)
    """
    if not circulos:
        logging.warning("⚠️ Sem círculos para organizar")
        return [''] * total_questoes, [0] * total_questoes
    
    logging.info("=" * 60)
    logging.info(f"🎯 ORGANIZANDO {len(circulos)} CÍRCULOS PARA {total_questoes} QUESTÕES")
    logging.info("=" * 60)
    
    # Log de todos os círculos
    for i, c in enumerate(sorted(circulos, key=lambda x: (x['y'], x['x']))):
        # ✅ Usar .get() para evitar KeyError
        ratio = c.get('dark_ratio', 0)
        logging.info(f"   [{i}] x={c['x']:4d}, y={c['y']:4d}, r={c['r']:2d}, ratio={ratio:.3f}")
    
    # Ordenar por Y depois X
    ordenados = sorted(circulos, key=lambda c: (c['y'], c['x']))
    
    # Calcular tolerância Y
    ys = [c['y'] for c in ordenados]
    distancias_y = []
    for i in range(1, len(ys)):
        d = abs(ys[i] - ys[i-1])
        if d > 5:
            distancias_y.append(d)
    
    if distancias_y:
        distancias_y.sort()
        y_limite = distancias_y[0] * 0.6
    else:
        y_limite = 20
    
    y_limite = max(10, min(y_limite, 35))
    logging.info(f"📏 Tolerância Y: {y_limite:.1f}px")
    
    # Agrupar em linhas
    linhas = []
    linha_atual = []
    
    for c in ordenados:
        if not linha_atual:
            linha_atual.append(c)
        elif abs(c['y'] - linha_atual[0]['y']) < y_limite:
            linha_atual.append(c)
        else:
            linha_atual.sort(key=lambda x: x['x'])
            linhas.append(linha_atual)
            linha_atual = [c]
    
    if linha_atual:
        linha_atual.sort(key=lambda x: x['x'])
        linhas.append(linha_atual)
    
    linhas.sort(key=lambda l: l[0]['y'])
    
    logging.info(f"📋 {len(linhas)} LINHAS agrupadas:")
    for i, linha in enumerate(linhas):
        xs = sorted([c['x'] for c in linha])
        ys_linha = [c['y'] for c in linha]
        logging.info(f"   L{i+1}: Y_medio={sum(ys_linha)//len(ys_linha)}, {len(linha)} círculos, X={xs}")
    
    # ✅ VALIDAÇÃO: linhas vs questões
    if len(linhas) < total_questoes * 0.6:
        logging.error(f"🚨 POUCAS linhas ({len(linhas)}) para {total_questoes} questões")
        return [''] * total_questoes, [0] * total_questoes
    
    if len(linhas) > total_questoes * 1.8:
        logging.error(f"🚨 MUITAS linhas ({len(linhas)}) para {total_questoes} questões")
        return [''] * total_questoes, [0] * total_questoes
    
    # ✅ Processar cada linha
    respostas = []
    confiancas = []
    letras = ['A', 'B', 'C', 'D']
    
    for idx, linha in enumerate(linhas):
        if idx >= total_questoes:
            break
        
        if not linha:
            respostas.append('')
            confiancas.append(30)
            continue
        
        # ✅ CORREÇÃO CRÍTICA: usar .get() ou verificar sem 'preenchido'
        # Como essa função recebe APENAS os círculos preenchidos,
        # devemos pegar o de maior dark_ratio
        mais_escuro = max(linha, key=lambda c: c.get('dark_ratio', 0))
        
        # Encontrar posição X
        linha_ordenada_x = sorted(linha, key=lambda c: c['x'])
        posicao = 0
        for i, c in enumerate(linha_ordenada_x):
            if c['x'] == mais_escuro['x'] and c['y'] == mais_escuro['y']:
                posicao = i
                break
        
        num_circ = len(linha_ordenada_x)
        
        # Mapear posição para letra
        if num_circ >= 4:
            if posicao < len(letras):
                letra = letras[posicao]
                conf = 85 if mais_escuro.get('dark_ratio', 0) > 0.35 else 70
            else:
                letra = ''
                conf = 30
        elif num_circ == 3:
            letra = letras[posicao] if posicao < 3 else ''
            conf = 70
        elif num_circ == 2:
            largura = linha_ordenada_x[-1]['x'] - linha_ordenada_x[0]['x']
            if largura > 0:
                pos_rel = (mais_escuro['x'] - linha_ordenada_x[0]['x']) / largura
                if pos_rel < 0.33:
                    letra = 'A'
                elif pos_rel < 0.67:
                    letra = 'B'
                else:
                    letra = 'C'
                conf = 50
            else:
                letra = ''
                conf = 30
        else:
            letra = ''
            conf = 30
        
        respostas.append(letra)
        confiancas.append(conf)
        
        logging.info(f"   Q{idx+1}: pos={posicao}/{num_circ} → '{letra}' (ratio={mais_escuro.get('dark_ratio', 0):.3f})")
    
    # Completar
    while len(respostas) < total_questoes:
        respostas.append('')
        confiancas.append(0)
    
    respostas = respostas[:total_questoes]
    confiancas = confiancas[:total_questoes]
    
    # ✅ VALIDAÇÃO: muitas respostas iguais?
    nao_vazias = [r for r in respostas if r]
    if len(nao_vazias) >= 5:
        contagem = Counter(nao_vazias)
        letra_mais_comum, qtd = contagem.most_common(1)[0]
        
        if qtd >= len(nao_vazias) * 0.7:
            logging.error(f"🚨 SUSPEITO: {qtd}/{len(nao_vazias)} respostas são '{letra_mais_comum}'")
            return [''] * total_questoes, [0] * total_questoes
    
    total_vazios = len([r for r in respostas if not r])
    if total_vazios > total_questoes * 0.6:
        logging.error(f"🚨 SUSPEITO: {total_vazios}/{total_questoes} respostas VAZIAS")
        return [''] * total_questoes, [0] * total_questoes
    
    logging.info("=" * 60)
    logging.info(f"📝 RESPOSTAS: {respostas}")
    logging.info(f"📊 CONFIANÇAS: {confiancas}")
    logging.info("=" * 60)
    
    return respostas, confiancas


# ============================================
# OCR (último recurso) - DESATIVADO
# ============================================

def extrair_respostas_com_ocr(imagem_base64, total_questoes, alternativas):
    logging.info("⚠️ OCR desativado")
    return []


# ============================================
# ✅ PROMPT DA IA - COM DESCRIÇÃO EXATA DO CARTÃO
# ============================================

def gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina):
    """✅ PROMPT COM DESCRIÇÃO EXATA - LETRA AO LADO DO CÍRCULO"""
    total = padrao_gabarito['total_questoes']
    alternativas = padrao_gabarito['alternativas']
    alternativas_str = ', '.join(alternativas)
    
    return f"""Você é um especialista em LEITURA DE CARTÕES RESPOSTA escolares brasileiros.

═══════════════════════════════════════════════════════════════
ESTRUTURA EXATA DESTE CARTÃO RESPOSTA:
═══════════════════════════════════════════════════════════════

O cartão tem {total} LINHAS numeradas (01, 02, 03... {total}).

Cada LINHA tem EXATAMENTE esta estrutura (da esquerda para direita):
  [NÚMERO]  [LETRA "A"] [CÍRCULO]  [LETRA "B"] [CÍRCULO]  
            [LETRA "C"] [CÍRCULO]  [LETRA "D"] [CÍRCULO]

⚠️ ATENÇÃO CRÍTICA: A LETRA (A, B, C, D) ESTÁ **AO LADO** DO CÍRCULO, 
   NÃO DENTRO DELE!

Exemplo visual de UMA LINHA (Q01):
  ┌────────────────────────────────────────────────────────────┐
  │  01 │  A ○    B ○    C ○    D ○                            │
  │         ↑       ↑       ↑       ↑                          │
  │      letra   letra   letra   letra                         │
  │         ↓       ↓       ↓       ↓                          │
  │      círculo círculo círculo círculo                       │
  └────────────────────────────────────────────────────────────┘

Se o aluno preencher a resposta "B", a linha fica:
  │  01 │  A ○    B ●    C ○    D ○                            │
  │                 ↑                                          │
  │         CÍRCULO PREENCHIDO (do lado da letra B)            │

═══════════════════════════════════════════════════════════════
SUA TAREFA:
═══════════════════════════════════════════════════════════════

Para CADA LINHA ({total} linhas no total):
1. Identifique qual dos 4 CÍRCULOS está PREENCHIDO (mais escuro)
2. Anote a LETRA que está AO LADO desse círculo preenchido
3. Essa letra é a RESPOSTA da questão

REGRAS:
- ✅ Círculo PREENCHIDO = círculo totalmente pintado (preto/azul escuro)
- ✅ Círculo VAZIO = apenas contorno visível, interior branco
- ✅ A letra ao lado do círculo preenchido é a resposta (A, B, C ou D)
- ❌ NÃO confunda a LETRA com o CÍRCULO. A letra NÃO é a resposta!
- ❌ NÃO invente respostas. Se não tem certeza, retorne ""

═══════════════════════════════════════════════════════════════
EXEMPLOS CORRETOS:
═══════════════════════════════════════════════════════════════

Linha: [01] A○  B●  C○  D○   → Resposta: "B"
Linha: [02] A●  B○  C○  D○   → Resposta: "A"
Linha: [03] A○  B○  C○  D●   → Resposta: "D"
Linha: [04] A○  B○  C○  D○   → Resposta: "" (nenhum preenchido)
Linha: [05] A●  B●  C○  D○   → Resposta: "A" (o mais escuro)

═══════════════════════════════════════════════════════════════
DADOS DA PROVA:
═══════════════════════════════════════════════════════════════
- Aluno: {aluno_nome}
- Série: {serie}
- Disciplina: {disciplina}
- Total de questões: {total}
- Alternativas possíveis: {alternativas_str}

═══════════════════════════════════════════════════════════════
FORMATO DE RESPOSTA (JSON PURO, SEM TEXTO EXTRA):
═══════════════════════════════════════════════════════════════
{{"respostas": ["B", "A", "D", "", "A", ...]}}

⚠️ O array deve ter EXATAMENTE {total} elementos!

Analise a imagem linha por linha e retorne o JSON:"""


def preprocessar_imagem_para_ia(imagem_base64):
    """Pré-processamento para IA"""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        if img is None:
            return imagem_base64
        
        h, w = img.shape[:2]
        if h > 2000:
            scale = 2000 / h
            img = cv2.resize(img, (int(w * scale), 2000), interpolation=cv2.INTER_AREA)
        elif h < 1000:
            scale = 1500 / h
            img = cv2.resize(img, (int(w * scale), 1500), interpolation=cv2.INTER_CUBIC)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
        final = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
        
        _, buffer = cv2.imencode('.jpg', final, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return base64.b64encode(buffer).decode('utf-8')
    except Exception as e:
        logging.error(f"Erro no preprocessamento: {e}")
        return imagem_base64


def corrigir_com_ia_fallback(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina='', bncc=None):
    gabarito = padrao_gabarito['gabarito_oficial']
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')
    if not OPENAI_AVAILABLE or openai_client is None:
        return erro_correcao(aluno_nome, serie, disciplina, 'IA OpenAI não disponível')
    
    try:
        prompt = gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina)
        
        imagem_limpa = imagem_base64
        if ',' in imagem_base64:
            imagem_limpa = imagem_base64.split(',')[1]
        
        mimetype = extrair_mimetype(imagem_base64)
        
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mimetype};base64,{imagem_limpa}"}}
                ]
            }],
            max_tokens=1500,
            temperature=0.0
        )
        
        resposta_texto = response.choices[0].message.content
        logging.info(f"📝 Resposta OpenAI: {resposta_texto[:500]}...")
        
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        if json_match:
            dados = json.loads(json_match.group())
            respostas_ia = dados.get('respostas', [])
            alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
            respostas_validas = validar_respostas(respostas_ia, gabarito, alternativas)
            
            # Confiança 75 para IA
            confiancas = [75 if r else 30 for r in respostas_validas]
            
            return calcular_resultado_correcao(
                respostas_validas, gabarito, aluno_nome, serie,
                disciplina, tipo_questoes, 'ia', bncc=bncc, confiancas=confiancas
            )
        return erro_correcao(aluno_nome, serie, disciplina, 'Resposta da IA inválida')
    except Exception as e:
        logging.error(f"❌ Erro no fallback OpenAI: {e}")
        return erro_correcao(aluno_nome, serie, disciplina, str(e))


# ============================================
# ✅ FUNÇÃO PRINCIPAL DE CORREÇÃO - DEFINITIVA
# ============================================

def corrigir_com_gemini_com_padrao(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina='', bncc=None):
    """
    ✅ VERSÃO DEFINITIVA com votação entre métodos
    
    Estratégia:
    1. Detectar círculos (método principal)
    2. Validar resultado (se suspeito, usar IA)
    3. Comparar com IA se disponível
    4. Retornar resultado mais confiável
    """
    gabarito = padrao_gabarito['gabarito_oficial']
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')
    
    total_questoes = len(gabarito)
    
    try:
        # ═══════════════════════════════════════════════════
        # MÉTODO 1: CÍRCULOS
        # ═══════════════════════════════════════════════════
        logging.info("=" * 60)
        logging.info("📌 MÉTODO 1: DETECÇÃO DE CÍRCULOS")
        logging.info("=" * 60)
        
        circulos = detectar_circulos_preenchidos(imagem_base64)
        
        respostas_circulos = [''] * total_questoes
        confiancas_circulos = [0] * total_questoes
        valido_circulos = False
        
        if circulos and len(circulos) >= 4:
            respostas_circulos, confiancas_circulos = organizar_respostas_por_posicao(circulos, total_questoes)
            
            # Contar quantas respostas foram detectadas
            total_detectadas = len([r for r in respostas_circulos if r])
            
            logging.info(f"📊 Círculos detectaram {total_detectadas}/{total_questoes} respostas")
            
            if total_detectadas >= total_questoes * 0.7:
                nao_vazias = [r for r in respostas_circulos if r]
                # Verificar variedade
                if len(set(nao_vazias)) >= 2:
                    valido_circulos = True
                    logging.info(f"✅ CÍRCULOS VÁLIDOS")
                else:
                    logging.warning(f"⚠️ CÍRCULOS INVÁLIDOS: todas respostas = '{nao_vazias[0] if nao_vazias else 'vazio'}'")
            else:
                logging.warning(f"⚠️ CÍRCULOS INVÁLIDOS: apenas {total_detectadas}/{total_questoes} detectadas")
        else:
            logging.warning("⚠️ Nenhum círculo detectado")
        
        # ═══════════════════════════════════════════════════
        # MÉTODO 2: IA (OpenAI)
        # ═══════════════════════════════════════════════════
        logging.info("=" * 60)
        logging.info("📌 MÉTODO 2: IA (OpenAI)")
        logging.info("=" * 60)
        
        respostas_ia = [''] * total_questoes
        confiancas_ia = [0] * total_questoes
        valido_ia = False
        
        if OPENAI_AVAILABLE:
            try:
                imagem_processada = preprocessar_imagem_para_ia(imagem_base64)
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_processada, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc=bncc
                )
                
                if not resultado_ia.get('erro'):
                    respostas_ia = resultado_ia.get('respostas_detectadas', [''] * total_questoes)
                    confiancas_ia = resultado_ia.get('confianca_por_questao', [75] * total_questoes)
                    
                    total_detectadas_ia = len([r for r in respostas_ia if r])
                    nao_vazias_ia = [r for r in respostas_ia if r]
                    
                    if total_detectadas_ia >= total_questoes * 0.7 and len(set(nao_vazias_ia)) >= 2:
                        valido_ia = True
                        logging.info(f"✅ IA VÁLIDA ({total_detectadas_ia}/{total_questoes})")
                    else:
                        logging.warning(f"⚠️ IA INVÁLIDA ({total_detectadas_ia}/{total_questoes})")
                else:
                    logging.warning(f"⚠️ IA retornou erro: {resultado_ia.get('erro')}")
            except Exception as e:
                logging.error(f"❌ Erro na IA: {e}")
        else:
            logging.warning("⚠️ OpenAI não disponível")
        
        # ═══════════════════════════════════════════════════
        # DECISÃO FINAL
        # ═══════════════════════════════════════════════════
        logging.info("=" * 60)
        logging.info("🎯 DECISÃO FINAL")
        logging.info("=" * 60)
        
        if valido_circulos and valido_ia:
            # ✅ COMPARAÇÃO: se forem muito diferentes, priorizar CÍRCULOS
            # (círculos são mais confiáveis que IA em cartões padronizados)
            respostas_iguais = sum(1 for i in range(total_questoes) 
                                   if respostas_circulos[i] == respostas_ia[i])
            
            logging.info(f"📊 Concordância: {respostas_iguais}/{total_questoes}")
            
            if respostas_iguais >= total_questoes * 0.7:
                # Alta concordância - usar CÍRCULOS
                logging.info("✅ ALTA CONCORDÂNCIA - Usando CÍRCULOS")
                resposta_final = respostas_circulos
                confiancas_final = [90 if c > 70 else 70 for c in confiancas_circulos]
                metodo_usado = 'circulos'
            else:
                # Baixa concordância - usar CÍRCULOS mesmo assim (mais preciso)
                logging.warning(f"⚠️ BAIXA CONCORDÂNCIA - Usando CÍRCULOS")
                resposta_final = respostas_circulos
                confiancas_final = [70 if c > 50 else 50 for c in confiancas_circulos]
                metodo_usado = 'circulos'
            
        elif valido_circulos:
            logging.info("✅ Apenas CÍRCULOS válidos")
            resposta_final = respostas_circulos
            confiancas_final = confiancas_circulos
            metodo_usado = 'circulos'
            
        elif valido_ia:
            logging.info("✅ Apenas IA válida")
            resposta_final = respostas_ia
            confiancas_final = confiancas_ia
            metodo_usado = 'ia'
        
        else:
            logging.error("❌ NENHUM método válido")
            return erro_correcao(
                aluno_nome, serie, disciplina,
                '❌ Não foi possível ler as respostas do cartão.\n\n'
                'Verifique:\n'
                '1. A foto está nítida (sem tremores)?\n'
                '2. Boa iluminação (sem sombras)?\n'
                '3. Os círculos foram pintados completamente?\n'
                '4. Caneta preta ou azul (não lápis)?\n'
                '5. O cartão está plano (não amassado)?'
            )
        
        # ═══════════════════════════════════════════════════
        # RESULTADO FINAL
        # ═══════════════════════════════════════════════════
        respostas_validas = validar_respostas(resposta_final, gabarito, padrao_gabarito['alternativas'])
        
        resultado = calcular_resultado_correcao(
            respostas_validas, gabarito, aluno_nome, serie,
            disciplina, tipo_questoes, metodo_usado,
            circulos=circulos if metodo_usado == 'circulos' else None,
            bncc=bncc,
            confiancas=confiancas_final
        )
        resultado['metodo_usado'] = metodo_usado
        
        logging.info(f"✅ RESULTADO FINAL: {resultado['acertos']}/{resultado['total']} acertos ({metodo_usado})")
        
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
            except Exception:
                pass
    return response


# ============================================
# ROTAS DE LOGIN E CORREÇÃO
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
                cur.execute("SELECT id, nome, username, senha_hash, perfil, ativo FROM usuarios WHERE username = %s", (username,))
                usuario = cur.fetchone()
                cur.close()
                conn.close()
                if usuario:
                    if hmac.compare_digest(str(usuario['senha_hash'] or ''), str(senha)) and usuario['ativo'] == True:
                        return jsonify({'sucesso': True, 'perfil': usuario['perfil'], 'usuario': usuario['username'], 'nome': usuario['nome']})
            except Exception as e:
                print(f"❌ Erro no banco: {e}")
                traceback.print_exc()
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if hmac.compare_digest(str(dados['senha']), str(senha)):
                return jsonify({'sucesso': True, 'perfil': dados['perfil'], 'usuario': username, 'nome': dados['nome']})
        return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
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
        
        imagem_hash = hashlib.md5(imagem_base64.encode()).hexdigest()
        cache_key = get_cache_key(imagem_hash, prova_id, aluno_id)
        if cache_key in CORRECOES_CACHE:
            cache_data = CORRECOES_CACHE[cache_key]
            if datetime.now().timestamp() - cache_data['timestamp'] < CORRECOES_CACHE_TTL:
                return jsonify(cache_data['resultado'])
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT p.*, a.nome AS aluno_nome, a.turma_id, a.escola_id,
                       t.serie AS turma_serie, e.nome AS escola_nome
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
                return jsonify({'erro': 'Gabarito inválido.'}), 400
            
            tipo_questoes = prova.get('tipo_questoes') or 4
            if isinstance(tipo_questoes, str):
                try:
                    tipo_questoes = int(tipo_questoes)
                except Exception:
                    tipo_questoes = 4
            
            padrao_gabarito = gerar_padrao_gabarito(gabarito, tipo_questoes)
            aluno = dados
            nome_aluno = aluno.get('aluno_nome') or 'Aluno'
            serie = aluno.get('turma_serie') or prova.get('serie') or '1º Ano'
            bncc_gabarito = prova.get('bncc', [])
            cur.close()
            conn.close()
            
            disciplina = prova.get('disciplina', '')
            prova_titulo = prova.get('titulo', '')
            
            resultado = corrigir_com_gemini_com_padrao(
                imagem_base64, padrao_gabarito, nome_aluno,
                serie, tipo_questoes, disciplina, bncc=bncc_gabarito
            )
            
            if resultado.get('erro'):
                return jsonify(resultado), 400
            
            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
            
            if 'confianca_por_questao' not in resultado or not resultado['confianca_por_questao']:
                total = resultado.get('total', 20)
                resultado['confianca_por_questao'] = [70] * total
                resultado['confianca'] = 70
            
            # Salvar no histórico
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor()
                    questoes_status = resultado.get('questoes_status', [])
                    for i, q in enumerate(questoes_status):
                        if i < len(bncc_gabarito):
                            q['bncc'] = bncc_gabarito[i] if bncc_gabarito[i] else ''
                        else:
                            q['bncc'] = ''
                    questoes_status_json = json.dumps(questoes_status)
                    respostas_detectadas = resultado.get('respostas_detectadas', [])
                    
                    cur.execute("SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s", (prova_id, aluno_id))
                    existe = cur.fetchone()
                    
                    if existe:
                        cur.execute("""
                            UPDATE historico
                            SET respostas = %s::text[], acertos = %s, nota = %s, total = %s,
                                tipo_correcao = %s, disciplina = %s, tipo_avaliacao = %s,
                                questoes_status = %s::jsonb, confianca = %s,
                                confianca_por_questao = %s::jsonb, bncc = %s::text[],
                                data_correcao = CURRENT_TIMESTAMP
                            WHERE prova_id = %s AND aluno_id = %s
                        """, (respostas_detectadas, resultado.get('acertos', 0), resultado.get('nota', 0),
                              resultado.get('total', 0), resultado.get('modo', 'ia'), disciplina,
                              tipo_avaliacao, questoes_status_json, resultado.get('confianca', 70),
                              json.dumps(resultado.get('confianca_por_questao', [])),
                              bncc_gabarito, prova_id, aluno_id))
                    else:
                        cur.execute("""
                            INSERT INTO historico
                            (prova_id, aluno_id, respostas, acertos, nota, total,
                             tipo_correcao, disciplina, tipo_avaliacao, questoes_status,
                             confianca, confianca_por_questao, bncc)
                            VALUES (%s, %s, %s::text[], %s, %s, %s, %s, %s, %s, %s::jsonb,
                                    %s, %s::jsonb, %s::text[])
                        """, (prova_id, aluno_id, respostas_detectadas, resultado.get('acertos', 0),
                              resultado.get('nota', 0), resultado.get('total', 0),
                              resultado.get('modo', 'ia'), disciplina, tipo_avaliacao,
                              questoes_status_json, resultado.get('confianca', 70),
                              json.dumps(resultado.get('confianca_por_questao', [])),
                              bncc_gabarito))
                    conn.commit()
                    cur.close()
                    conn.close()
            except Exception as e:
                logging.error(f"⚠️ Erro ao salvar histórico: {e}")
            
            resultado['tipo_avaliacao'] = tipo_avaliacao
            resultado['disciplina'] = disciplina
            resultado['bncc'] = bncc_gabarito
            
            CORRECOES_CACHE[cache_key] = {'timestamp': datetime.now().timestamp(), 'resultado': resultado}
            
            return jsonify(resultado)
        except Exception as e:
            logging.error(f"❌ Erro na correção: {e}")
            traceback.print_exc()
            return jsonify({'erro': str(e)}), 500
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


# ============================================
# CORREÇÃO MANUAL
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
        cur.execute("SELECT disciplina, titulo, serie, gabarito, bncc FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        disciplina = prova[0] if prova else ''
        prova_titulo = prova[1] if prova else ''
        serie_prova = prova[2] if prova else ''
        gabarito = prova[3] if prova else []
        bncc_gabarito = prova[4] if prova else []
        
        cur.execute("SELECT t.serie FROM alunos a LEFT JOIN turmas t ON a.turma_id = t.id WHERE a.id = %s", (aluno_id,))
        serie_result = cur.fetchone()
        serie = serie_result[0] if serie_result else serie_prova or '1º Ano'
        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
        
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
                'numero': i + 1, 'resposta': resp or '—', 'gabarito': gab or '—',
                'acertou': is_correto, 'status': status_msg,
                'status_texto': f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}",
                'bncc': codigo_bncc
            })
        
        questoes_status_json = json.dumps(questoes_status)
        
        cur.execute("SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s", (prova_id, aluno_id))
        existe = cur.fetchone()
        
        if existe:
            cur.execute("""
                UPDATE historico
                SET respostas = %s::text[], acertos = %s, nota = %s, total = %s,
                    tipo_correcao = 'manual', disciplina = %s, tipo_avaliacao = %s,
                    questoes_status = %s::jsonb, data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, tipo_avaliacao, questoes_status_json, prova_id, aluno_id))
            result_id = existe[0] if isinstance(existe, tuple) else existe
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
        
        conn.commit()
        cur.close()
        conn.close()
        
        porcentagem = round((acertos / total) * 100) if total > 0 else 0
        conceito = calcular_conceito(porcentagem)
        
        return jsonify({
            'sucesso': True, 'id': result_id,
            'mensagem': 'Correção manual salva com sucesso',
            'conceito': conceito, 'porcentagem': porcentagem,
            'tipo_avaliacao': tipo_avaliacao,
            'questoes_status': questoes_status, 'bncc': bncc_gabarito
        })
    except Exception as e:
        traceback.print_exc()
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

        if OPENAI_AVAILABLE and openai_client is not None:
            try:
                prompt = f"""
                Avalie a redação abaixo e retorne APENAS um JSON válido:
                
                Redação: {texto}
                
                Formato exigido:
                {{"nota": 7.5, "metricas": {{"nota_coerencia": 8, "nota_estrutura": 7.5, "nota_gramatica": 7, "nota_vocabulario": 7.5}}, "feedback": "texto..."}}
                """
                
                response = openai_client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "Você é um professor especialista em avaliar redações. Responda SEMPRE em JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.5,
                    response_format={"type": "json_object"}
                )
                
                resposta_texto = response.choices[0].message.content
                resultado = json.loads(resposta_texto)
                resultado['modo'] = 'openai'
                return jsonify(resultado)
            except Exception as e:
                print(f"⚠️ Erro no OpenAI para redação: {e}")

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
                    except Exception:
                        pass
            except Exception as e:
                print(f"⚠️ Erro no RelayFreeLLM para redação: {e}")

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
            aluno_id, prova_id, texto, nota,
            metricas.get('nota_coerencia', 0),
            metricas.get('nota_estrutura', 0),
            metricas.get('nota_gramatica', 0),
            metricas.get('nota_vocabulario', 0),
            feedback, 'ia'
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
# ROTAS DE HISTÓRICO
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
                params.append(int(escola_id))
                query += " AND e.id = %s"
            except ValueError:
                pass

        if turma_id and turma_id != '' and turma_id != 'null':
            try:
                params.append(int(turma_id))
                query += " AND t.id = %s"
            except ValueError:
                pass

        if aluno_id and aluno_id != '' and aluno_id != 'null':
            try:
                params.append(int(aluno_id))
                query += " AND h.aluno_id = %s"
            except ValueError:
                pass

        if prova_id and prova_id != '' and prova_id != 'null':
            try:
                params.append(int(prova_id))
                query += " AND h.prova_id = %s"
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
                p.gabarito as prova_gabarito,
                p.quantidade_questoes,
                p.bncc as prova_bncc,
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
                params.append(int(escola_id))
                query += " AND e.id = %s"
            except ValueError:
                pass

        if turma_id and turma_id != '' and turma_id != 'null':
            try:
                params.append(int(turma_id))
                query += " AND t.id = %s"
            except ValueError:
                pass

        if aluno_id and aluno_id != '' and aluno_id != 'null':
            try:
                params.append(int(aluno_id))
                query += " AND h.aluno_id = %s"
            except ValueError:
                pass

        if serie and serie != '' and serie != 'null':
            params.append(serie)
            query += " AND t.serie = %s"

        if prova_id and prova_id != '' and prova_id != 'null':
            try:
                params.append(int(prova_id))
                query += " AND h.prova_id = %s"
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

            respostas = item.get('respostas', [])
            gabarito = item.get('prova_gabarito', [])
            if not gabarito or len(gabarito) == 0:
                gabarito = item.get('gabarito', [])

            total_questoes = item.get('quantidade_questoes', 20)
            if len(respostas) < total_questoes:
                respostas = list(respostas) + [''] * (total_questoes - len(respostas))
            if len(gabarito) < total_questoes:
                gabarito = list(gabarito) + [''] * (total_questoes - len(gabarito))

            bncc_list = item.get('prova_bncc', [])
            if len(bncc_list) < total_questoes:
                bncc_list = list(bncc_list) + [''] * (total_questoes - len(bncc_list))

            questoes_status = []
            acertos = 0
            erros = 0

            for i in range(total_questoes):
                resp = str(respostas[i] if i < len(respostas) else '').strip().upper()
                gab = str(gabarito[i] if i < len(gabarito) else '').strip().upper()

                is_resposta_valida = resp and resp != '' and resp != '—' and resp != '-'
                is_correto = is_resposta_valida and resp == gab and gab != ''

                codigo_bncc = bncc_list[i] if i < len(bncc_list) and bncc_list[i] else ''

                if is_correto:
                    acertos += 1
                else:
                    erros += 1

                questoes_status.append({
                    'numero': i + 1,
                    'resposta': resp if resp else '—',
                    'gabarito': gab if gab else '—',
                    'acertou': is_correto,
                    'respondida': is_resposta_valida,
                    'bncc': codigo_bncc,
                    'status': '✅ ACERTOU' if is_correto else ('❌ ERROU' if is_resposta_valida else '— NÃO RESPONDEU')
                })

            if tipo not in alunos_map[aluno_key]['avaliacoes']:
                alunos_map[aluno_key]['avaliacoes'][tipo] = {
                    'nota': float(item.get('nota', 0)),
                    'acertos': acertos, 'erros': erros, 'total': total_questoes,
                    'prova': prova_titulo, 'data': item.get('data_correcao', ''),
                    'disciplina': disciplina, 'questoes_status': questoes_status,
                    'bncc': [q['bncc'] for q in questoes_status],
                    'respostas': [q['resposta'] for q in questoes_status],
                    'gabarito': [q['gabarito'] for q in questoes_status]
                }
            else:
                existing = alunos_map[aluno_key]['avaliacoes'][tipo]
                data_atual = item.get('data_correcao', '')
                data_existente = existing.get('data', '')
                if data_atual > data_existente:
                    alunos_map[aluno_key]['avaliacoes'][tipo] = {
                        'nota': float(item.get('nota', 0)),
                        'acertos': acertos, 'erros': erros, 'total': total_questoes,
                        'prova': prova_titulo, 'data': data_atual,
                        'disciplina': disciplina, 'questoes_status': questoes_status,
                        'bncc': [q['bncc'] for q in questoes_status],
                        'respostas': [q['resposta'] for q in questoes_status],
                        'gabarito': [q['gabarito'] for q in questoes_status]
                    }

        resultado = []
        for aluno_key, dados in alunos_map.items():
            avaliacoes = dados['avaliacoes']

            default = {
                'nota': 0, 'acertos': 0, 'erros': 0, 'total': 20,
                'questoes_status': [], 'bncc': [], 'respostas': [], 'gabarito': []
            }

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

        return jsonify({'sucesso': True, 'mensagem': 'Correção excluída com sucesso', 'id': id})

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS DE GABARITOS
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
            SET gabarito = NULL, quantidade_questoes = 0, bncc = NULL,
                textos_questoes = NULL, niveis = NULL
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
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS DE ESCOLAS
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
            SET nome = %s, inep = %s, municipio = %s, estado = %s,
                telefone = %s, diretor = %s
            WHERE id = %s RETURNING id
        """, (nome, data.get('inep', ''), data.get('municipio', ''),
              data.get('estado', 'PA'), data.get('telefone', ''), data.get('diretor', ''), id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Escola atualizada com sucesso'})

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/escolas/<int:id>', methods=['DELETE'])
def excluir_escola(id):
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

        return jsonify({
            'sucesso': True,
            'mensagem': f'Escola "{escola_nome}" excluída com sucesso!',
            'detalhes': {'turmas_excluidas': total_turmas, 'alunos_excluidos': total_alunos}
        })

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS DE TURMAS
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
                t.id, t.nome, t.serie, t.turno, t.professor, t.capacidade,
                t.ano_letivo, t.escola_id, e.nome as escola_nome,
                COUNT(a.id) as total_alunos
            FROM turmas t
            LEFT JOIN escolas e ON t.escola_id = e.id
            LEFT JOIN alunos a ON a.turma_id = t.id
        """
        params = []

        if escola_id and escola_id != '' and escola_id != 'null' and escola_id != 'undefined':
            try:
                params.append(int(escola_id))
                query += " WHERE t.escola_id = %s"
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
            SELECT t.id, t.nome, t.serie, t.turno, t.professor, t.capacidade,
                   t.ano_letivo, t.escola_id, e.nome as escola_nome
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
            SET escola_id = %s, nome = %s, serie = %s, turno = %s,
                professor = %s, capacidade = %s, ano_letivo = %s
            WHERE id = %s RETURNING id
        """, (data['escola_id'], data['nome'], data.get('serie', '1º Ano'),
              data.get('turno', 'Manhã'), data.get('professor', ''),
              data.get('capacidade', 35), data.get('ano_letivo', 2025), id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Turma atualizada com sucesso'})

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
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

        turma_id, turma_nome = turma[0], turma[1]

        cur.execute("SELECT COUNT(*) FROM alunos WHERE turma_id = %s", (turma_id,))
        total_alunos = cur.fetchone()[0]

        cur.execute("DELETE FROM turmas WHERE id = %s", (turma_id,))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'sucesso': True,
            'mensagem': f'Turma "{turma_nome}" excluída com sucesso!',
            'detalhes': {'alunos_excluidos': total_alunos}
        })

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS DE ALUNOS
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
                a.id, a.nome, a.matricula, a.numero_chamada, a.data_nascimento,
                a.genero, a.responsavel, a.telefone, a.email, a.observacoes,
                a.turma_id, a.escola_id,
                t.nome as turma_nome, t.serie as turma_serie, t.turno as turma_turno,
                e.nome as escola_nome
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            WHERE 1=1
        """
        params = []

        if escola_id and escola_id != '' and escola_id != 'null' and escola_id != 'undefined':
            try:
                params.append(int(escola_id))
                query += " AND a.escola_id = %s"
            except ValueError:
                pass

        if turma_id and turma_id != '' and turma_id != 'null' and turma_id != 'undefined':
            try:
                params.append(int(turma_id))
                query += " AND a.turma_id = %s"
            except ValueError:
                pass

        if serie and serie != '' and serie != 'null' and serie != 'undefined':
            params.append(serie)
            query += " AND t.serie = %s"

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
            data['escola_id'], data['turma_id'], data['nome'],
            data.get('matricula', ''), data.get('numero_chamada'),
            data.get('data_nascimento'), data.get('genero', 'Masculino'),
            data.get('responsavel', ''), data.get('telefone', ''),
            data.get('email', ''), data.get('observacoes', '')
        ))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'id': result['id'], 'mensagem': 'Aluno criado com sucesso'})

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
            SELECT a.*, t.nome as turma_nome, t.serie as turma_serie,
                   e.nome as escola_nome, e.id as escola_id
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
            SET escola_id = %s, turma_id = %s, nome = %s, matricula = %s,
                numero_chamada = %s, data_nascimento = %s, genero = %s,
                responsavel = %s, telefone = %s, email = %s, observacoes = %s
            WHERE id = %s RETURNING id
        """, (
            data['escola_id'], data['turma_id'], data['nome'],
            data.get('matricula', ''), data.get('numero_chamada'),
            data.get('data_nascimento'), data.get('genero', 'Masculino'),
            data.get('responsavel', ''), data.get('telefone', ''),
            data.get('email', ''), data.get('observacoes', ''), id
        ))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Aluno atualizado com sucesso'})

    except Exception as e:
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

        return jsonify({'sucesso': True, 'mensagem': f'Aluno "{aluno_nome}" excluído com sucesso!'})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS DE PROVAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.id, p.titulo, p.serie, p.disciplina, p.bimestre, p.data_prova,
                   p.valor_nota, p.tipo_questoes, p.quantidade_questoes, p.gabarito,
                   p.bncc, p.textos_questoes, p.niveis, p.created_at
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

        cur.execute("SELECT id FROM provas WHERE titulo = %s AND serie = %s", (titulo, serie))
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
            titulo, serie, data.get('disciplina', ''), data.get('bimestre', ''),
            data.get('data_prova'), data.get('nota_maxima', 10),
            data.get('tipo_questoes', '4'), data.get('quantidade_questoes', 20),
            data.get('gabarito', []), bncc_validos, textos_validos, niveis_validos
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
            SELECT id, titulo, serie, disciplina, bimestre, data_prova,
                   valor_nota, tipo_questoes, quantidade_questoes, gabarito,
                   bncc, textos_questoes, niveis, created_at
            FROM provas WHERE id = %s
        """, (id,))
        prova = cur.fetchone()
        cur.close()
        conn.close()

        if not prova:
            return jsonify({'erro': 'Prova não encontrada'}), 404

        return jsonify(prova)

    except Exception as e:
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
            SET titulo = %s, serie = %s, disciplina = %s, bimestre = %s,
                data_prova = %s, valor_nota = %s, tipo_questoes = %s,
                quantidade_questoes = %s, gabarito = %s, bncc = %s,
                textos_questoes = %s, niveis = %s
            WHERE id = %s RETURNING id
        """, (titulo, serie, data.get('disciplina', ''), data.get('bimestre', ''),
              data.get('data_prova'), data.get('nota_maxima', 10),
              data.get('tipo_questoes', '4'), data.get('quantidade_questoes', 20),
              data.get('gabarito', []), bncc_validos, textos_validos, niveis_validos, id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Prova atualizada com sucesso'})

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/provas/<int:id>', methods=['DELETE'])
def excluir_prova(id):
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

        return jsonify({'sucesso': True, 'mensagem': f'Prova "{prova_titulo}" excluída com sucesso!'})

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS DE USUÁRIOS
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
            'id': 0, 'nome': dados['nome'], 'username': username,
            'email': '', 'perfil': dados['perfil'], 'ativo': True,
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
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (nome, username, senha, email, perfil, ativo))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'id': result['id'], 'mensagem': 'Usuário criado com sucesso'})

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
        cur.execute("SELECT id, nome, username, email, perfil, ativo, criado_em FROM usuarios WHERE id = %s", (id,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if not usuario:
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        return jsonify(usuario)

    except Exception as e:
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

        update_fields = ["nome = %s", "username = %s", "email = %s", "perfil = %s", "ativo = %s"]
        params = [nome, username, email, perfil, ativo]

        if senha and len(senha) >= 4:
            update_fields.append("senha_hash = %s")
            params.append(senha)

        params.append(id)

        cur.execute(f"""
            UPDATE usuarios SET {', '.join(update_fields)}
            WHERE id = %s RETURNING id
        """, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Usuário atualizado com sucesso'})

    except Exception as e:
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

        return jsonify({'sucesso': True, 'mensagem': f'Usuário "{username}" excluído com sucesso'})

    except Exception as e:
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
                t.id as turma_id, t.nome as turma_nome, t.serie,
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
# ROTA DE GERAÇÃO DE CARTÃO RESPOSTA - OTIMIZADO
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json

        campos_obrigatorios = ['escola_id', 'turma_id', 'aluno_id', 'prova_id']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'erro': f'Campo "{campo}" é obrigatório'}), 400

        escola_id = data.get('escola_id')
        turma_id = data.get('turma_id')
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')

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

        cur.execute("SELECT p.* FROM provas p WHERE p.id = %s", (prova_id,))
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
        quantidade_questoes = int(prova.get('quantidade_questoes', 20))

        # ✅ Layout em 1 coluna para 10 questões, 2 colunas para 20
        if quantidade_questoes <= 12:
            q_por_coluna = quantidade_questoes
            num_colunas = 1
        elif quantidade_questoes <= 24:
            q_por_coluna = 12
            num_colunas = 2
        else:
            q_por_coluna = 15
            num_colunas = 2

        circle_size = 22
        circle_spacing = 6
        row_height = 36

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cartão Resposta - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        @page {{
            size: A4 portrait;
            margin: 6mm 5mm;
        }}
        
        body {{
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: #f5f5f5;
            padding: 10px;
            display: flex;
            justify-content: center;
        }}
        
        .folha {{
            width: 210mm;
            min-height: 297mm;
            background: #ffffff;
            padding: 4mm;
            position: relative;
            box-shadow: 0 2px 20px rgba(0,0,0,0.15);
        }}
        
        .fiducial {{
            position: absolute;
            width: 20mm;
            height: 20mm;
            background: #000000;
            z-index: 10;
        }}
        .fiducial-tl {{ top: 3mm; left: 3mm; }}
        .fiducial-tr {{ top: 3mm; right: 3mm; }}
        .fiducial-bl {{ bottom: 3mm; left: 3mm; }}
        .fiducial-br {{ bottom: 3mm; right: 3mm; }}
        
        .fiducial::after {{
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 6mm;
            height: 6mm;
            background: #ffffff;
            border-radius: 50%;
        }}
        
        .header {{
            text-align: center;
            border-bottom: 2px solid #000;
            padding-bottom: 6px;
            margin: 24mm 0 6px 0;
        }}
        .header h1 {{
            font-size: 11px;
            color: #000;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
        .header h2 {{
            font-size: 14px;
            color: #000;
            font-weight: 900;
            margin-top: 3px;
            border: 2px solid #000;
            display: inline-block;
            padding: 2px 16px;
        }}
        .header .prova {{
            font-size: 11px;
            color: #000;
            font-weight: bold;
            margin-top: 4px;
        }}
        .header .escola {{
            font-size: 9px;
            color: #333;
            margin-top: 2px;
        }}
        
        .info-aluno {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 4px;
            border: 2px solid #000;
            padding: 6px 10px;
            margin-bottom: 6px;
            font-size: 10px;
        }}
        .info-aluno .campo {{
            display: flex;
            gap: 6px;
        }}
        .info-aluno .campo strong {{
            color: #000;
            font-weight: 900;
        }}
        
        .instrucoes {{
            border: 2px solid #000;
            padding: 4px 10px;
            margin-bottom: 8px;
            font-size: 9px;
            font-weight: bold;
            text-align: center;
            background: #f0f0f0;
        }}
        
        .questoes-container {{
            display: grid;
            grid-template-columns: repeat({num_colunas}, 1fr);
            gap: 8px;
            border: 2px solid #000;
            padding: 8px;
        }}
        
        .coluna-questoes {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        
        .linha-questao {{
            display: flex;
            align-items: center;
            height: {row_height}px;
            padding: 0 4px;
            border-bottom: 1px dashed #ccc;
            gap: 8px;
        }}
        .linha-questao:last-child {{
            border-bottom: none;
        }}
        
        .num-questao {{
            font-size: 12px;
            font-weight: 900;
            color: #000;
            min-width: 24px;
            text-align: right;
            padding-right: 4px;
            border-right: 2px solid #000;
        }}
        
        .alternativas {{
            display: flex;
            gap: {circle_spacing}px;
            justify-content: space-around;
            flex: 1;
        }}
        
        .alt-item {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        
        .letra {{
            font-size: 11px;
            font-weight: 900;
            color: #000;
            min-width: 10px;
        }}
        
        .circulo {{
            width: {circle_size}px;
            height: {circle_size}px;
            border: 2.5px solid #000000;
            border-radius: 50%;
            background: #ffffff;
            display: inline-block;
            flex-shrink: 0;
        }}
        
        .rodape {{
            margin-top: 8px;
            display: flex;
            justify-content: space-between;
            font-size: 7px;
            color: #666;
            border-top: 1px solid #ccc;
            padding-top: 4px;
        }}
        
        .btn-print {{
            display: block;
            width: 100%;
            margin-top: 8px;
            padding: 10px;
            background: #000;
            color: #fff;
            border: none;
            font-size: 13px;
            font-weight: bold;
            cursor: pointer;
            border-radius: 4px;
        }}
        .btn-print:hover {{
            background: #333;
        }}
        
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .folha {{ box-shadow: none; }}
            .btn-print {{ display: none; }}
            .fiducial {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
            .fiducial::after {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
            .circulo {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>
    <div class="folha">
        <div class="fiducial fiducial-tl"></div>
        <div class="fiducial fiducial-tr"></div>
        <div class="fiducial fiducial-bl"></div>
        <div class="fiducial fiducial-br"></div>
        
        <div class="header">
            <h1>SECRETARIA MUNICIPAL DE EDUCAÇÃO — SISAM 2026</h1>
            <h2>CARTÃO RESPOSTA</h2>
            <div class="prova">{titulo_prova}</div>
            <div class="escola">{escola_nome} | Série: {serie} | Turma: {turma_nome}</div>
        </div>
        
        <div class="info-aluno">
            <div class="campo"><strong>Aluno(a):</strong> <span>{nome_aluno}</span></div>
            <div class="campo"><strong>Data:</strong> <span>{datetime.now().strftime('%d/%m/%Y')}</span></div>
        </div>
        
        <div class="instrucoes">
            ⚠️ PREENCHA COMPLETAMENTE O CÍRCULO COM CANETA PRETA OU AZUL — NÃO RASURE
        </div>
        
        <div class="questoes-container">
"""

        for col in range(num_colunas):
            inicio = col * q_por_coluna
            fim = min(inicio + q_por_coluna, quantidade_questoes)
            
            if inicio >= quantidade_questoes:
                break
            
            html += '<div class="coluna-questoes">'
            
            for i in range(inicio, fim):
                html += f"""
                    <div class="linha-questao">
                        <div class="num-questao">{i+1:02d}</div>
                        <div class="alternativas">
"""
                for alt in alternativas:
                    html += f"""
                            <div class="alt-item">
                                <span class="letra">{alt}</span>
                                <span class="circulo"></span>
                            </div>
"""
                html += """
                        </div>
                    </div>
"""
            
            html += '</div>'

        html += f"""
        </div>
        
        <button class="btn-print" onclick="window.print()">🖨️ IMPRIMIR CARTÃO RESPOSTA</button>
        
        <div class="rodape">
            <span>Gerado pelo sistema CorrigePro — {datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
            <span>Página 1/1</span>
        </div>
    </div>
</body>
</html>
"""
        return html, 200, {'Content-Type': 'text/html'}

    except Exception as e:
        print(f"❌ Erro ao gerar cartão: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ============================================
# ROTAS PARA MATRIZ DE PROFICIÊNCIA
# ============================================

@app.route('/api/matrizes', methods=['GET'])
def listar_matrizes():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, ano, disciplina, nivel, descritores, created_at
            FROM matrizes ORDER BY created_at DESC
        """)
        matrizes = cur.fetchall()
        cur.close()
        conn.close()

        for m in matrizes:
            if m['descritores']:
                try:
                    if isinstance(m['descritores'], str):
                        m['descritores'] = json.loads(m['descritores'])
                    elif isinstance(m['descritores'], dict):
                        m['descritores'] = [m['descritores']] if m['descritores'] else []
                except Exception as e:
                    print(f"⚠️ Erro ao converter descritores: {e}")
                    m['descritores'] = []
            else:
                m['descritores'] = []

        return jsonify(matrizes)
    except Exception as e:
        logging.error(f"Erro ao listar matrizes: {e}")
        return jsonify([]), 500


@app.route('/api/matrizes/<int:id>', methods=['GET'])
def buscar_matriz_por_id(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, ano, disciplina, nivel, descritores, created_at
            FROM matrizes WHERE id = %s
        """, (id,))
        matriz = cur.fetchone()
        cur.close()
        conn.close()

        if not matriz:
            return jsonify({'erro': 'Matriz não encontrada'}), 404

        if matriz['descritores']:
            try:
                matriz['descritores'] = json.loads(matriz['descritores'])
            except Exception:
                matriz['descritores'] = []
        else:
            matriz['descritores'] = []

        return jsonify(matriz)
    except Exception as e:
        logging.error(f"Erro ao buscar matriz por ID: {e}")
        return jsonify({'erro': str(e)}), 500


@app.route('/api/matrizes', methods=['POST'])
def criar_matriz():
    try:
        data = request.json
        ano = data.get('ano')
        disciplina = data.get('disciplina')
        nivel = data.get('nivel')
        descritores = data.get('descritores', [])

        if not ano or not disciplina or not nivel:
            return jsonify({'erro': 'Ano, disciplina e nível são obrigatórios'}), 400

        if not isinstance(descritores, list):
            descritores = []

        descritores_json = json.dumps(descritores, ensure_ascii=False)

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO matrizes (ano, disciplina, nivel, descritores)
            VALUES (%s, %s, %s, %s::jsonb) RETURNING id
        """, (ano, disciplina, nivel, descritores_json))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'id': result['id'], 'mensagem': 'Matriz criada com sucesso!'})
    except Exception as e:
        logging.error(f"Erro ao criar matriz: {e}")
        return jsonify({'erro': str(e)}), 500


@app.route('/api/matrizes/<int:id>', methods=['PUT'])
def atualizar_matriz(id):
    try:
        data = request.json
        ano = data.get('ano')
        disciplina = data.get('disciplina')
        nivel = data.get('nivel')
        descritores = data.get('descritores', [])

        if not ano or not disciplina or not nivel:
            return jsonify({'erro': 'Ano, disciplina e nível são obrigatórios'}), 400

        descritores_json = json.dumps(descritores, ensure_ascii=False)

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            UPDATE matrizes
            SET ano = %s, disciplina = %s, nivel = %s, descritores = %s::jsonb
            WHERE id = %s RETURNING id
        """, (ano, disciplina, nivel, descritores_json, id))

        result = cur.fetchone()
        if not result:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Matriz não encontrada'}), 404

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'id': result['id'], 'mensagem': 'Matriz atualizada com sucesso!'})
    except Exception as e:
        logging.error(f"Erro ao atualizar matriz: {e}")
        return jsonify({'erro': str(e)}), 500


@app.route('/api/matrizes/<int:id>', methods=['DELETE'])
def excluir_matriz(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("DELETE FROM matrizes WHERE id = %s RETURNING id", (id,))
        result = cur.fetchone()

        if not result:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Matriz não encontrada'}), 404

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'mensagem': 'Matriz excluída com sucesso!'})
    except Exception as e:
        logging.error(f"Erro ao excluir matriz: {e}")
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

        tables = ['escolas', 'turmas', 'alunos', 'provas', 'historico', 'usuarios', 'correcoes_texto', 'matrizes']
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
    except Exception:
        return jsonify({
            'mensagem': 'CorrigePro API',
            'status': 'online',
            'endpoints': [
                '/health', '/api/login', '/api/corrigir', '/api/corrigir_manual',
                '/api/corrigir_redacao', '/api/salvar_correcao_texto', '/api/correcoes_texto',
                '/api/escolas', '/api/turmas', '/api/alunos', '/api/provas',
                '/api/gabaritos', '/api/historico', '/api/historico/agrupado',
                '/api/dashboard', '/api/dashboard/Conceito', '/api/gerar_gabarito',
                '/api/backup', '/api/usuarios', '/api/matrizes'
            ]
        })


@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('.', path)
    except Exception:
        return jsonify({'erro': 'Arquivo não encontrado'}), 404


@app.route('/health', methods=['GET'])
def health_check():
    conn = get_db_connection()
    db_ok = conn is not None
    if conn:
        conn.close()
    return jsonify({
        'status': 'online',
        'openai': 'disponível' if OPENAI_AVAILABLE else 'indisponível',
        'openai_modelo': OPENAI_MODEL if OPENAI_AVAILABLE else None,
        'relay': 'disponível' if RELAY_AVAILABLE else 'indisponível',
        'database': 'conectado' if db_ok else 'desconectado',
        'pool': {'min': DB_POOL_MIN, 'max': DB_POOL_MAX}
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

            cur.execute("""
                CREATE TABLE matrizes (
                    id SERIAL PRIMARY KEY,
                    ano TEXT NOT NULL,
                    disciplina TEXT NOT NULL,
                    nivel TEXT NOT NULL,
                    descritores JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            print("✅ Tabelas criadas com sucesso!")
        else:
            print("📌 Tabelas já existem, verificando colunas...")

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'provas' AND column_name = 'bncc'
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE provas ADD COLUMN bncc TEXT[]")
                    print("✅ Coluna bncc adicionada!")
                except Exception as e:
                    print(f"⚠️ Erro: {e}")

            for col in ['textos_questoes', 'niveis']:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'provas' AND column_name = %s
                """, (col,))
                if not cur.fetchone():
                    try:
                        cur.execute(f"ALTER TABLE provas ADD COLUMN {col} TEXT[]")
                        print(f"✅ Coluna {col} adicionada!")
                    except Exception as e:
                        print(f"⚠️ Erro: {e}")

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'historico' AND column_name = 'questoes_status'
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE historico ADD COLUMN questoes_status JSONB DEFAULT '[]'")
                    print("✅ Coluna questoes_status adicionada!")
                except Exception as e:
                    print(f"⚠️ Erro: {e}")

            for col in ['confianca', 'confianca_por_questao']:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'historico' AND column_name = %s
                """, (col,))
                if not cur.fetchone():
                    try:
                        if col == 'confianca':
                            cur.execute("ALTER TABLE historico ADD COLUMN confianca DECIMAL(5,2)")
                        else:
                            cur.execute("ALTER TABLE historico ADD COLUMN confianca_por_questao JSONB DEFAULT '[]'")
                        print(f"✅ Coluna {col} adicionada!")
                    except Exception as e:
                        print(f"⚠️ Erro: {e}")

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'historico' AND column_name = 'bncc'
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE historico ADD COLUMN bncc TEXT[]")
                    print("✅ Coluna bncc adicionada ao historico!")
                except Exception as e:
                    print(f"⚠️ Erro: {e}")

            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'matrizes'
                )
            """)
            if not cur.fetchone()[0]:
                try:
                    cur.execute("""
                        CREATE TABLE matrizes (
                            id SERIAL PRIMARY KEY,
                            ano TEXT NOT NULL,
                            disciplina TEXT NOT NULL,
                            nivel TEXT NOT NULL,
                            descritores JSONB DEFAULT '[]',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    print("✅ Tabela matrizes criada!")
                except Exception as e:
                    print(f"⚠️ Erro: {e}")

        for username, dados in USUARIOS_FIXOS.items():
            cur.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO usuarios (nome, username, senha_hash, perfil, ativo)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (dados['nome'], username, dados['senha'], dados['perfil']))
                print(f"✅ Usuário {username} criado!")

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
            "CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username)",
            "CREATE INDEX IF NOT EXISTS idx_matrizes_ano ON matrizes(ano)",
            "CREATE INDEX IF NOT EXISTS idx_matrizes_disciplina ON matrizes(disciplina)",
            "CREATE INDEX IF NOT EXISTS idx_matrizes_nivel ON matrizes(nivel)"
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
    print(f"🤖 OpenAI (ChatGPT): {'✅ Disponível' if OPENAI_AVAILABLE else '❌ Indisponível'}")
    if OPENAI_AVAILABLE:
        print(f"📌 Modelo: {OPENAI_MODEL}")
    print(f"🤖 RelayFreeLLM: {'✅ Disponível' if RELAY_AVAILABLE else '❌ Indisponível'}")
    print("=" * 60)
    print("📋 ESTRATÉGIA DE CORREÇÃO:")
    print("   1️⃣ Detecção de círculos (OpenCV)")
    print("   2️⃣ Validação rigorosa dos resultados")
    print("   3️⃣ Fallback para IA (OpenAI) se necessário")
    print("   4️⃣ Comparação entre métodos")
    print("=" * 60)
    print("✅ MELHORIAS APLICADAS:")
    print("   - Threshold adaptativo de preenchimento")
    print("   - Filtro de tamanho de círculo (remove letras)")
    print("   - Validação de linhas e padrões suspeitos")
    print("   - Prompt da IA descrevendo letra AO LADO do círculo")
    print("   - Votação entre métodos (círculos vs IA)")
    print("   - Retorna erro se nada for confiável")
    print("=" * 60)

    init_db()
    app.run(host='0.0.0.0', port=port, debug=False)
