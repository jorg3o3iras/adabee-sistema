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
# 🔒 VERIFICAR SENHA ADMIN (protege a tela de Configurações)
# Aceita usuários da TABELA + fallback em USUARIOS_FIXOS
# ═══════════════════════════════════════════════════════════════
@bp.route('/verificar-senha-admin', methods=['POST'])
def verificar_senha_admin():
    """
    Verifica se a senha enviada pertence a um usuário ADMIN.
    Ordem de checagem:
      1) Tabela `usuarios`
      2) Fallback em `USUARIOS_FIXOS` (dev/teste — ex: 'admin' / 'admin')
    """
    try:
        data = request.get_json() or {}
        senha = data.get('senha', '').strip()
        username = data.get('username', '').strip()

        if not senha or not username:
            return jsonify({'ok': False, 'erro': 'Usuário e senha são obrigatórios'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'ok': False, 'erro': 'Banco indisponível'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, username, nome, senha_hash, perfil, ativo
            FROM usuarios
            WHERE username = %s
        """, (username,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        # ── 1) Usuário existe na TABELA ──
        if usuario:
            if not usuario['ativo']:
                return jsonify({'ok': False, 'erro': 'Usuário inativo'}), 401
            if usuario['perfil'] != 'admin':
                return jsonify({'ok': False, 'erro': 'Apenas administradores podem acessar'}), 403
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

        # ── 2) Fallback: USUARIOS_FIXOS (DEV/TESTE) ──
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            if dados.get('perfil') != 'admin':
                return jsonify({'ok': False, 'erro': 'Apenas administradores podem acessar'}), 403
            if not hmac.compare_digest(str(dados['senha']), str(senha)):
                return jsonify({'ok': False, 'erro': 'Senha incorreta'}), 401
            return jsonify({
                'ok': True,
                'usuario': {
                    'id': 0,
                    'username': username,
                    'nome': dados['nome'],
                    'perfil': dados['perfil']
                }
            }), 200

        # ── 3) Não achou em nenhum dos dois ──
        return jsonify({'ok': False, 'erro': 'Usuário não encontrado'}), 401

    except Exception as e:
        print(f'❌ Erro em verificar_senha_admin: {e}')
        traceback.print_exc()
        return jsonify({'ok': False, 'erro': 'Erro interno do servidor'}), 500
