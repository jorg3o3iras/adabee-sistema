# ============================================================
# ROUTES/DASHBOARD.PY — Dashboard + Conceito (por escola)
# ============================================================

import logging
import traceback

from flask import Blueprint, jsonify
from psycopg2.extras import RealDictCursor

from core.db import get_db_connection
from core.utils import calcular_conceito, get_escola_id


bp = Blueprint('dashboard', __name__, url_prefix='/api')


@bp.route('/dashboard', methods=['GET'])
def dashboard():
    conn = get_db_connection()
    if not conn:
        return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})

    try:
        escola_id = get_escola_id()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if escola_id is None:
            # Admin vê tudo
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM escolas) AS total_escolas,
                    (SELECT COUNT(*) FROM turmas) AS total_turmas,
                    (SELECT COUNT(*) FROM alunos) AS total_alunos,
                    (SELECT COUNT(*) FROM provas) AS total_provas
            """)
        else:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM escolas WHERE id = %s) AS total_escolas,
                    (SELECT COUNT(*) FROM turmas WHERE escola_id = %s) AS total_turmas,
                    (SELECT COUNT(*) FROM alunos WHERE escola_id = %s) AS total_alunos,
                    (SELECT COUNT(*) FROM provas WHERE escola_id = %s) AS total_provas
            """, (escola_id, escola_id, escola_id, escola_id))

        row = cur.fetchone()
        cur.close(); conn.close()

        return jsonify({
            'total_escolas': int(row['total_escolas'] or 0),
            'total_turmas': int(row['total_turmas'] or 0),
            'total_alunos': int(row['total_alunos'] or 0),
            'total_provas': int(row['total_provas'] or 0)
        })
    except Exception as e:
        logging.error("Erro no dashboard: %s", e)
        try: conn.close()
        except Exception: pass
        return jsonify({'total_escolas': 0, 'total_turmas': 0, 'total_alunos': 0, 'total_provas': 0})


@bp.route('/dashboard/Conceito', methods=['GET'])
def dashboard_conceito():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        escola_id = get_escola_id()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if escola_id is None:
            cur.execute("""
                SELECT
                    t.id as turma_id, t.nome as turma_nome, t.serie,
                    COUNT(DISTINCT a.id) as total_alunos,
                    COALESCE(AVG(h.acertos * 1.0 / NULLIF(h.total, 0)), 0) as media_porcentagem,
                    COALESCE(SUM(CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END), 0) as total_correcoes
                FROM turmas t
                LEFT JOIN alunos a ON a.turma_id = t.id
                LEFT JOIN historico h ON h.aluno_id = a.id
                GROUP BY t.id, t.nome, t.serie
                HAVING COUNT(DISTINCT a.id) > 0
                ORDER BY t.nome
            """)
        else:
            cur.execute("""
                SELECT
                    t.id as turma_id, t.nome as turma_nome, t.serie,
                    COUNT(DISTINCT a.id) as total_alunos,
                    COALESCE(AVG(h.acertos * 1.0 / NULLIF(h.total, 0)), 0) as media_porcentagem,
                    COALESCE(SUM(CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END), 0) as total_correcoes
                FROM turmas t
                LEFT JOIN alunos a ON a.turma_id = t.id
                LEFT JOIN historico h ON h.aluno_id = a.id
                WHERE t.escola_id = %s
                GROUP BY t.id, t.nome, t.serie
                HAVING COUNT(DISTINCT a.id) > 0
                ORDER BY t.nome
            """, (escola_id,))

        turmas = cur.fetchall()
        cur.close(); conn.close()

        resultado = []
        for turma in turmas:
            media_porcentagem = float(turma['media_porcentagem'] or 0)
            total_correcoes = int(turma['total_correcoes'] or 0)
            porcentagem = round(media_porcentagem * 100) if media_porcentagem > 0 else 0
            conceito = calcular_conceito(porcentagem)
            resultado.append({
                'id': turma['turma_id'],
                'nome': turma['turma_nome'] or f"Turma {turma['turma_id']}",
                'serie': turma['serie'],
                'total_alunos': turma['total_alunos'],
                'porcentagem': porcentagem,
                'total_correcoes': total_correcoes,
                'conceito': conceito
            })
        return jsonify(resultado)

    except Exception as e:
        print(f"❌ Erro em /api/dashboard/Conceito: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
