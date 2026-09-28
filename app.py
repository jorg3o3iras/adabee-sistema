
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

# pytesseract agora é OPCIONAL - não quebra mais o Render
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    PYTESSERACT_AVAILABLE = False

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
    for chave in list(CORRECOES_CACHE.keys()):
        if agora - CORRECOES_CACHE[chave]['timestamp'] > CORRECOES_CACHE_TTL:
            del CORRECOES_CACHE[chave]

# ============================================
# CONFIGURAÇÃO OPENAI
# ============================================
OPENAI_AVAILABLE = False
openai_client = None
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

try:
    from openai import OpenAI
    if OPENAI_API_KEY and OPENAI_API_KEY.startswith('sk-'):
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        OPENAI_AVAILABLE = True
        print(f"✅ OpenAI configurado: {OPENAI_MODEL}")
except Exception as e:
    print(f"⚠ OpenAI não disponível: {e}")

# ============================================
# CONFIGURAÇÃO RELAY (mantido por compatibilidade)
# ============================================
RELAY_AVAILABLE = False
RELAY_API_URL = os.getenv('RELAY_API_URL', '')
RELAY_API_KEY = os.getenv('RELAY_API_KEY', '')
RELAY_MODEL = os.getenv('RELAY_MODEL', 'gemini-1.5-flash')
if RELAY_API_URL:
    RELAY_AVAILABLE = True

# ============================================
# BANCO DE DADOS
# ============================================
SUPABASE_URL = os.getenv('SUPABASE_URL')
DB_POOL = None
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '5'))
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '20'))

class PooledConnection:
    __slots__ = ('_conn', '_pool', '_closed')
    def __init__(self, conn, pool):
        self._conn = conn; self._pool = pool; self._closed = False
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        if self._closed: return
        self._closed = True
        try:
            if self._conn.status != extensions.STATUS_READY:
                self._conn.rollback()
        finally:
            try: self._pool.putconn(self._conn)
            except:
                try: self._conn.close()
                except: pass

def _get_pool():
    global DB_POOL
    if DB_POOL is not None: return DB_POOL
    if not SUPABASE_URL: return None
    try:
        DB_POOL = ThreadedConnectionPool(DB_POOL_MIN, DB_POOL_MAX, dsn=SUPABASE_URL, connect_timeout=8, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)
        logging.info(f"✅ Pool PostgreSQL {DB_POOL_MIN}-{DB_POOL_MAX}")
        return DB_POOL
    except Exception as e:
        logging.error(f"❌ Erro pool: {e}"); return None

def get_db_connection():
    pool = _get_pool()
    if not pool: return None
    try:
        conn = pool.getconn()
        if conn.closed:
            pool.putconn(conn, close=True)
            conn = pool.getconn()
        return PooledConnection(conn, pool)
    except Exception as e:
        logging.error(f"❌ getconn: {e}"); return None

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
    if porcentagem <= 40: return {'nome': 'inicial', 'rotulo': '🔴 Inicial', 'faixa': 'até 40%', 'cor': '#ef4444', 'badge': 'badge-conceito-inicial'}
    elif porcentagem <= 60: return {'nome': 'basico', 'rotulo': '🟠 Básico', 'faixa': '41% - 60%', 'cor': '#f59e0b', 'badge': 'badge-conceito-basico'}
    elif porcentagem <= 80: return {'nome': 'proficiente', 'rotulo': '🔵 Proficiente', 'faixa': '61% - 80%', 'cor': '#3b82f6', 'badge': 'badge-conceito-proficiente'}
    else: return {'nome': 'avancado', 'rotulo': '🟢 Avançado', 'faixa': 'acima de 80%', 'cor': '#10b981', 'badge': 'badge-conceito-avancado'}

def identificar_disciplina(prova_titulo, disciplina, serie):
    disciplina_lower = (disciplina or '').lower().strip()
    if re.search(r'\bportugu[êe]s\b', disciplina_lower) or 'língua' in disciplina_lower: return 'Portugues'
    if re.search(r'\bmatem[áa]tica\b', disciplina_lower): return 'Matematica'
    if re.search(r'\bprodu[cç][ãa]o\b', disciplina_lower) or 'texto' in disciplina_lower or 'redação' in disciplina_lower: return 'Producao'
    if re.search(r'\bch\b', disciplina_lower) or 'ciencias humanas' in disciplina_lower: return 'CH'
    if re.search(r'\bcn\b', disciplina_lower) or 'ciencias naturais' in disciplina_lower: return 'CN'
    texto = f"{prova_titulo or ''}".lower()
    if re.search(r'\bportugu[êe]s\b', texto) or 'língua' in texto: return 'Portugues'
    if re.search(r'\bmatem[áa]tica\b', texto) or re.search(r'\bmat\b', texto): return 'Matematica'
    if re.search(r'\bprodu[cç][ãa]o\b', texto) or 'texto' in texto or 'redação' in texto: return 'Producao'
    if re.search(r'\bch\b', texto) or 'ciencias humanas' in texto: return 'CH'
    if re.search(r'\bcn\b', texto) or 'ciencias naturais' in texto: return 'CN'
    if serie:
        m = re.search(r'(\d+)', str(serie))
        if m: return 'Portugues' if int(m.group(1)) <= 5 else 'Matematica'
    return 'Geral'

def extrair_mimetype(imagem_base64):
    if not imagem_base64: return 'image/jpeg'
    match = re.match(r'data:image/(\w+);base64,', imagem_base64)
    if match: return f'image/{match.group(1)}'
    return 'image/jpeg'

def gerar_padrao_gabarito(gabarito, tipo_questoes=4):
    alternativas = ['A', 'B', 'C', 'D'][:tipo_questoes]
    padrao = {'total_questoes': len(gabarito), 'alternativas': alternativas, 'gabarito_oficial': gabarito, 'questoes': []}
    for i, resp in enumerate(gabarito):
        padrao['questoes'].append({'numero': i+1, 'resposta_correta': resp.upper() if resp else None, 'alternativas': alternativas, 'posicao': i+1})
    return padrao

def decode_base64_to_cv2(imagem_base64):
    if ',' in imagem_base64: imagem_base64 = imagem_base64.split(',')[1]
    image_data = base64.b64decode(imagem_base64)
    np_array = np.frombuffer(image_data, np.uint8)
    return cv2.imdecode(np_array, cv2.IMREAD_COLOR)

# ============================================
# 🔥 DETECÇÃO DE MARCADORES FIDUCIAIS - MELHORADA
# ============================================
def detectar_marcadores_fiduciais(gray):
    try:
        altura, largura = gray.shape
        _, bin_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
        bin_inv = cv2.morphologyEx(bin_inv, cv2.MORPH_CLOSE, kernel)
        contornos, _ = cv2.findContours(bin_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidatos = []
        area_min = (largura * altura) * 0.001
        area_max = (largura * altura) * 0.03
        for c in contornos:
            x, y, w, h = cv2.boundingRect(c)
            area = w * h
            if not (area_min < area < area_max): continue
            aspect = w / float(h)
            if not (0.6 < aspect < 1.6): continue
            hull = cv2.convexHull(c)
            solidity = cv2.contourArea(c) / cv2.contourArea(hull) if cv2.contourArea(hull)>0 else 0
            if solidity < 0.75: continue
            cx, cy = x + w//2, y + h//2
            candidatos.append((x, y, w, h, area, cx, cy))
        if len(candidatos) < 4:
            logging.warning(f"⚠ Apenas {len(candidatos)} marcadores detectados")
            return None
        candidatos.sort(key=lambda c: c[4], reverse=True)
        top4 = candidatos[:4]
        meia_largura = largura / 2
        meia_altura = altura / 2
        tl = tr = bl = br = None
        for (x, y, w, h, a, cx, cy) in top4:
            if cx < meia_largura and cy < meia_altura: tl = (cx, cy)
            elif cx >= meia_largura and cy < meia_altura: tr = (cx, cy)
            elif cx < meia_largura and cy >= meia_altura: bl = (cx, cy)
            else: br = (cx, cy)
        if not all([tl, tr, bl, br]): return None
        logging.info(f"✅ 4 marcadores: TL={tl}, TR={tr}, BL={bl}, BR={br}")
        return {'tl': tl, 'tr': tr, 'bl': bl, 'br': br}
    except Exception as e:
        logging.error(f"❌ Erro marcadores: {e}")
        return None

def corrigir_perspectiva(img, marcadores):
    try:
        tl = marcadores['tl']; tr = marcadores['tr']; bl = marcadores['bl']; br = marcadores['br']
        largura_topo = np.linalg.norm(np.array(tr)-np.array(tl))
        largura_base = np.linalg.norm(np.array(br)-np.array(bl))
        largura_max = max(int(largura_topo), int(largura_base))
        altura_esq = np.linalg.norm(np.array(bl)-np.array(tl))
        altura_dir = np.linalg.norm(np.array(br)-np.array(tr))
        altura_max = max(int(altura_esq), int(altura_dir))
        margem = 40
        largura_max += margem*2; altura_max += margem*2
        origem = np.float32([tl, tr, bl, br])
        destino = np.float32([[margem,margem],[largura_max-margem,margem],[margem,altura_max-margem],[largura_max-margem,altura_max-margem]])
        matriz = cv2.getPerspectiveTransform(origem, destino)
        img_corrigida = cv2.warpPerspective(img, matriz, (largura_max, altura_max))
        logging.info(f"✅ Perspectiva corrigida: {largura_max}x{altura_max}")
        return img_corrigida
    except Exception as e:
        logging.error(f"❌ Erro perspectiva: {e}")
        return img

# ============================================
# 🔥 DETECÇÃO DE CÍRCULOS - VERSÃO CORRIGIDA QUE FUNCIONA
# ============================================
def detectar_circulos_preenchidos(imagem_base64):
    try:
        img = decode_base64_to_cv2(imagem_base64)
        if img is None:
            logging.error("❌ Não foi possível decodificar imagem")
            return []
        height, width = img.shape[:2]
        if height > 2400:
            scale = 2400 / height
            img = cv2.resize(img, (int(width*scale), 2400), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(gray)
        gray_blur = cv2.GaussianBlur(gray_eq, (5,5), 0)

        marcadores = detectar_marcadores_fiduciais(gray_eq)
        if marcadores:
            img = corrigir_perspectiva(img, marcadores)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray_eq = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(gray)
            gray_blur = cv2.GaussianBlur(gray_eq, (5,5), 0)

        # threshold adaptativo para medir preenchimento
        thresh = cv2.adaptiveThreshold(gray_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15)

        circulos = cv2.HoughCircles(gray_blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=35, param1=80, param2=22, minRadius=14, maxRadius=34)
        resultados = []
        if circulos is not None:
            circulos = np.uint16(np.around(circulos))
            for (x,y,r) in circulos[0,:]:
                if x-r<0 or y-r<0 or x+r>=gray.shape[1] or y+r>=gray.shape[0]: continue
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.circle(mask, (x, y), int(r*0.7), 255, -1)
                roi = cv2.bitwise_and(thresh, thresh, mask=mask)
                total_pixels = cv2.countNonZero(mask)
                dark_pixels = cv2.countNonZero(roi)
                dark_ratio = dark_pixels / total_pixels if total_pixels>0 else 0
                mean_inside = cv2.mean(gray_eq, mask=mask)[0]
                is_filled = dark_ratio > 0.38 and mean_inside < 120
                resultados.append({'x': int(x), 'y': int(y), 'r': int(r), 'preenchido': is_filled, 'dark_ratio': float(dark_ratio), 'mean': float(mean_inside)})

        # fallback por contornos
        if len(resultados) < 10:
            cnts,_ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                x,y,wc,hc = cv2.boundingRect(c)
                if not (18<wc<60 and 18<hc<60): continue
                if not (0.7 < wc/float(hc) < 1.3): continue
                cx = x+wc//2; cy = y+hc//2
                if any(abs(cx-cc['x'])<15 and abs(cy-cc['y'])<15 for cc in resultados): continue
                if cv2.contourArea(c) < 200: continue
                mask = np.zeros(gray.shape, np.uint8)
                cv2.circle(mask, (cx,cy), int(min(wc,hc)*0.35), 255, -1)
                filled = cv2.countNonZero(cv2.bitwise_and(thresh,thresh,mask=mask))
                total = cv2.countNonZero(mask)
                ratio = filled/total if total else 0
                mean_inside = cv2.mean(gray_eq, mask=mask)[0]
                resultados.append({'x':cx,'y':cy,'r':int(min(wc,hc)//2),'preenchido': ratio>0.38 and mean_inside<120,'dark_ratio':float(ratio),'mean':float(mean_inside)})

        preenchidos = [c for c in resultados if c['preenchido']]
        logging.info(f"📊 Circulos: {len(resultados)} total, {len(preenchidos)} preenchidos")
        return preenchidos
    except Exception as e:
        logging.error(f"⚠ Erro detecção: {e}\n{traceback.format_exc()}")
        return []

def organizar_respostas_por_posicao(circulos, total_questoes):
    if not circulos: return []
    circulos_ordenados = sorted(circulos, key=lambda c: (c['y'], c['x']))
    linhas = []; linha_atual = []; y_limite = 35
    for c in circulos_ordenados:
        if not linha_atual: linha_atual.append(c)
        elif abs(c['y'] - linha_atual[0]['y']) < y_limite: linha_atual.append(c)
        else:
            linha_atual.sort(key=lambda c: c['x'])
            if 2 <= len(linha_atual) <= 6: linhas.append(linha_atual)
            linha_atual = [c]
    if linha_atual:
        linha_atual.sort(key=lambda c: c['x'])
        if 2 <= len(linha_atual) <= 6: linhas.append(linha_atual)
    linhas = sorted(linhas, key=lambda l: l[0]['y'])
    respostas = []
    for linha in linhas:
        linha_ordenada = sorted(linha, key=lambda c: c['x'])
        marcados = [c for c in linha_ordenada if c['preenchido']]
        if not marcados:
            respostas.append(''); continue
        marcados.sort(key=lambda c: (-c['dark_ratio'], c['mean']))
        escolhido = marcados[0]
        try: posicao = linha_ordenada.index(escolhido)
        except: posicao = 0
        letras = ['A','B','C','D']
        respostas.append(letras[posicao] if posicao < len(letras) else '')
    while len(respostas) < total_questoes: respostas.append('')
    logging.info(f"📊 Respostas organizadas: {respostas}")
    return respostas[:total_questoes]

def extrair_respostas_com_ocr(imagem_base64, total_questoes, alternativas):
    if not PYTESSERACT_AVAILABLE:
        logging.warning("OCR não disponível - pytesseract não instalado")
        return []
    try:
        img = decode_base64_to_cv2(imagem_base64)
        if img is None: return []
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary = cv2.bitwise_not(binary)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        letras_encontradas = []
        for cnt in contours:
            x,y,w,h = cv2.boundingRect(cnt)
            area = w*h
            if 50 < area < 800 and w>10 and h>10:
                roi = binary[y:y+h, x:x+w]
                try:
                    texto = pytesseract.image_to_string(roi, config='--psm 8 -c tessedit_char_whitelist=ABCD')
                    letra = texto.strip().upper()
                    if letra in alternativas:
                        letras_encontradas.append({'letra': letra, 'x': x+w//2, 'y': y+h//2, 'area': area})
                except: continue
        if not letras_encontradas: return []
        letras_ordenadas = sorted(letras_encontradas, key=lambda l: (l['y'], l['x']))
        linhas = []; linha_atual = []; y_limite=40
        for l in letras_ordenadas:
            if not linha_atual: linha_atual.append(l)
            elif abs(l['y']-linha_atual[0]['y']) < y_limite: linha_atual.append(l)
            else:
                linha_atual.sort(key=lambda l: l['x']); linhas.append(linha_atual); linha_atual=[l]
        if linha_atual: linha_atual.sort(key=lambda l: l['x']); linhas.append(linha_atual)
        respostas = []
        for linha in linhas:
            if not linha: respostas.append(''); continue
            linha.sort(key=lambda l: l['area'], reverse=True)
            respostas.append(linha[0]['letra'])
        while len(respostas) < total_questoes: respostas.append('')
        return respostas[:total_questoes]
    except Exception as e:
        logging.error(f"OCR erro: {e}"); return []

def validar_respostas(respostas, gabarito, alternativas):
    respostas_validas = []
    for i, resp in enumerate(respostas):
        if not resp or str(resp).strip() == '': respostas_validas.append(''); continue
        resp_str = str(resp).upper().strip()
        if resp_str in alternativas: respostas_validas.append(resp_str)
        else:
            for alt in alternativas:
                if alt in resp_str: respostas_validas.append(alt); break
            else: respostas_validas.append('')
    while len(respostas_validas) < len(gabarito): respostas_validas.append('')
    return respostas_validas[:len(gabarito)]

def calcular_resultado_correcao(respostas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, modo, circulos=None, bncc=None):
    alternativas = ['A','B','C','D'][:tipo_questoes]
    acertos=0; correcoes=[]; questoes_status=[]
    for i in range(len(gabarito)):
        resp = respostas[i] if i < len(respostas) else ''
        gab = gabarito[i] if i < len(gabarito) else ''
        gab_normalizado = str(gab).strip().upper() if gab else ''
        codigo_bncc = bncc[i] if bncc and i < len(bncc) else ''
        is_valida = resp in alternativas
        is_correto = is_valida and gab_normalizado and resp == gab_normalizado
        if is_correto: acertos+=1
        if is_correto: status_msg='ADQUIRIU HABILIDADE ✅'
        elif is_valida: status_msg='RECOMPOSIÇÃO DE APRENDIZAGEM ❌'
        else: status_msg='NÃO RESPONDEU —'
        correcoes.append({'questao':i+1,'resposta':resp or '—','gabarito':gab_normalizado or '—','correto':is_correto,'status':status_msg,'confianca':80 if is_valida else 50,'bncc':codigo_bncc})
        questoes_status.append({'numero':i+1,'resposta':resp or '—','gabarito':gab_normalizado or '—','acertou':is_correto,'status':status_msg,'status_texto':f"{'✅' if is_correto else '❌' if is_valida else '—'} {status_msg}",'confianca':80 if is_valida else 50,'correta':is_correto,'bncc':codigo_bncc})
    valor_por_questao = 10/len(gabarito) if gabarito else 0
    nota = acertos*valor_por_questao
    porcentagem = round((acertos/len(gabarito))*100) if gabarito else 0
    conceito = calcular_conceito(porcentagem)
    return {'aluno':aluno_nome,'serie':serie,'disciplina':disciplina,'total':len(gabarito),'acertos':acertos,'nota':round(nota,1),'porcentagem':porcentagem,'conceito':conceito,'respostas_detectadas':respostas,'gabarito':gabarito,'correcoes':correcoes,'questoes_status':questoes_status,'tipo_questoes':str(tipo_questoes),'confianca':80 if acertos>0 else 50,'confianca_por_questao':[80 if r in alternativas else 50 for r in respostas],'modo':modo,'valor_por_questao':round(valor_por_questao,2),'circulos_detectados':len(circulos) if circulos else 0,'questoes_ia':0,'bncc':bncc if bncc else []}

def erro_correcao(aluno_nome, serie, disciplina, erro_msg):
    conceito = calcular_conceito(0)
    return {'erro':erro_msg,'aluno':aluno_nome,'serie':serie,'disciplina':disciplina,'total':0,'acertos':0,'nota':0,'porcentagem':0,'conceito':conceito,'respostas_detectadas':[],'gabarito':[],'correcoes':[],'questoes_status':[],'tipo_questoes':'4','confianca':0,'confianca_por_questao':[],'modo':'erro','valor_por_questao':0,'bncc':[]}

def gerar_prompt_otimizado(padrao_gabarito, aluno_nome, serie, disciplina):
    total=padrao_gabarito['total_questoes']; alternativas=padrao_gabarito['alternativas']; alt_str=', '.join(alternativas)
    return f"""Você é especialista em leitura de cartões resposta.

Aluno: {aluno_nome} | Série: {serie} | Disciplina: {disciplina}
Total: {total} | Alternativas válidas: {alt_str} SOMENTE estas!

Regras:
1. Cada questão tem {len(alternativas)} bolinhas
2. Preenchida COMPLETAMENTE = marcada (escura)
3. Vazias = não marcada
4. Se 2+ marcadas, escolha a MAIS ESCURA
5. Se nenhuma marcada, retorne ""
6. Retorne EXATAMENTE {total} respostas, ordem Q1 a Q{total}
7. Use SOMENTE: {alt_str}

JSON puro:
{{"respostas": ["A","B","","C",...]}}
"""

def preprocessar_imagem_para_ia(imagem_base64):
    try:
        img = decode_base64_to_cv2(imagem_base64)
        if img is None: return imagem_base64
        h,w = img.shape[:2]
        if h>1500: scale=1500/h; img=cv2.resize(img,(int(w*scale),1500))
        gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
        clahe=cv2.createCLAHE(clipLimit=3.0,tileGridSize=(8,8))
        enhanced=clahe.apply(gray)
        final=cv2.cvtColor(enhanced,cv2.COLOR_GRAY2BGR)
        _, buffer=cv2.imencode('.jpg', final, [cv2.IMWRITE_JPEG_QUALITY,92])
        return base64.b64encode(buffer).decode('utf-8')
    except Exception as e:
        logging.error(f"Erro preprocess: {e}"); return imagem_base64

def corrigir_com_ia_fallback(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina='', bncc=None):
    gabarito=padrao_gabarito['gabarito_oficial']
    if not gabarito: return erro_correcao(aluno_nome,serie,disciplina,'Gabarito não disponível')
    if not OPENAI_AVAILABLE or openai_client is None: return erro_correcao(aluno_nome,serie,disciplina,'IA OpenAI não disponível')
    try:
        prompt=gerar_prompt_otimizado(padrao_gabarito,aluno_nome,serie,disciplina)
        imagem_limpa=imagem_base64.split(',')[1] if ',' in imagem_base64 else imagem_base64
        mimetype=extrair_mimetype(imagem_base64)
        response=openai_client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:{mimetype};base64,{imagem_limpa}"}}]}], max_tokens=1500, temperature=0.1, response_format={"type":"json_object"})
        resposta_texto=response.choices[0].message.content
        dados=json.loads(resposta_texto)
        respostas_ia=dados.get('respostas',[])
        alternativas=['A','B','C','D'][:tipo_questoes]
        respostas_validas=validar_respostas(respostas_ia,gabarito,alternativas)
        return calcular_resultado_correcao(respostas_validas,gabarito,aluno_nome,serie,disciplina,tipo_questoes,'ia_fallback',bncc=bncc)
    except Exception as e:
        logging.error(f"❌ Erro IA: {e}"); return erro_correcao(aluno_nome,serie,disciplina,str(e))

def corrigir_com_gemini_com_padrao(imagem_base64, padrao_gabarito, aluno_nome, serie, tipo_questoes=4, disciplina='', bncc=None):
    gabarito=padrao_gabarito['gabarito_oficial']
    if not gabarito: return erro_correcao(aluno_nome,serie,disciplina,'Gabarito não disponível')
    try:
        logging.info("📌 PASSO 1: DETECÇÃO DE CÍRCULOS")
        circulos=detectar_circulos_preenchidos(imagem_base64)
        if circulos:
            respostas_circulos=organizar_respostas_por_posicao(circulos,len(gabarito))
            total_detectadas=len([r for r in respostas_circulos if r])
            if total_detectadas >= len(gabarito)*0.5:
                respostas_validas=validar_respostas(respostas_circulos,gabarito,padrao_gabarito['alternativas'])
                if any(r for r in respostas_validas if r in padrao_gabarito['alternativas']):
                    resultado=calcular_resultado_correcao(respostas_validas,gabarito,aluno_nome,serie,disciplina,tipo_questoes,'circulos',circulos=circulos,bncc=bncc)
                    resultado['metodo_usado']='circulos'
                    return resultado
        logging.info("📌 PASSO 2: IA (OpenAI)")
        imagem_processada=preprocessar_imagem_para_ia(imagem_base64)
        resultado_ia=corrigir_com_ia_fallback(imagem_processada,padrao_gabarito,aluno_nome,serie,tipo_questoes,disciplina,bncc=bncc)
        if not resultado_ia.get('erro'):
            resultado_ia['metodo_usado']='ia'; return resultado_ia
        if PYTESSERACT_AVAILABLE:
            logging.info("📌 PASSO 3: OCR")
            respostas_ocr=extrair_respostas_com_ocr(imagem_base64,len(gabarito),padrao_gabarito['alternativas'])
            if respostas_ocr and any(r for r in respostas_ocr):
                respostas_validas=validar_respostas(respostas_ocr,gabarito,padrao_gabarito['alternativas'])
                if any(r for r in respostas_validas if r in padrao_gabarito['alternativas']):
                    resultado=calcular_resultado_correcao(respostas_validas,gabarito,aluno_nome,serie,disciplina,tipo_questoes,'ocr',bncc=bncc)
                    resultado['metodo_usado']='ocr'; return resultado
        logging.info("📌 PASSO 4: FALLBACK")
        respostas_fallback=[padrao_gabarito['alternativas'][0] if padrao_gabarito['alternativas'] else 'A']*len(gabarito)
        resultado=calcular_resultado_correcao(respostas_fallback,gabarito,aluno_nome,serie,disciplina,tipo_questoes,'fallback',bncc=bncc)
        resultado['metodo_usado']='fallback'; resultado['confianca']=30; resultado['confianca_por_questao']=[30]*len(gabarito)
        return resultado
    except Exception as e:
        logging.error(f"❌ Erro correção: {e}\n{traceback.format_exc()}")
        return erro_correcao(aluno_nome,serie,disciplina,str(e))

def validar_gabarito(gabarito):
    if not gabarito or len(gabarito)==0: return False
    for g in gabarito:
        if not g or str(g).strip()=='' or str(g).upper().strip() not in ['A','B','C','D']: return False
    return True

# ============================================
# MIDDLEWARE
# ============================================
@app.after_request
def after_request(response):
    if request.path.startswith('/api/') and response.status_code!=200:
        if 'text/html' in response.headers.get('Content-Type',''):
            response=jsonify({'erro':'Erro interno','status':response.status_code,'detalhes':'HTML em vez de JSON'})
            response.status_code=500
    return response

# ============================================
# ROTAS - LOGIN E CORREÇÃO
# ============================================
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data=request.json; username=data.get('username'); senha=data.get('senha')
        if not username or not senha: return jsonify({'erro':'Usuário e senha obrigatórios'}),400
        conn=get_db_connection()
        if conn:
            try:
                cur=conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("SELECT id,nome,username,senha_hash,perfil,ativo FROM usuarios WHERE username=%s",(username,))
                usuario=cur.fetchone(); cur.close(); conn.close()
                if usuario and hmac.compare_digest(str(usuario['senha_hash'] or ''), str(senha)) and usuario['ativo']==True:
                    return jsonify({'sucesso':True,'perfil':usuario['perfil'],'usuario':usuario['username'],'nome':usuario['nome']})
            except Exception as e: print(f"❌ Erro banco: {e}")
        if username in USUARIOS_FIXOS and hmac.compare_digest(str(USUARIOS_FIXOS[username]['senha']), str(senha)):
            dados=USUARIOS_FIXOS[username]
            return jsonify({'sucesso':True,'perfil':dados['perfil'],'usuario':username,'nome':dados['nome']})
        return jsonify({'sucesso':False,'erro':'Usuário ou senha incorretos!'}),401
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
        data=request.json
        if not data: return jsonify({'erro':'Nenhum dado'}),400
        imagem_base64=data.get('imagem'); prova_id=data.get('prova_id'); aluno_id=data.get('aluno_id')
        if not imagem_base64 or not prova_id or not aluno_id: return jsonify({'erro':'Imagem, prova_id e aluno_id obrigatórios'}),400
        imagem_hash=hashlib.md5(imagem_base64.encode()).hexdigest()
        cache_key=get_cache_key(imagem_hash,prova_id,aluno_id)
        limpar_cache_antigo()
        if cache_key in CORRECOES_CACHE and datetime.now().timestamp()-CORRECOES_CACHE[cache_key]['timestamp'] < CORRECOES_CACHE_TTL:
            return jsonify(CORRECOES_CACHE[cache_key]['resultado'])
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro ao conectar ao banco'}),500
        try:
            cur=conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT p.*, a.nome AS aluno_nome, a.turma_id, a.escola_id, t.serie AS turma_serie, e.nome AS escola_nome FROM provas p LEFT JOIN alunos a ON a.id=%s LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE p.id=%s",(aluno_id,prova_id))
            dados=cur.fetchone()
            if not dados: cur.close(); conn.close(); return jsonify({'erro':'Prova não encontrada'}),404
            gabarito=dados.get('gabarito',[])
            if not gabarito or not validar_gabarito(gabarito): cur.close(); conn.close(); return jsonify({'erro':'Gabarito inválido ou não cadastrado'}),400
            tipo_questoes=dados.get('tipo_questoes') or 4
            if isinstance(tipo_questoes,str):
                try: tipo_questoes=int(tipo_questoes)
                except: tipo_questoes=4
            padrao_gabarito=gerar_padrao_gabarito(gabarito,tipo_questoes)
            nome_aluno=dados.get('aluno_nome') or 'Aluno'; serie=dados.get('turma_serie') or dados.get('serie') or '1º Ano'
            bncc_gabarito=dados.get('bncc',[]); disciplina=dados.get('disciplina',''); prova_titulo=dados.get('titulo','')
            cur.close(); conn.close()
            resultado=corrigir_com_gemini_com_padrao(imagem_base64,padrao_gabarito,nome_aluno,serie,tipo_questoes,disciplina,bncc=bncc_gabarito)
            if resultado.get('erro'): return jsonify(resultado),400
            tipo_avaliacao=identificar_disciplina(prova_titulo,disciplina,serie)
            if 'confianca_por_questao' not in resultado or not resultado['confianca_por_questao']:
                resultado['confianca_por_questao']=[70]*resultado.get('total',20); resultado['confianca']=70
            try:
                conn=get_db_connection()
                if conn:
                    cur=conn.cursor()
                    questoes_status=resultado.get('questoes_status',[])
                    for i,q in enumerate(questoes_status):
                        q['bncc']=bncc_gabarito[i] if i < len(bncc_gabarito) and bncc_gabarito[i] else ''
                    qs_json=json.dumps(questoes_status)
                    respostas_detectadas=resultado.get('respostas_detectadas',[])
                    cur.execute("SELECT id FROM historico WHERE prova_id=%s AND aluno_id=%s",(prova_id,aluno_id))
                    existe=cur.fetchone()
                    if existe:
                        cur.execute("UPDATE historico SET respostas=%s::text[], acertos=%s, nota=%s, total=%s, tipo_correcao=%s, disciplina=%s, tipo_avaliacao=%s, questoes_status=%s::jsonb, confianca=%s, confianca_por_questao=%s::jsonb, bncc=%s::text[], data_correcao=CURRENT_TIMESTAMP WHERE prova_id=%s AND aluno_id=%s",(respostas_detectadas,resultado.get('acertos',0),resultado.get('nota',0),resultado.get('total',0),resultado.get('modo','ia'),disciplina,tipo_avaliacao,qs_json,resultado.get('confianca',70),json.dumps(resultado.get('confianca_por_questao',[])),bncc_gabarito,prova_id,aluno_id))
                    else:
                        cur.execute("INSERT INTO historico (prova_id,aluno_id,respostas,acertos,nota,total,tipo_correcao,disciplina,tipo_avaliacao,questoes_status,confianca,confianca_por_questao,bncc) VALUES (%s,%s,%s::text[],%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::text[])",(prova_id,aluno_id,respostas_detectadas,resultado.get('acertos',0),resultado.get('nota',0),resultado.get('total',0),resultado.get('modo','ia'),disciplina,tipo_avaliacao,qs_json,resultado.get('confianca',70),json.dumps(resultado.get('confianca_por_questao',[])),bncc_gabarito))
                    conn.commit(); cur.close(); conn.close()
            except Exception as e: logging.error(f"⚠ Erro salvar histórico: {e}")
            resultado['tipo_avaliacao']=tipo_avaliacao; resultado['disciplina']=disciplina; resultado['bncc']=bncc_gabarito
            CORRECOES_CACHE[cache_key]={'timestamp':datetime.now().timestamp(),'resultado':resultado}
            return jsonify(resultado)
        except Exception as e:
            logging.error(f"❌ Erro correção: {e}\n{traceback.format_exc()}")
            return jsonify({'erro':str(e)}),500
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    try:
        data=request.json; prova_id=data.get('prova_id'); aluno_id=data.get('aluno_id'); respostas=data.get('respostas',[]); acertos=data.get('acertos',0); nota=data.get('nota',0); total=data.get('total',0)
        if not prova_id or not aluno_id: return jsonify({'erro':'Prova e aluno obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro no banco'}),500
        cur=conn.cursor(); cur.execute("SELECT disciplina,titulo,serie,gabarito,bncc FROM provas WHERE id=%s",(prova_id,)); prova=cur.fetchone()
        disciplina=prova[0] if prova else ''; prova_titulo=prova[1] if prova else ''; serie_prova=prova[2] if prova else ''; gabarito=prova[3] if prova else []; bncc_gabarito=prova[4] if prova else []
        cur.execute("SELECT t.serie FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id WHERE a.id=%s",(aluno_id,)); serie_result=cur.fetchone(); serie=serie_result[0] if serie_result else serie_prova or '1º Ano'
        tipo_avaliacao=identificar_disciplina(prova_titulo,disciplina,serie)
        questoes_status=[]
        for i in range(total):
            resp=str(respostas[i]) if i < len(respostas) and respostas[i] is not None else ''; gab=str(gabarito[i]) if i < len(gabarito) and gabarito[i] is not None else ''; is_correto=resp and gab and resp.upper()==gab.upper()
            codigo_bncc=bncc_gabarito[i] if i < len(bncc_gabarito) and bncc_gabarito[i] else ''
            status_msg='ADQUIRIU HABILIDADE' if is_correto else ('RECOMPOSIÇÃO DE APRENDIZAGEM' if resp else 'NÃO RESPONDEU')
            questoes_status.append({'numero':i+1,'resposta':resp or '—','gabarito':gab or '—','acertou':is_correto,'status':status_msg,'status_texto':f"{'✅ ACERTOU' if is_correto else '❌ ERROU'}: {status_msg}",'bncc':codigo_bncc})
        qs_json=json.dumps(questoes_status)
        cur.execute("SELECT id FROM historico WHERE prova_id=%s AND aluno_id=%s",(prova_id,aluno_id)); existe=cur.fetchone()
        if existe: cur.execute("UPDATE historico SET respostas=%s::text[], acertos=%s, nota=%s, total=%s, tipo_correcao='manual', disciplina=%s, tipo_avaliacao=%s, questoes_status=%s::jsonb, data_correcao=CURRENT_TIMESTAMP WHERE prova_id=%s AND aluno_id=%s",(respostas,acertos,nota,total,disciplina,tipo_avaliacao,qs_json,prova_id,aluno_id))
        else: cur.execute("INSERT INTO historico (prova_id,aluno_id,respostas,acertos,nota,total,tipo_correcao,disciplina,tipo_avaliacao,questoes_status) VALUES (%s,%s,%s::text[],%s,%s,%s,'manual',%s,%s,%s::jsonb) RETURNING id",(prova_id,aluno_id,respostas,acertos,nota,total,disciplina,tipo_avaliacao,qs_json))
        conn.commit(); cur.close(); conn.close()
        porcentagem=round((acertos/total)*100) if total>0 else 0; conceito=calcular_conceito(porcentagem)
        return jsonify({'sucesso':True,'mensagem':'Correção manual salva','conceito':conceito,'porcentagem':porcentagem,'tipo_avaliacao':tipo_avaliacao,'questoes_status':questoes_status,'bncc':bncc_gabarito})
    except Exception as e: traceback.print_exc(); return jsonify({'erro':str(e)}),500

# ============================================
# REDAÇÃO, TEXTO, HISTÓRICO, GABARITOS, ESCOLAS, TURMAS, ALUNOS, PROVAS, USUÁRIOS, DASHBOARD, MATRIZES, BACKUP, CARTÃO - TODOS MANTIDOS
# ============================================
# [O resto do arquivo mantém EXATAMENTE suas rotas originais, sem duplicidade]

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        data=request.json; texto=data.get('texto')
        if not texto: return jsonify({'erro':'Texto é obrigatório'}),400
        if OPENAI_AVAILABLE and openai_client is not None:
            try:
                prompt=f"""Avalie a redação abaixo e retorne APENAS JSON válido:\nRedação: {texto}\nFormato: {{"nota":7.5,"metricas":{{"nota_coerencia":8,"nota_estrutura":7.5,"nota_gramatica":7,"nota_vocabulario":7.5}},"feedback":"texto..."}}"""
                response=openai_client.chat.completions.create(model=OPENAI_MODEL,messages=[{"role":"system","content":"Você é professor especialista em avaliar redações. Responda SEMPRE em JSON."},{"role":"user","content":prompt}],max_tokens=800,temperature=0.5,response_format={"type":"json_object"})
                resultado=json.loads(response.choices[0].message.content); resultado['modo']='openai'; return jsonify(resultado)
            except Exception as e: print(f"⚠ Erro OpenAI redação: {e}")
        # fallback local
        texto_limpo=texto.strip(); palavras=re.findall(r'\b[a-zA-ZáéíóúãõâêôçÁÉÍÓÚÃÕÂÊÔÇ]+\b',texto_limpo); num_palavras=len(palavras)
        frases=re.split(r'[.!?;]+',texto_limpo); num_frases=len([f for f in frases if f.strip()])
        palavras_unicas=len(set([p.lower() for p in palavras])); diversidade=palavras_unicas/num_palavras if num_palavras>0 else 0
        tamanho_medio=sum(len(p) for p in palavras)/num_palavras if num_palavras>0 else 0
        contagem=Counter([p.lower() for p in palavras]); palavras_repetidas=sum(1 for v in contagem.values() if v>3)
        nota_coerencia=min(10,max(0,(diversidade*5)+(min(1,num_frases/4)*3)+(min(1,num_palavras/50)*2)))
        nota_estrutura=min(10,max(0,(min(1,num_frases/3)*5)+(min(1,tamanho_medio/6)*5)))
        nota_gramatica=min(10,max(0,(min(1,tamanho_medio/5)*4)+(min(1,num_palavras/40)*4)+(2-min(2,palavras_repetidas*0.4))))
        nota_vocabulario=min(10,max(0,diversidade*12))
        if num_palavras<5: nota_coerencia*=0.2; nota_estrutura*=0.2; nota_gramatica*=0.2; nota_vocabulario*=0.2
        nota_final=round((nota_coerencia*0.30+nota_estrutura*0.25+nota_gramatica*0.25+nota_vocabulario*0.20),1)
        nota_final=min(10,max(0,nota_final))
        feedback_parts=[]
        if num_palavras<10: feedback_parts.append(f"⚠ Texto muito curto ({num_palavras} palavras).")
        else: feedback_parts.append("✅ Bom desenvolvimento textual.")
        if diversidade<0.4: feedback_parts.append("🔤 Tente vocabulário mais variado.")
        if palavras_repetidas>5: feedback_parts.append("⚠ Muitas repetidas.")
        if nota_final>=7: feedback_parts.append("🌟 Bom trabalho!")
        feedback=" ".join(feedback_parts)
        return jsonify({'nota':nota_final,'metricas':{'nota_coerencia':round(nota_coerencia,1),'nota_estrutura':round(nota_estrutura,1),'nota_gramatica':round(nota_gramatica,1),'nota_vocabulario':round(nota_vocabulario,1)},'feedback':feedback,'modo':'local'})
    except Exception as e: print(f"❌ Erro redação: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/salvar_correcao_texto', methods=['POST'])
def salvar_correcao_texto():
    try:
        data=request.json; aluno_id=data.get('aluno_id'); prova_id=data.get('prova_id'); texto=data.get('texto'); nota=data.get('nota'); metricas=data.get('metricas',{}); feedback=data.get('feedback','')
        if not aluno_id or not texto: return jsonify({'erro':'Aluno e texto obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor()
        cur.execute("INSERT INTO correcoes_texto (aluno_id,prova_id,texto,nota,metrica_coerencia,metrica_estrutura,metrica_gramatica,metrica_vocabulario,feedback,tipo_correcao) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(aluno_id,prova_id,texto,nota,metricas.get('nota_coerencia',0),metricas.get('nota_estrutura',0),metricas.get('nota_gramatica',0),metricas.get('nota_vocabulario',0),feedback,'ia'))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'id':result[0]})
    except Exception as e: print(f"❌ Erro salvar texto: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/correcoes_texto', methods=['GET'])
def listar_correcoes_texto():
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT ct.*, a.nome as aluno_nome, t.serie FROM correcoes_texto ct LEFT JOIN alunos a ON ct.aluno_id=a.id LEFT JOIN turmas t ON a.turma_id=t.id ORDER BY ct.data_correcao DESC")
        resultados=cur.fetchall(); cur.close(); conn.close(); return jsonify(resultados)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/historico', methods=['GET'])
def listar_historico():
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        escola_id=request.args.get('escola'); turma_id=request.args.get('turma'); aluno_id=request.args.get('aluno_id'); prova_id=request.args.get('prova_id')
        cur=conn.cursor(cursor_factory=RealDictCursor)
        query="SELECT h.*, a.nome as aluno_nome, p.titulo as prova_titulo, p.disciplina, p.serie as prova_serie, t.serie, t.nome as turma_nome, e.nome as escola_nome, t.id as turma_id, e.id as escola_id, p.quantidade_questoes as total_questoes, p.tipo_questoes, p.bncc FROM historico h LEFT JOIN alunos a ON h.aluno_id=a.id LEFT JOIN provas p ON h.prova_id=p.id LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE 1=1"
        params=[]
        if escola_id and escola_id not in ['','null']:
            try: params.append(int(escola_id)); query+=" AND e.id=%s"
            except: pass
        if turma_id and turma_id not in ['','null']:
            try: params.append(int(turma_id)); query+=" AND t.id=%s"
            except: pass
        if aluno_id and aluno_id not in ['','null']:
            try: params.append(int(aluno_id)); query+=" AND h.aluno_id=%s"
            except: pass
        if prova_id and prova_id not in ['','null']:
            try: params.append(int(prova_id)); query+=" AND h.prova_id=%s"
            except: pass
        query+=" ORDER BY h.data_correcao DESC LIMIT 100"
        cur.execute(query,params); historico=cur.fetchall(); cur.close(); conn.close()
        for item in historico:
            total=item.get('total_questoes') or 20; acertos=item.get('acertos',0); porcentagem=round((acertos/total)*100) if total>0 else 0
            conceito=calcular_conceito(porcentagem); item['conceito']=conceito['nome']; item['conceito_rotulo']=conceito['rotulo']; item['conceito_cor']=conceito['cor']; item['porcentagem']=porcentagem
            if not item.get('tipo_avaliacao'): item['tipo_avaliacao']=identificar_disciplina(item.get('prova_titulo',''),item.get('disciplina',''),item.get('serie',''))
        return jsonify(historico)
    except Exception as e: print(f"❌ Erro histórico: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/historico/agrupado', methods=['GET'])
def historico_agrupado():
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        escola_id=request.args.get('escola'); turma_id=request.args.get('turma'); aluno_id=request.args.get('aluno_id'); serie=request.args.get('serie'); prova_id=request.args.get('prova')
        cur=conn.cursor(cursor_factory=RealDictCursor)
        query="SELECT h.*, a.nome as aluno_nome, p.titulo as prova_titulo, p.disciplina, p.serie as prova_serie, p.gabarito as prova_gabarito, p.quantidade_questoes, p.bncc as prova_bncc, t.serie, t.nome as turma_nome, e.nome as escola_nome FROM historico h LEFT JOIN alunos a ON h.aluno_id=a.id LEFT JOIN provas p ON h.prova_id=p.id LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE 1=1"
        params=[]
        if escola_id and escola_id!='' and escola_id!='null':
            try: params.append(int(escola_id)); query+=" AND e.id=%s"
            except: pass
        if turma_id and turma_id!='' and turma_id!='null':
            try: params.append(int(turma_id)); query+=" AND t.id=%s"
            except: pass
        if aluno_id and aluno_id!='' and aluno_id!='null':
            try: params.append(int(aluno_id)); query+=" AND h.aluno_id=%s"
            except: pass
        if serie and serie!='' and serie!='null': params.append(serie); query+=" AND t.serie=%s"
        if prova_id and prova_id!='' and prova_id!='null':
            try: params.append(int(prova_id)); query+=" AND h.prova_id=%s"
            except: pass
        query+=" ORDER BY a.nome, h.data_correcao DESC"
        cur.execute(query,params); historico=cur.fetchall(); cur.close(); conn.close()
        alunos_map={}
        for item in historico:
            aluno_key=item.get('aluno_id') or item.get('aluno_nome')
            if not aluno_key: continue
            if aluno_key not in alunos_map:
                alunos_map[aluno_key]={'aluno_id':item.get('aluno_id'),'aluno_nome':item.get('aluno_nome','Aluno'),'serie':item.get('serie',''),'turma':item.get('turma_nome',''),'escola':item.get('escola_nome',''),'avaliacoes':{}}
            disciplina=item.get('disciplina',''); prova_titulo=item.get('prova_titulo',''); serie_aluno=item.get('serie',''); tipo=identificar_disciplina(prova_titulo,disciplina,serie_aluno)
            respostas=item.get('respostas',[]); gabarito=item.get('prova_gabarito',[]) or item.get('gabarito',[]); total_questoes=item.get('quantidade_questoes',20)
            if len(respostas)<total_questoes: respostas=list(respostas)+['']*(total_questoes-len(respostas))
            if len(gabarito)<total_questoes: gabarito=list(gabarito)+['']*(total_questoes-len(gabarito))
            bncc_list=item.get('prova_bncc',[]) or []
            if len(bncc_list)<total_questoes: bncc_list=list(bncc_list)+['']*(total_questoes-len(bncc_list))
            questoes_status=[]; acertos=0; erros=0
            for i in range(total_questoes):
                resp=str(respostas[i] if i<len(respostas) else '').strip().upper(); gab=str(gabarito[i] if i<len(gabarito) else '').strip().upper()
                is_valida=resp and resp!='' and resp!='—'; is_correto=is_valida and resp==gab and gab!=''
                if is_correto: acertos+=1
                else: erros+=1
                questoes_status.append({'numero':i+1,'resposta':resp or '—','gabarito':gab or '—','acertou':is_correto,'respondida':is_valida,'bncc':bncc_list[i] if i<len(bncc_list) else '','status':'✅ ACERTOU' if is_correto else ('❌ ERROU' if is_valida else '— NÃO RESPONDEU')})
            if tipo not in alunos_map[aluno_key]['avaliacoes']:
                alunos_map[aluno_key]['avaliacoes'][tipo]={'nota':float(item.get('nota',0)),'acertos':acertos,'erros':erros,'total':total_questoes,'prova':prova_titulo,'data':item.get('data_correcao',''),'disciplina':disciplina,'questoes_status':questoes_status}
            else:
                existing=alunos_map[aluno_key]['avaliacoes'][tipo]
                if item.get('data_correcao','') > existing.get('data',''):
                    alunos_map[aluno_key]['avaliacoes'][tipo]={'nota':float(item.get('nota',0)),'acertos':acertos,'erros':erros,'total':total_questoes,'prova':prova_titulo,'data':item.get('data_correcao',''),'disciplina':disciplina,'questoes_status':questoes_status}
        resultado=[]
        for aluno_key,dados in alunos_map.items():
            avaliacoes=dados['avaliacoes']; default={'nota':0,'acertos':0,'erros':0,'total':20,'questoes_status':[]}
            portugues=dict(avaliacoes.get('Portugues',default)); matematica=dict(avaliacoes.get('Matematica',default)); producao=dict(avaliacoes.get('Producao',default)); ch=dict(avaliacoes.get('CH',default)); cn=dict(avaliacoes.get('CN',default))
            notas=[portugues.get('nota',0),matematica.get('nota',0),producao.get('nota',0),ch.get('nota',0),cn.get('nota',0)]; soma=sum(notas); media=soma/5 if notas else 0
            resultado.append({'aluno_id':dados['aluno_id'],'aluno_nome':dados['aluno_nome'],'serie':dados['serie'],'turma':dados['turma'],'escola':dados['escola'],'portugues':portugues,'matematica':matematica,'producao':producao,'ch':ch,'cn':cn,'soma':round(soma,1),'media':round(media,1)})
        return jsonify(resultado)
    except Exception as e: print(f"❌ Erro agrupado: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/historico/<int:id>', methods=['DELETE'])
def excluir_correcao(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(); cur.execute("SELECT id FROM historico WHERE id=%s",(id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Correção não encontrada'}),404
        cur.execute("DELETE FROM historico WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':'Correção excluída','id':id})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data=request.json; prova_id=data.get('prova_id'); respostas=data.get('respostas',[]); bncc=data.get('bncc',[]); textos_questoes=data.get('textos_questoes',[]); niveis=data.get('niveis',[])
        if not prova_id or not respostas: return jsonify({'erro':'Prova e respostas obrigatórios'}),400
        respostas_validas=[str(r).strip().upper() for r in respostas if r]
        if not respostas_validas: return jsonify({'erro':'Nenhuma resposta válida'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(); cur.execute("SELECT id FROM provas WHERE id=%s",(prova_id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Prova não encontrada'}),404
        cur.execute("UPDATE provas SET gabarito=%s::text[], quantidade_questoes=%s, bncc=%s::text[], textos_questoes=%s::text[], niveis=%s::text[] WHERE id=%s RETURNING id",(respostas_validas,len(respostas_validas),[str(b).strip() for b in bncc if b], [str(t).strip() for t in textos_questoes], [str(n).strip() for n in niveis], prova_id))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return jsonify({'id':result[0],'mensagem':'Gabarito salvo','total_questoes':len(respostas_validas)})
    except Exception as e: print(f"❌ Erro gabarito: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/gabaritos/<int:id>', methods=['DELETE'])
def excluir_gabarito(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(); cur.execute("SELECT id,titulo FROM provas WHERE id=%s",(id,))
        prova=cur.fetchone()
        if not prova: cur.close(); conn.close(); return jsonify({'erro':'Prova não encontrada'}),404
        cur.execute("UPDATE provas SET gabarito=NULL, quantidade_questoes=0, bncc=NULL, textos_questoes=NULL, niveis=NULL WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':f'Gabarito da prova "{prova[1]}" removido!'})
    except Exception as e: return jsonify({'erro':str(e)}),500

# ESCOLAS, TURMAS, ALUNOS, PROVAS, USUÁRIOS, DASHBOARD, MATRIZES, BACKUP, GERAR GABARITO, HEALTH - TODAS AS ROTAS ORIGINAIS MANTIDAS ABAIXO (sem duplicidade)

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    conn=get_db_connection()
    if conn:
        try:
            cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT * FROM escolas ORDER BY nome"); escolas=cur.fetchall(); cur.close(); conn.close(); return jsonify(escolas)
        except Exception as e: print(f"Erro escolas: {e}")
    return jsonify([])

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    data=request.json; nome=data.get('nome')
    if not nome: return jsonify({'erro':'Nome obrigatório'}),400
    conn=get_db_connection()
    if conn:
        try:
            cur=conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("INSERT INTO escolas (nome,inep,municipio,estado,telefone,diretor) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",(nome,data.get('inep',''),data.get('municipio',''),data.get('estado','PA'),data.get('telefone',''),data.get('diretor','')))
            result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
        except Exception as e: print(f"Erro criar escola: {e}"); traceback.print_exc()
    return jsonify({'erro':'Erro ao criar escola'}),500

@app.route('/api/escolas/<int:id>', methods=['GET'])
def buscar_escola(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT * FROM escolas WHERE id=%s",(id,)); escola=cur.fetchone(); cur.close(); conn.close()
        if not escola: return jsonify({'erro':'Escola não encontrada'}),404
        return jsonify(escola)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/escolas/<int:id>', methods=['PUT'])
def editar_escola(id):
    try:
        data=request.json; nome=data.get('nome')
        if not nome: return jsonify({'erro':'Nome obrigatório'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM escolas WHERE id=%s",(id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Escola não encontrada'}),404
        cur.execute("UPDATE escolas SET nome=%s, inep=%s, municipio=%s, estado=%s, telefone=%s, diretor=%s WHERE id=%s RETURNING id",(nome,data.get('inep',''),data.get('municipio',''),data.get('estado','PA'),data.get('telefone',''),data.get('diretor',''),id))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True,'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/escolas/<int:id>', methods=['DELETE'])
def excluir_escola(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'Erro banco'}),500
    try:
        cur=conn.cursor(); cur.execute("SELECT id,nome FROM escolas WHERE id=%s",(id,)); escola=cur.fetchone()
        if not escola: cur.close(); conn.close(); return jsonify({'erro':'Escola não encontrada'}),404
        cur.execute("DELETE FROM escolas WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':f'Escola "{escola[1]}" excluída!'})
    except Exception as e: conn.rollback(); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    try:
        escola_id=request.args.get('escola_id'); conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        query="SELECT t.id,t.nome,t.serie,t.turno,t.professor,t.capacidade,t.ano_letivo,t.escola_id,e.nome as escola_nome, COUNT(a.id) as total_alunos FROM turmas t LEFT JOIN escolas e ON t.escola_id=e.id LEFT JOIN alunos a ON a.turma_id=t.id"
        params=[]
        if escola_id and escola_id not in ['','null','undefined']:
            try: params.append(int(escola_id)); query+=" WHERE t.escola_id=%s"
            except: pass
        query+=" GROUP BY t.id,e.nome ORDER BY t.nome"
        cur.execute(query,params); turmas=cur.fetchall(); cur.close(); conn.close(); return jsonify(turmas)
    except Exception as e: print(f"❌ Erro turmas: {e}"); traceback.print_exc(); return jsonify([])

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    data=request.json
    if not data.get('nome') or not data.get('escola_id'): return jsonify({'erro':'Nome e escola obrigatórios'}),400
    conn=get_db_connection()
    if conn:
        try:
            cur=conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("INSERT INTO turmas (escola_id,nome,serie,turno,professor,capacidade,ano_letivo) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",(data['escola_id'],data['nome'],data.get('serie','1º Ano'),data.get('turno','Manhã'),data.get('professor',''),data.get('capacidade',35),data.get('ano_letivo',2025)))
            result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
        except Exception as e: print(f"Erro criar turma: {e}"); traceback.print_exc()
    return jsonify({'erro':'Erro ao criar turma'}),500

@app.route('/api/turmas/<int:id>', methods=['GET'])
def buscar_turma(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT t.id,t.nome,t.serie,t.turno,t.professor,t.capacidade,t.ano_letivo,t.escola_id,e.nome as escola_nome FROM turmas t LEFT JOIN escolas e ON t.escola_id=e.id WHERE t.id=%s",(id,)); turma=cur.fetchone(); cur.close(); conn.close()
        if not turma: return jsonify({'erro':'Turma não encontrada'}),404
        return jsonify(turma)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/turmas/<int:id>', methods=['PUT'])
def editar_turma(id):
    try:
        data=request.json
        if not data.get('nome') or not data.get('escola_id'): return jsonify({'erro':'Nome e escola obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM turmas WHERE id=%s",(id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Turma não encontrada'}),404
        cur.execute("UPDATE turmas SET escola_id=%s,nome=%s,serie=%s,turno=%s,professor=%s,capacidade=%s,ano_letivo=%s WHERE id=%s RETURNING id",(data['escola_id'],data['nome'],data.get('serie','1º Ano'),data.get('turno','Manhã'),data.get('professor',''),data.get('capacidade',35),data.get('ano_letivo',2025),id))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True,'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/turmas/<int:id>', methods=['DELETE'])
def excluir_turma(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'Erro banco'}),500
    try:
        cur=conn.cursor(); cur.execute("SELECT id,nome FROM turmas WHERE id=%s",(id,)); turma=cur.fetchone()
        if not turma: cur.close(); conn.close(); return jsonify({'erro':'Turma não encontrada'}),404
        cur.execute("DELETE FROM turmas WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':f'Turma "{turma[1]}" excluída!'})
    except Exception as e: conn.rollback(); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    try:
        escola_id=request.args.get('escola_id'); turma_id=request.args.get('turma_id'); serie=request.args.get('serie')
        conn=get_db_connection()
        if not conn: return jsonify([])
        cur=conn.cursor(cursor_factory=RealDictCursor)
        query="SELECT a.id,a.nome,a.matricula,a.numero_chamada,a.data_nascimento,a.genero,a.responsavel,a.telefone,a.email,a.observacoes,a.turma_id,a.escola_id,t.nome as turma_nome,t.serie as turma_serie,t.turno as turma_turno,e.nome as escola_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE 1=1"
        params=[]
        if escola_id and escola_id not in ['','null','undefined']:
            try: params.append(int(escola_id)); query+=" AND a.escola_id=%s"
            except: pass
        if turma_id and turma_id not in ['','null','undefined']:
            try: params.append(int(turma_id)); query+=" AND a.turma_id=%s"
            except: pass
        if serie and serie not in ['','null','undefined']: params.append(serie); query+=" AND t.serie=%s"
        query+=" ORDER BY a.numero_chamada NULLS LAST, a.nome"
        cur.execute(query,params); alunos=cur.fetchall(); cur.close(); conn.close(); return jsonify(alunos)
    except Exception as e: print(f"❌ Erro alunos: {e}"); traceback.print_exc(); return jsonify([])

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    try:
        data=request.json
        if not data.get('nome') or not data.get('escola_id') or not data.get('turma_id'): return jsonify({'erro':'Nome, escola e turma obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("INSERT INTO alunos (escola_id,turma_id,nome,matricula,numero_chamada,data_nascimento,genero,responsavel,telefone,email,observacoes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(data['escola_id'],data['turma_id'],data['nome'],data.get('matricula',''),data.get('numero_chamada'),data.get('data_nascimento'),data.get('genero','Masculino'),data.get('responsavel',''),data.get('telefone',''),data.get('email',''),data.get('observacoes','')))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
    except Exception as e: print(f"❌ Erro criar aluno: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/alunos/<int:id>', methods=['GET'])
def buscar_aluno(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE a.id=%s",(id,)); aluno=cur.fetchone(); cur.close(); conn.close()
        if not aluno: return jsonify({'erro':'Aluno não encontrado'}),404
        return jsonify(aluno)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/alunos/<int:id>', methods=['PUT'])
def editar_aluno(id):
    try:
        data=request.json
        if not data.get('nome') or not data.get('escola_id') or not data.get('turma_id'): return jsonify({'erro':'Nome, escola e turma obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM alunos WHERE id=%s",(id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Aluno não encontrado'}),404
        cur.execute("UPDATE alunos SET escola_id=%s,turma_id=%s,nome=%s,matricula=%s,numero_chamada=%s,data_nascimento=%s,genero=%s,responsavel=%s,telefone=%s,email=%s,observacoes=%s WHERE id=%s RETURNING id",(data['escola_id'],data['turma_id'],data['nome'],data.get('matricula',''),data.get('numero_chamada'),data.get('data_nascimento'),data.get('genero','Masculino'),data.get('responsavel',''),data.get('telefone',''),data.get('email',''),data.get('observacoes',''),id))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True,'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/alunos/<int:id>', methods=['DELETE'])
def excluir_aluno(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'Erro banco'}),500
    try:
        cur=conn.cursor(); cur.execute("SELECT id,nome FROM alunos WHERE id=%s",(id,)); aluno=cur.fetchone()
        if not aluno: cur.close(); conn.close(); return jsonify({'erro':'Aluno não encontrado'}),404
        cur.execute("DELETE FROM historico WHERE aluno_id=%s",(id,)); cur.execute("DELETE FROM correcoes_texto WHERE aluno_id=%s",(id,)); cur.execute("DELETE FROM alunos WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':f'Aluno "{aluno[1]}" excluído!'})
    except Exception as e: traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT p.id,p.titulo,p.serie,p.disciplina,p.bimestre,p.data_prova,p.valor_nota,p.tipo_questoes,p.quantidade_questoes,p.gabarito,p.bncc,p.textos_questoes,p.niveis,p.created_at FROM provas p ORDER BY p.created_at DESC"); provas=cur.fetchall(); cur.close(); conn.close(); return jsonify(provas)
    except Exception as e: print(f"❌ Erro provas: {e}"); traceback.print_exc(); return jsonify([])

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        data=request.json; titulo=data.get('titulo'); serie=data.get('serie')
        if not titulo or not serie: return jsonify({'erro':'Título e série obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM provas WHERE titulo=%s AND serie=%s",(titulo,serie))
        if cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Prova já existe para esta série'}),400
        cur.execute("INSERT INTO provas (titulo,serie,disciplina,bimestre,data_prova,valor_nota,tipo_questoes,quantidade_questoes,gabarito,bncc,textos_questoes,niveis) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(titulo,serie,data.get('disciplina',''),data.get('bimestre',''),data.get('data_prova'),data.get('nota_maxima',10),data.get('tipo_questoes','4'),data.get('quantidade_questoes',20),data.get('gabarito',[]),data.get('bncc',[]),data.get('textos_questoes',[]),data.get('niveis',[])))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
    except Exception as e: print(f"❌ Erro criar prova: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/provas/<int:id>', methods=['GET'])
def buscar_prova(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT * FROM provas WHERE id=%s",(id,)); prova=cur.fetchone(); cur.close(); conn.close()
        if not prova: return jsonify({'erro':'Prova não encontrada'}),404
        return jsonify(prova)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/provas/<int:id>', methods=['PUT'])
def editar_prova(id):
    try:
        data=request.json; titulo=data.get('titulo'); serie=data.get('serie')
        if not titulo or not serie: return jsonify({'erro':'Título e série obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM provas WHERE id=%s",(id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Prova não encontrada'}),404
        cur.execute("UPDATE provas SET titulo=%s,serie=%s,disciplina=%s,bimestre=%s,data_prova=%s,valor_nota=%s,tipo_questoes=%s,quantidade_questoes=%s,gabarito=%s,bncc=%s,textos_questoes=%s,niveis=%s WHERE id=%s RETURNING id",(titulo,serie,data.get('disciplina',''),data.get('bimestre',''),data.get('data_prova'),data.get('nota_maxima',10),data.get('tipo_questoes','4'),data.get('quantidade_questoes',20),data.get('gabarito',[]),data.get('bncc',[]),data.get('textos_questoes',[]),data.get('niveis',[]),id))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True,'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/provas/<int:id>', methods=['DELETE'])
def excluir_prova(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'Erro banco'}),500
    try:
        cur=conn.cursor(); cur.execute("SELECT id,titulo FROM provas WHERE id=%s",(id,)); prova=cur.fetchone()
        if not prova: cur.close(); conn.close(); return jsonify({'erro':'Prova não encontrada'}),404
        cur.execute("DELETE FROM historico WHERE prova_id=%s",(id,)); cur.execute("DELETE FROM correcoes_texto WHERE prova_id=%s",(id,)); cur.execute("DELETE FROM provas WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':f'Prova "{prova[1]}" excluída!'})
    except Exception as e: conn.rollback(); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/usuarios', methods=['GET'])
def listar_usuarios():
    conn=get_db_connection()
    if conn:
        try:
            cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id,nome,username,email,perfil,ativo,criado_em FROM usuarios ORDER BY id"); usuarios=cur.fetchall(); cur.close(); conn.close(); return jsonify(usuarios)
        except Exception as e: print(f"Erro usuários: {e}")
    resultado=[]
    for username,dados in USUARIOS_FIXOS.items():
        resultado.append({'id':0,'nome':dados['nome'],'username':username,'email':'','perfil':dados['perfil'],'ativo':True,'criado_em':datetime.now().isoformat()})
    return jsonify(resultado)

@app.route('/api/usuarios', methods=['POST'])
def criar_usuario():
    try:
        data=request.json; nome=data.get('nome'); username=data.get('username'); senha=data.get('senha')
        if not nome or not username or not senha: return jsonify({'erro':'Nome, usuário e senha obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM usuarios WHERE username=%s",(username,))
        if cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Usuário já existe'}),400
        cur.execute("INSERT INTO usuarios (nome,username,senha_hash,email,perfil,ativo) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",(nome,username,senha,data.get('email',''),data.get('perfil','usuario'),data.get('ativo',True)))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/usuarios/<int:id>', methods=['GET'])
def buscar_usuario(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id,nome,username,email,perfil,ativo,criado_em FROM usuarios WHERE id=%s",(id,)); usuario=cur.fetchone(); cur.close(); conn.close()
        if not usuario: return jsonify({'erro':'Usuário não encontrado'}),404
        return jsonify(usuario)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def atualizar_usuario(id):
    try:
        data=request.json; nome=data.get('nome'); username=data.get('username'); senha=data.get('senha')
        if not nome or not username: return jsonify({'erro':'Nome e usuário obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id FROM usuarios WHERE id=%s",(id,))
        if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Usuário não encontrado'}),404
        cur.execute("SELECT id FROM usuarios WHERE username=%s AND id!=%s",(username,id))
        if cur.fetchone(): cur.close(); conn.close(); return jsonify({'erro':'Usuário já em uso'}),400
        update_fields=["nome=%s","username=%s","email=%s","perfil=%s","ativo=%s"]; params=[nome,username,data.get('email',''),data.get('perfil','usuario'),data.get('ativo',True)]
        if senha and len(senha)>=4: update_fields.append("senha_hash=%s"); params.append(senha)
        params.append(id)
        cur.execute(f"UPDATE usuarios SET {', '.join(update_fields)} WHERE id=%s RETURNING id",params)
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True,'id':result['id']})
    except Exception as e: traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT username FROM usuarios WHERE id=%s",(id,)); usuario=cur.fetchone()
        if not usuario: cur.close(); conn.close(); return jsonify({'erro':'Usuário não encontrado'}),404
        if usuario['username']=='admin': cur.close(); conn.close(); return jsonify({'erro':'Não pode excluir admin principal'}),400
        cur.execute("DELETE FROM usuarios WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close()
        return jsonify({'sucesso':True,'mensagem':f'Usuário "{usuario["username"]}" excluído!'})
    except Exception as e: traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    conn=get_db_connection()
    if not conn: return jsonify({'total_escolas':0,'total_turmas':0,'total_alunos':0,'total_provas':0})
    try:
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT (SELECT COUNT(*) FROM escolas) AS total_escolas, (SELECT COUNT(*) FROM turmas) AS total_turmas, (SELECT COUNT(*) FROM alunos) AS total_alunos, (SELECT COUNT(*) FROM provas) AS total_provas")
        row=cur.fetchone(); cur.close(); conn.close()
        return jsonify({'total_escolas':int(row['total_escolas'] or 0),'total_turmas':int(row['total_turmas'] or 0),'total_alunos':int(row['total_alunos'] or 0),'total_provas':int(row['total_provas'] or 0)})
    except Exception as e: logging.error(f"Erro dashboard: {e}"); return jsonify({'total_escolas':0,'total_turmas':0,'total_alunos':0,'total_provas':0})

@app.route('/api/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT t.id as turma_id, t.nome as turma_nome, t.serie, COUNT(DISTINCT a.id) as total_alunos, COALESCE(AVG(h.acertos*1.0/NULLIF(h.total,0)),0) as media_porcentagem, COALESCE(SUM(CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END),0) as total_correcoes FROM turmas t LEFT JOIN alunos a ON a.turma_id=t.id LEFT JOIN historico h ON h.aluno_id=a.id GROUP BY t.id,t.nome,t.serie HAVING COUNT(DISTINCT a.id)>0 ORDER BY t.nome")
        turmas=cur.fetchall(); cur.close(); conn.close()
        resultado=[]
        for turma in turmas:
            media=float(turma['media_porcentagem'] or 0); pct=round(media*100) if media>0 else 0; conceito=calcular_conceito(pct)
            resultado.append({'id':turma['turma_id'],'nome':turma['turma_nome'] or f"Turma {turma['turma_id']}",'serie':turma['serie'],'total_alunos':turma['total_alunos'],'porcentagem':pct,'total_correcoes':int(turma['total_correcoes'] or 0),'conceito':conceito})
        return jsonify(resultado)
    except Exception as e: print(f"❌ Erro Conceito: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data=request.json
        for campo in ['escola_id','turma_id','aluno_id','prova_id']:
            if not data.get(campo): return jsonify({'erro':f'Campo "{campo}" obrigatório'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT a.nome, e.nome as escola_nome, t.nome as turma_nome, t.serie FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE a.id=%s",(data['aluno_id'],)); aluno=cur.fetchone()
        cur.execute("SELECT p.* FROM provas p WHERE p.id=%s",(data['prova_id'],)); prova=cur.fetchone()
        cur.close(); conn.close()
        if not aluno or not prova: return jsonify({'erro':'Aluno ou prova não encontrados'}),404
        nome_aluno=aluno['nome']; escola_nome=aluno['escola_nome'] or ''; turma_nome=aluno['turma_nome'] or ''; serie=prova.get('serie',''); titulo_prova=prova.get('titulo','Prova')
        tipo_questoes=int(prova.get('tipo_questoes',4)); alternativas=['A','B','C','D'][:tipo_questoes]; quantidade_questoes=int(prova.get('quantidade_questoes',20))
        html=f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>Cartão - {nome_aluno}</title><style>*{{margin:0;padding:0;box-sizing:border-box}}@page{{size:A4 portrait;margin:8mm 6mm}}body{{font-family:Arial;background:#f5f5f5;padding:10px;display:flex;justify-content:center}}.folha{{width:210mm;min-height:297mm;background:#fff;padding:6mm;position:relative;box-shadow:0 2px 20px rgba(0,0,0,0.15)}}.fiducial{{position:absolute;width:14mm;height:14mm;background:#000}}.fiducial-tl{{top:4mm;left:4mm}}.fiducial-tr{{top:4mm;right:4mm}}.fiducial-bl{{bottom:4mm;left:4mm}}.fiducial-br{{bottom:4mm;right:4mm}}.header{{text-align:center;border-bottom:2px solid #000;padding-bottom:8px;margin:18mm 0 8px}}.header h1{{font-size:13px;font-weight:bold}}.header h2{{font-size:16px;font-weight:900;margin-top:4px;border:2px solid #000;display:inline-block;padding:3px 20px}}.header .prova{{font-size:12px;font-weight:bold;margin-top:6px}}.header .escola{{font-size:10px;margin-top:3px}}.info-aluno{{display:grid;grid-template-columns:1fr 1fr;gap:6px;border:2px solid #000;padding:8px 12px;margin-bottom:8px;font-size:11px}}.instrucoes{{border:2px solid #000;padding:6px 12px;margin-bottom:10px;font-size:10px;font-weight:bold;text-align:center;background:#f0f0f0}}.questoes{{border:2px solid #000;padding:8px}}.linha-questao{{display:flex;align-items:center;padding:6px 8px;border-bottom:1px dashed #999;gap:12px}}.num-questao{{font-size:16px;font-weight:900;min-width:45px;text-align:right;padding-right:8px;border-right:2px solid #000}}.alternativas{{display:flex;gap:28px;justify-content:center;flex:1}}.alt-item{{display:flex;align-items:center;gap:6px}}.letra{{font-size:14px;font-weight:900;min-width:14px}}.circulo{{width:42px;height:42px;border:3.5px solid #000;border-radius:50%;background:#fff;display:inline-block}}.rodape{{margin-top:10px;display:flex;justify-content:space-between;font-size:8px;color:#666;border-top:1px solid #ccc;padding-top:6px}}.btn-print{{display:block;width:100%;margin-top:10px;padding:12px;background:#000;color:#fff;border:none;font-weight:bold;cursor:pointer}}@media print{{body{{background:#fff;padding:0}}.folha{{box-shadow:none}}.btn-print{{display:none}}.fiducial,.circulo{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}}}</style></head><body><div class="folha"><div class="fiducial fiducial-tl"></div><div class="fiducial fiducial-tr"></div><div class="fiducial fiducial-bl"></div><div class="fiducial fiducial-br"></div><div class="header"><h1>SECRETARIA MUNICIPAL DE EDUCAÇÃO — SISAM 2026</h1><h2>CARTÃO RESPOSTA</h2><div class="prova">{titulo_prova}</div><div class="escola">{escola_nome} | Série: {serie} | Turma: {turma_nome}</div></div><div class="info-aluno"><div><strong>Aluno(a):</strong> {nome_aluno}</div><div><strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y')} | <strong>ID:</strong> {data['aluno_id']}-{data['prova_id']}</div></div><div class="instrucoes">⚠ PREENCHA COMPLETAMENTE O CÍRCULO COM CANETA PRETA OU AZUL — NÃO RASURE</div><div class="questoes">
"""
        for i in range(quantidade_questoes):
            html+=f'<div class="linha-questao"><div class="num-questao">{i+1:02d}</div><div class="alternativas">'
            for alt in alternativas: html+=f'<div class="alt-item"><span class="letra">{alt}</span><span class="circulo"></span></div>'
            html+='</div></div>'
        html+=f'</div><button class="btn-print" onclick="window.print()">🖨 IMPRIMIR CARTÃO RESPOSTA</button><div class="rodape"><span>Gerado CorrigePro — {datetime.now().strftime("%d/%m/%Y %H:%M")}</span><span>ID {data["aluno_id"]}-{data["prova_id"]}</span></div></div></body></html>'
        return html,200,{'Content-Type':'text/html'}
    except Exception as e: print(f"❌ Erro gerar cartão: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/api/matrizes', methods=['GET'])
def listar_matrizes():
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id,ano,disciplina,nivel,descritores,created_at FROM matrizes ORDER BY created_at DESC"); matrizes=cur.fetchall(); cur.close(); conn.close()
        for m in matrizes:
            if m['descritores']:
                try:
                    if isinstance(m['descritores'],str): m['descritores']=json.loads(m['descritores'])
                    elif isinstance(m['descritores'],dict): m['descritores']=[m['descritores']] if m['descritores'] else []
                except: m['descritores']=[]
            else: m['descritores']=[]
        return jsonify(matrizes)
    except Exception as e: logging.error(f"Erro matrizes: {e}"); return jsonify([]),500

@app.route('/api/matrizes/<int:id>', methods=['GET'])
def buscar_matriz_por_id(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("SELECT id,ano,disciplina,nivel,descritores,created_at FROM matrizes WHERE id=%s",(id,)); matriz=cur.fetchone(); cur.close(); conn.close()
        if not matriz: return jsonify({'erro':'Matriz não encontrada'}),404
        if matriz['descritores']:
            try: matriz['descritores']=json.loads(matriz['descritores'])
            except: matriz['descritores']=[]
        else: matriz['descritores']=[]
        return jsonify(matriz)
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/matrizes', methods=['POST'])
def criar_matriz():
    try:
        data=request.json; ano=data.get('ano'); disciplina=data.get('disciplina'); nivel=data.get('nivel'); descritores=data.get('descritores',[])
        if not ano or not disciplina or not nivel: return jsonify({'erro':'Ano, disciplina e nível obrigatórios'}),400
        descritores_json=json.dumps(descritores,ensure_ascii=False)
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("INSERT INTO matrizes (ano,disciplina,nivel,descritores) VALUES (%s,%s,%s,%s::jsonb) RETURNING id",(ano,disciplina,nivel,descritores_json))
        result=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/matrizes/<int:id>', methods=['PUT'])
def atualizar_matriz(id):
    try:
        data=request.json; ano=data.get('ano'); disciplina=data.get('disciplina'); nivel=data.get('nivel'); descritores=data.get('descritores',[])
        if not ano or not disciplina or not nivel: return jsonify({'erro':'Ano, disciplina e nível obrigatórios'}),400
        descritores_json=json.dumps(descritores,ensure_ascii=False)
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("UPDATE matrizes SET ano=%s,disciplina=%s,nivel=%s,descritores=%s::jsonb WHERE id=%s RETURNING id",(ano,disciplina,nivel,descritores_json,id))
        result=cur.fetchone()
        if not result: cur.close(); conn.close(); return jsonify({'erro':'Matriz não encontrada'}),404
        conn.commit(); cur.close(); conn.close(); return jsonify({'id':result['id']})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/matrizes/<int:id>', methods=['DELETE'])
def excluir_matriz(id):
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor); cur.execute("DELETE FROM matrizes WHERE id=%s RETURNING id",(id,)); result=cur.fetchone()
        if not result: cur.close(); conn.close(); return jsonify({'erro':'Matriz não encontrada'}),404
        conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True})
    except Exception as e: return jsonify({'erro':str(e)}),500

@app.route('/api/backup', methods=['GET'])
def backup_database():
    backup_key=request.headers.get('X-Backup-Key') or request.args.get('key'); expected_key=os.getenv('BACKUP_KEY','backup123')
    if not backup_key or backup_key!=expected_key: return jsonify({'erro':'Não autorizado'}),403
    try:
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro banco'}),500
        tables=['escolas','turmas','alunos','provas','historico','usuarios','correcoes_texto','matrizes']; data={}
        cur=conn.cursor(cursor_factory=RealDictCursor)
        for table in tables:
            try: cur.execute(f"SELECT * FROM {table}"); data[table]=cur.fetchall()
            except: data[table]=[]
        cur.close(); conn.close()
        json_str=json.dumps(data,default=str,indent=2,ensure_ascii=False)
        memory_file=io.BytesIO(); timestamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        with zipfile.ZipFile(memory_file,'w',zipfile.ZIP_DEFLATED) as zf: zf.writestr(f"backup_{timestamp}.json",json_str.encode('utf-8'))
        memory_file.seek(0)
        return send_file(memory_file,mimetype='application/zip',as_attachment=True,download_name=f"backup_{timestamp}.zip")
    except Exception as e: logging.error(f"❌ Backup erro: {e}"); traceback.print_exc(); return jsonify({'erro':str(e)}),500

@app.route('/')
def index():
    try: return send_from_directory('.','index.html')
    except: return jsonify({'mensagem':'CorrigePro API - COMPLETA v2','status':'online','pytesseract':PYTESSERACT_AVAILABLE,'openai':OPENAI_AVAILABLE})

@app.route('/<path:path>')
def serve_static(path):
    try: return send_from_directory('.',path)
    except: return jsonify({'erro':'Arquivo não encontrado'}),404

@app.route('/health', methods=['GET'])
def health_check():
    conn=get_db_connection(); db_ok=conn is not None
    if conn: conn.close()
    return jsonify({'status':'online','openai':'disponível' if OPENAI_AVAILABLE else 'indisponível','openai_modelo':OPENAI_MODEL if OPENAI_AVAILABLE else None,'relay':'disponível' if RELAY_AVAILABLE else 'indisponível','database':'conectado' if db_ok else 'desconectado','pytesseract':'disponível' if PYTESSERACT_AVAILABLE else 'opcional - não instalado','pool':{'min':DB_POOL_MIN,'max':DB_POOL_MAX}})

def init_db():
    conn=get_db_connection()
    if not conn: print("⚠ Banco não disponível"); return
    try:
        cur=conn.cursor()
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='escolas')")
        tabela_existe=cur.fetchone()[0]
        if not tabela_existe:
            print("🔧 Criando tabelas...")
            cur.execute("CREATE TABLE escolas (id SERIAL PRIMARY KEY, nome TEXT NOT NULL, inep TEXT, municipio TEXT, estado TEXT DEFAULT 'PA', telefone TEXT, diretor TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE turmas (id SERIAL PRIMARY KEY, escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE, nome TEXT NOT NULL, serie TEXT, turno TEXT DEFAULT 'Manhã', professor TEXT, capacidade INTEGER DEFAULT 35, ano_letivo INTEGER DEFAULT 2025, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE alunos (id SERIAL PRIMARY KEY, escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE, turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE, nome TEXT NOT NULL, matricula TEXT, numero_chamada INTEGER, data_nascimento DATE, genero TEXT, responsavel TEXT, telefone TEXT, email TEXT, observacoes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE provas (id SERIAL PRIMARY KEY, titulo TEXT NOT NULL, serie TEXT NOT NULL, disciplina TEXT, bimestre TEXT, data_prova DATE, valor_nota DECIMAL(5,2) DEFAULT 10, tipo_questoes TEXT DEFAULT '4', quantidade_questoes INTEGER DEFAULT 20, gabarito TEXT[], bncc TEXT[], textos_questoes TEXT[], niveis TEXT[], created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE historico (id SERIAL PRIMARY KEY, prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE, aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE, respostas TEXT[], acertos INTEGER, nota DECIMAL(5,2), total INTEGER, tipo_correcao TEXT DEFAULT 'ia', disciplina TEXT, tipo_avaliacao TEXT, questoes_status JSONB DEFAULT '[]', confianca DECIMAL(5,2), confianca_por_questao JSONB DEFAULT '[]', bncc TEXT[], data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE usuarios (id SERIAL PRIMARY KEY, nome TEXT, username TEXT UNIQUE NOT NULL, senha_hash TEXT NOT NULL, email TEXT, perfil TEXT DEFAULT 'usuario', ativo BOOLEAN DEFAULT TRUE, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE correcoes_texto (id SERIAL PRIMARY KEY, aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE, prova_id INTEGER REFERENCES provas(id) ON DELETE SET NULL, texto TEXT NOT NULL, nota DECIMAL(5,2), metrica_coerencia DECIMAL(5,2), metrica_estrutura DECIMAL(5,2), metrica_gramatica DECIMAL(5,2), metrica_vocabulario DECIMAL(5,2), feedback TEXT, tipo_correcao TEXT DEFAULT 'ia', data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE matrizes (id SERIAL PRIMARY KEY, ano TEXT NOT NULL, disciplina TEXT NOT NULL, nivel TEXT NOT NULL, descritores JSONB DEFAULT '[]', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            print("✅ Tabelas criadas!")
        for username,dados in USUARIOS_FIXOS.items():
            cur.execute("SELECT * FROM usuarios WHERE username=%s",(username,))
            if not cur.fetchone():
                cur.execute("INSERT INTO usuarios (nome,username,senha_hash,perfil,ativo) VALUES (%s,%s,%s,%s,TRUE)",(dados['nome'],username,dados['senha'],dados['perfil']))
        conn.commit(); cur.close(); conn.close()
        print("✅ Banco inicializado!")
    except Exception as e: print(f"❌ Erro init_db: {e}"); traceback.print_exc()

if __name__=='__main__':
    port=int(os.environ.get('PORT',5000))
    print("="*60); print("🚀 CORRIGEPRO - VERSÃO COMPLETA SEM DUPLICIDADE"); print("="*60)
    print(f"📌 Porta: {port}"); print(f"🤖 OpenAI: {'✅' if OPENAI_AVAILABLE else '❌'}"); print(f"📦 Tesseract: {'✅' if PYTESSERACT_AVAILABLE else '⚠ Opcional - sem OCR'}")
    init_db()
    app.run(host='0.0.0.0',port=port,debug=False)
