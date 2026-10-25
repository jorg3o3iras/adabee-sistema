# ============================================================
# SERVICES/CORRECAO.PY — Orquestrador EvalBee + IA fallback
# ⚠️ CORRIGIDO:
#    - MULTIPLA MARCAÇÃO = errada
#    - EM BRANCO = errada (não é "suspeita")
#    - requer_revisao_manual só conta questões RESPONDIDAS com baixa conf.
# ============================================================

import logging
import traceback

from services.evalbee import (
    carregar_mapa_template,
    corrigir_com_template_mapping,
    gerar_mapa_template_padrao,
)
from services.ia_fallback import (
    OPENAI_AVAILABLE,
    corrigir_com_ia_fallback,
    openai_client,
)
from core.utils import calcular_resultado_correcao, erro_correcao


def _questao_respondida(q):
    """Compatível com questoes_status que tenha 'respondida' OU só 'resposta'."""
    if 'respondida' in q:
        return bool(q['respondida'])
    resp = q.get('resposta', '')
    return bool(resp and resp not in ('—', '-', ''))


def _pos_processar_resultado(resultado):
    """
    Pós-processa o dict retornado por calcular_resultado_correcao:

    1) MÚLTIPLA → marcada como errada, motivo explícito na UI
    2) EM BRANCO → NÃO é "suspeita"; não dispara revisão manual
    3) Recalcula confiança média ignorando questões em branco
    4) Limpa questoes_suspeitas (remove em branco e múltiplas)
    5) requer_revisao_manual só se ≥3 respondidas com confiança <70 E ≥30% delas
    """
    if not isinstance(resultado, dict):
        return resultado

    questoes_status = resultado.get('questoes_status', []) or []

    # ── (1) MÚLTIPLA
    for q in questoes_status:
        if q.get('resposta') == 'MULTIPLA':
            q['multipla'] = True
            q['acertou'] = False
            q['respondida'] = True
            q['status'] = '⚠️ MÚLTIPLA MARCAÇÃO'
            q['status_texto'] = '⚠️ MÚLTIPLA MARCAÇÃO: mais de uma bolha preenchida'

    # ── (2)/(3)/(4) separar respondidas × em branco
    respondidas = [q for q in questoes_status if _questao_respondida(q)]
    respondidas_baixa = [
        q for q in respondidas
        if not q.get('multipla') and q.get('confianca', 100) < 70
    ]

    # Confiança média = só questões efetivamente respondidas
    if respondidas:
        confs = [q.get('confianca', 70) for q in respondidas]
        resultado['confianca'] = round(sum(confs) / len(confs))
    else:
        # Ninguém respondeu nada: 100% de certeza que está tudo em branco
        resultado['confianca'] = 100

    # requer_revisao_manual só olha questões RESPONDIDAS com baixa confiança
    total_resp = len(respondidas)
    total_baixa = len(respondidas_baixa)
    resultado['requer_revisao_manual'] = (
        total_baixa >= 3 and total_resp > 0 and total_baixa >= total_resp * 0.3
    )

    # Limpa questoes_suspeitas
    suspeitas_orig = resultado.get('questoes_suspeitas') or []
    suspeitas_novas = []
    for num in suspeitas_orig:
        idx = num - 1
        if 0 <= idx < len(questoes_status):
            q = questoes_status[idx]
            if _questao_respondida(q) and not q.get('multipla') and q.get('confianca', 100) < 70:
                suspeitas_novas.append(num)
    resultado['questoes_suspeitas'] = suspeitas_novas

    return resultado


def corrigir_com_gemini_com_padrao(imagem_base64, padrao_gabarito, aluno_nome, serie,
                                     tipo_questoes=4, disciplina='', bncc=None,
                                     mapa_template=None, prova_id=None, aluno_id=None):
    """
    Correção usando EvalBee v4 (template + fill ratio) como método PRINCIPAL,
    com fallback para IA quando necessário.
    """
    gabarito = padrao_gabarito['gabarito_oficial']
    if not gabarito or len(gabarito) == 0:
        return erro_correcao(aluno_nome, serie, disciplina, 'Gabarito não disponível')

    total_questoes = len(gabarito)

    logging.info("=" * 60)
    logging.info(f"📌 CORREÇÃO EVALBEE v4 - {total_questoes}Q "
                 f"({','.join(padrao_gabarito['alternativas'])})")
    logging.info("=" * 60)

    try:
        if not mapa_template and prova_id and aluno_id:
            mapa_template = carregar_mapa_template(prova_id, aluno_id)
            if mapa_template:
                logging.info(f"✅ Mapa carregado do banco: {len(mapa_template)} bolhas")

        if not mapa_template:
            num_colunas = 1 if total_questoes <= 12 else 2
            mapa_template = gerar_mapa_template_padrao(
                total_questoes, padrao_gabarito['alternativas'], num_colunas
            )
            logging.info(f"⚠️ Usando mapa PADRÃO gerado: {len(mapa_template)} bolhas")

        resultado_template = corrigir_com_template_mapping(
            imagem_base64, padrao_gabarito, aluno_nome, serie,
            tipo_questoes, disciplina, bncc, mapa_template,
            prova_id=prova_id, aluno_id=aluno_id
        )

        if not resultado_template:
            logging.warning("⚠️ EvalBee falhou. Tentando IA como fallback...")
            if OPENAI_AVAILABLE and openai_client is not None:
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_base64, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc
                )
                return _pos_processar_resultado(resultado_ia)
            return erro_correcao(
                aluno_nome, serie, disciplina,
                '❌ Não foi possível ler as respostas do cartão.\n\n'
                'Tire uma nova foto com:\n'
                '1. Boa iluminação (luz natural, sem sombra)\n'
                '2. Os 4 marcadores pretos visíveis nos cantos\n'
                '3. Foco nítido (segure firme)\n'
                '4. Sem reflexo de flash'
            )

        respostas = resultado_template['respostas']
        confiancas = resultado_template['confiancas']

        conf_media = sum(confiancas) / len(confiancas) if confiancas else 0
        detectadas = sum(1 for r in respostas if r)
        multiplas_detectadas = sum(1 for r in respostas if r == 'MULTIPLA')

        logging.info(f"📊 EvalBee: média={conf_media:.1f}% "
                     f"detectadas={detectadas}/{total_questoes} "
                     f"múltiplas={multiplas_detectadas} respostas={respostas}")

        # Se quase nada foi detectado (nem branco nem marcação), tenta IA
        if detectadas < total_questoes * 0.15:
            logging.warning(f"⚠️ Só {detectadas}/{total_questoes}. Tentando IA...")
            if OPENAI_AVAILABLE and openai_client is not None:
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_base64, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc
                )
                if not resultado_ia.get('erro'):
                    resultado_ia['modo'] = 'ia_fallback'
                    return _pos_processar_resultado(resultado_ia)
            return erro_correcao(
                aluno_nome, serie, disciplina,
                f'Detectou só {detectadas}/{total_questoes}. '
                'Tire foto mais clara, com os 4 marcadores visíveis.'
            )

        # Só considera "suspeito" se TODAS forem a MESMA letra válida
        # ('MULTIPLA' repetido e '' repetido NÃO são suspeitos)
        nao_vazias = [r for r in respostas if r and r != 'MULTIPLA']
        letras_validas = set(padrao_gabarito['alternativas'])
        todas_sao_mesma_letra = (
            len(nao_vazias) >= 3
            and len(set(nao_vazias)) == 1
            and nao_vazias[0] in letras_validas
        )
        if todas_sao_mesma_letra:
            logging.warning(f"⚠️ Todas respostas = '{nao_vazias[0]}'. Tentando IA...")
            if OPENAI_AVAILABLE and openai_client is not None:
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_base64, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc
                )
                if not resultado_ia.get('erro'):
                    resultado_ia['modo'] = 'ia_fallback'
                    return _pos_processar_resultado(resultado_ia)
            return erro_correcao(
                aluno_nome, serie, disciplina,
                f'Todas as respostas "{nao_vazias[0]}" — impossível. '
                'Foto com reflexo?'
            )

        resultado = calcular_resultado_correcao(
            respostas, gabarito, aluno_nome, serie,
            disciplina, tipo_questoes, 'template_evalbee_v4',
            bncc=bncc, confiancas=confiancas
        )
        return _pos_processar_resultado(resultado)

    except Exception as e:
        logging.error(f"❌ Erro na correção: {e}")
        traceback.print_exc()
        if OPENAI_AVAILABLE and openai_client is not None:
            logging.warning("⚠️ Exceção no template. Tentando IA...")
            resultado_ia = corrigir_com_ia_fallback(
                imagem_base64, padrao_gabarito, aluno_nome,
                serie, tipo_questoes, disciplina, bncc
            )
            return _pos_processar_resultado(resultado_ia)
        return erro_correcao(aluno_nome, serie, disciplina, str(e))
