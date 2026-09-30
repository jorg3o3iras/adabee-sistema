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
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================
# CACHE PERSISTENTE DE CORREÇÕES (PostgreSQL)
# ============================================
CORRECOES_CACHE_TTL_HORAS = 168

# ⚡ DEBUG: CACHE DESATIVADO TEMPORARIAMENTE
CACHE_ENABLED = False


def init_cache_table():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS correcoes_cache (
                id SERIAL PRIMARY KEY,
                chave_hash TEXT NOT NULL,
                resultado JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_correcoes_cache_hash 
            ON correcoes_cache(chave_hash, created_at DESC)
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ Tabela de cache de correções pronta")
    except Exception as e:
        logging.warning(f"⚠️ Erro ao criar tabela de cache: {e}")


def get_cache_key(imagem_hash, prova_id, aluno_id):
    return f"{imagem_hash}_{prova_id}_{aluno_id}"


def get_cache_correcao(chave):
    if not CACHE_ENABLED:
        return None
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT resultado FROM correcoes_cache
            WHERE chave_hash = %s
            AND created_at > NOW() - INTERVAL '%s hours'
            ORDER BY created_at DESC
            LIMIT 1
        """, (chave, CORRECOES_CACHE_TTL_HORAS))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row['resultado'] if isinstance(row['resultado'], dict) else json.loads(row['resultado'])
        return None
    except Exception as e:
        logging.warning(f"⚠️ Erro ao buscar cache: {e}")
        return None


def set_cache_correcao(chave, resultado):
    if not CACHE_ENABLED:
        return
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO correcoes_cache (chave_hash, resultado)
            VALUES (%s, %s::jsonb)
        """, (chave, json.dumps(resultado, default=str)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"⚠️ Erro ao salvar cache: {e}")


def limpar_cache_antigo():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM correcoes_cache
            WHERE created_at < NOW() - INTERVAL '%s hours'
        """, (CORRECOES_CACHE_TTL_HORAS,))
        removidas = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if removidas > 0:
            logging.info(f"🧹 Cache antigo limpo: {removidas} entradas")
    except Exception as e:
        logging.warning(f"⚠️ Erro ao limpar cache: {e}")


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
    OPENAI_AVAILABLE = False
except Exception as e:
    print(f"⚠️ Erro ao configurar OpenAI: {e}")
    OPENAI_AVAILABLE = False

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


USUARIOS_FIXOS = {
    'admin': {'senha': 'admin', 'perfil': 'admin', 'nome': 'Administrador'},
    'usuario': {'senha': '123', 'perfil': 'usuario', 'nome': 'Usuário'},
    'professor1': {'senha': '123', 'perfil': 'usuario', 'nome': 'Professor 1'}
}


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
    alternativas = ['A', 'B', 'C', 'D', 'E'][:tipo_questoes]
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


def validar_gabarito(gabarito, tipo_questoes=4):
    if not gabarito or len(gabarito) == 0:
        return False
    try:
        tipo = int(tipo_questoes)
    except (ValueError, TypeError):
        tipo = 4
    tipo = max(3, min(tipo, 5))
    alternativas_validas = ['A', 'B', 'C', 'D', 'E'][:tipo]
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
    alternativas = ['A', 'B', 'C', 'D', 'E'][:tipo_questoes]
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

    questoes_suspeitas = []
    if confiancas:
        for i, c in enumerate(confiancas):
            if c < 50:
                questoes_suspeitas.append(i + 1)
    requer_revisao = len(questoes_suspeitas) > 0 or confianca_media < 60

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
        'questoes_ia': 0, 'bncc': bncc if bncc else [],
        'requer_revisao_manual': requer_revisao,
        'questoes_suspeitas': questoes_suspeitas
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
        'valor_por_questao': 0, 'bncc': [],
        'requer_revisao_manual': False, 'questoes_suspeitas': []
    }


# ============================================
# DETECÇÃO DE MARCADORES FIDUCIAIS
# ============================================

def detectar_marcadores_fiduciais(gray):
    """Detecta os 4 marcadores fiduciais nos cantos do cartão."""
    try:
        altura, largura = gray.shape
        logging.info(f"🔍 Procurando marcadores em {largura}x{altura}...")

        area_imagem = largura * altura
        area_min = area_imagem * 0.0015
        area_max = area_imagem * 0.05

        candidatos = []

        _, binaria = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)

        contornos, hierarquia = cv2.findContours(
            binaria, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        if hierarquia is not None and len(contornos) > 0:
            hierarquia = hierarquia[0]

            for i, c in enumerate(contornos):
                x, y, w, h = cv2.boundingRect(c)
                area = w * h

                if not (area_min < area < area_max):
                    continue

                aspect = w / float(h) if h > 0 else 0
                if not (0.6 < aspect < 1.5):
                    continue

                area_contorno = cv2.contourArea(c)
                if area_contorno < area * 0.3:
                    continue

                roi = binaria[y:y+h, x:x+w]
                densidade = cv2.countNonZero(roi) / float(w * h)

                tem_filho = False
                if i < len(hierarquia):
                    filho_idx = hierarquia[i][2]
                    if filho_idx != -1:
                        tem_filho = True

                if densidade > 0.6 or (tem_filho and densidade > 0.3):
                    candidatos.append((x, y, w, h, area, densidade, tem_filho))

        logging.info(f"🔍 Encontrados {len(candidatos)} candidatos (método 1)")

        if len(candidatos) < 4:
            logging.info("🔄 Tentando método alternativo...")

            binaria2 = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                blockSize=51, C=10
            )
            kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            binaria2 = cv2.morphologyEx(binaria2, cv2.MORPH_CLOSE, kernel2)

            contornos2, _ = cv2.findContours(
                binaria2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for c in contornos2:
                x, y, w, h = cv2.boundingRect(c)
                area = w * h

                if not (area_min < area < area_max):
                    continue

                aspect = w / float(h) if h > 0 else 0
                if not (0.5 < aspect < 2.0):
                    continue

                roi = binaria2[y:y+h, x:x+w]
                densidade = cv2.countNonZero(roi) / float(w * h)

                if densidade > 0.4:
                    candidatos.append((x, y, w, h, area, densidade, False))

            logging.info(f"🔍 Após método 2: {len(candidatos)} candidatos")

        if len(candidatos) < 4:
            logging.warning(f"⚠️ Apenas {len(candidatos)} candidatos — falhou")
            return None

        candidatos.sort(key=lambda c: c[4], reverse=True)
        candidatos = candidatos[:20]

        meia_largura = largura / 2
        meia_altura = altura / 2

        tl = tr = bl = br = None
        tl_s = tr_s = bl_s = br_s = -1

        for (x, y, w, h, a, d, furo) in candidatos:
            cx, cy = x + w // 2, y + h // 2

            bonus_furo = 500 if furo else 0

            if cx < meia_largura and cy < meia_altura:
                score = bonus_furo + a / 1000 - (cx + cy) / 10
                if score > tl_s:
                    tl = (cx, cy); tl_s = score

            elif cx >= meia_largura and cy < meia_altura:
                score = bonus_furo + a / 1000 - ((largura - cx) + cy) / 10
                if score > tr_s:
                    tr = (cx, cy); tr_s = score

            elif cx < meia_largura and cy >= meia_altura:
                score = bonus_furo + a / 1000 - (cx + (altura - cy)) / 10
                if score > bl_s:
                    bl = (cx, cy); bl_s = score

            elif cx >= meia_largura and cy >= meia_altura:
                score = bonus_furo + a / 1000 - ((largura - cx) + (altura - cy)) / 10
                if score > br_s:
                    br = (cx, cy); br_s = score

        if not all([tl, tr, bl, br]):
            logging.warning(f"⚠️ Não achou os 4 cantos: tl={tl} tr={tr} bl={bl} br={br}")
            return None

        largura_topo = ((tr[0] - tl[0]) ** 2 + (tr[1] - tl[1]) ** 2) ** 0.5
        largura_base = ((br[0] - bl[0]) ** 2 + (br[1] - bl[1]) ** 2) ** 0.5
        altura_esq = ((bl[0] - tl[0]) ** 2 + (bl[1] - tl[1]) ** 2) ** 0.5
        altura_dir = ((br[0] - tr[0]) ** 2 + (br[1] - tr[1]) ** 2) ** 0.5

        dist_min = min(largura, altura) * 0.4

        if largura_topo < dist_min or altura_esq < dist_min:
            logging.warning(
                f"⚠️ Marcadores muito próximos: "
                f"topo={largura_topo:.0f}px, esq={altura_esq:.0f}px (min={dist_min:.0f})"
            )
            return None

        logging.info(f"✅ 4 marcadores detectados:")
        logging.info(f"   TL={tl}  TR={tr}")
        logging.info(f"   BL={bl}  BR={br}")

        return {'tl': tl, 'tr': tr, 'bl': bl, 'br': br}

    except Exception as e:
        logging.error(f"❌ Erro detectar_marcadores: {e}")
        traceback.print_exc()
        return None


def corrigir_perspectiva(img, marcadores):
    """
    Corrige perspectiva com DIMENSÕES FIXAS (1900x2440).
    Garante que toda imagem corrigida tenha as mesmas proporções.
    """
    try:
        tl = marcadores['tl']
        tr = marcadores['tr']
        bl = marcadores['bl']
        br = marcadores['br']

        LARGURA_TOTAL = 1900
        ALTURA_TOTAL = 2440
        MARGEM = 50

        origem = np.float32([tl, tr, bl, br])
        destino = np.float32([
            [MARGEM, MARGEM],
            [LARGURA_TOTAL - MARGEM, MARGEM],
            [MARGEM, ALTURA_TOTAL - MARGEM],
            [LARGURA_TOTAL - MARGEM, ALTURA_TOTAL - MARGEM]
        ])

        matriz = cv2.getPerspectiveTransform(origem, destino)
        img_corrigida = cv2.warpPerspective(img, matriz, (LARGURA_TOTAL, ALTURA_TOTAL))

        logging.info(f"✅ Perspectiva corrigida (FIXA): {LARGURA_TOTAL}x{ALTURA_TOTAL}")
        return img_corrigida

    except Exception as e:
        logging.error(f"❌ Erro ao corrigir perspectiva: {e}")
        return img


# ============================================
# TEMPLATE MAPPING
# ============================================

def gerar_mapa_template_padrao(total_questoes, alternativas, num_colunas):
    """Gera mapa de posições (0-1) alinhado com o HTML."""
    mapa = []

    if num_colunas == 1:
        q_por_coluna = total_questoes
    elif total_questoes <= 24:
        q_por_coluna = 12
        num_colunas = 2
    else:
        q_por_coluna = 15
        num_colunas = 2

    num_alts = len(alternativas)

    topo_questoes = 0.24
    base_questoes = 0.92
    altura_questoes = base_questoes - topo_questoes

    coluna_inicio = 0.10
    coluna_fim = 0.95
    largura_colunas = coluna_fim - coluna_inicio

    if num_colunas == 2:
        largura_por_coluna = largura_colunas / 2
        pad = 0.01
    else:
        largura_por_coluna = largura_colunas
        pad = 0.01

    for col in range(num_colunas):
        inicio_col = col * q_por_coluna
        fim_col = min(inicio_col + q_por_coluna, total_questoes)
        num_questoes_col = fim_col - inicio_col

        if num_questoes_col <= 0:
            continue

        x_col_inicio = coluna_inicio + col * largura_por_coluna + pad
        x_col_fim = coluna_inicio + (col + 1) * largura_por_coluna - pad

        largura_bolhas = x_col_fim - x_col_inicio
        espacamento_bolha = largura_bolhas / num_alts

        for i in range(num_questoes_col):
            num_questao = inicio_col + i + 1

            if num_questoes_col > 1:
                y = topo_questoes + (i / (num_questoes_col - 1)) * altura_questoes
            else:
                y = topo_questoes + altura_questoes / 2

            for j, letra in enumerate(alternativas):
                x = x_col_inicio + (j + 0.5) * espacamento_bolha
                mapa.append({
                    'questao': num_questao,
                    'alternativa': letra,
                    'x': round(x, 4),
                    'y': round(y, 4)
                })

    return mapa


def salvar_mapa_template(prova_id, aluno_id, tipo_questoes, quantidade_questoes, num_colunas, mapa_template):
    try:
        conn = get_db_connection()
        if not conn:
            logging.warning("⚠️ Sem conexão para salvar mapa")
            return False

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cartoes_template 
            (prova_id, aluno_id, tipo_questoes, quantidade_questoes, num_colunas, mapa_template)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (prova_id, aluno_id) 
            DO UPDATE SET 
                mapa_template = EXCLUDED.mapa_template,
                tipo_questoes = EXCLUDED.tipo_questoes,
                quantidade_questoes = EXCLUDED.quantidade_questoes,
                num_colunas = EXCLUDED.num_colunas,
                created_at = CURRENT_TIMESTAMP
        """, (prova_id, aluno_id, tipo_questoes, quantidade_questoes,
              num_colunas, json.dumps(mapa_template)))
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"💾 Mapa salvo: prova={prova_id}, aluno={aluno_id}, {len(mapa_template)} bolhas")
        return True
    except Exception as e:
        logging.error(f"❌ Erro ao salvar mapa template: {e}")
        traceback.print_exc()
        return False


def carregar_mapa_template(prova_id, aluno_id):
    try:
        conn = get_db_connection()
        if not conn:
            return None

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT mapa_template, num_colunas
            FROM cartoes_template
            WHERE prova_id = %s AND aluno_id = %s
            LIMIT 1
        """, (prova_id, aluno_id))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row and row['mapa_template']:
            mapa = row['mapa_template']
            if isinstance(mapa, str):
                mapa = json.loads(mapa)
            logging.info(f"✅ Mapa CARREGADO do banco: {len(mapa)} bolhas")
            return mapa
        return None
    except Exception as e:
        logging.warning(f"⚠️ Erro ao carregar mapa: {e}")
        return None


def amostrar_bolha_template(binaria, x_norm, y_norm, raio_fracao=0.015):
    """
    ⚡ v6.0 — MÁSCARA ANELAR (coroa).
    
    Pega apenas a região entre 45% e 85% do raio, evitando a LETRA CENTRAL
    que está impressa no meio da bolha (A, B, C ou D em preto).
    
    Resultado:
    - Bolha VAZIA: ratio 0.05-0.20 (só o fundo branco com sombra)
    - Bolha MARCADA: ratio 0.70-0.95 (preenchimento ocupa o anel)
    """
    h, w = binaria.shape[:2]
    cx = int(x_norm * w)
    cy = int(y_norm * h)

    r = int(raio_fracao * w)
    r = max(20, min(r, 45))

    if cx < r or cy < r or cx + r > w or cy + r > h:
        return 0.0

    # ═══ MÁSCARA ANELAR ═══
    # Círculo externo cheio (até 85% do raio — dentro da bolha)
    mask = np.zeros(binaria.shape, dtype=np.uint8)
    cv2.circle(mask, (cx, cy), int(r * 0.85), 255, -1)
    # Furo interno (até 45% do raio — fora da letra central)
    cv2.circle(mask, (cx, cy), int(r * 0.45), 0, -1)

    roi = cv2.bitwise_and(binaria, binaria, mask=mask)
    total = cv2.countNonZero(mask)
    if total == 0:
        return 0.0
    return cv2.countNonZero(roi) / total


def corrigir_por_template(img_corrigida, mapa_template, alternativas, debug=False):
    """
    v5.0 — ADAPTATIVO: Detecta as bolhas REAIS do cartão e usa como referência.
    """
    h, w = img_corrigida.shape[:2]
    gray = cv2.cvtColor(img_corrigida, cv2.COLOR_BGR2GRAY)

    bg_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, bg_kernel)
    bg = cv2.GaussianBlur(bg, (51, 51), 0)
    bg = np.where(bg == 0, 1, bg).astype(np.float32)
    gray_norm = np.clip((gray.astype(np.float32) / bg) * 200.0, 0, 255).astype(np.uint8)

    binaria = cv2.adaptiveThreshold(
        gray_norm, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=25, C=10
    )

    # ═══════════════════════════════════════════════════════
    # PASSO 1: DETECTAR BOLHAS REAIS POR HOUGHCIRCLES
    # ═══════════════════════════════════════════════════════
    gray_blur = cv2.GaussianBlur(gray_norm, (5, 5), 0)

    raio_esperado = int(h * 0.014)
    raio_min = max(8, int(raio_esperado * 0.6))
    raio_max = max(15, int(raio_esperado * 1.6))

    circulos = cv2.HoughCircles(
        gray_blur,
        cv2.HOUGH_GRADIENT,
        dp=1.0,
        minDist=int(raio_esperado * 1.5),
        param1=80,
        param2=25,
        minRadius=raio_min,
        maxRadius=raio_max
    )

    bolhas_detectadas = []

    if circulos is not None:
        circulos = np.round(circulos[0, :]).astype("int")

        for (x, y, r) in circulos:
            if (x < w * 0.05 and y < h * 0.05) or \
               (x > w * 0.95 and y < h * 0.05) or \
               (x < w * 0.05 and y > h * 0.95) or \
               (x > w * 0.95 and y > h * 0.95):
                continue

            mask = np.zeros(binaria.shape, dtype=np.uint8)
            cv2.circle(mask, (x, y), int(r * 0.75), 255, -1)
            roi = cv2.bitwise_and(binaria, binaria, mask=mask)
            total_px = cv2.countNonZero(mask)
            if total_px == 0:
                continue
            ratio = cv2.countNonZero(roi) / total_px

            bolhas_detectadas.append({
                'x': int(x),
                'y': int(y),
                'r': int(r),
                'ratio': float(ratio)
            })

    logging.info(f"🔍 HoughCircles: {len(bolhas_detectadas)} bolhas detectadas")
    logging.info(f"   Raio esperado: {raio_esperado}px (min={raio_min}, max={raio_max})")

    # ═══════════════════════════════════════════════════════
    # PASSO 2: FALLBACK — Mapa teórico se poucas bolhas
    # ═══════════════════════════════════════════════════════
    if len(bolhas_detectadas) < len(mapa_template) * 0.5:
        logging.warning(f"⚠️ Poucas bolhas detectadas ({len(bolhas_detectadas)}) — usando mapa teórico")

        por_questao = {}
        for b in mapa_template:
            por_questao.setdefault(b['questao'], []).append(b)

        respostas = []
        confiancas = []
        debug_info = []

        for q in sorted(por_questao.keys()):
            bolhas = por_questao[q]
            medidas = []
            for b in bolhas:
                ratio = amostrar_bolha_template(binaria, b['x'], b['y'])
                medidas.append((b['alternativa'], ratio, b))

            medidas.sort(key=lambda m: m[1], reverse=True)
            max_ratio = medidas[0][1]
            min_ratio = medidas[-1][1]
            separacao = max_ratio - min_ratio

            if separacao > 0.50:
                confianca = 98
            elif separacao > 0.35:
                confianca = 92
            elif separacao > 0.20:
                confianca = 80
            elif separacao > 0.10:
                confianca = 65
            else:
                confianca = 40

            letra_escolhida = medidas[0][0]

            # ⚡ CORREÇÃO #3: threshold 0.25
            if max_ratio < 0.25:
                respostas.append('')
                confiancas.append(30)
                debug_info.append({
                    'questao': q, 'resposta': '', 'motivo': 'todas vazias',
                    'medidas': [(m[0], round(m[1], 3)) for m in medidas]
                })
            else:
                respostas.append(letra_escolhida)
                confiancas.append(confianca)
                debug_info.append({
                    'questao': q, 'resposta': letra_escolhida,
                    'confianca': confianca,
                    'medidas': [(m[0], round(m[1], 3)) for m in medidas]
                })

        if debug:
            return respostas, confiancas, debug_info
        return respostas, confiancas

    # ═══════════════════════════════════════════════════════
    # PASSO 3: ORGANIZAR BOLHAS EM GRID
    # ═══════════════════════════════════════════════════════
    raios = [b['r'] for b in bolhas_detectadas]
    raio_mediano = sorted(raios)[len(raios) // 2]

    bolhas_detectadas = [
        b for b in bolhas_detectadas
        if raio_mediano * 0.7 <= b['r'] <= raio_mediano * 1.4
    ]

    logging.info(f"🔍 Após filtro de raio: {len(bolhas_detectadas)} bolhas")

    bolhas_detectadas.sort(key=lambda b: b['y'])

    ys = [b['y'] for b in bolhas_detectadas]
    gaps = [ys[i+1] - ys[i] for i in range(len(ys)-1) if ys[i+1] - ys[i] > 5]

    if gaps:
        gaps.sort()
        y_tol = gaps[0] * 0.5
    else:
        y_tol = 30

    y_tol = max(15, min(y_tol, 60))

    linhas = []
    for b in bolhas_detectadas:
        if not linhas:
            linhas.append([b])
            continue

        linha_atual = linhas[-1]
        y_media = sum(x['y'] for x in linha_atual) / len(linha_atual)

        if abs(b['y'] - y_media) < y_tol:
            linha_atual.append(b)
        else:
            linhas.append([b])

    for linha in linhas:
        linha.sort(key=lambda b: b['x'])

    logging.info(f"🔍 Linhas detectadas: {len(linhas)}")

    linhas = [l for l in linhas if len(l) >= 3]

    logging.info(f"🔍 Linhas com 3+ bolhas: {len(linhas)}")

    total_questoes = len(mapa_template) // len(alternativas)
    num_alts = len(alternativas)

    logging.info(f"🔍 Total questões no mapa: {total_questoes}, alternativas: {alternativas}")

    # ═══════════════════════════════════════════════════════
    # PASSO 4: MAPEAR CADA BOLHA A UMA QUESTÃO
    # ═══════════════════════════════════════════════════════
    respostas = []
    confiancas = []
    debug_info = []

    if len(linhas) < total_questoes:
        logging.warning(f"⚠️ Apenas {len(linhas)} linhas para {total_questoes} questões")
        respostas = [''] * total_questoes
        confiancas = [30] * total_questoes
        if debug:
            return respostas, confiancas, []
        return respostas, confiancas

    linhas_usar = linhas[:total_questoes]

    xs_todas = [b['x'] for b in bolhas_detectadas]

    x_min = min(xs_todas)
    x_max = max(xs_todas)
    range_x = x_max - x_min

    colunas = {letra: [] for letra in alternativas}

    for x in xs_todas:
        pos_rel = (x - x_min) / range_x if range_x > 0 else 0.5
        idx = min(int(pos_rel * num_alts), num_alts - 1)
        colunas[alternativas[idx]].append(x)

    posicoes_colunas = {}
    for letra in alternativas:
        if colunas[letra]:
            posicoes_colunas[letra] = sum(colunas[letra]) / len(colunas[letra])
        else:
            posicoes_colunas[letra] = x_min + (range_x / (num_alts - 1)) * alternativas.index(letra) if num_alts > 1 else x_min

    logging.info(f"🔍 Posições colunas: {posicoes_colunas}")

    for idx_linha, linha in enumerate(linhas_usar):
        if idx_linha >= total_questoes:
            break

        medidas = []

        for letra in alternativas:
            x_esperado = posicoes_colunas[letra]

            melhor_bolha = None
            melhor_dist = float('inf')

            for b in linha:
                dist = abs(b['x'] - x_esperado)
                if dist < melhor_dist:
                    melhor_dist = dist
                    melhor_bolha = b

            if melhor_bolha:
                medidas.append((letra, melhor_bolha['ratio'], melhor_bolha))
            else:
                medidas.append((letra, 0.0, None))

        medidas.sort(key=lambda m: m[1], reverse=True)
        max_ratio = medidas[0][1]
        min_ratio = medidas[-1][1]
        separacao = max_ratio - min_ratio

        if separacao > 0.50:
            confianca = 98
        elif separacao > 0.35:
            confianca = 92
        elif separacao > 0.20:
            confianca = 80
        elif separacao > 0.10:
            confianca = 65
        else:
            confianca = 40

        letra_escolhida = medidas[0][0]

        # ⚡ CORREÇÃO #3: threshold 0.25 (era 0.50)
        if max_ratio < 0.25:
            respostas.append('')
            confiancas.append(30)
            debug_info.append({
                'questao': idx_linha + 1, 'resposta': '', 'motivo': f'max_ratio={max_ratio:.2f} < 0.25',
                'medidas': [(m[0], round(m[1], 3)) for m in medidas]
            })
        else:
            respostas.append(letra_escolhida)
            confiancas.append(confianca)
            debug_info.append({
                'questao': idx_linha + 1, 'resposta': letra_escolhida,
                'confianca': confianca,
                'medidas': [(m[0], round(m[1], 3)) for m in medidas]
            })

    logging.info(f"✅ Template ADAPTATIVO: {sum(1 for r in respostas if r)}/{total_questoes} detectadas")

    if debug:
        return respostas, confiancas, debug_info
    return respostas, confiancas


def preparar_imagem_para_template(imagem_base64):
    try:
        raw = imagem_base64
        if isinstance(raw, tuple):
            raw = raw[0]
        if not raw:
            return None, False

        if ',' in raw and raw.strip().startswith('data:'):
            raw = raw.split(',', 1)[1]
        raw = raw.strip().replace('\n', '').replace('\r', '').replace(' ', '')

        try:
            image_data = base64.b64decode(raw, validate=False)
        except Exception:
            return None, False

        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if img is None:
            return None, False

        h, w = img.shape[:2]
        TARGET_H = 1500
        if h > TARGET_H:
            scale = TARGET_H / h
            img = cv2.resize(img, (int(w * scale), TARGET_H), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        marcadores = detectar_marcadores_fiduciais(gray)

        if not marcadores:
            logging.warning("⚠️ Template Mapping: marcadores não detectados")
            return None, False

        img_corrigida = corrigir_perspectiva(img, marcadores)
        logging.info(f"✅ Template: perspectiva corrigida {img_corrigida.shape[1]}x{img_corrigida.shape[0]}")
        return img_corrigida, True

    except Exception as e:
        logging.error(f"❌ Erro em preparar_imagem_para_template: {e}")
        return None, False


def corrigir_com_template_mapping(imagem_base64, padrao_gabarito, aluno_nome, serie,
                                   tipo_questoes=4, disciplina='', bncc=None,
                                   mapa_template=None, prova_id=None, aluno_id=None):
    """Correção via Template Mapping."""
    total_questoes = padrao_gabarito['total_questoes']
    alternativas = padrao_gabarito['alternativas']

    if not mapa_template and prova_id and aluno_id:
        mapa_template = carregar_mapa_template(prova_id, aluno_id)
        if mapa_template:
            logging.info(f"⚡ Usando mapa EXATO salvo no banco ({len(mapa_template)} bolhas)")

    if not mapa_template:
        if total_questoes <= 12:
            num_colunas = 1
        else:
            num_colunas = 2
        mapa_template = gerar_mapa_template_padrao(total_questoes, alternativas, num_colunas)
        logging.info(f"⚠️ Usando mapa PADRÃO gerado ({len(mapa_template)} bolhas)")

    img_corrigida, ok = preparar_imagem_para_template(imagem_base64)
    if not ok:
        logging.warning("⚠️ Template: falha ao preparar imagem")
        return None

    respostas, confiancas = corrigir_por_template(
        img_corrigida, mapa_template, alternativas, debug=False
    )

    nao_vazias = [r for r in respostas if r]

    logging.info("=" * 60)
    logging.info(f"🔬 TEMPLATE RESULTADO FINAL:")
    logging.info(f"   Respostas: {respostas}")
    logging.info(f"   Não vazias: {len(nao_vazias)}/{total_questoes}")
    logging.info("=" * 60)

    # ⚡ CORREÇÃO #1: Aceita Template SEMPRE (0 respostas incluído para cartão em branco)
    if len(nao_vazias) >= 8 and len(set(nao_vazias)) == 1:
        logging.warning(f"⚠️ Template: todas respostas são '{nao_vazias[0]}' — rejeitando")
        return None

    if len(nao_vazias) == 0:
        logging.info("✅ Template: 0 respostas (cartão em branco) — ACEITANDO")

    logging.info(f"✅ Template Mapping ACEITO: {len(nao_vazias)}/{total_questoes} detectadas")
    return {
        'respostas': respostas,
        'confiancas': confiancas,
        'metodo': 'template'
    }


# ============================================
# DETECÇÃO DE BOLHAS (OPENCV - FALLBACK DESATIVADO)
# ============================================

def detectar_circulos_preenchidos(imagem_base64):
    """Detecção OpenCV (mantida mas não usada como fallback)."""
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]

        image_data = base64.b64decode(imagem_base64)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if img is None:
            logging.error("❌ Imagem inválida")
            return [], {}

        height, width = img.shape[:2]
        logging.info(f"📐 Imagem original: {width}x{height}")

        TARGET_HEIGHT = 1500
        if height > TARGET_HEIGHT:
            scale = TARGET_HEIGHT / height
            new_width = int(width * scale)
            img = cv2.resize(img, (new_width, TARGET_HEIGHT), interpolation=cv2.INTER_AREA)

        height, width = img.shape[:2]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray_enhanced = clahe.apply(gray)
        gray_blur = cv2.GaussianBlur(gray_enhanced, (5, 5), 0)

        marcadores = detectar_marcadores_fiduciais(gray)
        marcadores_xy = []

        if marcadores:
            img = corrigir_perspectiva(img, marcadores)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            gray_enhanced = clahe.apply(gray)
            gray_blur = cv2.GaussianBlur(gray_enhanced, (5, 5), 0)
            height, width = img.shape[:2]

            margem = 30
            marcadores_xy = [
                (margem, margem),
                (width - margem, margem),
                (margem, height - margem),
                (width - margem, height - margem)
            ]

        _, binaria = cv2.threshold(gray_blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        circulos = cv2.HoughCircles(
            gray_blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=25,
            param1=50,
            param2=20,
            minRadius=12,
            maxRadius=30
        )

        if circulos is None:
            logging.warning("⚠️ Nenhum círculo detectado")
            return [], {}

        circulos = np.round(circulos[0, :]).astype("int")
        logging.info(f"🔵 HoughCircles: {len(circulos)} candidatos")

        MARGEM_EXCLUSAO = 100
        circulos_filtrados = []

        for (x, y, r) in circulos:
            perto_de_marcador = False
            for (mx, my) in marcadores_xy:
                dist = np.sqrt((x - mx) ** 2 + (y - my) ** 2)
                if dist < MARGEM_EXCLUSAO:
                    perto_de_marcador = True
                    break

            if not perto_de_marcador:
                circulos_filtrados.append((x, y, r))

        circulos = circulos_filtrados

        if len(circulos) < 4:
            logging.warning("⚠️ Poucos círculos após exclusão")
            return [], {}

        raios = [r for (x, y, r) in circulos]
        raios_sorted = sorted(raios)
        mediana_r = raios_sorted[len(raios_sorted) // 2]

        r_min = mediana_r * 0.8
        r_max = mediana_r * 1.2

        circulos = [(x, y, r) for (x, y, r) in circulos if r_min <= r <= r_max]

        if len(circulos) < 4:
            return [], {}

        todos_circulos = []

        for (x, y, r) in circulos:
            if x < r or y < r or x + r > gray.shape[1] or y + r > gray.shape[0]:
                continue

            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.circle(mask, (x, y), int(r * 0.7), 255, -1)
            roi = cv2.bitwise_and(binaria, binaria, mask=mask)

            total_pixels = cv2.countNonZero(mask)
            dark_pixels = cv2.countNonZero(roi)
            dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0

            todos_circulos.append({
                'x': int(x), 'y': int(y), 'r': int(r),
                'dark_ratio': float(dark_ratio)
            })

        unicos = []
        for c in sorted(todos_circulos, key=lambda c: c['dark_ratio'], reverse=True):
            duplicado = False
            for u in unicos:
                dist = np.sqrt((c['x'] - u['x']) ** 2 + (c['y'] - u['y']) ** 2)
                if dist < u['r'] * 1.5:
                    duplicado = True
                    break
            if not duplicado:
                unicos.append(c)

        posicoes_colunas = {}

        if len(unicos) >= 12:
            xs_ordenados = sorted(set(c['x'] for c in unicos))
            x_min = xs_ordenados[0]
            x_max = xs_ordenados[-1]
            range_x = x_max - x_min

            clusters = {0: [], 1: [], 2: [], 3: []}
            for c in unicos:
                pos_rel = (c['x'] - x_min) / range_x if range_x > 0 else 0.5
                if pos_rel < 0.2:
                    clusters[0].append(c)
                elif pos_rel < 0.45:
                    clusters[1].append(c)
                elif pos_rel < 0.7:
                    clusters[2].append(c)
                else:
                    clusters[3].append(c)

            letras = ['A', 'B', 'C', 'D']
            for i, letra in enumerate(letras):
                if clusters[i]:
                    xs_cluster = [c['x'] for c in clusters[i]]
                    posicoes_colunas[letra] = int(sum(xs_cluster) / len(xs_cluster))
                else:
                    posicoes_colunas[letra] = int(x_min + range_x * (i / 3))
        else:
            posicoes_colunas = {'A': 100, 'B': 400, 'C': 700, 'D': 1000}

        ratios = sorted([c['dark_ratio'] for c in unicos])

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

        threshold = max(0.30, min(threshold, 0.60))

        preenchidos = []
        for c in unicos:
            if c['dark_ratio'] > threshold:
                x = c['x']
                distancias = {letra: abs(x - pos) for letra, pos in posicoes_colunas.items()}
                letra_mais_proxima = min(distancias, key=distancias.get)
                c['letra'] = letra_mais_proxima
                preenchidos.append(c)

        return preenchidos, posicoes_colunas

    except Exception as e:
        logging.error(f"⚠️ Erro na detecção: {e}")
        traceback.print_exc()
        return [], {}


def organizar_respostas_por_posicao(circulos, total_questoes, posicoes_colunas=None):
    """Organiza respostas do OpenCV."""
    if not circulos:
        return [''] * total_questoes, [0] * total_questoes

    ordenados = sorted(circulos, key=lambda c: c['y'])

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
        y_limite = 30

    y_limite = max(20, min(y_limite, 80))

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

    while len(linhas) > total_questoes:
        menor_gap = float('inf')
        idx_juntar = -1

        for i in range(len(linhas) - 1):
            gap = linhas[i+1][0]['y'] - linhas[i][0]['y']
            if gap < menor_gap:
                menor_gap = gap
                idx_juntar = i

        if idx_juntar >= 0:
            linhas[idx_juntar] = linhas[idx_juntar] + linhas[idx_juntar + 1]
            linhas[idx_juntar].sort(key=lambda c: c['x'])
            del linhas[idx_juntar + 1]
        else:
            break

    if len(linhas) > total_questoes:
        linhas = linhas[:total_questoes]

    if len(linhas) < total_questoes * 0.6:
        return [''] * total_questoes, [0] * total_questoes

    respostas = []
    confiancas = []

    for idx, linha in enumerate(linhas):
        if idx >= total_questoes:
            break

        if not linha:
            respostas.append('')
            confiancas.append(30)
            continue

        mais_escuro = max(linha, key=lambda c: c.get('dark_ratio', 0))
        letra = mais_escuro.get('letra', '')

        if letra:
            conf = 90 if mais_escuro.get('dark_ratio', 0) > 0.5 else 75
        else:
            if len(linha) >= 4:
                linha_ordenada = sorted(linha, key=lambda c: c['x'])
                posicao = 0
                for i, c in enumerate(linha_ordenada):
                    if c['x'] == mais_escuro['x'] and c['y'] == mais_escuro['y']:
                        posicao = i
                        break
                letra = ['A', 'B', 'C', 'D'][posicao] if posicao < 4 else ''
            else:
                letra = ''
            conf = 50

        respostas.append(letra)
        confiancas.append(conf)

    while len(respostas) < total_questoes:
        respostas.append('')
        confiancas.append(0)

    respostas = respostas[:total_questoes]
    confiancas = confiancas[:total_questoes]

    nao_vazias = [r for r in respostas if r]
    if len(nao_vazias) >= 5:
        contagem = Counter(nao_vazias)
        letra_mais_comum, qtd = contagem.most_common(1)[0]
        if qtd >= len(nao_vazias) * 0.85:
            return [''] * total_questoes, [0] * total_questoes

    return respostas, confiancas


# ============================================
# PREPROCESSAMENTO DE IMAGEM PARA IA
# ============================================

def preprocessar_imagem_para_ia(imagem_base64):
    try:
        raw = imagem_base64
        if isinstance(raw, tuple):
            raw = raw[0]
        if not raw or not isinstance(raw, str):
            return '', 'image/jpeg'

        if ',' in raw and raw.strip().startswith('data:'):
            raw = raw.split(',', 1)[1]

        raw = raw.strip().replace('\n', '').replace('\r', '').replace(' ', '')

        try:
            image_data = base64.b64decode(raw, validate=False)
        except Exception as e:
            logging.error(f"❌ Base64 inválido: {e}")
            return '', 'image/jpeg'

        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if img is None:
            try:
                from PIL import Image as PILImage
                pil_img = PILImage.open(io.BytesIO(image_data))
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception as e_pil:
                logging.error(f"❌ PIL também falhou: {e_pil}")
                return '', 'image/jpeg'

        if img is None or img.size == 0:
            return '', 'image/jpeg'

        h, w = img.shape[:2]
        logging.info(f"🖼️ IA - Imagem original: {w}x{h}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        brilho_medio = float(np.mean(gray))

        if brilho_medio < 100:
            alpha = min(140.0 / max(brilho_medio, 1), 2.2)
            img = cv2.convertScaleAbs(img, alpha=alpha, beta=25)
        elif brilho_medio > 220:
            alpha = 200.0 / max(brilho_medio, 1)
            img = cv2.convertScaleAbs(img, alpha=alpha, beta=-15)

        gray2 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bg_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51))
        bg = cv2.morphologyEx(gray2, cv2.MORPH_CLOSE, bg_kernel)
        bg = cv2.GaussianBlur(bg, (51, 51), 0)
        bg = np.where(bg == 0, 1, bg).astype(np.float32)
        gray_norm = (gray2.astype(np.float32) / bg) * 200.0
        gray_norm = np.clip(gray_norm, 0, 255).astype(np.uint8)

        img_float = img.astype(np.float32)
        gray_float = gray2.astype(np.float32)
        gray_float = np.where(gray_float == 0, 1, gray_float)
        ratio = gray_norm.astype(np.float32) / gray_float
        ratio = np.clip(ratio, 0.3, 3.0)
        img = np.clip(img_float * ratio[:, :, None], 0, 255).astype(np.uint8)

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

        TARGET = 2400
        if h > TARGET:
            scale = TARGET / float(h)
            img = cv2.resize(img, (int(w * scale), TARGET), interpolation=cv2.INTER_AREA)
        elif h < 1600:
            scale = 1600 / float(h)
            img = cv2.resize(img, (int(w * scale), 1600), interpolation=cv2.INTER_CUBIC)

        gray_final = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        binary = cv2.adaptiveThreshold(
            gray_final, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=25,
            C=8
        )

        binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        img = cv2.addWeighted(img, 0.7, binary_bgr, 0.3, 0)

        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        b64 = base64.b64encode(buffer).decode('utf-8')
        return b64, 'image/jpeg'
    except Exception as e:
        logging.error(f"Erro no preprocessamento IA: {e}")
        traceback.print_exc()
        raw = imagem_base64.split(',', 1)[1] if ',' in imagem_base64 else imagem_base64
        return raw, extrair_mimetype(imagem_base64)


# ============================================
# PROMPT DA IA
# ============================================

def gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina, aviso_extra=None):
    total = padrao_gabarito['total_questoes']
    alternativas = padrao_gabarito['alternativas']
    alternativas_str = ', '.join(alternativas)
    num_alts = len(alternativas)

    aviso_bloco = ""
    if aviso_extra:
        aviso_bloco = f"""
⚠️ ERRO NA TENTATIVA ANTERIOR: {aviso_extra}
Você precisa OLHAR A IMAGEM COM MAIS ATENÇÃO.
Se você não consegue distinguir as bolhas, retorne null (não chute!).
"""

    return f"""Você é um sistema OMR (Optical Mark Recognition) profissional.

═══════════════════════════════════════════════════════
TAREFA
═══════════════════════════════════════════════════════
Analise a foto de um cartão-resposta e identifique QUAL bolha está
preenchida em CADA uma das {total} questões.

O cartão tem 4 marcadores pretos nos cantos. Entre eles há uma grade
com EXATAMENTE {total} linhas numeradas (01 a {total:02d}).
Cada linha tem {num_alts} bolhas: {alternativas_str}.
A bolha MARCADA tem o INTERIOR ESCURO (caneta/lápis).
A bolha NÃO MARCADA tem o INTERIOR BRANCO.

═══════════════════════════════════════════════════════
REGRA CRÍTICA
═══════════════════════════════════════════════════════
🚨 Se você NÃO TEM CERTEZA ABSOLUTA de qual bolha está marcada,
   retorne null para aquela questão.
🚨 NUNCA chute. NUNCA invente.
🚨 É MELHOR retornar null do que errar.

═══════════════════════════════════════════════════════
FORMATO DE SAÍDA (JSON puro)
═══════════════════════════════════════════════════════
{{
  "respostas": ["B", null, "C", "A", null, ...],
  "confianca_por_questao": [95, 0, 90, 88, 0, ...]
}}

REGRAS DO JSON:
- "respostas" DEVE ter EXATAMENTE {total} itens
- Cada item é uma letra ({alternativas_str}) OU null
- "confianca_por_questao" DEVE ter {total} números de 0 a 100
- Se você respondeu null, a confiança DEVE ser 0

{aviso_bloco}
Retorne SOMENTE o JSON.""".strip()


def _parse_respostas_ia(texto, total_esperado, alternativas):
    if not texto:
        return None

    texto = texto.strip()
    texto = re.sub(r'^```(?:json)?\s*', '', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\s*```\s*$', '', texto)

    dados = None
    try:
        dados = json.loads(texto)
    except Exception:
        m = re.search(r'\{[\s\S]*\}', texto)
        if m:
            try:
                dados = json.loads(m.group(0))
            except Exception:
                pass

    if not isinstance(dados, dict):
        return None

    respostas = dados.get('respostas')
    if not isinstance(respostas, list):
        return None

    alternativas_upper = [a.upper() for a in alternativas]
    normalizadas = []

    for r in respostas:
        if r is None:
            normalizadas.append('')
            continue
        if isinstance(r, str) and r.strip().lower() in ('null', 'none', 'n/a', ''):
            normalizadas.append('')
            continue

        s = str(r).strip().upper()
        s = re.sub(r'^[\(\[]*', '', s)
        s = re.sub(r'[\)\]\.\,\;\:\-\s]*$', '', s)
        s = s.strip()

        if not s:
            normalizadas.append('')
            continue

        if s in alternativas_upper:
            normalizadas.append(s)
            continue

        for alt in alternativas_upper:
            if s == alt or s.startswith(alt + ')') or s.startswith(alt + '.'):
                normalizadas.append(alt)
                break
        else:
            letras_encontradas = [alt for alt in alternativas_upper if alt in s]
            if len(letras_encontradas) == 1:
                normalizadas.append(letras_encontradas[0])
            else:
                normalizadas.append('')

    while len(normalizadas) < total_esperado:
        normalizadas.append('')

    return normalizadas[:total_esperado]


def _parse_confiancas_ia(texto, total_esperado):
    if not texto:
        return None

    dados = None
    try:
        dados = json.loads(texto)
    except Exception:
        m = re.search(r'\{[\s\S]*\}', texto)
        if m:
            try:
                dados = json.loads(m.group(0))
            except Exception:
                pass

    if not isinstance(dados, dict):
        m = re.search(r'"confianca_por_questao"\s*:\s*\[([^\]]*)\]', texto)
        if not m:
            return None
        raw = m.group(1)
        nums = re.findall(r'-?\d+(?:\.\d+)?', raw)
        confs = [int(float(n)) for n in nums]
    else:
        confs = dados.get('confianca_por_questao')
        if not isinstance(confs, list):
            return None
        parsed = []
        for c in confs:
            try:
                parsed.append(int(float(c)))
            except (ValueError, TypeError):
                parsed.append(75)
        confs = parsed

    while len(confs) < total_esperado:
        confs.append(50)
    return confs[:total_esperado]


def _validar_resposta_ia_contra_gabarito(respostas, gabarito):
    if not respostas:
        return True, "Resposta vazia"

    nao_vazias = [r for r in respostas if r]
    if not nao_vazias:
        return True, "Nenhuma resposta detectada"

    if len(nao_vazias) >= 5 and len(set(nao_vazias)) == 1:
        return True, f"Todas as {len(nao_vazias)} respostas são '{nao_vazias[0]}'"

    if len(nao_vazias) >= 6:
        if nao_vazias == ['A', 'B'] * (len(nao_vazias) // 2):
            return True, "Padrão alternado A,B detectado"

    if len(nao_vazias) >= 6:
        contagem = Counter(nao_vazias)
        letra, qtd = contagem.most_common(1)[0]
        if qtd / len(nao_vazias) >= 0.85:
            return True, f"{qtd}/{len(nao_vazias)} respostas são '{letra}'"

    if gabarito and len(gabarito) == len(respostas):
        acertos = sum(
            1 for r, g in zip(respostas, gabarito)
            if r and g and r.upper() == g.upper()
        )
        total_validas = sum(1 for r in respostas if r)
        if total_validas > 0:
            taxa = acertos / total_validas
            if taxa < 0.15 and total_validas >= 5:
                return True, f"IA acertou apenas {acertos}/{total_validas} ({taxa*100:.0f}%) — improvável"

    return False, ""


# ============================================
# CORREÇÃO COM IA
# ============================================

def _executar_chamada_openai(data_url, padrao_gabarito, aluno_nome,
                              serie, disciplina, tipo_questoes, aviso_extra=None):
    total_questoes = padrao_gabarito['total_questoes']
    alternativas = padrao_gabarito['alternativas']

    prompt = gerar_prompt_otimizado(
        padrao_gabarito, aluno_nome, serie, disciplina, aviso_extra=aviso_extra
    )

    messages = [
        {
            "role": "system",
            "content": (
                "Você é um sistema OMR profissional. Analise cartões-resposta "
                "com precisão EXTREMA. Se não tiver CERTEZA ABSOLUTA de uma "
                "resposta, retorne null. NUNCA chute. Responda APENAS com JSON "
                "válido no formato {\"respostas\": [...], \"confianca_por_questao\": [...]}. "
                "Sem markdown, sem texto extra."
            )
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}
            ]
        }
    ]

    for tentativa in range(1, 4):
        try:
            logging.info(f"🤖 OpenAI tentativa {tentativa}/3...")

            create_kwargs = {
                "model": OPENAI_MODEL,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.0,
            }

            response = openai_client.chat.completions.create(**create_kwargs)
            resposta_texto = (response.choices[0].message.content or "").strip()

            logging.info(f"📝 Resposta OpenAI ({len(resposta_texto)} chars)")

            if not resposta_texto:
                logging.warning(f"⚠️ Resposta vazia na tentativa {tentativa}")
                continue

            logging.info(f"📝 Conteúdo: {resposta_texto[:500]}")

            respostas_validas = _parse_respostas_ia(
                resposta_texto, total_questoes, alternativas
            )

            if respostas_validas is None:
                logging.warning(f"⚠️ Parse falhou na tentativa {tentativa}")
                continue

            confiancas_ia = _parse_confiancas_ia(resposta_texto, total_questoes)
            if not confiancas_ia:
                confiancas_ia = [85 if r else 0 for r in respostas_validas]

            for i, r in enumerate(respostas_validas):
                if not r:
                    confiancas_ia[i] = 0

            logging.info(f"✅ OpenAI sucesso na tentativa {tentativa}")
            return respostas_validas, confiancas_ia, resposta_texto

        except Exception as e:
            logging.error(f"❌ Erro OpenAI tentativa {tentativa}: {e}")
            traceback.print_exc()
            if tentativa < 3:
                import time
                time.sleep(2)

    logging.error("❌ OpenAI falhou em todas as 3 tentativas")
    return None, None, None


def corrigir_com_ia_fallback(imagem_base64, padrao_gabarito, aluno_nome,
                              serie, tipo_questoes=4, disciplina='', bncc=None):
    gabarito = padrao_gabarito['gabarito_oficial']
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')
    if not OPENAI_AVAILABLE or openai_client is None:
        return erro_correcao(aluno_nome, serie, disciplina, 'IA OpenAI não disponível')

    try:
        total_questoes = len(gabarito)

        if isinstance(imagem_base64, tuple):
            imagem_limpa, mimetype = imagem_base64
        else:
            if ',' in imagem_base64 and imagem_base64.strip().startswith('data:'):
                mimetype = extrair_mimetype(imagem_base64)
                imagem_limpa = imagem_base64.split(',', 1)[1]
            else:
                imagem_limpa = imagem_base64
                mimetype = 'image/jpeg'

        if not imagem_limpa or len(imagem_limpa) < 100:
            return erro_correcao(aluno_nome, serie, disciplina, 'Imagem inválida ou vazia')

        data_url = f"data:{mimetype};base64,{imagem_limpa}"

        respostas_validas, confiancas_ia, texto_resposta = _executar_chamada_openai(
            data_url, padrao_gabarito, aluno_nome, serie, disciplina,
            tipo_questoes, aviso_extra=None
        )

        if respostas_validas is None:
            return erro_correcao(aluno_nome, serie, disciplina, 'Resposta da IA inválida (JSON)')

        suspeito, motivo = _validar_resposta_ia_contra_gabarito(respostas_validas, gabarito)
        if suspeito:
            logging.warning(f"🚨 Tentativa 1 suspeita: {motivo}")

            respostas_2, confiancas_2, texto_2 = _executar_chamada_openai(
                data_url, padrao_gabarito, aluno_nome, serie, disciplina,
                tipo_questoes, aviso_extra=motivo
            )

            if respostas_2 is not None:
                suspeito_2, motivo_2 = _validar_resposta_ia_contra_gabarito(respostas_2, gabarito)
                if not suspeito_2:
                    respostas_validas = respostas_2
                    confiancas_ia = confiancas_2
                else:
                    return erro_correcao(
                        aluno_nome, serie, disciplina,
                        f'IA não conseguiu ler o cartão com confiança. ({motivo_2})'
                    )

        total_detectadas = sum(1 for r in respostas_validas if r)

        if total_detectadas < total_questoes * 0.3:
            return erro_correcao(
                aluno_nome, serie, disciplina,
                f'IA detectou apenas {total_detectadas}/{total_questoes} respostas.'
            )

        return calcular_resultado_correcao(
            respostas_validas, gabarito, aluno_nome, serie,
            disciplina, tipo_questoes, 'ia', bncc=bncc, confiancas=confiancas_ia
        )

    except Exception as e:
        logging.error(f"❌ Erro no fallback OpenAI: {e}")
        traceback.print_exc()
        return erro_correcao(aluno_nome, serie, disciplina, str(e))


# ============================================
# FUNÇÃO PRINCIPAL DE CORREÇÃO — v4.1
# ============================================

def corrigir_com_gemini_com_padrao(imagem_base64, padrao_gabarito, aluno_nome, serie,
                                     tipo_questoes=4, disciplina='', bncc=None,
                                     mapa_template=None, prova_id=None, aluno_id=None):
    """
    CASCATA v4.1 — Template com PRIORIDADE ABSOLUTA, OpenCV DESATIVADO.
    """
    gabarito = padrao_gabarito['gabarito_oficial']
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')

    total_questoes = len(gabarito)

    try:
        # ═══════════════════════════════════════════════════════
        # ETAPA 1: TEMPLATE MAPPING (PRIORIDADE ABSOLUTA)
        # ═══════════════════════════════════════════════════════
        logging.info("=" * 60)
        logging.info("📌 ETAPA 1: Template Mapping (PRIORIDADE ABSOLUTA)")
        logging.info("=" * 60)

        resultado_template = None
        try:
            resultado_template = corrigir_com_template_mapping(
                imagem_base64, padrao_gabarito, aluno_nome, serie,
                tipo_questoes, disciplina, bncc, mapa_template,
                prova_id=prova_id, aluno_id=aluno_id
            )
        except Exception as e:
            logging.warning(f"⚠️ Template falhou: {e}")

        if resultado_template:
            resp_tm = resultado_template['respostas']
            confs_tm = resultado_template['confiancas']
            detectadas_tm = sum(1 for r in resp_tm if r)

            logging.info(
                f"✅ Template retornou: detectadas={detectadas_tm}/{total_questoes}"
            )
            logging.info(f"📋 Respostas Template: {resp_tm}")
            logging.info(f"📋 Confianças Template: {confs_tm}")

            # ⚡ CORREÇÃO #1: Aceita Template com 0+ respostas
            logging.info("🎯 USANDO TEMPLATE (OpenCV ignorado!)")
            return calcular_resultado_correcao(
                resp_tm, gabarito, aluno_nome, serie,
                disciplina, tipo_questoes, 'template',
                bncc=bncc, confiancas=confs_tm
            )
        else:
            logging.warning("⚠️ Template retornou None — caindo para IA")

        # ═══════════════════════════════════════════════════════
        # ETAPA 2: OPENCV — DESATIVADO INTENCIONALMENTE
        # ═══════════════════════════════════════════════════════
        logging.info("=" * 60)
        logging.info("📌 ETAPA 2: OpenCV — DESATIVADO (Template adaptativo é mais preciso)")
        logging.info("=" * 60)

        # ═══════════════════════════════════════════════════════
        # ETAPA 3: IA (último recurso)
        # ═══════════════════════════════════════════════════════
        logging.info("=" * 60)
        logging.info("📌 ETAPA 3: IA OpenAI (último recurso)")
        logging.info("=" * 60)

        if OPENAI_AVAILABLE and openai_client is not None:
            try:
                imagem_processada = preprocessar_imagem_para_ia(imagem_base64)
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_processada, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc=bncc
                )
                if not resultado_ia.get('erro'):
                    resultado_ia['metodo_usado'] = 'ia'
                    logging.info("✅ IA resolveu o cartão")
                    return resultado_ia
            except Exception as e:
                logging.error(f"❌ Erro na IA: {e}")

        return erro_correcao(
            aluno_nome, serie, disciplina,
            '❌ Não foi possível ler as respostas do cartão.'
        )

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

        cached = get_cache_correcao(cache_key)
        if cached:
            logging.info(f"💾 Cache HIT: {cache_key[:30]}...")
            return jsonify(cached)

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

            tipo_questoes = prova.get('tipo_questoes') or 4
            if isinstance(tipo_questoes, str):
                try:
                    tipo_questoes = int(tipo_questoes)
                except Exception:
                    tipo_questoes = 4

            if not validar_gabarito(gabarito, tipo_questoes):
                cur.close()
                conn.close()
                return jsonify({'erro': 'Gabarito inválido para este tipo de prova.'}), 400

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
                serie, tipo_questoes, disciplina, bncc=bncc_gabarito,
                prova_id=prova_id, aluno_id=aluno_id
            )

            if resultado.get('erro'):
                return jsonify(resultado), 400

            tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)

            if 'confianca_por_questao' not in resultado or not resultado['confianca_por_questao']:
                total = resultado.get('total', 20)
                resultado['confianca_por_questao'] = [70] * total
                resultado['confianca'] = 70

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

            set_cache_correcao(cache_key, resultado)

            return jsonify(resultado)
        except Exception as e:
            logging.error(f"❌ Erro na correção: {e}")
            traceback.print_exc()
            return jsonify({'erro': str(e)}), 500
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/corrigir-lote', methods=['POST'])
def corrigir_lote():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'erro': 'Nenhum dado recebido'}), 400

        itens = dados.get('correcoes', [])
        if not itens:
            return jsonify({'erro': 'Envie entre 1 e 20 cartões'}), 400
        if len(itens) > 20:
            return jsonify({'erro': 'Máximo de 20 cartões por lote'}), 400

        gabaritos_cache = {}
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                prova_ids = set()
                for item in itens:
                    pid = item.get('prova_id')
                    if pid:
                        prova_ids.add(pid)

                for pid in prova_ids:
                    cur.execute("SELECT * FROM provas WHERE id = %s", (pid,))
                    p = cur.fetchone()
                    if p:
                        gabaritos_cache[pid] = p
                cur.close()
                conn.close()
            except Exception as e:
                logging.warning(f"⚠️ Erro ao carregar gabaritos: {e}")

        resultados = []
        for idx, item in enumerate(itens):
            aluno_id = item.get('aluno_id')
            try:
                imagem = item.get('imagem')
                prova_id = item.get('prova_id')

                if not imagem or not prova_id or not aluno_id:
                    resultados.append({
                        'sucesso': False,
                        'erro': 'imagem, prova_id ou aluno_id ausente',
                        'aluno_id': aluno_id
                    })
                    continue

                prova = gabaritos_cache.get(prova_id)
                if not prova:
                    resultados.append({
                        'sucesso': False,
                        'erro': 'Prova não encontrada',
                        'aluno_id': aluno_id
                    })
                    continue

                gabarito = prova.get('gabarito', [])
                if not gabarito:
                    resultados.append({
                        'sucesso': False,
                        'erro': 'Prova sem gabarito',
                        'aluno_id': aluno_id
                    })
                    continue

                tipo_questoes = prova.get('tipo_questoes') or 4
                if isinstance(tipo_questoes, str):
                    try:
                        tipo_questoes = int(tipo_questoes)
                    except Exception:
                        tipo_questoes = 4

                padrao_gabarito = gerar_padrao_gabarito(gabarito, tipo_questoes)

                conn_al = get_db_connection()
                nome_aluno = 'Aluno'
                serie = prova.get('serie', '1º Ano')
                if conn_al:
                    try:
                        cur = conn_al.cursor(cursor_factory=RealDictCursor)
                        cur.execute("""
                            SELECT a.nome AS aluno_nome, t.serie AS turma_serie
                            FROM alunos a
                            LEFT JOIN turmas t ON a.turma_id = t.id
                            WHERE a.id = %s
                        """, (aluno_id,))
                        al = cur.fetchone()
                        if al:
                            nome_aluno = al.get('aluno_nome') or 'Aluno'
                            serie = al.get('turma_serie') or serie
                        cur.close()
                        conn_al.close()
                    except Exception:
                        try:
                            conn_al.close()
                        except Exception:
                            pass

                bncc_gabarito = prova.get('bncc', [])
                disciplina = prova.get('disciplina', '')

                resultado = corrigir_com_gemini_com_padrao(
                    imagem, padrao_gabarito, nome_aluno, serie,
                    tipo_questoes, disciplina, bncc=bncc_gabarito,
                    prova_id=prova_id, aluno_id=aluno_id
                )

                if resultado.get('erro'):
                    resultados.append({
                        'sucesso': False,
                        'erro': resultado.get('erro'),
                        'aluno_id': aluno_id,
                        'aluno': nome_aluno
                    })
                    continue

                resultado['aluno_id'] = aluno_id
                resultado['sucesso'] = True
                resultados.append(resultado)

            except Exception as e:
                logging.error(f"❌ Erro no item {idx}: {e}")
                resultados.append({
                    'sucesso': False,
                    'erro': str(e),
                    'aluno_id': aluno_id
                })

        sucessos = sum(1 for r in resultados if r.get('sucesso'))

        return jsonify({
            'resultados': resultados,
            'total': len(resultados),
            'sucessos': sucessos
        })

    except Exception as e:
        logging.error(f"❌ Erro no lote: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


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
        cur.execute("DELETE FROM cartoes_template WHERE aluno_id = %s", (id,))
        cur.execute("DELETE FROM alunos WHERE id = %s", (id,))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'mensagem': f'Aluno "{aluno_nome}" excluído com sucesso!'})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


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
        cur.execute("DELETE FROM cartoes_template WHERE prova_id = %s", (id,))
        cur.execute("DELETE FROM provas WHERE id = %s", (id,))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'mensagem': f'Prova "{prova_titulo}" excluída com sucesso!'})

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


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
        alternativas = ['A', 'B', 'C', 'D', 'E'][:tipo_questoes]
        quantidade_questoes = int(prova.get('quantidade_questoes', 20))

        if quantidade_questoes <= 12:
            q_por_coluna = quantidade_questoes
            num_colunas = 1
        elif quantidade_questoes <= 24:
            q_por_coluna = 12
            num_colunas = 2
        else:
            q_por_coluna = 15
            num_colunas = 2

        mapa_template = gerar_mapa_template_padrao(
            quantidade_questoes, alternativas, num_colunas
        )

        salvar_mapa_template(
            prova_id, aluno_id, tipo_questoes, quantidade_questoes,
            num_colunas, mapa_template
        )

        logging.info(f"🎨 Cartão gerado com mapa ALINHADO para aluno {aluno_id}")

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Cartão Resposta - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        @page {{ size: A4 portrait; margin: 0; }}
        
        body {{
            font-family: Arial, sans-serif;
            background: #f5f5f5;
            padding: 10px;
            display: flex;
            justify-content: center;
        }}
        
        .folha {{
            width: 210mm;
            height: 297mm;
            background: #fff;
            position: relative;
            box-shadow: 0 2px 20px rgba(0,0,0,0.15);
        }}
        
        .fiducial {{
            position: absolute;
            width: 10mm;
            height: 10mm;
            background: #000;
            z-index: 100;
        }}
        .fiducial::after {{
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 4mm;
            height: 4mm;
            background: #fff;
            border-radius: 50%;
        }}
        
        .fiducial-tl {{ top: 38mm; left: 5mm; }}
        .fiducial-tr {{ top: 38mm; right: 5mm; }}
        .fiducial-bl {{ bottom: 5mm; left: 5mm; }}
        .fiducial-br {{ bottom: 5mm; right: 5mm; }}
        
        .area-util {{
            position: absolute;
            top: 48mm;
            left: 15mm;
            width: 180mm;
            height: 234mm;
            display: flex;
            flex-direction: column;
        }}
        
        .header-bloco {{
            height: 24%;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            padding-bottom: 2mm;
            border-bottom: 1.5px solid #000;
        }}
        
        .header-titulo {{
            font-size: 8pt;
            font-weight: bold;
            text-align: center;
            letter-spacing: 0.5px;
        }}
        .header-cartao {{
            font-size: 12pt;
            font-weight: 900;
            text-align: center;
            border: 2px solid #000;
            display: inline-block;
            padding: 1mm 6mm;
            margin: 1mm auto;
        }}
        .header-prova {{
            font-size: 8pt;
            font-weight: bold;
            text-align: center;
            margin-top: 1mm;
        }}
        .header-escola {{
            font-size: 7pt;
            text-align: center;
            color: #333;
        }}
        
        .info-aluno {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2mm;
            padding: 1mm 0;
            font-size: 7pt;
            margin-top: 1mm;
        }}
        
        .instrucoes {{
            font-size: 6pt;
            font-weight: bold;
            text-align: center;
            padding: 0.8mm;
            background: #f0f0f0;
            border: 1px solid #999;
            margin-top: 0.5mm;
        }}
        
        .questoes-bloco {{
            flex: 1;
            display: grid;
            grid-template-columns: repeat({num_colunas}, 1fr);
            gap: 4mm;
            padding: 3mm 0;
            min-height: 0;
        }}
        
        .coluna-questoes {{
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
            min-height: 0;
        }}
        
        .linha-questao {{
            display: flex;
            align-items: center;
            height: {100 / max(q_por_coluna, 1):.4f}%;
            gap: 2mm;
            min-height: 0;
        }}
        
        .num-questao {{
            font-size: 9pt;
            font-weight: 900;
            min-width: 8mm;
            text-align: right;
            border-right: 1.5px solid #000;
            padding-right: 1mm;
            line-height: 1;
        }}
        
        .alternativas {{
            display: flex;
            flex: 1;
            justify-content: space-around;
            align-items: center;
        }}
        
        .bolha {{
            width: 7mm;
            height: 7mm;
            border: 2px solid #000;
            border-radius: 50%;
            background: #fff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 9pt;
            font-weight: 900;
            color: #000;
            flex-shrink: 0;
            line-height: 1;
        }}
        
        .rodape-bloco {{
            height: 8%;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            font-size: 5pt;
            color: #666;
            border-top: 1px solid #ccc;
            padding-top: 1mm;
        }}
        
        .btn-print {{
            position: absolute;
            bottom: 5mm;
            left: 50%;
            transform: translateX(-50%);
            padding: 3mm 10mm;
            background: #000;
            color: #fff;
            border: none;
            font-size: 11pt;
            font-weight: bold;
            cursor: pointer;
            border-radius: 2mm;
        }}
        
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .folha {{ box-shadow: none; }}
            .btn-print {{ display: none; }}
            .fiducial, .fiducial::after {{ 
                print-color-adjust: exact; 
                -webkit-print-color-adjust: exact; 
            }}
            .bolha {{ 
                print-color-adjust: exact; 
                -webkit-print-color-adjust: exact; 
            }}
        }}
    </style>
</head>
<body>
    <div class="folha">
        <div class="fiducial fiducial-tl"></div>
        <div class="fiducial fiducial-tr"></div>
        <div class="fiducial fiducial-bl"></div>
        <div class="fiducial fiducial-br"></div>
        
        <div class="area-util">
            <div class="header-bloco">
                <div class="header-titulo">SECRETARIA MUNICIPAL DE EDUCAÇÃO — SISAM 2026</div>
                <div style="text-align: center;">
                    <div class="header-cartao">CARTÃO RESPOSTA</div>
                </div>
                <div class="header-prova">{titulo_prova}</div>
                <div class="header-escola">{escola_nome} | Série: {serie} | Turma: {turma_nome}</div>
                
                <div class="info-aluno">
                    <span><strong>Aluno(a):</strong> {nome_aluno}</span>
                    <span><strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y')}</span>
                </div>
                
                <div class="instrucoes">
                    ⚠️ PREENCHA COMPLETAMENTE A BOLHA — CANETA PRETA OU AZUL — NÃO RASURE
                </div>
            </div>
            
            <div class="questoes-bloco">
"""

        for col in range(num_colunas):
            inicio = col * q_por_coluna
            fim = min(inicio + q_por_coluna, quantidade_questoes)

            if inicio >= quantidade_questoes:
                break

            html += '<div class="coluna-questoes">'

            for i in range(inicio, fim):
                html += f'''
                <div class="linha-questao">
                    <div class="num-questao">{i+1:02d}</div>
                    <div class="alternativas">
'''
                for alt in alternativas:
                    html += f'<span class="bolha">{alt}</span>'
                html += '''
                    </div>
                </div>
'''

            html += '</div>'

        html += f'''
            </div>
            
            <div class="rodape-bloco">
                <span>Gerado por CorrigePro — {datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
                <span>Página 1/1</span>
            </div>
        </div>
        
        <button class="btn-print" onclick="window.print()">🖨️ IMPRIMIR</button>
    </div>
</body>
</html>
'''
        return html, 200, {'Content-Type': 'text/html'}

    except Exception as e:
        print(f"❌ Erro ao gerar cartão: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


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
# ARQUIVOS ESTÁTICOS
# ============================================

MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.eot': 'application/vnd.ms-fontobject',
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.xml': 'application/xml',
}


def _get_mimetype(filename):
    _, ext = os.path.splitext(filename.lower())
    return MIME_TYPES.get(ext, None)


@app.route('/')
def index():
    try:
        if os.path.isfile('index.html'):
            return send_file('index.html', mimetype='text/html')
        return jsonify({
            'mensagem': 'CorrigePro API',
            'status': 'online',
            'aviso': 'index.html não encontrado'
        }), 200
    except Exception as e:
        logging.error(f"❌ Erro ao servir index.html: {e}")
        return jsonify({'mensagem': 'CorrigePro API', 'status': 'online'}), 200


@app.route('/style.css')
def serve_css():
    try:
        if os.path.isfile('style.css'):
            return send_file('style.css', mimetype='text/css')
        return "/* não encontrado */", 404, {'Content-Type': 'text/css'}
    except Exception as e:
        return "/* erro */", 500, {'Content-Type': 'text/css'}


@app.route('/script.js')
def serve_js():
    try:
        if os.path.isfile('script.js'):
            return send_file('script.js', mimetype='application/javascript')
        return "// não encontrado", 404, {'Content-Type': 'application/javascript'}
    except Exception as e:
        return "// erro", 500, {'Content-Type': 'application/javascript'}


@app.route('/<path:filename>')
def serve_static_file(filename):
    try:
        if '..' in filename or filename.startswith('/'):
            return jsonify({'erro': 'Caminho inválido'}), 400

        mimetype = _get_mimetype(filename)

        if os.path.isfile(filename):
            return send_file(filename, mimetype=mimetype)

        if filename.endswith('.css'):
            return "/* não encontrado */", 404, {'Content-Type': 'text/css'}
        if filename.endswith('.js'):
            return "// não encontrado", 404, {'Content-Type': 'application/javascript'}

        return jsonify({'erro': 'Arquivo não encontrado', 'path': filename}), 404

    except Exception as e:
        if filename.endswith('.css'):
            return "/* erro */", 500, {'Content-Type': 'text/css'}
        if filename.endswith('.js'):
            return "// erro", 500, {'Content-Type': 'application/javascript'}
        return jsonify({'erro': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    conn = get_db_connection()
    db_ok = conn is not None
    if conn:
        conn.close()

    arquivos = {
        'index.html': os.path.isfile('index.html'),
        'style.css': os.path.isfile('style.css'),
        'script.js': os.path.isfile('script.js'),
    }

    return jsonify({
        'status': 'online',
        'openai': 'disponível' if OPENAI_AVAILABLE else 'indisponível',
        'openai_modelo': OPENAI_MODEL if OPENAI_AVAILABLE else None,
        'relay': 'disponível' if RELAY_AVAILABLE else 'indisponível',
        'database': 'conectado' if db_ok else 'desconectado',
        'pool': {'min': DB_POOL_MIN, 'max': DB_POOL_MAX},
        'correcao': 'cascata v4.1 (template adaptativo + opencv desativado)',
        'cache': 'DESATIVADO' if not CACHE_ENABLED else 'ativo',
        'arquivos': arquivos
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
                    except Exception as e:
                        print(f"⚠️ Erro: {e}")

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'historico' AND column_name = 'questoes_status'
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE historico ADD COLUMN questoes_status JSONB DEFAULT '[]'")
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
                    except Exception as e:
                        print(f"⚠️ Erro: {e}")

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'historico' AND column_name = 'bncc'
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE historico ADD COLUMN bncc TEXT[]")
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
                except Exception as e:
                    print(f"⚠️ Erro: {e}")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS cartoes_template (
                id SERIAL PRIMARY KEY,
                prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                tipo_questoes INTEGER NOT NULL,
                quantidade_questoes INTEGER NOT NULL,
                num_colunas INTEGER NOT NULL,
                mapa_template JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prova_id, aluno_id)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cartoes_template_prova_aluno
            ON cartoes_template(prova_id, aluno_id)
        """)
        print("✅ Tabela cartoes_template pronta")

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
    print("🚀 SERVIDOR CORRIGEPRO v4.1 — TEMPLATE ADAPTATIVO + OPENCV OFF")
    print("=" * 60)
    print(f"📌 Porta: {port}")
    print(f"📌 Pool de conexões: {DB_POOL_MIN}-{DB_POOL_MAX}")
    print(f"🤖 OpenAI (ChatGPT): {'✅ Disponível' if OPENAI_AVAILABLE else '❌ Indisponível'}")
    if OPENAI_AVAILABLE:
        print(f"📌 Modelo: {OPENAI_MODEL}")
    print("=" * 60)
    print("🎯 v4.1 — CORREÇÕES APLICADAS:")
    print("   ✅ Template adaptativo (detecta bolhas reais)")
    print("   ✅ Template SEMPRE aceito (mesmo com 0 respostas)")
    print("   ✅ Threshold de amostragem em 0.25 (mais permissivo)")
    print("   ✅ OpenCV DESATIVADO (era muito impreciso)")
    print(f"   ✅ Cache: {'ATIVO' if CACHE_ENABLED else 'DESATIVADO'}")
    print("=" * 60)

    init_db()
    init_cache_table()
    limpar_cache_antigo()
    app.run(host='0.0.0.0', port=port, debug=False)
