# ============================================================
# SERVICES/REDACAO.PY — Correção de redação + extração OCR
# ============================================================

import json
import logging
import re
import traceback
from collections import Counter

from config import OPENAI_MODEL, RELAY_MODEL, RELAY_AVAILABLE
from core.utils import extrair_mimetype
from services.ia_fallback import OPENAI_AVAILABLE, openai_client


def corrigir_redacao_por_texto(texto):
    """
    Retorna dict com nota, metricas e feedback.
    Tenta OpenAI → Relay → fallback local.
    """

    if OPENAI_AVAILABLE and openai_client is not None:
        try:
            prompt = f"""
            Avalie a redação abaixo e retorne APENAS um JSON válido:
            
            Redação: {texto}
            
            Formato exigido:
            {{"nota": 7.5, "metricas": {{"nota_coerencia": 8, "nota_estrutura": 7.5, "nota_gramatica": 7, "nota_vocabulario": 7.5}}, "feedback": "texto..."}}
            """

            create_kwargs = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "Você é um professor especialista em avaliar redações. Responda SEMPRE em JSON."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 800,
                "temperature": 0.5,
            }
            if OPENAI_MODEL.startswith('gpt-4o') or 'turbo' in OPENAI_MODEL:
                create_kwargs["response_format"] = {"type": "json_object"}

            response = openai_client.chat.completions.create(**create_kwargs)

            resposta_texto = response.choices[0].message.content
            json_match = re.search(r'\{[\s\S]*\}', resposta_texto)
            if json_match:
                resultado = json.loads(json_match.group())
                resultado['modo'] = 'openai'
                return resultado
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
                    return resultado
                except Exception:
                    pass
        except Exception as e:
            print(f"⚠️ Erro no RelayFreeLLM para redação: {e}")

    # ═══ FALLBACK LOCAL (heurístico) ═══
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

    return {
        'nota': nota_final,
        'metricas': {
            'nota_coerencia': round(nota_coerencia, 1),
            'nota_estrutura': round(nota_estrutura, 1),
            'nota_gramatica': round(nota_gramatica, 1),
            'nota_vocabulario': round(nota_vocabulario, 1)
        },
        'feedback': " ".join(feedback_parts),
        'modo': 'local'
    }


def extrair_texto_por_imagem(imagem_base64):
    """
    Extrai texto de uma foto de redação usando OpenAI Vision.
    Retorna dict {sucesso, texto, caracteres} ou {erro}.
    """
    if not OPENAI_AVAILABLE or openai_client is None:
        return {'erro': 'IA OpenAI não disponível'}

    try:
        if isinstance(imagem_base64, tuple):
            imagem_base64 = imagem_base64[0]
        if ',' in imagem_base64 and imagem_base64.strip().startswith('data:'):
            mimetype = extrair_mimetype(imagem_base64)
            imagem_limpa = imagem_base64.split(',', 1)[1]
        else:
            imagem_limpa = imagem_base64
            mimetype = 'image/jpeg'

        data_url = f"data:{mimetype};base64,{imagem_limpa}"

        prompt = (
            "Você é um sistema OCR profissional. Extraia TODO o texto manuscrito "
            "ou impresso desta redação. Retorne APENAS o texto puro, sem comentários, "
            "sem markdown, sem explicações. Preserve quebras de linha e parágrafos. "
            "Se houver palavras ilegíveis, escreva [ilegível]."
        )

        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um sistema OCR. Retorne apenas o texto extraído, sem formatação extra."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}
                    ]
                }
            ],
            max_tokens=4000,
            temperature=0.0,
        )

        texto_extraido = (response.choices[0].message.content or "").strip()

        if not texto_extraido:
            return {'erro': 'Não foi possível ler texto na imagem'}

        return {
            'sucesso': True,
            'texto': texto_extraido,
            'caracteres': len(texto_extraido)
        }

    except Exception as e:
        logging.error(f"❌ Erro ao extrair texto: {e}")
        traceback.print_exc()
        return {'erro': str(e)}