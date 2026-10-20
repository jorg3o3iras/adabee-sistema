# ============================================================
# ROUTES/REDACAO.PY — Correção de redação + OCR + salvar
# com validação de escola
# ============================================================

import json
import logging
import traceback

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from core.db import get_db_connection
from core.utils import identificar_disciplina, get_escola_id
from services.redacao import corrigir_redacao_por_texto, extrair_texto_por_imagem


bp = Blueprint('redacao', __name__, url_prefix='/api')


# ═══════════════════════════════════════════════════════════════
# 🔒 HELPERS DE ESCOPO
# ═══════════════════════════════════════════════════════════════
def _aluno_pertence_escola_sessao(cur, aluno_id, escola_sessao):
    """
    Verifica se o aluno existe e (se não-admin) se pertence à escola.
    Retorna (ok, aluno_row|None, erro_msg|None, http_status).
    """
    cur.execute("SELECT id, escola_id FROM alunos WHERE id = %s", (aluno_id,))
    row = cur.fetchone()
    if not row:
        return False, None, 'Aluno não encontrado', 404
    if escola_sessao is not None and row.get('escola_id') != escola_sessao:
        return False, None, 'Acesso negado a este aluno', 403
    return True, row, None, 200


# ═══════════════════════════════════════════════════════════════
# 🧠 CORREÇÃO DE REDAÇÃO (texto puro — não toca em dados)
# ═══════════════════════════════════════════════════════════════
@bp.route('/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        data = request.json or {}
        texto = data.get('texto')
        aluno_id = data.get('aluno_id')  # não usado, mas mantido por compatibilidade

        if not texto:
            return jsonify({'erro': 'Texto é obrigatório'}), 400

        resultado = corrigir_redacao_por_texto(texto)
        return jsonify(resultado)

    except Exception as e:
        print(f"❌ Erro na correção de redação: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 📷 OCR — EXTRAIR TEXTO DE FOTO (não toca em dados)
# ═══════════════════════════════════════════════════════════════
@bp.route('/extrair_texto_redacao', methods=['POST'])
def extrair_texto_redacao():
    """Extrai o texto de uma foto de redação usando OpenAI Vision."""
    try:
        data = request.json or {}
        imagem_base64 = data.get('imagem')
        if not imagem_base64:
            return jsonify({'erro': 'Imagem é obrigatória'}), 400

        resultado = extrair_texto_por_imagem(imagem_base64)

        if resultado.get('erro'):
            status = 503 if 'não disponível' in resultado['erro'] else 400
            return jsonify(resultado), status

        return jsonify(resultado)

    except Exception as e:
        logging.error(f"❌ Erro ao extrair texto: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 💾 SALVAR CORREÇÃO DE TEXTO (+ integração com histórico)
# ═══════════════════════════════════════════════════════════════
@bp.route('/salvar_correcao_texto', methods=['POST'])
def salvar_correcao_texto():
    try:
        data = request.json or {}
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

        # 🔒 Escola da sessão (None = admin)
        escola_sessao = get_escola_id()

        cur = conn.cursor(cursor_factory=RealDictCursor)

        ok, aluno_row, err, status = _aluno_pertence_escola_sessao(
            cur, aluno_id, escola_sessao
        )
        if not ok:
            cur.close()
            conn.close()
            return jsonify({'erro': err}), status

        # Volta para cursor padrão (tuplas) — o resto do código original usa `cur.fetchone()[0]`
        cur = conn.cursor()

        # 1) Insert da correção de texto
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
        id_correcao_texto = result[0] if result else None

        # 2) Integração com histórico (quando prova_id e nota existem)
        if prova_id and nota is not None:
            try:
                cur.execute("SELECT disciplina, titulo, serie FROM provas WHERE id = %s", (prova_id,))
                prova_row = cur.fetchone()

                cur.execute("""
                    SELECT t.serie FROM alunos a
                    LEFT JOIN turmas t ON a.turma_id = t.id
                    WHERE a.id = %s
                """, (aluno_id,))
                serie_row = cur.fetchone()

                disciplina_hist = (prova_row[0] if prova_row else None) or 'Redação'
                prova_titulo_hist = (prova_row[1] if prova_row else '') or ''
                serie_hist = (serie_row[0] if serie_row else None) or (prova_row[2] if prova_row else '') or '1º Ano'

                tipo_avaliacao = identificar_disciplina(prova_titulo_hist, disciplina_hist, serie_hist)

                nota_float = float(nota or 0)
                acertos_equiv = int(round(nota_float))
                total_equiv = 10

                questoes_status_hist = [{
                    'numero': 1,
                    'resposta': f'{nota_float}',
                    'gabarito': '10.0',
                    'acertou': nota_float >= 6,
                    'respondida': True,
                    'bncc': '',
                    'status': f'📝 Redação — Nota {nota_float}',
                    'status_texto': f'📝 Redação — Nota {nota_float}',
                    'confianca': 100,
                    'correta': nota_float >= 6
                }]

                respostas_hist = [f'{nota_float}']

                cur.execute(
                    "SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s",
                    (prova_id, aluno_id)
                )
                existe = cur.fetchone()

                if existe:
                    cur.execute("""
                        UPDATE historico
                        SET respostas = %s::text[], acertos = %s, nota = %s, total = %s,
                            tipo_correcao = 'ia_redacao', disciplina = %s, tipo_avaliacao = %s,
                            questoes_status = %s::jsonb, confianca = 100,
                            confianca_por_questao = %s::jsonb,
                            data_correcao = CURRENT_TIMESTAMP
                        WHERE prova_id = %s AND aluno_id = %s
                    """, (respostas_hist, acertos_equiv, nota_float, total_equiv,
                          disciplina_hist, tipo_avaliacao,
                          json.dumps(questoes_status_hist), json.dumps([100]),
                          prova_id, aluno_id))
                else:
                    cur.execute("""
                        INSERT INTO historico
                        (prova_id, aluno_id, respostas, acertos, nota, total,
                         tipo_correcao, disciplina, tipo_avaliacao, questoes_status,
                         confianca, confianca_por_questao, bncc)
                        VALUES (%s, %s, %s::text[], %s, %s, %s, 'ia_redacao', %s, %s, %s::jsonb,
                                100, %s::jsonb, %s::text[])
                    """, (prova_id, aluno_id, respostas_hist, acertos_equiv, nota_float,
                          total_equiv, disciplina_hist, tipo_avaliacao,
                          json.dumps(questoes_status_hist), json.dumps([100]), []))

                logging.info(f"✅ Redação integrada ao histórico: aluno={aluno_id}, prova={prova_id}, nota={nota_float}")

            except Exception as e_int:
                logging.warning(f"⚠️ Falha ao integrar redação ao histórico: {e_int}")

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'sucesso': True,
            'id': id_correcao_texto,
            'mensagem': 'Correção de texto salva e integrada ao histórico'
        })

    except Exception as e:
        print(f"❌ Erro ao salvar correção de texto: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 📋 LISTAR CORREÇÕES DE TEXTO (com filtro por escola)
# ═══════════════════════════════════════════════════════════════
@bp.route('/correcoes_texto', methods=['GET'])
def listar_correcoes_texto():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        escola_sessao = get_escola_id()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if escola_sessao is None:
            cur.execute("""
                SELECT ct.*, a.nome as aluno_nome, t.serie
                FROM correcoes_texto ct
                LEFT JOIN alunos a ON ct.aluno_id = a.id
                LEFT JOIN turmas t ON a.turma_id = t.id
                ORDER BY ct.data_correcao DESC
            """)
        else:
            cur.execute("""
                SELECT ct.*, a.nome as aluno_nome, t.serie
                FROM correcoes_texto ct
                LEFT JOIN alunos a ON ct.aluno_id = a.id
                LEFT JOIN turmas t ON a.turma_id = t.id
                WHERE a.escola_id = %s
                ORDER BY ct.data_correcao DESC
            """, (escola_sessao,))

        resultados = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify(resultados)

    except Exception as e:
        print(f"❌ Erro ao listar correções de texto: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
