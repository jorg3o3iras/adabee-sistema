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
        data = request.json
        username = data.get('username')
        senha = data.get('senha')
        if not username or not senha:
            return jsonify({'erro': 'Usuário e senha são obrigatórios'}), 400
        print(f"🔑 Tentativa de login: {username}")
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("SELECT id, nome, username, senha_hash, perfil, ativo FROM usuarios WHERE username = %s", (username,))
                usuario = cur.fetchone()
                cur.close()
                conn.close()
                if usuario:
                    if hmac.compare_digest(str(usuario['senha_hash'] or ''), str(senha)) and usuario['ativo'] == True:
                        return jsonify({'sucesso': True, 'perfil': usuario['perfil'], 'usuario': usuario['username'], 'nome': usuario['nome']})
            except Exception as e:
                print(f"❌ Erro no banco: {e}")
                traceback.print_exc()
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if hmac.compare_digest(str(dados['senha']), str(senha)):
                return jsonify({'sucesso': True, 'perfil': dados['perfil'], 'usuario': username, 'nome': dados['nome']})
        return jsonify({'sucesso': False, 'erro': 'Usuário ou senha incorretos!'}), 401
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 🔒 NOVA ROTA — VERIFICAR SENHA ADMIN
# (url_prefix='/api' já está no Blueprint, então NÃO coloque /api aqui)
# URL final: /api/verificar-senha-admin
# ═══════════════════════════════════════════════════════════════
@bp.route('/verificar-senha-admin', methods=['POST'])
def verificar_senha_admin():
    """
    Verifica se a senha enviada pertence a um usuário ADMIN.
    Usado para proteger a tela de Configurações.
    """
    try:
        data = request.get_json()
        senha = data.get('senha', '').strip()
        username = data.get('username', '').strip()

        if not senha or not username:
            return jsonify({'ok': False, 'erro': 'Usuário e senha são obrigatórios'}), 400

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, username, nome, senha_hash, perfil, ativo
            FROM usuarios
            WHERE username = %s
        """, (username,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if not usuario:
            return jsonify({'ok': False, 'erro': 'Usuário não encontrado'}), 401

        if not usuario['ativo']:
            return jsonify({'ok': False, 'erro': 'Usuário inativo'}), 401

        if usuario['perfil'] != 'admin':
            return jsonify({'ok': False, 'erro': 'Apenas administradores podem acessar'}), 403

        # Compara a senha (mesma técnica do login: hmac.compare_digest)
        if not hmac.compare_digest(str(usuario['senha_hash'] or ''), str(senha)):
            return jsonify({'ok': False, 'erro': 'Senha incorreta'}), 401

        return jsonify({
            'ok': True,
            'usuario': {
                'id': usuario['id'],
                'username': usuario['username'],
                'nome': usuario['nome'],
                'perfil': usuario['perfil']
            }
        }), 200

    except Exception as e:
        print(f'❌ Erro em verificar_senha_admin: {e}')
        traceback.print_exc()
        return jsonify({'ok': False, 'erro': 'Erro interno do servidor'}), 500
