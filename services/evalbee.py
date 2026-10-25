# ============================================================
# SERVICES/EVALBEE.PY — Motor de detecção fiducial + template
# ⚠️ CORRIGIDO: detecta automaticamente scanner vs foto
# ============================================================

import cv2
cv2.setNumThreads(1)

import base64
import json
import logging
import traceback

import numpy as np
from psycopg2.extras import RealDictCursor
from collections import defaultdict

from core.db import get_db_connection


def detectar_tipo_entrada(gray):
    """
    Detecta se a imagem veio de scanner de mesa ou foto de celular.
    
    Scanner: fundo branco uniforme (255), sem sombras, desvio padrão baixo.
    Foto: iluminação variável, sombras, desvio padrão alto.
    """
    try:
        brilho_medio = float(np.mean(gray))
        desvio = float(np.std(gray))
        h, w = gray.shape[:2]
        
        # Amostra os 4 cantos (onde não há conteúdo, só fundo)
        amostra = max(30, min(h, w) // 20)
        cantos = np.concatenate([
            gray[:amostra, :amostra].flatten(),
            gray[:amostra, -amostra:].flatten(),
            gray[-amostra:, :amostra].flatten(),
            gray[-amostra:, -amostra:].flatten(),
        ])
        brilho_cantos = float(np.mean(cantos))
        uniformidade_cantos = float(np.std(cantos))
        quase_branco = float(np.sum(gray > 240) / gray.size)
        
        # Scanner: cantos branco puro (255), uniformes
        if (brilho_cantos > 230 
            and uniformidade_cantos < 15 
            and brilho_medio > 180 
            and quase_branco > 0.5):
            return 'scanner'
        return 'foto'
    except Exception:
        return 'foto'


def detectar_marcadores_fiduciais_v4(gray):
    try:
        h, w = gray.shape

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        binaria = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            41, 10
        )

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)

        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        area_img = w * h
        candidatos = []

        for c in contornos:
            area = cv2.contourArea(c)

            if not (area_img * 0.0005 < area < area_img * 0.03):
                continue

            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) != 4:
                continue

            x, y, bw, bh = cv2.boundingRect(approx)

            ar = bw / float(bh) if bh > 0 else 0
            if not (0.75 < ar < 1.35):
                continue

            hull = cv2.convexHull(c)
            solidez = area / (cv2.contourArea(hull) + 1e-6)
            if solidez < 0.80:
                continue

            candidatos.append((x, y, bw, bh, area, approx))

        if len(candidatos) < 4:
            logging.warning(f"⚠️ Fiducial v4: apenas {len(candidatos)} candidatos válidos")
            return None

        cx, cy = w / 2, h / 2

        def score_dist(c, canto):
            x, y, bw, bh, _, _ = c
            ccx = x + bw // 2
            ccy = y + bh // 2
            if canto == 'tl': return ccx + ccy
            if canto == 'tr': return (w - ccx) + ccy
            if canto == 'bl': return ccx + (h - ccy)
            if canto == 'br': return (w - ccx) + (h - ccy)
            return 0

        quadrantes = {'tl': [], 'tr': [], 'bl': [], 'br': []}
        for c in candidatos:
            x, y, bw, bh, _, _ = c
            ccx = x + bw // 2
            ccy = y + bh // 2
            if ccx < cx and ccy < cy:
                quadrantes['tl'].append(c)
            elif ccx >= cx and ccy < cy:
                quadrantes['tr'].append(c)
            elif ccx < cx and ccy >= cy:
                quadrantes['bl'].append(c)
            else:
                quadrantes['br'].append(c)

        melhor = {}
        for k in ['tl', 'tr', 'bl', 'br']:
            if not quadrantes[k]:
                logging.warning(f"⚠️ Fiducial v4: nenhum candidato no quadrante {k.upper()}")
                return None
            quadrantes[k].sort(key=lambda c: score_dist(c, k))
            melhor[k] = quadrantes[k][0]

        tl = (melhor['tl'][0] + melhor['tl'][2] // 2, melhor['tl'][1] + melhor['tl'][3] // 2)
        tr = (melhor['tr'][0] + melhor['tr'][2] // 2, melhor['tr'][1] + melhor['tr'][3] // 2)
        bl = (melhor['bl'][0] + melhor['bl'][2] // 2, melhor['bl'][1] + melhor['bl'][3] // 2)
        br = (melhor['br'][0] + melhor['br'][2] // 2, melhor['br'][1] + melhor['br'][3] // 2)

        logging.info(f"✅ Fiducial v4 OK: TL={tl} TR={tr} BL={bl} BR={br}")
        return {'tl': tl, 'tr': tr, 'bl': bl, 'br': br}

    except Exception as e:
        logging.error(f"❌ Fiducial v4 erro: {e}")
        traceback.print_exc()
        return None


def corrigir_perspectiva(img, marcadores):
    try:
        tl = marcadores['tl']
        tr = marcadores['tr']
        bl = marcadores['bl']
        br = marcadores['br']

        larg_topo = np.linalg.norm(np.array(tr) - np.array(tl))
        larg_base = np.linalg.norm(np.array(br) - np.array(bl))
        alt_esq = np.linalg.norm(np.array(bl) - np.array(tl))
        alt_dir = np.linalg.norm(np.array(br) - np.array(tr))

        larg_max = int(max(larg_topo, larg_base))
        alt_max = int(max(alt_esq, alt_dir))

        origem = np.float32([tl, tr, bl, br])
        destino = np.float32([
            [0, 0],
            [larg_max - 1, 0],
            [0, alt_max - 1],
            [larg_max - 1, alt_max - 1]
        ])

        M = cv2.getPerspectiveTransform(origem, destino)
        corrigida = cv2.warpPerspective(img, M, (larg_max, alt_max))

        logging.info(f"✅ Perspectiva corrigida: {larg_max}x{alt_max}")
        return corrigida

    except Exception as e:
        logging.error(f"❌ Perspectiva erro: {e}")
        return img


def gerar_mapa_template_padrao(total_questoes, alternativas, num_colunas):
    mapa = []

    A4_W, A4_H = 210.0, 297.0
    MARCADOR_SIZE = 10.0
    MARCADOR_MARGIN = 15.0

    IMG_ORIGIN_X = MARCADOR_MARGIN + MARCADOR_SIZE / 2
    IMG_ORIGIN_Y = MARCADOR_MARGIN + MARCADOR_SIZE / 2
    IMG_RANGE_X = A4_W - 2 * IMG_ORIGIN_X
    IMG_RANGE_Y = A4_H - 2 * IMG_ORIGIN_Y

    AREA_LEFT = MARCADOR_MARGIN + MARCADOR_SIZE + 2
    AREA_TOP = MARCADOR_MARGIN + MARCADOR_SIZE + 2
    AREA_RIGHT = A4_W - MARCADOR_MARGIN - 2
    AREA_BOTTOM = A4_H - MARCADOR_MARGIN - 2
    AREA_WIDTH = AREA_RIGHT - AREA_LEFT
    AREA_HEIGHT = AREA_BOTTOM - AREA_TOP

    HEADER_HEIGHT = 52.0
    QUESTOES_TOP = AREA_TOP + HEADER_HEIGHT
    QUESTOES_HEIGHT = AREA_BOTTOM - QUESTOES_TOP
    QUESTOES_PADDING = 5.0
    QUESTOES_INNER_TOP = QUESTOES_TOP + QUESTOES_PADDING
    QUESTOES_INNER_HEIGHT = QUESTOES_HEIGHT - 2 * QUESTOES_PADDING

    if total_questoes <= 12:
        num_colunas = 1
        q_por_coluna = total_questoes
    elif total_questoes <= 26:
        num_colunas = 2
        q_por_coluna = (total_questoes + 1) // 2
    else:
        num_colunas = 2
        q_por_coluna = 18

    num_alts = len(alternativas)
    GAP_COLUNA = 8.0
    col_width = (AREA_WIDTH - GAP_COLUNA * (num_colunas - 1)) / num_colunas

    NUM_WIDTH = 10.0
    NUM_GAP = 2.0
    ALT_LEFT_OFFSET = NUM_WIDTH + NUM_GAP + 2

    for col in range(num_colunas):
        inicio = col * q_por_coluna
        fim = min(inicio + q_por_coluna, total_questoes)
        n_col = fim - inicio
        if n_col <= 0:
            continue

        col_left = AREA_LEFT + col * (col_width + GAP_COLUNA)
        col_right = col_left + col_width
        alt_left = col_left + ALT_LEFT_OFFSET
        alt_right = col_right - 1
        alt_width = alt_right - alt_left
        espacamento_bolha = alt_width / num_alts
        espaco_linha = QUESTOES_INNER_HEIGHT / n_col

        for i in range(n_col):
            num_questao = inicio + i + 1
            y_centro = QUESTOES_INNER_TOP + (i + 0.5) * espaco_linha

            for j, letra in enumerate(alternativas):
                x_centro = alt_left + (j + 0.5) * espacamento_bolha
                x_norm = (x_centro - IMG_ORIGIN_X) / IMG_RANGE_X
                y_norm = (y_centro - IMG_ORIGIN_Y) / IMG_RANGE_Y

                mapa.append({
                    'questao': num_questao,
                    'alternativa': letra,
                    'x': round(x_norm, 5),
                    'y': round(y_norm, 5),
                    'x_mm': round(x_centro, 2),
                    'y_mm': round(y_centro, 2),
                })

    return mapa


def salvar_mapa_template(prova_id, aluno_id, tipo_questoes, quantidade_questoes, num_colunas, mapa_template):
    try:
        conn = get_db_connection()
        if not conn:
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


def corrigir_por_template_evalbee_v2(img_corrigida, mapa_template, alternativas, debug=False):
    """
    ⚠️ CORRIGIDO: detecta tipo de entrada (scanner/foto) e ajusta
    threshold, raio e limiares automaticamente.
    """
    try:
        h, w = img_corrigida.shape[:2]

        gray = cv2.cvtColor(img_corrigida, cv2.COLOR_BGR2GRAY)
        tipo = detectar_tipo_entrada(gray)
        logging.info(f"📷 Tipo de imagem detectada: {tipo.upper()} ({w}x{h})")

        if tipo == 'scanner':
            # Scanner: imagem limpa → Otsu é melhor que adaptive
            _, binaria = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            radius_factor = 0.016
            limiar_min = 0.40
            limiar_confirma = 0.55
            relative_multi = 0.70
        else:
            # Foto: sombras → adaptive é melhor
            binaria = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                25, 12
            )
            radius_factor = 0.018
            limiar_min = 0.30
            limiar_confirma = 0.45
            relative_multi = 0.60

        por_questao = defaultdict(list)
        for b in mapa_template:
            por_questao[b['questao']].append(b)

        respostas = []
        confiancas = []
        debug_ratios = {}

        for q_num in sorted(por_questao.keys()):
            bolhas_q = sorted(por_questao[q_num], key=lambda b: b['x'])
            ratios = []

            for b in bolhas_q:
                cx = int(b['x'] * w)
                cy = int(b['y'] * h)
                r = max(6, int(min(w, h) * radius_factor))

                if cx - r < 0 or cy - r < 0 or cx + r >= w or cy + r >= h:
                    ratios.append(0.0)
                    continue

                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.circle(mask, (cx, cy), r, 255, -1)
                total = cv2.countNonZero(mask)
                if total == 0:
                    ratios.append(0.0)
                    continue

                preto = cv2.countNonZero(cv2.bitwise_and(binaria, binaria, mask=mask))
                ratio = preto / total
                ratios.append(ratio)

            debug_ratios[q_num] = [round(r, 3) for r in ratios]

            if not ratios:
                respostas.append('')
                confiancas.append(0)
                continue

            max_ratio = max(ratios)
            if max_ratio < limiar_min:
                respostas.append('')
                confiancas.append(15)
                continue

            limiar_relativo = max_ratio * relative_multi
            marcadas_idx = [
                i for i, r in enumerate(ratios)
                if r >= limiar_min and r >= limiar_relativo
            ]

            if len(marcadas_idx) >= 2:
                letras = [bolhas_q[i]['alternativa'] for i in marcadas_idx]
                logging.info(f"⚠️ Q{q_num}: MÚLTIPLA ({tipo}): {letras} "
                             f"ratios={['%.2f' % ratios[i] for i in marcadas_idx]}")
                respostas.append('MULTIPLA')
                confiancas.append(90)
                continue

            idx_max = marcadas_idx[0] if marcadas_idx else int(np.argmax(ratios))
            letra = bolhas_q[idx_max]['alternativa']
            respostas.append(letra)

            sorted_r = sorted(ratios, reverse=True)
            separacao = (sorted_r[0] - sorted_r[1]) if len(sorted_r) > 1 else 1.0

            if max_ratio > limiar_confirma and separacao > 0.25:
                conf = 96
            elif max_ratio > 0.35 and separacao > 0.15:
                conf = 82
            elif separacao > 0.08:
                conf = 68
            else:
                conf = 50
            confiancas.append(conf)

        # Log resumido dos ratios (útil para debugar)
        if debug or logging.getLogger().level <= logging.INFO:
            resumo = ' | '.join(
                f"Q{n}:{debug_ratios[n]}" for n in list(debug_ratios.keys())[:10]
            )
            logging.info(f"📊 Ratios ({tipo}) — primeiras 10: {resumo}")

        return respostas, confiancas

    except Exception as e:
        logging.error(f"❌ EvalBee v2 erro: {e}")
        traceback.print_exc()
        return [], []


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

        np_arr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return None, False

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        tipo = detectar_tipo_entrada(gray)

        marcadores = detectar_marcadores_fiduciais_v4(gray)
        if not marcadores:
            logging.warning("⚠️ Template Mapping: marcadores não detectados")
            return None, False

        img_corr = corrigir_perspectiva(img, marcadores)

        h, w = img_corr.shape[:2]
        # ⚡ Scans preservam mais resolução (bordas finas das bolhas)
        TARGET_H = 2400 if tipo == 'scanner' else 1800
        if h > TARGET_H:
            scale = TARGET_H / h
            img_corr = cv2.resize(img_corr, (int(w * scale), TARGET_H),
                                  interpolation=cv2.INTER_AREA)

        logging.info(f"✅ Template: {tipo} {img_corr.shape[1]}x{img_corr.shape[0]} "
                     f"(TARGET_H={TARGET_H})")
        return img_corr, True

    except Exception as e:
        logging.error(f"❌ Prepara imagem: {e}")
        return None, False


def corrigir_com_template_mapping(imagem_base64, padrao_gabarito, aluno_nome, serie,
                                   tipo_questoes=4, disciplina='', bncc=None,
                                   mapa_template=None, prova_id=None, aluno_id=None):
    total_questoes = padrao_gabarito['total_questoes']
    alternativas = padrao_gabarito['alternativas']

    if not mapa_template and prova_id and aluno_id:
        mapa_template = carregar_mapa_template(prova_id, aluno_id)

    if not mapa_template:
        num_colunas = 1 if total_questoes <= 12 else 2
        mapa_template = gerar_mapa_template_padrao(total_questoes, alternativas, num_colunas)

    img_corr, ok = preparar_imagem_para_template(imagem_base64)
    if not ok:
        return None

    respostas, confiancas = corrigir_por_template_evalbee_v2(
        img_corr, mapa_template, alternativas
    )

    if not respostas:
        return None

    return {
        'respostas': respostas,
        'confiancas': confiancas if confiancas else [70] * len(respostas),
        'metodo': 'evalbee_v4'
    }


def extrair_dados_qrcode(imagem_base64):
    try:
        from pyzbar.pyzbar import decode
    except ImportError:
        logging.warning("⚠️ pyzbar não disponível. Instale com: pip install pyzbar")
        return None

    try:
        if ',' in imagem_base64 and imagem_base64.strip().startswith('data:'):
            imagem_base64 = imagem_base64.split(',', 1)[1]
        imagem_base64 = imagem_base64.strip().replace('\n', '').replace('\r', '').replace(' ', '')

        image_data = base64.b64decode(imagem_base64, validate=False)
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if img is None:
            logging.warning("⚠️ QR: imagem inválida")
            return None

        logging.info(f"📷 QR: procurando em imagem {img.shape[1]}x{img.shape[0]}...")

        codigos = decode(img)

        if not codigos:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            gray_enhanced = clahe.apply(gray)
            codigos = decode(gray_enhanced)

        if not codigos:
            logging.warning("⚠️ QR: nenhum código encontrado")
            return None

        for codigo in codigos:
            dados = codigo.data.decode('utf-8')
            logging.info(f"📷 QR detectado: {dados}")

            if not dados.startswith('ALUNO:'):
                continue

            resultado = {}
            for parte in dados.split('|'):
                if ':' in parte:
                    chave, valor = parte.split(':', 1)
                    chave = chave.strip().upper()
                    valor = valor.strip()
                    if valor.isdigit():
                        if chave == 'ALUNO':
                            resultado['aluno_id'] = int(valor)
                        elif chave == 'PROVA':
                            resultado['prova_id'] = int(valor)
                        elif chave == 'ESCOLA':
                            resultado['escola_id'] = int(valor)
                        elif chave == 'TURMA':
                            resultado['turma_id'] = int(valor)

            if 'aluno_id' in resultado and 'prova_id' in resultado:
                logging.info(f"✅ QR: dados extraídos: {resultado}")
                return resultado

        return None

    except Exception as e:
        logging.error(f"❌ Erro ao ler QR Code: {e}")
        traceback.print_exc()
        return None
