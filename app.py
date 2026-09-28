from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import io
import re
from datetime import datetime
import os
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from psycopg2 import extensions
import pytesseract
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
# CACHE
# ============================================
CORRECOES_CACHE = {}
CACHE_TTL = 3600

def get_cache_key(img_hash, prova_id, aluno_id):
    return f"{img_hash}_{prova_id}_{aluno_id}"

def limpar_cache():
    agora = datetime.now().timestamp()
    for k in list(CORRECOES_CACHE.keys()):
        if agora - CORRECOES_CACHE[k]['timestamp'] > CACHE_TTL:
            del CORRECOES_CACHE[k]

# ============================================
# OPENAI
# ============================================
OPENAI_AVAILABLE = False
openai_client = None
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

try:
    from openai import OpenAI
    api_key = os.getenv('OPENAI_API_KEY','')
    if api_key.startswith('sk-'):
        openai_client = OpenAI(api_key=api_key)
        OPENAI_AVAILABLE = True
        logging.info(f"✅ OpenAI configurado: {OPENAI_MODEL}")
except Exception as e:
    logging.warning(f"⚠ OpenAI indisponível: {e}")

# ============================================
# BANCO - POOL
# ============================================
SUPABASE_URL = os.getenv('SUPABASE_URL')
DB_POOL = None
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN','5'))
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX','20'))

class PooledConnection:
    __slots__ = ('_conn','_pool','_closed')
    def __init__(self, conn, pool):
        self._conn=conn; self._pool=pool; self._closed=False
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        if self._closed: return
        self._closed=True
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
    if DB_POOL: return DB_POOL
    if not SUPABASE_URL: return None
    try:
        DB_POOL = ThreadedConnectionPool(DB_POOL_MIN, DB_POOL_MAX, dsn=SUPABASE_URL,
            connect_timeout=8, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)
        logging.info(f"✅ Pool DB {DB_POOL_MIN}-{DB_POOL_MAX}")
        return DB_POOL
    except Exception as e:
        logging.error(f"❌ Pool erro: {e}")
        return None

def get_db_connection():
    pool=_get_pool()
    if not pool: return None
    try:
        conn=pool.getconn()
        if conn.closed:
            pool.putconn(conn, close=True)
            conn=pool.getconn()
        return PooledConnection(conn, pool)
    except Exception as e:
        logging.error(f"❌ getconn: {e}")
        return None

# ============================================
# USUARIOS FIXOS
# ============================================
USUARIOS_FIXOS = {
    'admin': {'senha':'admin','perfil':'admin','nome':'Administrador'},
    'usuario': {'senha':'123','perfil':'usuario','nome':'Usuário'},
    'professor1': {'senha':'123','perfil':'usuario','nome':'Professor 1'}
}

# ============================================
# HELPERS GERAIS
# ============================================
def calcular_conceito(pct):
    if pct <= 40: return {'nome':'inicial','rotulo':'🔴 Inicial','cor':'#ef4444','badge':'badge-conceito-inicial'}
    if pct <= 60: return {'nome':'basico','rotulo':'🟠 Básico','cor':'#f59e0b','badge':'badge-conceito-basico'}
    if pct <= 80: return {'nome':'proficiente','rotulo':'🔵 Proficiente','cor':'#3b82f6','badge':'badge-conceito-proficiente'}
    return {'nome':'avancado','rotulo':'🟢 Avançado','cor':'#10b981','badge':'badge-conceito-avancado'}

def identificar_disciplina(titulo, disciplina, serie):
    txt = f"{disciplina or ''} {titulo or ''}".lower()
    if re.search(r'portugu|lingua', txt): return 'Portugues'
    if re.search(r'matem', txt): return 'Matematica'
    if re.search(r'produ[cç].*texto|redac', txt): return 'Producao'
    if re.search(r'\bch\b|humanas', txt): return 'CH'
    if re.search(r'\bcn\b|natureza', txt): return 'CN'
    if serie and re.search(r'\d+', str(serie)):
        return 'Portugues' if int(re.search(r'\d+', str(serie)).group()) <=5 else 'Matematica'
    return 'Geral'

def validar_gabarito(gab):
    if not gab: return False
    return all(str(g).strip().upper() in ['A','B','C','D'] for g in gab if str(g).strip())

def extrair_mimetype(b64):
    m=re.match(r'data:image/(\w+);base64,', b64 or '')
    return f"image/{m.group(1)}" if m else "image/jpeg"

def decode_base64_to_cv2(b64_str):
    if ',' in b64_str: b64_str = b64_str.split(',')[1]
    data = base64.b64decode(b64_str)
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

# ============================================
# 🔥 CORREÇÃO DE CARTÃO - NOVA LÓGICA ROBUSTA
# ============================================

def detectar_marcadores(gray):
    """Detecta 4 quadrados pretos nos cantos com maior robustez"""
    try:
        h,w = gray.shape
        _, bin_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # fecha buracos
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT,(5,5))
        bin_inv = cv2.morphologyEx(bin_inv, cv2.MORPH_CLOSE, kernel)
        
        contornos,_ = cv2.findContours(bin_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidatos=[]
        for c in contornos:
            x,y,wc,hc = cv2.boundingRect(c)
            area=wc*hc
            if not (h*w*0.001 < area < h*w*0.03): continue
            if not (0.7 < wc/float(hc) < 1.4): continue
            # solidez
            hull = cv2.convexHull(c)
            solidity = cv2.contourArea(c) / cv2.contourArea(hull) if cv2.contourArea(hull)>0 else 0
            if solidity < 0.8: continue
            candidatos.append((x,y,wc,hc,area, x+wc//2, y+hc//2))
        if len(candidatos) <4:
            return None
        candidatos.sort(key=lambda c: c[4], reverse=True)
        top4=candidatos[:4]
        # ordena por posicao
        cx_mid = w/2; cy_mid = h/2
        pts={}
        for x,y,wc,hc,_,cx,cy in top4:
            if cx<cx_mid and cy<cy_mid: pts['tl']=(cx,cy)
            elif cx>=cx_mid and cy<cy_mid: pts['tr']=(cx,cy)
            elif cx<cx_mid and cy>=cy_mid: pts['bl']=(cx,cy)
            else: pts['br']=(cx,cy)
        if len(pts)!=4: return None
        logging.info(f"✅ Marcadores: {pts}")
        return pts
    except Exception as e:
        logging.error(f"marcadores erro: {e}")
        return None

def corrigir_perspectiva(img, marcadores):
    tl,tr,bl,br = marcadores['tl'],marcadores['tr'],marcadores['bl'],marcadores['br']
    w_top = np.linalg.norm(np.array(tr)-np.array(tl))
    w_bot = np.linalg.norm(np.array(br)-np.array(bl))
    h_left = np.linalg.norm(np.array(bl)-np.array(tl))
    h_right= np.linalg.norm(np.array(br)-np.array(tr))
    W = int(max(w_top,w_bot)); H = int(max(h_left,h_right))
    margem=40
    src = np.float32([tl,tr,bl,br])
    dst = np.float32([[margem,margem],[W-margem,margem],[margem,H-margem],[W-margem,H-margem]])
    M = cv2.getPerspectiveTransform(src,dst)
    return cv2.warpPerspective(img, M, (W,H))

def detectar_circulos_e_classificar(imagem_base64, debug=False):
    """
    Pipeline definitivo:
    1. Decodifica
    2. Tenta corrigir perspectiva via fiduciais
    3. CLAHE + blur
    4. Detecta circulos via Hough + contornos
    5. Para cada circulo, mede fill ratio em imagem adaptativa
    """
    try:
        img = decode_base64_to_cv2(imagem_base64)
        if img is None: return [], None
        # resize
        h,w = img.shape[:2]
        if h>2400:
            s=2400/h
            img=cv2.resize(img,(int(w*s),2400))
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.createCLAHE(3.0,(8,8)).apply(gray)
        
        # tenta perspectiva
        marc = detectar_marcadores(gray_eq)
        if marc:
            img = corrigir_perspectiva(img, marc)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray_eq = cv2.createCLAHE(3.0,(8,8)).apply(gray)
        
        blur = cv2.GaussianBlur(gray_eq,(5,5),0)
        # threshold adaptativo para medir preenchimento
        thresh = cv2.adaptiveThreshold(blur,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV,51,15)
        
        # Detecta circulos - Hough
        circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=35,
                                   param1=80, param2=22, minRadius=14, maxRadius=34)
        all_circles=[]
        if circles is not None:
            circles=np.uint16(np.around(circles))
            for (x,y,r) in circles[0,:]:
                if x-r<0 or y-r<0 or x+r>=gray.shape[1] or y+r>=gray.shape[0]: continue
                mask = np.zeros(gray.shape, np.uint8)
                cv2.circle(mask,(x,y),int(r*0.7),255,-1)
                filled = cv2.countNonZero(cv2.bitwise_and(thresh,thresh,mask=mask))
                total = cv2.countNonZero(mask)
                ratio = filled/total if total else 0
                # borda escura?
                mean_inside = cv2.mean(gray_eq, mask=mask)[0]
                all_circles.append({'x':int(x),'y':int(y),'r':int(r),'ratio':float(ratio),
                                    'mean':float(mean_inside),'preenchido': ratio>0.38 and mean_inside<120})
        
        # fallback: contornos circulares
        if len(all_circles)<10:
            cnts,_=cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                x,y,wc,hc=cv2.boundingRect(c)
                if not (18<wc<60 and 18<hc<60): continue
                if not (0.7 < wc/float(hc) <1.3): continue
                # evita duplicatas perto de hough
                cx=x+wc//2; cy=y+hc//2
                if any(abs(cx-cc['x'])<15 and abs(cy-cc['y'])<15 for cc in all_circles): continue
                area=cv2.contourArea(c)
                if area < 200: continue
                mask=np.zeros(gray.shape,np.uint8)
                cv2.circle(mask,(cx,cy),int(min(wc,hc)*0.35),255,-1)
                filled=cv2.countNonZero(cv2.bitwise_and(thresh,thresh,mask=mask))
                total=cv2.countNonZero(mask)
                ratio=filled/total if total else 0
                mean_inside=cv2.mean(gray_eq,mask=mask)[0]
                all_circles.append({'x':cx,'y':cy,'r':int(min(wc,hc)//2),'ratio':ratio,
                                    'mean':mean_inside,'preenchido': ratio>0.38 and mean_inside<120})
        
        logging.info(f"🔵 Circulos: {len(all_circles)} total, {sum(1 for c in all_circles if c['preenchido'])} preenchidos")
        return all_circles, img
    except Exception as e:
        logging.error(f"detectar_circulos erro: {e}\n{traceback.format_exc()}")
        return [], None

def agrupar_em_linhas(circulos, y_tol=28):
    if not circulos: return []
    ordenados=sorted(circulos, key=lambda c: c['y'])
    linhas=[]; atual=[ordenados[0]]
    for c in ordenados[1:]:
        if abs(c['y']-atual[0]['y']) < y_tol:
            atual.append(c)
        else:
            linhas.append(sorted(atual, key=lambda cc: cc['x']))
            atual=[c]
    if atual: linhas.append(sorted(atual, key=lambda cc: cc['x']))
    # filtra linhas que não parecem questão (menos de 2 circulos ou mais de 6)
    linhas=[l for l in linhas if 2<=len(l)<=6]
    return sorted(linhas, key=lambda l: l[0]['y'])

def extrair_respostas(circulos, total_q, alternativas):
    """Melhor resposta por linha = mais escuro + maior ratio"""
    linhas=agrupar_em_linhas(circulos)
    respostas=[]
    for linha in linhas:
        # ordena esquerda -> direita
        linha=sorted(linha, key=lambda c: c['x'])
        # pega só preenchidos
        marcados=[c for c in linha if c['preenchido']]
        if not marcados:
            respostas.append('')
            continue
        # desempate: maior ratio + menor mean (mais escuro)
        marcados.sort(key=lambda c: (-c['ratio'], c['mean']))
        escolhido=marcados[0]
        idx=linha.index(escolhido) if escolhido in linha else 0
        # se linha tem mais alts que o numero de alternativas, mapeia proporcional
        letra = alternativas[min(idx, len(alternativas)-1)] if idx < len(alternativas) else ''
        respostas.append(letra)
    # completa
    while len(respostas)<total_q: respostas.append('')
    return respostas[:total_q], linhas

# ============================================
# IA CORREÇÃO
# ============================================
def corrigir_com_ia(imagem_base64, total_q, alternativas, aluno_nome):
    if not OPENAI_AVAILABLE: return None
    try:
        if ',' in imagem_base64: b64_clean = imagem_base64.split(',')[1]
        else: b64_clean=imagem_base64
        prompt = f"""Você é um corretor de cartão resposta.
Analise a imagem. Cada linha tem {len(alternativas)} círculos ({','.join(alternativas)} da esquerda para direita).
Retorne APENAS JSON: {{"respostas": ["A","B","","C"...]}} com EXATAMENTE {total_q} itens.
Regras: círculo totalmente preenchido = marcado. Se vazio ou dúvida = "". Se 2 marcados na mesma linha, escolha o mais escuro.
Aluno: {aluno_nome}
"""
        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"user","content":[
                {"type":"text","text":prompt},
                {"type":"image_url","image_url":{"url":f"data:{extrair_mimetype(imagem_base64)};base64,{b64_clean}"}}
            ]}],
            max_tokens=800, temperature=0.1, response_format={"type":"json_object"}
        )
        txt=resp.choices[0].message.content
        dados=json.loads(txt)
        resps=dados.get('respostas',[])
        # valida
        vals=[]
        for r in resps[:total_q]:
            r=str(r).upper().strip() if r else ''
            vals.append(r if r in alternativas else '')
        while len(vals)<total_q: vals.append('')
        logging.info(f"🤖 IA retornou: {vals}")
        return vals
    except Exception as e:
        logging.error(f"IA erro: {e}")
        return None

def calcular_resultado(respostas, gabarito, aluno_nome, serie, disciplina, tipo_q, modo, bncc=None, meta_extra=None):
    alts=['A','B','C','D'][:tipo_q]
    acertos=0; correcoes=[]; qstatus=[]
    for i in range(len(gabarito)):
        resp=respostas[i] if i < len(respostas) else ''
        gab=str(gabarito[i]).upper().strip() if i < len(gabarito) and gabarito[i] else ''
        valido=resp in alts
        correto= valido and gab and resp==gab
        if correto: acertos+=1
        bncc_code = bncc[i] if bncc and i < len(bncc) else ''
        correcoes.append({'questao':i+1,'resposta':resp or '—','gabarito':gab or '—','correto':correto,'bncc':bncc_code})
        qstatus.append({'numero':i+1,'resposta':resp or '—','gabarito':gab or '—','acertou':correto,
                        'status':'ADQUIRIU HABILIDADE ✅' if correto else ('RECOMPOSIÇÃO ❌' if valido else 'NÃO RESPONDEU —'),
                        'bncc':bncc_code})
    nota = round((acertos/len(gabarito)*10) if gabarito else 0,1)
    pct = round((acertos/len(gabarito)*100) if gabarito else 0)
    conceito=calcular_conceito(pct)
    return {
        'aluno':aluno_nome,'serie':serie,'disciplina':disciplina,
        'total':len(gabarito),'acertos':acertos,'nota':nota,'porcentagem':pct,'conceito':conceito,
        'respostas_detectadas':respostas,'gabarito':gabarito,
        'correcoes':correcoes,'questoes_status':qstatus,
        'tipo_questoes':str(tipo_q),'confianca': 92 if modo=='circulos' else 85,
        'confianca_por_questao':[90 if r in alts else 50 for r in respostas],
        'modo':modo,'valor_por_questao': round(10/len(gabarito),2) if gabarito else 0,
        'bncc': bncc or [], 'meta': meta_extra or {}
    }

# ============================================
# PIPELINE PRINCIPAL
# ============================================
def pipeline_correcao(imagem_b64, gabarito, aluno_nome, serie, disciplina, tipo_q, bncc=None):
    if not gabarito: return {'erro':'Gabarito vazio'}
    total=len(gabarito)
    alts=['A','B','C','D'][:tipo_q]
    
    # 1) OpenCV
    circulos,_ = detectar_circulos_e_classificar(imagem_b64)
    if circulos:
        respostas, linhas = extrair_respostas(circulos, total, alts)
        detectadas = sum(1 for r in respostas if r)
        logging.info(f"📊 OpenCV: {detectadas}/{total}")
        if detectadas >= total*0.6: # 60% já é suficiente
            return calcular_resultado(respostas,gabarito,aluno_nome,serie,disciplina,tipo_q,'circulos',bncc,
                                      meta_extra={'circulos_total':len(circulos),'preenchidos':sum(1 for c in circulos if c['preenchido'])})
    
    # 2) IA
    resp_ia = corrigir_com_ia(imagem_b64, total, alts, aluno_nome)
    if resp_ia and sum(1 for r in resp_ia if r) >= total*0.4:
        return calcular_resultado(resp_ia,gabarito,aluno_nome,serie,disciplina,tipo_q,'ia',bncc)
    
    # 3) Se ainda falhou, tenta combinar: se OpenCV pegou algo, usa
    if circulos:
        respostas, _ = extrair_respostas(circulos, total, alts)
        if any(r for r in respostas):
            return calcular_resultado(respostas,gabarito,aluno_nome,serie,disciplina,tipo_q,'circulos_parcial',bncc)
    
    return {'erro':'Não foi possível detectar marcações. Verifique iluminação e enquadramento.','modo':'erro'}

# ============================================
# ROTAS (SEM DUPLICIDADE)
# ============================================

@app.after_request
def after_request(response):
    if request.path.startswith('/api/') and response.status_code!=200:
        if 'text/html' in response.headers.get('Content-Type',''):
            response=jsonify({'erro':'Erro interno','status':response.status_code})
            response.status_code=500
    return response

@app.route('/api/login', methods=['POST'])
def login():
    data=request.json or {}
    u=data.get('username'); s=data.get('senha')
    if not u or not s: return jsonify({'erro':'Usuário e senha obrigatórios'}),400
    conn=get_db_connection()
    if conn:
        try:
            cur=conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT id,nome,username,senha_hash,perfil,ativo FROM usuarios WHERE username=%s",(u,))
            usr=cur.fetchone(); cur.close(); conn.close()
            if usr and hmac.compare_digest(str(usr['senha_hash'] or ''), str(s)) and usr['ativo']:
                return jsonify({'sucesso':True,'perfil':usr['perfil'],'usuario':usr['username'],'nome':usr['nome']})
        except Exception as e: logging.error(e)
    if u in USUARIOS_FIXOS and hmac.compare_digest(USUARIOS_FIXOS[u]['senha'], str(s)):
        d=USUARIOS_FIXOS[u]
        return jsonify({'sucesso':True,'perfil':d['perfil'],'usuario':u,'nome':d['nome']})
    return jsonify({'sucesso':False,'erro':'Usuário ou senha incorretos'}),401

@app.route('/api/corrigir', methods=['POST'])
def corrigir():
    try:
        data=request.json or {}
        imagem=data.get('imagem'); prova_id=data.get('prova_id'); aluno_id=data.get('aluno_id')
        if not imagem or not prova_id or not aluno_id:
            return jsonify({'erro':'imagem, prova_id e aluno_id são obrigatórios'}),400
        
        img_hash=hashlib.md5(imagem.encode()).hexdigest()
        key=get_cache_key(img_hash,prova_id,aluno_id)
        limpar_cache()
        if key in CORRECOES_CACHE and (datetime.now().timestamp()-CORRECOES_CACHE[key]['timestamp']<CACHE_TTL):
            return jsonify(CORRECOES_CACHE[key]['resultado'])

        conn=get_db_connection()
        if not conn: return jsonify({'erro':'Erro DB'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*, a.nome as aluno_nome, t.serie as turma_serie, e.nome as escola_nome
            FROM provas p
            LEFT JOIN alunos a ON a.id=%s
            LEFT JOIN turmas t ON a.turma_id=t.id
            LEFT JOIN escolas e ON a.escola_id=e.id
            WHERE p.id=%s
        """,(aluno_id,prova_id))
        dados=cur.fetchone()
        if not dados or not dados.get('gabarito'):
            cur.close(); conn.close()
            return jsonify({'erro':'Prova/gabarito não encontrado'}),404
        
        gabarito=dados['gabarito']; tipo_q=int(dados.get('tipo_questoes') or 4)
        bncc=dados.get('bncc',[])
        nome=dados.get('aluno_nome') or 'Aluno'
        serie=dados.get('turma_serie') or dados.get('serie') or '1º Ano'
        disciplina=dados.get('disciplina',''); titulo=dados.get('titulo','')
        cur.close(); conn.close()

        resultado=pipeline_correcao(imagem,gabarito,nome,serie,disciplina,tipo_q,bncc)
        if resultado.get('erro'): return jsonify(resultado),400

        resultado['tipo_avaliacao']=identificar_disciplina(titulo,disciplina,serie)
        resultado['disciplina']=disciplina

        # salva historico
        try:
            conn=get_db_connection()
            if conn:
                cur=conn.cursor()
                qs=json.dumps(resultado['questoes_status'])
                cur.execute("SELECT id FROM historico WHERE prova_id=%s AND aluno_id=%s",(prova_id,aluno_id))
                ex=cur.fetchone()
                if ex:
                    cur.execute("""
                        UPDATE historico SET respostas=%s::text[], acertos=%s, nota=%s, total=%s,
                        tipo_correcao=%s, disciplina=%s, tipo_avaliacao=%s, questoes_status=%s::jsonb,
                        confianca=%s, confianca_por_questao=%s::jsonb, bncc=%s::text[], data_correcao=CURRENT_TIMESTAMP
                        WHERE prova_id=%s AND aluno_id=%s
                    """,(resultado['respostas_detectadas'],resultado['acertos'],resultado['nota'],resultado['total'],
                        resultado['modo'],disciplina,resultado['tipo_avaliacao'],qs,resultado['confianca'],
                        json.dumps(resultado['confianca_por_questao']),bncc,prova_id,aluno_id))
                else:
                    cur.execute("""
                        INSERT INTO historico (prova_id,aluno_id,respostas,acertos,nota,total,tipo_correcao,disciplina,tipo_avaliacao,questoes_status,confianca,confianca_por_questao,bncc)
                        VALUES (%s,%s,%s::text[],%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::text[])
                    """,(prova_id,aluno_id,resultado['respostas_detectadas'],resultado['acertos'],resultado['nota'],resultado['total'],
                          resultado['modo'],disciplina,resultado['tipo_avaliacao'],qs,resultado['confianca'],
                          json.dumps(resultado['confianca_por_questao']),bncc))
                conn.commit(); cur.close(); conn.close()
        except Exception as e: logging.error(f"salvar hist erro: {e}")

        CORRECOES_CACHE[key]={'timestamp':datetime.now().timestamp(),'resultado':resultado}
        return jsonify(resultado)
    except Exception as e:
        logging.error(traceback.format_exc())
        return jsonify({'erro':str(e)}),500

@app.route('/api/corrigir_manual', methods=['POST'])
def corrigir_manual():
    try:
        data=request.json or {}
        prova_id=data.get('prova_id'); aluno_id=data.get('aluno_id')
        respostas=data.get('respostas',[]); total=data.get('total',len(respostas))
        if not prova_id or not aluno_id: return jsonify({'erro':'prova e aluno obrigatórios'}),400
        conn=get_db_connection()
        if not conn: return jsonify({'erro':'DB'}),500
        cur=conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT disciplina,titulo,serie,gabarito,bncc FROM provas WHERE id=%s",(prova_id,))
        prova=cur.fetchone()
        if not prova: return jsonify({'erro':'Prova não encontrada'}),404
        disciplina=prova['disciplina'] or ''; titulo=prova['titulo'] or ''; gabarito=prova['gabarito'] or []
        bncc=prova['bncc'] or []
        cur.execute("SELECT t.serie FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id WHERE a.id=%s",(aluno_id,))
        r=cur.fetchone(); serie=r['serie'] if r else prova['serie'] or '1º Ano'
        tipo=identificar_disciplina(titulo,disciplina,serie)
        acertos=sum(1 for i in range(min(len(respostas),len(gabarito))) if str(respostas[i]).upper()==str(gabarito[i]).upper() and respostas[i])
        nota=round(acertos/len(gabarito)*10,1) if gabarito else 0
        qstatus=[]
        for i in range(total):
            resp=str(respostas[i]).upper() if i<len(respostas) and respostas[i] else ''
            gab=str(gabarito[i]).upper() if i<len(gabarito) and gabarito[i] else ''
            correto=resp==gab and resp!=''
            qstatus.append({'numero':i+1,'resposta':resp or '—','gabarito':gab or '—','acertou':correto,
                            'status':'ADQUIRIU' if correto else 'RECOMPOSIÇÃO' if resp else 'NÃO RESPONDEU','bncc':bncc[i] if i<len(bncc) else ''})
        cur=conn.cursor()
        qs=json.dumps(qstatus)
        cur.execute("SELECT id FROM historico WHERE prova_id=%s AND aluno_id=%s",(prova_id,aluno_id))
        ex=cur.fetchone()
        if ex:
            cur.execute("UPDATE historico SET respostas=%s::text[], acertos=%s, nota=%s, total=%s, tipo_correcao='manual', disciplina=%s, tipo_avaliacao=%s, questoes_status=%s::jsonb WHERE prova_id=%s AND aluno_id=%s",
                        (respostas,acertos,nota,total,disciplina,tipo,qs,prova_id,aluno_id))
        else:
            cur.execute("INSERT INTO historico (prova_id,aluno_id,respostas,acertos,nota,total,tipo_correcao,disciplina,tipo_avaliacao,questoes_status) VALUES (%s,%s,%s::text[],%s,%s,%s,'manual',%s,%s,%s::jsonb)",
                        (prova_id,aluno_id,respostas,acertos,nota,total,disciplina,tipo,qs))
        conn.commit(); cur.close(); conn.close()
        pct=round(acertos/total*100) if total else 0
        return jsonify({'sucesso':True,'acertos':acertos,'nota':nota,'porcentagem':pct,'conceito':calcular_conceito(pct),'questoes_status':qstatus,'tipo_avaliacao':tipo})
    except Exception as e:
        traceback.print_exc(); return jsonify({'erro':str(e)}),500

# --------- OUTRAS ROTAS SIMPLIFICADAS (SEM DUPLICIDADE) ---------
@app.route('/api/escolas', methods=['GET','POST'])
def escolas():
    conn=get_db_connection()
    if not conn: return jsonify([]) if request.method=='GET' else jsonify({'erro':'DB'}),500
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        cur.execute("SELECT * FROM escolas ORDER BY nome"); res=cur.fetchall(); cur.close(); conn.close(); return jsonify(res)
    data=request.json; nome=data.get('nome')
    if not nome: return jsonify({'erro':'Nome obrigatório'}),400
    cur.execute("INSERT INTO escolas (nome,inep,municipio,estado,telefone,diretor) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (nome,data.get('inep',''),data.get('municipio',''),data.get('estado','PA'),data.get('telefone',''),data.get('diretor','')))
    r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r['id']})

@app.route('/api/escolas/<int:id>', methods=['GET','PUT','DELETE'])
def escola_id(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        cur.execute("SELECT * FROM escolas WHERE id=%s",(id,)); e=cur.fetchone(); cur.close(); conn.close()
        return jsonify(e) if e else (jsonify({'erro':'Não encontrada'}),404)
    if request.method=='PUT':
        data=request.json; cur.execute("UPDATE escolas SET nome=%s, inep=%s, municipio=%s, estado=%s, telefone=%s, diretor=%s WHERE id=%s RETURNING id",
            (data.get('nome'),data.get('inep',''),data.get('municipio',''),data.get('estado','PA'),data.get('telefone',''),data.get('diretor',''),id))
        r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r['id']})
    cur=conn.cursor(); cur.execute("DELETE FROM escolas WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True})

@app.route('/api/turmas', methods=['GET','POST'])
def turmas():
    conn=get_db_connection()
    if not conn: return jsonify([])
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        esc=request.args.get('escola_id'); q="SELECT t.*, e.nome as escola_nome, COUNT(a.id) as total_alunos FROM turmas t LEFT JOIN escolas e ON t.escola_id=e.id LEFT JOIN alunos a ON a.turma_id=t.id"; p=[]
        if esc and esc.isdigit(): q+=" WHERE t.escola_id=%s"; p=[int(esc)]
        q+=" GROUP BY t.id, e.nome ORDER BY t.nome"; cur.execute(q,p); r=cur.fetchall(); cur.close(); conn.close(); return jsonify(r)
    data=request.json; cur.execute("INSERT INTO turmas (escola_id,nome,serie,turno,professor,capacidade,ano_letivo) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (data['escola_id'],data['nome'],data.get('serie','1º Ano'),data.get('turno','Manhã'),data.get('professor',''),data.get('capacidade',35),data.get('ano_letivo',2025)))
    res=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':res['id']})

@app.route('/api/turmas/<int:id>', methods=['GET','PUT','DELETE'])
def turma_id(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        cur.execute("SELECT t.*, e.nome as escola_nome FROM turmas t LEFT JOIN escolas e ON t.escola_id=e.id WHERE t.id=%s",(id,)); t=cur.fetchone(); cur.close(); conn.close()
        return jsonify(t) if t else (jsonify({'erro':'Não encontrada'}),404)
    if request.method=='PUT':
        d=request.json; cur.execute("UPDATE turmas SET escola_id=%s,nome=%s,serie=%s,turno=%s,professor=%s,capacidade=%s,ano_letivo=%s WHERE id=%s RETURNING id",
            (d['escola_id'],d['nome'],d.get('serie'),d.get('turno'),d.get('professor',''),d.get('capacidade',35),d.get('ano_letivo',2025),id))
        r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r['id']})
    cur=conn.cursor(); cur.execute("DELETE FROM turmas WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True})

@app.route('/api/alunos', methods=['GET','POST'])
def alunos():
    conn=get_db_connection()
    if not conn: return jsonify([])
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        esc=request.args.get('escola_id'); turma=request.args.get('turma_id'); serie=request.args.get('serie')
        q="SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE 1=1"; p=[]
        if esc and esc.isdigit(): q+=" AND a.escola_id=%s"; p.append(int(esc))
        if turma and turma.isdigit(): q+=" AND a.turma_id=%s"; p.append(int(turma))
        if serie: q+=" AND t.serie=%s"; p.append(serie)
        q+=" ORDER BY a.numero_chamada NULLS LAST, a.nome"; cur.execute(q,p); r=cur.fetchall(); cur.close(); conn.close(); return jsonify(r)
    d=request.json
    if not all([d.get('nome'),d.get('escola_id'),d.get('turma_id')]): return jsonify({'erro':'nome, escola e turma obrigatórios'}),400
    cur.execute("INSERT INTO alunos (escola_id,turma_id,nome,matricula,numero_chamada,data_nascimento,genero,responsavel,telefone,email,observacoes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (d['escola_id'],d['turma_id'],d['nome'],d.get('matricula',''),d.get('numero_chamada'),d.get('data_nascimento'),d.get('genero','Masculino'),d.get('responsavel',''),d.get('telefone',''),d.get('email',''),d.get('observacoes','')))
    res=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':res['id']})

@app.route('/api/alunos/<int:id>', methods=['GET','PUT','DELETE'])
def aluno_id(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        cur.execute("SELECT a.*, t.nome as turma_nome, e.nome as escola_nome FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE a.id=%s",(id,)); a=cur.fetchone(); cur.close(); conn.close()
        return jsonify(a) if a else (jsonify({'erro':'Não encontrado'}),404)
    if request.method=='PUT':
        d=request.json; cur.execute("UPDATE alunos SET escola_id=%s,turma_id=%s,nome=%s,matricula=%s,numero_chamada=%s,data_nascimento=%s,genero=%s,responsavel=%s,telefone=%s,email=%s,observacoes=%s WHERE id=%s RETURNING id",
            (d['escola_id'],d['turma_id'],d['nome'],d.get('matricula',''),d.get('numero_chamada'),d.get('data_nascimento'),d.get('genero'),d.get('responsavel',''),d.get('telefone',''),d.get('email',''),d.get('observacoes',''),id))
        r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r['id']})
    cur=conn.cursor(); cur.execute("DELETE FROM historico WHERE aluno_id=%s",(id,)); cur.execute("DELETE FROM alunos WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True})

@app.route('/api/provas', methods=['GET','POST'])
def provas():
    conn=get_db_connection()
    if not conn: return jsonify([])
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        cur.execute("SELECT * FROM provas ORDER BY created_at DESC"); r=cur.fetchall(); cur.close(); conn.close(); return jsonify(r)
    d=request.json
    if not d.get('titulo') or not d.get('serie'): return jsonify({'erro':'titulo e serie obrigatórios'}),400
    cur.execute("INSERT INTO provas (titulo,serie,disciplina,bimestre,data_prova,valor_nota,tipo_questoes,quantidade_questoes,gabarito,bncc,textos_questoes,niveis) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (d['titulo'],d['serie'],d.get('disciplina',''),d.get('bimestre',''),d.get('data_prova'),d.get('nota_maxima',10),d.get('tipo_questoes','4'),d.get('quantidade_questoes',20),d.get('gabarito',[]),d.get('bncc',[]),d.get('textos_questoes',[]),d.get('niveis',[])))
    r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r['id']})

@app.route('/api/provas/<int:id>', methods=['GET','PUT','DELETE'])
def prova_id(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(cursor_factory=RealDictCursor)
    if request.method=='GET':
        cur.execute("SELECT * FROM provas WHERE id=%s",(id,)); p=cur.fetchone(); cur.close(); conn.close()
        return jsonify(p) if p else (jsonify({'erro':'Não encontrada'}),404)
    if request.method=='PUT':
        d=request.json; cur.execute("UPDATE provas SET titulo=%s,serie=%s,disciplina=%s,bimestre=%s,data_prova=%s,valor_nota=%s,tipo_questoes=%s,quantidade_questoes=%s,gabarito=%s,bncc=%s,textos_questoes=%s,niveis=%s WHERE id=%s RETURNING id",
            (d['titulo'],d['serie'],d.get('disciplina',''),d.get('bimestre',''),d.get('data_prova'),d.get('nota_maxima',10),d.get('tipo_questoes','4'),d.get('quantidade_questoes',20),d.get('gabarito',[]),d.get('bncc',[]),d.get('textos_questoes',[]),d.get('niveis',[]),id))
        r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r['id']})
    cur=conn.cursor(); cur.execute("DELETE FROM historico WHERE prova_id=%s",(id,)); cur.execute("DELETE FROM provas WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True})

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    data=request.json or {}; pid=data.get('prova_id'); resps=data.get('respostas',[])
    if not pid or not resps: return jsonify({'erro':'prova_id e respostas obrigatórios'}),400
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(); cur.execute("UPDATE provas SET gabarito=%s::text[], quantidade_questoes=%s, bncc=%s::text[], textos_questoes=%s::text[], niveis=%s::text[] WHERE id=%s RETURNING id",
        ([str(r).upper() for r in resps], len(resps), data.get('bncc',[]), data.get('textos_questoes',[]), data.get('niveis',[]), pid))
    r=cur.fetchone(); conn.commit(); cur.close(); conn.close(); return jsonify({'id':r[0]})

@app.route('/api/historico', methods=['GET'])
def historico():
    conn=get_db_connection()
    if not conn: return jsonify([])
    cur=conn.cursor(cursor_factory=RealDictCursor)
    esc=request.args.get('escola'); turma=request.args.get('turma'); aluno=request.args.get('aluno_id'); prova=request.args.get('prova_id')
    q="SELECT h.*, a.nome as aluno_nome, p.titulo as prova_titulo, p.disciplina, t.serie, t.nome as turma_nome, e.nome as escola_nome, p.quantidade_questoes as total_questoes FROM historico h LEFT JOIN alunos a ON h.aluno_id=a.id LEFT JOIN provas p ON h.prova_id=p.id LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE 1=1"; p=[]
    if esc and esc.isdigit(): q+=" AND e.id=%s"; p.append(int(esc))
    if turma and turma.isdigit(): q+=" AND t.id=%s"; p.append(int(turma))
    if aluno and aluno.isdigit(): q+=" AND h.aluno_id=%s"; p.append(int(aluno))
    if prova and prova.isdigit(): q+=" AND h.prova_id=%s"; p.append(int(prova))
    q+=" ORDER BY h.data_correcao DESC LIMIT 200"; cur.execute(q,p); res=cur.fetchall(); cur.close(); conn.close()
    for item in res:
        total=item.get('total_questoes') or item.get('total') or 20
        pct=round((item.get('acertos',0)/total*100) if total else 0)
        item['porcentagem']=pct; item['conceito']=calcular_conceito(pct)['nome']
    return jsonify(res)

@app.route('/api/historico/<int:id>', methods=['DELETE'])
def hist_del(id):
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(); cur.execute("DELETE FROM historico WHERE id=%s",(id,)); conn.commit(); cur.close(); conn.close(); return jsonify({'sucesso':True})

@app.route('/api/dashboard', methods=['GET'])
def dash():
    conn=get_db_connection()
    if not conn: return jsonify({'total_escolas':0,'total_turmas':0,'total_alunos':0,'total_provas':0})
    cur=conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT (SELECT COUNT(*) FROM escolas) as e, (SELECT COUNT(*) FROM turmas) as t, (SELECT COUNT(*) FROM alunos) as a, (SELECT COUNT(*) FROM provas) as p")
    r=cur.fetchone(); cur.close(); conn.close()
    return jsonify({'total_escolas':r['e'],'total_turmas':r['t'],'total_alunos':r['a'],'total_provas':r['p']})

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_cartao():
    data=request.json or {}
    for c in ['escola_id','turma_id','aluno_id','prova_id']:
        if not data.get(c): return jsonify({'erro':f'{c} obrigatório'}),400
    conn=get_db_connection()
    if not conn: return jsonify({'erro':'DB'}),500
    cur=conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT a.nome, e.nome as escola_nome, t.nome as turma_nome, t.serie FROM alunos a LEFT JOIN turmas t ON a.turma_id=t.id LEFT JOIN escolas e ON a.escola_id=e.id WHERE a.id=%s",(data['aluno_id'],))
    aluno=cur.fetchone()
    cur.execute("SELECT * FROM provas WHERE id=%s",(data['prova_id'],)); prova=cur.fetchone()
    cur.close(); conn.close()
    if not aluno or not prova: return jsonify({'erro':'Aluno/prova não encontrados'}),404
    # HTML otimizado mantido, mas com círculos maiores e ID único
    tipo_q=int(prova.get('tipo_questoes',4)); alts=['A','B','C','D'][:tipo_q]; qtd=int(prova.get('quantidade_questoes',20))
    html = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'><style>
    @page{{size:A4;margin:8mm}} body{{font-family:Arial;display:flex;justify-content:center;background:#f5f5f5}}
    .folha{{width:210mm;min-height:297mm;background:#fff;padding:6mm;position:relative}}
    .fiducial{{position:absolute;width:14mm;height:14mm;background:#000}} .fiducial-tl{{top:4mm;left:4mm}} .fiducial-tr{{top:4mm;right:4mm}} .fiducial-bl{{bottom:4mm;left:4mm}} .fiducial-br{{bottom:4mm;right:4mm}}
    .header{{text-align:center;border-bottom:2px solid #000;padding-bottom:8px;margin:18mm 0 8px}} .header h2{{border:2px solid #000;padding:3px 20px;display:inline-block}}
    .info{{border:2px solid #000;padding:8px 12px;display:flex;justify-content:space-between;font-size:11px;margin-bottom:8px}}
    .inst{{border:2px solid #000;padding:6px;text-align:center;background:#f0f0f0;font-weight:bold;font-size:10px;margin-bottom:10px}}
    .questoes{{border:2px solid #000;padding:8px}} .linha{{display:flex;align-items:center;padding:6px 8px;border-bottom:1px dashed #999;gap:12px}}
    .num{{font-weight:900;min-width:45px;text-align:right;border-right:2px solid #000;padding-right:8px}} .alts{{display:flex;gap:28px;flex:1;justify-content:center}} .alt{{display:flex;align-items:center;gap:6px}} .letra{{font-weight:900}}
    .circulo{{width:42px;height:42px;border:3.5px solid #000;border-radius:50%;background:#fff}} 
    @media print{{.no-print{{display:none}} .fiducial{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}}}
    </style></head><body><div class='folha'>
    <div class='fiducial fiducial-tl'></div><div class='fiducial fiducial-tr'></div><div class='fiducial fiducial-bl'></div><div class='fiducial fiducial-br'></div>
    <div class='header'><h1>SECRETARIA MUNICIPAL - SISAM 2026</h1><h2>CARTÃO RESPOSTA</h2><div>{prova.get('titulo','Prova')} | {aluno.get('escola_nome','')} | {aluno.get('serie','')}</div></div>
    <div class='info'><span><b>Aluno:</b> {aluno['nome']}</span><span><b>Data:</b> {datetime.now().strftime('%d/%m/%Y')}</span><span><b>ID:</b> {data['aluno_id']}-{data['prova_id']}</span></div>
    <div class='inst'>⚠ PREENCHA COMPLETAMENTE COM CANETA PRETA - ID: {data['aluno_id']}-{data['prova_id']}</div>
    <div class='questoes'>
    """
    for i in range(qtd):
        html+=f"<div class='linha'><div class='num'>{i+1:02d}</div><div class='alts'>"
        for a in alts: html+=f"<div class='alt'><span class='letra'>{a}</span><span class='circulo'></span></div>"
        html+="</div></div>"
    html+=f"</div><button class='no-print' onclick='window.print()' style='width:100%;padding:12px;background:#000;color:#fff;margin-top:10px'>🖨 IMPRIMIR</button></div></body></html>"
    return html, 200, {'Content-Type':'text/html'}

@app.route('/health', methods=['GET'])
def health():
    conn=get_db_connection(); ok=conn is not None
    if conn: conn.close()
    return jsonify({'status':'online','openai': OPENAI_AVAILABLE,'database': ok})

@app.route('/')
def index():
    try: return send_from_directory('.', 'index.html')
    except: return jsonify({'mensagem':'CorrigePro API v2 - sem duplicidade','status':'online'})

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=False)
