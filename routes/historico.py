# ============================================================
# ROUTES/HISTORICO.PY — Histórico simples + agrupado + delete
# com isolamento por escola
# ============================================================

import json
import logging
import traceback

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from core.db import get_db_connection
from core.utils import calcular_conceito, identificar_disciplina, get_escola_id


bp = Blueprint('historico', __name__, url_prefix='/api')


@bp.route('/historico', methods=['GET'])
def listar_historico():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        # 🔒 Escola da sessão (None = admin → respeita query param)
        escola_sessao = get_escola_id()
        escola_param = request.args.get('escola')

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

        # 🔒 Força escola da sessão se não-admin
        if escola_sessao is not None:
            params.append(escola_sessao)
            query += " AND a.escola_id = %s"
        elif escola_param and escola_param not in ('', 'null'):
            try:
                params.append(int(escola_param))
                query += " AND e.id = %s"
            except ValueError:
                pass

        if turma_id and turma_id not in ('', 'null'):
            try:
                params.append(int(turma_id))
                query += " AND t.id = %s"
            except ValueError:
                pass

        if aluno_id and aluno_id not in ('', 'null'):
            try:
                params.append(int(aluno_id))
                query += " AND h.aluno_id = %s"
            except ValueError:
                pass

        if prova_id and prova_id not in ('', 'null'):
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


@bp.route('/historico/agrupado', methods=['GET'])
def historico_agrupado():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        escola_sessao = get_escola_id()
        escola_param = request.args.get('escola')

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

        if escola_sessao is not None:
            params.append(escola_sessao)
            query += " AND a.escola_id = %s"
        elif escola_param and escola_param not in ('', 'null'):
            try:
                params.append(int(escola_param))
                query += " AND e.id = %s"
            except ValueError:
                pass

        if turma_id and turma_id not in ('', 'null'):
            try:
                params.append(int(turma_id))
                query += " AND t.id = %s"
            except ValueError:
                pass

        if aluno_id and aluno_id not in ('', 'null'):
            try:
                params.append(int(aluno_id))
                query += " AND h.aluno_id = %s"
            except ValueError:
                pass

        if serie and serie not in ('', 'null'):
            params.append(serie)
            query += " AND t.serie = %s"

        if prova_id and prova_id not in ('', 'null'):
            try:
                params.append(int(prova_id))
                query += " AND h.prova_id = %s"
            except ValueError:
                pass

        query += " ORDER BY a.nome, h.data_correcao DESC"

        tem_filtro_restritivo = bool(
            (turma_id and turma_id not in ('', 'null')) or
            (aluno_id and aluno_id not in ('', 'null')) or
            (prova_id and prova_id not in ('', 'null'))
        )
        if not tem_filtro_restritivo:
            query += " LIMIT 1000"
            logging.warning(
                "⚠️ /api/historico/agrupado SEM filtro restritivo → LIMIT 1000 aplicado "
                "(escola=%s, serie=%s)", escola_param, serie
            )

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

            disc_lower = (disciplina or '').lower()
            prova_lower = (prova_titulo or '').lower()
            is_redacao = ('reda' in disc_lower or 'reda' in prova_lower
                          or item.get('tipo_correcao') == 'ia_redacao')
            is_producao_manual = item.get('tipo_correcao') == 'manual_producao'
            if is_producao_manual:
                tipo = 'Producao'

            if is_redacao or is_producao_manual:
                nota_red = float(item.get('nota') or 0)
                acertos_red = int(item.get('acertos') or 0)
                total_red = int(item.get('total') or 10)
                erros_red = max(0, total_red - acertos_red)

                questoes_status = [{
                    'numero': 1,
                    'resposta': f'Nota {nota_red}',
                    'gabarito': '10.0',
                    'acertou': nota_red >= 6,
                    'respondida': True,
                    'bncc': '',
                    'status': f'📝 Nota {nota_red}'
                }]

                if tipo not in alunos_map[aluno_key]['avaliacoes']:
                    alunos_map[aluno_key]['avaliacoes'][tipo] = {
                        'nota': nota_red,
                        'acertos': acertos_red, 'erros': erros_red, 'total': total_red,
                        'prova': prova_titulo, 'data': item.get('data_correcao', ''),
                        'disciplina': disciplina, 'questoes_status': questoes_status,
                        'bncc': [''], 'respostas': [f'Nota {nota_red}'], 'gabarito': ['10.0']
                    }
                else:
                    existing = alunos_map[aluno_key]['avaliacoes'][tipo]
                    data_atual = item.get('data_correcao', '')
                    data_existente = existing.get('data', '')
                    if data_atual > data_existente:
                        alunos_map[aluno_key]['avaliacoes'][tipo] = {
                            'nota': nota_red,
                            'acertos': acertos_red, 'erros': erros_red, 'total': total_red,
                            'prova': prova_titulo, 'data': data_atual,
                            'disciplina': disciplina, 'questoes_status': questoes_status,
                            'bncc': [''], 'respostas': [f'Nota {nota_red}'], 'gabarito': ['10.0']
                        }
                continue

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
                is_resposta_valida = resp and resp not in ('', '—', '-')
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
            default = {'nota': 0, 'acertos': 0, 'erros': 0, 'total': 20,
                       'questoes_status': [], 'bncc': [], 'respostas': [], 'gabarito': []}
            portugues = dict(avaliacoes.get('Portugues', default))
            matematica = dict(avaliacoes.get('Matematica', default))
            producao = dict(avaliacoes.get('Producao', default))
            ch = dict(avaliacoes.get('CH', default))
            cn = dict(avaliacoes.get('CN', default))
            notas = [portugues.get('nota', 0), matematica.get('nota', 0),
                     producao.get('nota', 0), ch.get('nota', 0), cn.get('nota', 0)]
            soma = sum(notas); media = soma / 5 if notas else 0
            resultado.append({
                'aluno_id': dados['aluno_id'], 'aluno_nome': dados['aluno_nome'],
                'serie': dados['serie'], 'turma': dados['turma'], 'escola': dados['escola'],
                'portugues': portugues, 'matematica': matematica,
                'producao': producao, 'ch': ch, 'cn': cn,
                'soma': round(soma, 1), 'media': round(media, 1)
            })

        return jsonify(resultado)

    except Exception as e:
        print(f"❌ Erro ao buscar histórico agrupado: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


@bp.route('/historico/<int:id>', methods=['DELETE'])
def excluir_correcao(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        escola_sessao = get_escola_id()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT h.id, a.escola_id
            FROM historico h
            LEFT JOIN alunos a ON h.aluno_id = a.id
            WHERE h.id = %s
        """, (id,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return jsonify({'erro': 'Correção não encontrada'}), 404

        if escola_sessao is not None and row.get('escola_id') != escola_sessao:
            cur.close(); conn.close()
            return jsonify({'erro': 'Acesso negado a esta correção'}), 403

        cur.execute("DELETE FROM historico WHERE id = %s", (id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({'sucesso': True, 'mensagem': 'Correção excluída com sucesso', 'id': id})

    except Exception as e:
        return jsonify({'erro': str(e)}), 500
