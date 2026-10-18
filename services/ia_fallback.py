# ============================================================
# SERVICES/IA_FALLBACK.PY — Fallback de correção por IA
# ============================================================

import base64
import io
import json
import logging
import re
import traceback
import time

import cv2
import numpy as np

from config import OPENAI_MODEL, OPENAI_API_KEY
from core.utils import (
    calcular_resultado_correcao,
    erro_correcao,
    extrair_mimetype,
)


# ═══ OPENAI SETUP ═══
OPENAI_AVAILABLE = False
openai_client = None

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
    """Valida se a resposta da IA é plausível (não chute)."""
    from collections import Counter

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
        acertos = 0
        total_validas = 0
        for r, g in zip(respostas, gabarito):
            if r and g:
                total_validas += 1
                if str(r).upper() == str(g).upper():
                    acertos += 1
        if total_validas > 0:
            taxa = acertos / total_validas
            if taxa < 0.15 and total_validas >= 5:
                return True, f"IA acertou apenas {acertos}/{total_validas} ({taxa*100:.0f}%) — improvável"

    return False, ""


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