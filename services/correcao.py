# ============================================================
# SERVICES/CORRECAO.PY — Orquestrador EvalBee + IA fallback
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
                return corrigir_com_ia_fallback(
                    imagem_base64, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc
                )
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

        logging.info(f"📊 EvalBee: média={conf_media:.1f}% "
                     f"detectadas={detectadas}/{total_questoes} respostas={respostas}")

        if detectadas < total_questoes * 0.15:
            logging.warning(f"⚠️ Só {detectadas}/{total_questoes}. Tentando IA...")
            if OPENAI_AVAILABLE and openai_client is not None:
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_base64, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc
                )
                if not resultado_ia.get('erro'):
                    resultado_ia['modo'] = 'ia_fallback'
                    return resultado_ia
            return erro_correcao(
                aluno_nome, serie, disciplina,
                f'Detectou só {detectadas}/{total_questoes}. '
                'Tire foto mais clara, com os 4 marcadores visíveis.'
            )

        nao_vazias = [r for r in respostas if r]
        if len(nao_vazias) >= 3 and len(set(nao_vazias)) == 1:
            logging.warning(f"⚠️ Todas respostas = '{nao_vazias[0]}'. Tentando IA...")
            if OPENAI_AVAILABLE and openai_client is not None:
                resultado_ia = corrigir_com_ia_fallback(
                    imagem_base64, padrao_gabarito, aluno_nome,
                    serie, tipo_questoes, disciplina, bncc
                )
                if not resultado_ia.get('erro'):
                    resultado_ia['modo'] = 'ia_fallback'
                    return resultado_ia
            return erro_correcao(
                aluno_nome, serie, disciplina,
                f'Todas as respostas "{nao_vazias[0]}" — impossível. '
                'Foto com reflexo?'
            )

        return calcular_resultado_correcao(
            respostas, gabarito, aluno_nome, serie,
            disciplina, tipo_questoes, 'template_evalbee_v4',
            bncc=bncc, confiancas=confiancas
        )

    except Exception as e:
        logging.error(f"❌ Erro na correção: {e}")
        traceback.print_exc()
        if OPENAI_AVAILABLE and openai_client is not None:
            logging.warning("⚠️ Exceção no template. Tentando IA...")
            return corrigir_com_ia_fallback(
                imagem_base64, padrao_gabarito, aluno_nome,
                serie, tipo_questoes, disciplina, bncc
            )
        return erro_correcao(aluno_nome, serie, disciplina, str(e))