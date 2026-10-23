# ============================================================
# ROUTES/CORRECAO.PY — Correção IA, lote, manual, produção, QR
# Provas GLOBAIS — valida apenas a escola do ALUNO
# ============================================================

import hashlib
import json
import logging
import traceback

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from config import OPENAI_MODEL
from core.cache import get_cache_correcao, get_cache_key, set_cache_correcao
from core.db import get_db_connection
from core.utils import (
    calcular_conceito, extrair_mimetype, gerar_padrao_gabarito,
    identificar_disciplina, validar_gabarito, get_escola_id,
)
from services.correcao import corrigir_com_gemini_com_padrao


bp = Blueprint('correcao', __name__, url_prefix='/api')


def _validar_aluno_prova_escola(cur, aluno_id, prova_id, escola_sessao):
    """
    Valida aluno + prova.
    - Aluno: usuário comum precisa pertencer à mesma escola.
    - Prova: GLOBAL — não filtra por escola (todos veem todas as provas).
    Retorna (ok, dados|None, erro_msg|None, status_code).
    """
    cur.execute("""
        SELECT p.*,
               a.nome AS aluno_nome,
               a.turma_id,
               a.escola_id AS aluno_escola_id,
               t.serie AS turma_serie,
               t.nome  AS turma_nome,              -- ✅ CORRIGIDO: adicionado aqui
               e.nome AS escola_nome
        FROM provas p
        LEFT JOIN alunos a ON a.id = %s
        LEFT JOIN turmas t ON a.turma_id = t.id
        LEFT JOIN escolas e ON a.escola_id = e.id
        WHERE p.id = %s
    """, (aluno_id, prova_id))
    dados = cur.fetchone()
    if not dados:
        return False, None, 'Prova não encontrada', 404
    # ⚠️ Só valida a escola DO ALUNO (prova é global)
    if escola_sessao is not None and dados.get('aluno_escola_id') != escola_sessao:
        return False, None, 'Acesso negado a este aluno', 403
    return True, dados, None, 200


@bp.route('/corrigir', methods=['POST'])
def corrigir_com_ia():
    try:
        data = request.json
        if not data:
            return jsonify({'erro': 'Nenhum dado recebido'}), 400
        imagem_base64 = data.get('imagem')
        prova_id = data.get('prova_id')
        aluno_id = data.get('aluno_id')
        if not imagem_base64: return jsonify({'erro': 'Imagem é obrigatória'}), 400
        if not prova_id: return jsonify({'erro': 'Prova ID é obrigatório'}), 400
        if not aluno_id: return jsonify({'erro': 'Aluno ID é obrigatório'}), 400

        imagem_hash = hashlib.md5(imagem_base64.encode()).hexdigest()
        cache_key = get_cache_key(imagem_hash, prova_id, aluno_id)
        cached = get_cache_correcao(cache_key)
        if cached:
            return jsonify(cached)

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        try:
            escola_sessao = get_escola_id()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            ok, dados, err, status = _validar_aluno_prova_escola(
                cur, aluno_id, prova_id, escola_sessao
            )
            if not ok:
                cur.close(); conn.close()
                return jsonify({'erro': err}), status

            prova = dados
            gabarito = prova.get('gabarito', [])
            if not gabarito or len(gabarito) == 0:
                cur.close(); conn.close()
                return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400

            tipo_questoes = prova.get('tipo_questoes') or 4
            if isinstance(tipo_questoes, str):
                try: tipo_questoes = int(tipo_questoes)
                except Exception: tipo_questoes = 4

            if not validar_gabarito(gabarito, tipo_questoes):
                cur.close(); conn.close()
                return jsonify({'erro': 'Gabarito inválido para este tipo de prova.'}), 400

            padrao_gabarito = gerar_padrao_gabarito(gabarito, tipo_questoes)
            aluno = dados
            nome_aluno = aluno.get('aluno_nome') or 'Aluno'
            serie = aluno.get('turma_serie') or prova.get('serie') or '1º Ano'
            bncc_gabarito = prova.get('bncc', [])
            cur.close(); conn.close()

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
                        q['bncc'] = bncc_gabarito[i] if i < len(bncc_gabarito) and bncc_gabarito[i] else ''
                    questoes_status_json = json.dumps(questoes_status)
                    respostas_detectadas = resultado.get('respostas_detectadas', [])

                    cur.execute("SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s", (prova_id, aluno_id))
                    existe = cur.fetchone()
                    if existe:
                        cur.execute("""
                            UPDATE historico SET respostas = %s::text[], acertos = %s, nota = %s, total = %s,
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
                              json.dumps(resultado.get('confianca_por_questao', [])), bncc_gabarito))
                    conn.commit(); cur.close(); conn.close()
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


@bp.route('/corrigir_manual', methods=['POST'])
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
        if not conn: return jsonify({'erro': 'Erro no banco'}), 500
        escola_sessao = get_escola_id()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        ok, dados, err, status = _validar_aluno_prova_escola(
            cur, aluno_id, prova_id, escola_sessao
        )
        if not ok:
            cur.close(); conn.close()
            return jsonify({'erro': err}), status

        disciplina = dados.get('disciplina') or ''
        prova_titulo = dados.get('titulo') or ''
        serie_prova = dados.get('serie') or ''
        gabarito = dados.get('gabarito') or []
        bncc_gabarito = dados.get('bncc') or []

        if (disciplina or '').strip() == 'Produção de Texto':
            cur.close(); conn.close()
            return jsonify({
                'erro': 'Esta prova é de Produção de Texto. Use o botão "SALVAR NOTA" (Nota Manual).',
                'tipo': 'producao'
            }), 400

        serie = dados.get('turma_serie') or serie_prova or '1º Ano'
        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)

        questoes_status = []
        for i in range(total):
            resp = str(respostas[i]) if i < len(respostas) and respostas[i] is not None else ''
            gab = str(gabarito[i]) if i < len(gabarito) and gabarito[i] is not None else ''
            is_correto = bool(resp and gab and resp.upper() == gab.upper())
            codigo_bncc = bncc_gabarito[i] if i < len(bncc_gabarito) and bncc_gabarito[i] else ''
            status_msg = ('ADQUIRIU HABILIDADE' if is_correto
                          else ('RECOMPOSIÇÃO DE APRENDIZAGEM' if resp else 'NÃO RESPONDEU'))
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
                UPDATE historico SET respostas = %s::text[], acertos = %s, nota = %s, total = %s,
                    tipo_correcao = 'manual', disciplina = %s, tipo_avaliacao = %s,
                    questoes_status = %s::jsonb, data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas, acertos, nota, total, disciplina, tipo_avaliacao,
                  questoes_status_json, prova_id, aluno_id))
            result_id = existe['id']
        else:
            cur.execute("""
                INSERT INTO historico
                (prova_id, aluno_id, respostas, acertos, nota, total,
                 tipo_correcao, disciplina, tipo_avaliacao, questoes_status)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual', %s, %s, %s::jsonb)
                RETURNING id
            """, (prova_id, aluno_id, respostas, acertos, nota, total,
                  disciplina, tipo_avaliacao, questoes_status_json))
            row = cur.fetchone(); result_id = row['id'] if row else None

        conn.commit(); cur.close(); conn.close()
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


@bp.route('/salvar_nota_producao', methods=['POST'])
def salvar_nota_producao():
    try:
        data = request.json
        if not data: return jsonify({'erro': 'Nenhum dado recebido'}), 400
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')
        nota = data.get('nota')
        observacao = (data.get('observacao') or '').strip()
        questoes_status_recebidas = data.get('questoes_status', [])
        if not aluno_id: return jsonify({'erro': 'Aluno é obrigatório'}), 400
        if not prova_id: return jsonify({'erro': 'Prova é obrigatória'}), 400
        if nota is None or nota == '': return jsonify({'erro': 'Nota é obrigatória'}), 400
        try: nota_float = float(nota)
        except (ValueError, TypeError): return jsonify({'erro': 'Nota inválida'}), 400
        if nota_float < 0 or nota_float > 10:
            return jsonify({'erro': 'Nota deve estar entre 0 e 10'}), 400

        conn = get_db_connection()
        if not conn: return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        escola_sessao = get_escola_id()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        ok, dados, err, status = _validar_aluno_prova_escola(
            cur, aluno_id, prova_id, escola_sessao
        )
        if not ok:
            cur.close(); conn.close()
            return jsonify({'erro': err}), status

        disciplina = dados.get('disciplina') or 'Produção de Texto'
        serie = dados.get('turma_serie') or dados.get('serie') or '1º Ano'
        tipo_avaliacao = 'Producao'
        acertos_equiv = int(round(nota_float))
        total_equiv = 10

        if questoes_status_recebidas and isinstance(questoes_status_recebidas, list) and len(questoes_status_recebidas) > 0:
            questoes_status = questoes_status_recebidas
            for q in questoes_status:
                if isinstance(q, dict): q['nota_manual'] = nota_float
        else:
            questoes_status = [{
                'numero': 1, 'resposta': f'{nota_float:.1f}', 'gabarito': '10.0',
                'acertou': nota_float >= 6, 'respondida': True, 'bncc': '',
                'status': f'📝 Produção de Texto — Nota Manual {nota_float:.1f}',
                'status_texto': f'📝 Nota {nota_float:.1f}', 'confianca': 100,
                'correta': nota_float >= 6
            }]
        if observacao and questoes_status:
            questoes_status[0]['status_texto'] = (
                questoes_status[0].get('status_texto', '') + f' — {observacao[:200]}'
            )

        respostas_hist = [f'{nota_float:.1f}']
        questoes_status_json = json.dumps(questoes_status, ensure_ascii=False, default=str)

        cur.execute("SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s", (prova_id, aluno_id))
        existe = cur.fetchone()
        if existe:
            cur.execute("""
                UPDATE historico SET respostas = %s::text[], acertos = %s, nota = %s, total = %s,
                    tipo_correcao = 'manual_producao', disciplina = %s, tipo_avaliacao = %s,
                    questoes_status = %s::jsonb, confianca = 100,
                    confianca_por_questao = %s::jsonb, data_correcao = CURRENT_TIMESTAMP
                WHERE prova_id = %s AND aluno_id = %s
            """, (respostas_hist, acertos_equiv, nota_float, total_equiv,
                  disciplina, tipo_avaliacao, questoes_status_json,
                  json.dumps([100]), prova_id, aluno_id))
            hist_id = existe['id']
        else:
            cur.execute("""
                INSERT INTO historico
                (prova_id, aluno_id, respostas, acertos, nota, total,
                 tipo_correcao, disciplina, tipo_avaliacao, questoes_status,
                 confianca, confianca_por_questao, bncc)
                VALUES (%s, %s, %s::text[], %s, %s, %s, 'manual_producao', %s, %s,
                        %s::jsonb, 100, %s::jsonb, %s::text[])
                RETURNING id
            """, (prova_id, aluno_id, respostas_hist, acertos_equiv, nota_float,
                  total_equiv, disciplina, tipo_avaliacao, questoes_status_json,
                  json.dumps([100]), []))
            hist_id = cur.fetchone()['id']

        conn.commit(); cur.close(); conn.close()

        porcentagem = int(round((nota_float / 10) * 100))
        conceito = calcular_conceito(porcentagem)
        return jsonify({
            'sucesso': True, 'id': hist_id,
            'mensagem': f'Nota {nota_float:.1f} salva com sucesso!',
            'aluno': dados.get('aluno_nome'), 'prova': dados.get('titulo'),
            'nota': nota_float, 'porcentagem': porcentagem, 'conceito': conceito,
            'tipo_avaliacao': tipo_avaliacao, 'disciplina': disciplina
        })
    except Exception as e:
        logging.error(f"❌ Erro ao salvar nota produção: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


@bp.route('/corrigir-automatico', methods=['POST'])
def corrigir_automatico():
    try:
        data = request.json
        if not data: return jsonify({'erro': 'Nenhum dado recebido'}), 400
        imagem_base64 = data.get('imagem')
        if not imagem_base64: return jsonify({'erro': 'Imagem é obrigatória'}), 400
        salvar_auto = data.get('salvar_auto', True)

        from services.evalbee import extrair_dados_qrcode
        info_qr = extrair_dados_qrcode(imagem_base64)
        if not info_qr:
            return jsonify({
                'sucesso': False,
                'erro': 'Não foi possível ler o QR Code do cartão.',
                'dicas': [
                    '1. O QR Code está visível na foto?',
                    '2. A foto está nítida e bem iluminada?',
                    '3. O QR Code não está amassado ou rasgado?',
                    '4. Você está usando o cartão gerado pelo sistema?'
                ]
            }), 404

        aluno_id = info_qr.get('aluno_id')
        prova_id = info_qr.get('prova_id')
        escola_id = info_qr.get('escola_id')
        turma_id = info_qr.get('turma_id')

        if not aluno_id or not prova_id:
            return jsonify({
                'sucesso': False,
                'erro': 'QR Code não contém dados de aluno e prova',
                'qr_lido': info_qr
            }), 400

        conn = get_db_connection()
        if not conn: return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        try:
            escola_sessao = get_escola_id()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            ok, dados, err, status = _validar_aluno_prova_escola(
                cur, aluno_id, prova_id, escola_sessao
            )
            if not ok:
                cur.close(); conn.close()
                return jsonify({'sucesso': False, 'erro': err}), status

            prova = dados
            gabarito = prova.get('gabarito', [])
            if not gabarito:
                cur.close(); conn.close()
                return jsonify({'sucesso': False, 'erro': 'Prova não tem gabarito cadastrado',
                                'prova_id': prova_id}), 400

            tipo_questoes = prova.get('tipo_questoes') or 4
            if isinstance(tipo_questoes, str):
                try: tipo_questoes = int(tipo_questoes)
                except Exception: tipo_questoes = 4

            if not validar_gabarito(gabarito, tipo_questoes):
                cur.close(); conn.close()
                return jsonify({'sucesso': False, 'erro': 'Gabarito inválido para este tipo de prova'}), 400

            padrao_gabarito = gerar_padrao_gabarito(gabarito, tipo_questoes)
            nome_aluno = prova.get('aluno_nome') or 'Aluno'
            serie = prova.get('turma_serie') or prova.get('serie') or '1º Ano'
            bncc_gabarito = prova.get('bncc', [])
            disciplina = prova.get('disciplina', '')
            prova_titulo = prova.get('titulo', '')
            escola_nome_banco = prova.get('escola_nome', '')
            turma_nome_banco = prova.get('turma_nome', '')  # ✅ agora vem preenchido
            cur.close(); conn.close()
        except Exception as e:
            logging.error(f"❌ Erro ao buscar dados: {e}")
            try: conn.close()
            except Exception: pass
            return jsonify({'erro': str(e)}), 500

        resultado = corrigir_com_gemini_com_padrao(
            imagem_base64, padrao_gabarito, nome_aluno,
            serie, tipo_questoes, disciplina, bncc=bncc_gabarito,
            prova_id=prova_id, aluno_id=aluno_id
        )
        if resultado.get('erro'):
            return jsonify({'sucesso': False, 'erro': resultado.get('erro'),
                            'aluno': nome_aluno, 'prova': prova_titulo}), 400

        tipo_avaliacao = identificar_disciplina(prova_titulo, disciplina, serie)
        if 'confianca_por_questao' not in resultado or not resultado['confianca_por_questao']:
            total = resultado.get('total', 20)
            resultado['confianca_por_questao'] = [70] * total
            resultado['confianca'] = 70

        if salvar_auto:
            try:
                conn = get_db_connection()
                if conn:
                    cur = conn.cursor()
                    questoes_status = resultado.get('questoes_status', [])
                    for i, q in enumerate(questoes_status):
                        q['bncc'] = bncc_gabarito[i] if i < len(bncc_gabarito) and bncc_gabarito[i] else ''
                    qjson = json.dumps(questoes_status)
                    resp = resultado.get('respostas_detectadas', [])
                    cur.execute("SELECT id FROM historico WHERE prova_id = %s AND aluno_id = %s", (prova_id, aluno_id))
                    existe = cur.fetchone()
                    if existe:
                        cur.execute("""UPDATE historico SET respostas=%s::text[], acertos=%s, nota=%s,
                            total=%s, tipo_correcao=%s, disciplina=%s, tipo_avaliacao=%s,
                            questoes_status=%s::jsonb, confianca=%s, confianca_por_questao=%s::jsonb,
                            bncc=%s::text[], data_correcao=CURRENT_TIMESTAMP
                            WHERE prova_id=%s AND aluno_id=%s""",
                            (resp, resultado.get('acertos',0), resultado.get('nota',0),
                             resultado.get('total',0), resultado.get('modo','ia'), disciplina,
                             tipo_avaliacao, qjson, resultado.get('confianca',70),
                             json.dumps(resultado.get('confianca_por_questao',[])),
                             bncc_gabarito, prova_id, aluno_id))
                    else:
                        cur.execute("""INSERT INTO historico
                            (prova_id, aluno_id, respostas, acertos, nota, total,
                             tipo_correcao, disciplina, tipo_avaliacao, questoes_status,
                             confianca, confianca_por_questao, bncc)
                            VALUES (%s,%s,%s::text[],%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::text[])""",
                            (prova_id, aluno_id, resp, resultado.get('acertos',0),
                             resultado.get('nota',0), resultado.get('total',0),
                             resultado.get('modo','ia'), disciplina, tipo_avaliacao,
                             qjson, resultado.get('confianca',70),
                             json.dumps(resultado.get('confianca_por_questao',[])),
                             bncc_gabarito))
                    conn.commit(); cur.close(); conn.close()
            except Exception as e:
                logging.error(f"⚠️ Erro ao salvar histórico: {e}")

        resultado['sucesso'] = True
        resultado['qr_lido'] = info_qr
        resultado['aluno'] = nome_aluno
        resultado['aluno_id'] = aluno_id
        resultado['prova_id'] = prova_id
        resultado['prova_titulo'] = prova_titulo
        resultado['escola_nome'] = escola_nome_banco
        resultado['turma_nome'] = turma_nome_banco          # ✅ agora preenchido
        resultado['tipo_avaliacao'] = tipo_avaliacao
        resultado['disciplina'] = disciplina
        resultado['bncc'] = bncc_gabarito
        resultado['escola_id'] = escola_id
        resultado['turma_id'] = turma_id
        resultado['serie'] = serie
        return jsonify(resultado)

    except Exception as e:
        logging.error(f"❌ Erro em /api/corrigir-automatico: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
