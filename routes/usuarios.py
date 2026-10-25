# ============================================================
# ROUTES/USUARIOS.PY — CRUD de usuários (com escola_id)
# ============================================================

import traceback
from datetime import datetime

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from config import USUARIOS_FIXOS
from core.db import get_db_connection
from core.utils import get_usuario_atual


bp = Blueprint('usuarios', __name__, url_prefix='/api')


def _bloqueia_nao_admin():
    """Retorna uma resposta 403 se o usuário autenticado não for admin.
    Retorna None se for admin OU se não houver header (compatibilidade)."""
    u = get_usuario_atual()
    if u and u.get('perfil') != 'admin':
        return jsonify({'erro': 'Apenas administradores podem gerenciar usuários'}), 403
    return None


# ═══════════════════════════════════════════════════════════
# LISTAR
# ═══════════════════════════════════════════════════════════
@bp.route('/usuarios', methods=['GET'])
def listar_usuarios():
    bloqueio = _bloqueia_nao_admin()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT u.id, u.nome, u.username, u.email, u.perfil, u.ativo,
                       u.escola_id, e.nome AS escola_nome, u.criado_em
                FROM usuarios u
                LEFT JOIN escolas e ON e.id = u.escola_id
                ORDER BY u.id
            """)
            usuarios = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(usuarios)
        except Exception as e:
            print(f"Erro ao listar usuários: {e}")
            try: conn.close()
            except Exception: pass

    resultado = []
    for username, dados in USUARIOS_FIXOS.items():
        resultado.append({
            'id': 0, 'nome': dados['nome'], 'username': username,
            'email': '', 'perfil': dados['perfil'], 'ativo': True,
            'escola_id': dados.get('escola_id'), 'escola_nome': None,
            'criado_em': datetime.now().isoformat()
        })
    return jsonify(resultado)


# ═══════════════════════════════════════════════════════════
# CRIAR
# ═══════════════════════════════════════════════════════════
@bp.route('/usuarios', methods=['POST'])
def criar_usuario():
    bloqueio = _bloqueia_nao_admin()
    if bloqueio:
        return bloqueio

    try:
        data = request.json or {}
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)
        escola_id = data.get('escola_id')  # ← NOVO

        if not nome or not username or not senha:
            return jsonify({'erro': 'Nome, usuário e senha são obrigatórios'}), 400
        if len(senha) < 4:
            return jsonify({'erro': 'Senha deve ter pelo menos 4 caracteres'}), 400
        if perfil != 'admin' and not escola_id:
            return jsonify({'erro': 'Escola é obrigatória para usuários não administradores'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário já existe'}), 400

        if escola_id:
            cur.execute("SELECT id FROM escolas WHERE id = %s", (escola_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({'erro': 'Escola não encontrada'}), 404

        cur.execute("""
            INSERT INTO usuarios (nome, username, senha_hash, email, perfil, ativo, escola_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (nome, username, senha, email, perfil, ativo, escola_id))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'id': result['id'], 'mensagem': 'Usuário criado com sucesso'})

    except Exception as e:
        print(f"Erro ao criar usuário: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════
# BUSCAR
# ═══════════════════════════════════════════════════════════
@bp.route('/usuarios/<int:id>', methods=['GET'])
def buscar_usuario(id):
    bloqueio = _bloqueia_nao_admin()
    if bloqueio:
        return bloqueio

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.id, u.nome, u.username, u.email, u.perfil, u.ativo,
                   u.escola_id, e.nome AS escola_nome, u.criado_em
            FROM usuarios u
            LEFT JOIN escolas e ON e.id = u.escola_id
            WHERE u.id = %s
        """, (id,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if not usuario:
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        return jsonify(usuario)

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════
# ATUALIZAR
# ═══════════════════════════════════════════════════════════
@bp.route('/usuarios/<int:id>', methods=['PUT'])
def atualizar_usuario(id):
    bloqueio = _bloqueia_nao_admin()
    if bloqueio:
        return bloqueio

    try:
        data = request.json or {}
        nome = data.get('nome')
        username = data.get('username')
        senha = data.get('senha')
        email = data.get('email', '')
        perfil = data.get('perfil', 'usuario')
        ativo = data.get('ativo', True)
        escola_id = data.get('escola_id')  # ← NOVO

        if not nome or not username:
            return jsonify({'erro': 'Nome e usuário são obrigatórios'}), 400
        if len(username) < 3:
            return jsonify({'erro': 'Usuário deve ter pelo menos 3 caracteres'}), 400
        if perfil != 'admin' and not escola_id:
            return jsonify({'erro': 'Escola é obrigatória para usuários não administradores'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM usuarios WHERE id = %s", (id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        cur.execute("SELECT id FROM usuarios WHERE username = %s AND id != %s", (username, id))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'erro': 'Este nome de usuário já está em uso'}), 400

        if escola_id:
            cur.execute("SELECT id FROM escolas WHERE id = %s", (escola_id,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({'erro': 'Escola não encontrada'}), 404

        update_fields = ["nome = %s", "username = %s", "email = %s",
                         "perfil = %s", "ativo = %s", "escola_id = %s"]
        params = [nome, username, email, perfil, ativo, escola_id]

        if senha and len(senha) >= 4:
            update_fields.append("senha_hash = %s")
            params.append(senha)

        params.append(id)

        cur.execute(f"""
            UPDATE usuarios SET {', '.join(update_fields)}
            WHERE id = %s RETURNING id
        """, params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'id': result['id'], 'mensagem': 'Usuário atualizado com sucesso'})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500


# ═══════════════════════════════════════════════════════════
# EXCLUIR
# ═══════════════════════════════════════════════════════════
@bp.route('/usuarios/<int:id>', methods=['DELETE'])
def excluir_usuario(id):
    bloqueio = _bloqueia_nao_admin()
    if bloqueio:
        return bloqueio

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500

        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT username FROM usuarios WHERE id = %s", (id,))
        usuario = cur.fetchone()
        if not usuario:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado'}), 404

        username = usuario['username']

        if username == 'admin':
            cur.close()
            conn.close()
            return jsonify({'erro': 'Não é possível excluir o usuário administrador principal'}), 400

        cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'sucesso': True, 'mensagem': f'Usuário "{username}" excluído com sucesso'})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
