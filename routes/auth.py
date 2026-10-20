# ============================================================
# ROUTES/AUTH.PY — Login + Verificação de Senha Admin
# ============================================================

import hmac
import traceback

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from config import USUARIOS_FIXOS
from core.db import get_db_connection


bp = Blueprint('auth', __name__, url_prefix='/api')


# ═══════════════════════════════════════════════════════════════
# 🔑 ROTA DE LOGIN
# ═══════════════════════════════════════════════════════════════
@bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.json or {}
        username = data.get('username')
        senha = data.get('senha')
        if not username or not senha:
            return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
        print(f"🔑 Tentativa de login: {username}")
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT u.id, u.nome, u.username, u.senha_hash, u.perfil,
                           u.ativo, u.escola_id, e.nome AS escola_nome
                    FROM usuarios u
                    LEFT JOIN escolas e ON e.id = u.escola_id
                    WHERE u.username = %s
                """, (username,))
                usuario = cur.fetchone()
                cur.close()
                conn.close()
                if usuario:
                    if hmac.compare_digest(str(usuario['senha_hash'] or ''), str(senha)) and usuario['ativo'] == True:
                        return jsonify({
                            'sucesso': True,
                            'id': usuario['id'],
                            'perfil': usuario['perfil'],
                            'usuario': usuario['username'],
                            'username': usuario['username'],
                            'nome': usuario['nome'],
                            'escola_id': usuario.get('escola_id'),
                            'escola_nome': usuario.get('escola_nome'),
                        })
            except Exception as e:
                print(f"❌ Erro no banco: {e}")
                traceback.print_exc()
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if hmac.compare_digest(str(dados['senha']), str(senha)):
                return jsonify({
                    'sucesso': True,
                    'id': 0,
                    'perfil': dados['perfil'],
                    'usuario': username,
                    'username': username,
                    'nome': dados['nome'],
                    'escola_id': dados.get('escola_id'),
                    'escola_nome': None,
                })
        return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 🔒 VERIFICAR SENHA ADMIN
# A lógica: aceita a senha de QUALQUER admin ativo (mesma senha do login)
# ═══════════════════════════════════════════════════════════════
@bp.route('/verificar-senha-admin', methods=['POST'])
def verificar_senha_admin():
    """
    Valida a senha de administrador.

    Estratégia (na ordem):
      1) Se o `username` enviado for um admin ativo → confere a senha dele
      2) Fallback: procura QUALQUER admin ativo no banco cuja senha bata
         (assim, se o front manda 'admin' fixo, mas a senha é do 'jorge',
          o fallback encontra o 'jorge' e libera)
      3) Fallback final: senha do 'admin' fixo (USUARIOS_FIXOS)
    """
    try:
        data = request.get_json() or {}
        senha = data.get('senha', '').strip()
        username = data.get('username', '').strip()

        if not senha:
            return jsonify({'ok': False, 'erro': 'Senha é obrigatória'}), 400

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)

                # ── 1) Tentar pelo username enviado ──
                if username:
                    cur.execute("""
                        SELECT id, username, nome, senha_hash, perfil, ativo
                        FROM usuarios WHERE username = %s
                    """, (username,))
                    u = cur.fetchone()
                    if (u and u.get('ativo') and u.get('perfil') == 'admin'
                            and hmac.compare_digest(str(u['senha_hash'] or ''), str(senha))):
                        cur.close()
                        conn.close()
                        return jsonify({
                            'ok': True,
                            'usuario': {
                                'id': u['id'],
                                'username': u['username'],
                                'nome': u['nome'],
                                'perfil': u['perfil']
                            }
                        }), 200

                # ── 2) Fallback: QUALQUER admin ativo com essa senha ──
                cur.execute("""
                    SELECT id, username, nome, senha_hash, perfil
                    FROM usuarios WHERE perfil = 'admin' AND ativo = TRUE
                """)
                admins = cur.fetchall() or []
                for a in admins:
                    if hmac.compare_digest(str(a['senha_hash'] or ''), str(senha)):
                        cur.close()
                        conn.close()
                        print(f"✅ Senha admin validada (fallback por senha): {a['username']}")
                        return jsonify({
                            'ok': True,
                            'usuario': {
                                'id': a['id'],
                                'username': a['username'],
                                'nome': a['nome'],
                                'perfil': a['perfil']
                            }
                        }), 200

                cur.close()
            except Exception as e:
                print(f"⚠️ Erro na checagem do banco: {e}")
                traceback.print_exc()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        # ── 3) Fallback final: 'admin' fixo (DEV) ──
        if 'admin' in USUARIOS_FIXOS:
            fixo = USUARIOS_FIXOS['admin']
            if fixo.get('perfil') == 'admin' and hmac.compare_digest(str(fixo['senha']), str(senha)):
                print("✅ Senha admin validada (fixo 'admin')")
                return jsonify({
                    'ok': True,
                    'usuario': {
                        'id': 0,
                        'username': 'admin',
                        'nome': fixo.get('nome', 'Administrador'),
                        'perfil': 'admin'
                    }
                }), 200

        return jsonify({'ok': False, 'erro': 'Senha incorreta'}), 401

    except Exception as e:
        print(f'❌ Erro em verificar_senha_admin: {e}')
        traceback.print_exc()
        return jsonify({'ok': False, 'erro': 'Erro interno do servidor'}), 500
