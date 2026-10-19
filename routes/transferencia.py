# ============================================================
# ROUTES/TRANSFERENCIA.PY — Transferência de Alunos
# ============================================================

import traceback

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from core.db import get_db_connection

bp = Blueprint('transferencia', __name__, url_prefix='/api')


@bp.route('/alunos/transferir', methods=['POST'])
def transferir_aluno():
    try:
        data = request.get_json() or {}
        alunos_ids = data.get('alunos_ids', [])
        escola_origem_id = data.get('escola_origem_id')
        turma_origem_id = data.get('turma_origem_id')
        escola_destino_id = data.get('escola_destino_id')
        turma_destino_id = data.get('turma_destino_id')
        serie_destino = data.get('serie_destino', '')
        motivo = data.get('motivo', 'Transferência solicitada')
        usuario_responsavel = data.get('usuario_responsavel', 'sistema')

        if not alunos_ids:
            return jsonify({'ok': False, 'erro': 'Nenhum aluno selecionado'}), 400
        if not escola_destino_id or not turma_destino_id:
            return jsonify({'ok': False, 'erro': 'Escola e turma destino obrigatórias'}), 400
        if escola_origem_id == escola_destino_id and turma_origem_id == turma_destino_id:
            return jsonify({'ok': False, 'erro': 'Origem e destino são iguais'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'ok': False, 'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Busca os alunos SEM a coluna 'serie' (que não existe em alunos)
        cur.execute("""
            SELECT id, nome, escola_id, turma_id, matricula, numero_chamada
            FROM alunos WHERE id = ANY(%s)
        """, (alunos_ids,))
        alunos = cur.fetchall()

        if not alunos:
            cur.close(); conn.close()
            return jsonify({'ok': False, 'erro': 'Nenhum aluno encontrado'}), 404

        # 2. Valida que todos estão na turma de origem
        invalidos = [a for a in alunos if a['turma_id'] != turma_origem_id]
        if invalidos:
            cur.close(); conn.close()
            nomes = ', '.join(a['nome'] for a in invalidos[:3])
            return jsonify({'ok': False, 'erro': f'Alunos fora da turma de origem: {nomes}'}), 400

        # 3. Busca a série REAL da turma de origem (não do aluno)
        cur.execute("SELECT serie FROM turmas WHERE id = %s", (turma_origem_id,))
        t_origem = cur.fetchone()
        serie_origem = t_origem['serie'] if t_origem else ''

        # 4. Busca a série REAL da turma de destino
        cur.execute("SELECT serie FROM turmas WHERE id = %s", (turma_destino_id,))
        t_destino = cur.fetchone()
        if not t_destino:
            cur.close(); conn.close()
            return jsonify({'ok': False, 'erro': 'Turma de destino não encontrada'}), 404
        serie_destino_final = serie_destino or t_destino['serie']

        # 5. Próxima matrícula na escola destino
        cur.execute("""
            SELECT COALESCE(MAX(CAST(matricula AS INTEGER)), 0) + 1 AS proxima
            FROM alunos WHERE escola_id = %s AND matricula ~ '^[0-9]+$'
        """, (escola_destino_id,))
        proxima_matricula = cur.fetchone()['proxima']

        # 6. Próximo número de chamada na turma destino
        cur.execute("""
            SELECT COALESCE(MAX(numero_chamada), 0) + 1 AS proximo
            FROM alunos WHERE turma_id = %s
        """, (turma_destino_id,))
        proximo_numero = cur.fetchone()['proximo']

        transferidos = 0
        erros = []

        for aluno in alunos:
            try:
                # 7. Registra histórico na tabela transferencias
                cur.execute("""
                    INSERT INTO transferencias (
                        aluno_id, escola_origem_id, escola_destino_id,
                        turma_origem_id, turma_destino_id,
                        serie_origem, serie_destino,
                        matricula_origem, matricula_destino,
                        numero_chamada_origem, numero_chamada_destino,
                        motivo, usuario_responsavel
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    aluno['id'],
                    aluno['escola_id'], escola_destino_id,
                    aluno['turma_id'], turma_destino_id,
                    serie_origem, serie_destino_final,
                    aluno['matricula'], str(proxima_matricula),
                    aluno['numero_chamada'], proximo_numero,
                    motivo, usuario_responsavel
                ))

                # 8. Atualiza aluno (SEM coluna 'serie')
                cur.execute("""
                    UPDATE alunos
                    SET escola_id = %s,
                        turma_id = %s,
                        matricula = %s,
                        numero_chamada = %s
                    WHERE id = %s
                """, (
                    escola_destino_id, turma_destino_id,
                    str(proxima_matricula), proximo_numero,
                    aluno['id']
                ))

                proxima_matricula += 1
                proximo_numero += 1
                transferidos += 1
            except Exception as e:
                erros.append({'aluno': aluno['nome'], 'erro': str(e)})

        conn.commit()
        cur.close(); conn.close()

        return jsonify({
            'ok': True,
            'transferidos': transferidos,
            'total': len(alunos_ids),
            'erros': erros,
            'mensagem': f'{transferidos} aluno(s) transferido(s)'
        }), 200

    except Exception as e:
        print(f'❌ Erro em transferir_aluno: {e}')
        traceback.print_exc()
        return jsonify({'ok': False, 'erro': str(e)}), 500


@bp.route('/alunos/<int:aluno_id>/transferencias', methods=['GET'])
def listar_transferencias_aluno(aluno_id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT t.*,
                   eo.nome AS escola_origem_nome,
                   ed.nome AS escola_destino_nome,
                   tor.nome AS turma_origem_nome,
                   tde.nome AS turma_destino_nome
            FROM transferencias t
            LEFT JOIN escolas eo ON eo.id = t.escola_origem_id
            LEFT JOIN escolas ed ON ed.id = t.escola_destino_id
            LEFT JOIN turmas tor ON tor.id = t.turma_origem_id
            LEFT JOIN turmas tde ON tde.id = t.turma_destino_id
            WHERE t.aluno_id = %s
            ORDER BY t.data_transferencia DESC
        """, (aluno_id,))
        transferencias = cur.fetchall()
        cur.close(); conn.close()
        return jsonify(transferencias), 200
    except Exception as e:
        print(f'❌ Erro: {e}')
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
