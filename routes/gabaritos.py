# ============================================================
# ROUTES/GABARITOS.PY — Salvar / remover gabaritos
# ============================================================

import json
import traceback

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from core.db import get_db_connection


bp = Blueprint('gabaritos', __name__, url_prefix='/api')


@bp.route('/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        data = request.json
        prova_id = data.get('prova_id')
        respostas = data.get('respostas', [])
        bncc = data.get('bncc', [])
        textos_questoes = data.get('textos_questoes', [])
        niveis = data.get('niveis', [])

        if not prova_id:
            return jsonify({'erro': 'Prova ID é obrigatório'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, disciplina FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()

        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404

        is_producao = (prova.get('disciplina') or '').strip() == 'Produção de Texto'

        if is_producao:
            respostas_serializadas = []
            for item in respostas:
                if isinstance(item, str):
                    respostas_serializadas.append(item.strip())
                else:
                    respostas_serializadas.append(str(item).strip() if item else '')

            textos_serializados = []
            for t in textos_questoes:
                if isinstance(t, (dict, list)):
                    textos_serializados.append(json.dumps(t, ensure_ascii=False))
                else:
                    textos_serializados.append(str(t).strip() if t else '')

            bncc_validos = [str(b).strip() for b in bncc if b and str(b).strip()]
            niveis_validos = [str(n).strip().upper() for n in niveis if n and str(n).strip()]

            cur.execute("""
                UPDATE provas
                SET gabarito = %s::text[],
                    quantidade_questoes = %s,
                    bncc = %s::text[],
                    textos_questoes = %s::text[],
                    niveis = %s::text[]
                WHERE id = %s
                RETURNING id
            """, (respostas_serializadas, len(respostas_serializadas),
                  bncc_validos, textos_serializados, niveis_validos, prova_id))

            result = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                'id': result['id'],
                'mensagem': 'Gabarito de Produção de Texto salvo com sucesso',
                'total_questoes': len(respostas_serializadas),
                'tipo': 'producao'
            })

        if not respostas or len(respostas) == 0:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Respostas são obrigatórias'}), 400

        respostas_validas = [str(r).strip().upper() for r in respostas if r]
        if not respostas_validas:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Nenhuma resposta válida'}), 400

        bncc_validos = [str(b).strip() for b in bncc if b and str(b).strip()]
        textos_validos = [str(t).strip() for t in textos_questoes]
        niveis_validos = [str(n).strip() for n in niveis]

        cur.execute("""
            UPDATE provas
            SET gabarito = %s::text[],
                quantidade_questoes = %s,
                bncc = %s::text[],
                textos_questoes = %s::text[],
                niveis = %s::text[]
            WHERE id = %s
            RETURNING id
        """, (respostas_validas, len(respostas_validas), bncc_validos,
              textos_validos, niveis_validos, prova_id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'id': result['id'],
            'mensagem': 'Gabarito salvo com sucesso',
            'total_questoes': len(respostas_validas)
        })

    except Exception as e:
        print(f"❌ Erro ao salvar gabarito: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


@bp.route('/gabaritos/<int:id>', methods=['DELETE'])
def excluir_gabarito(id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor()
        cur.execute("SELECT id, titulo FROM provas WHERE id = %s", (id,))
        prova = cur.fetchone()
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404

        cur.execute("""
            UPDATE provas
            SET gabarito = NULL, quantidade_questoes = 0, bncc = NULL,
                textos_questoes = NULL, niveis = NULL
            WHERE id = %s
        """, (id,))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'sucesso': True,
            'mensagem': f'Gabarito da prova "{prova[1]}" removido com sucesso!'
        })

    except Exception as e:
        return jsonify({'erro': str(e)}), 500