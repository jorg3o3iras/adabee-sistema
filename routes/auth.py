@app.route('/api/verificar-senha-admin', methods=['POST'])
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
        cursor = conn.cursor()
        
        # Busca o usuário pelo username
        cursor.execute("""
            SELECT id, username, nome, senha, perfil, ativo
            FROM usuarios
            WHERE username = %s
        """, (username,))
        
        usuario = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not usuario:
            return jsonify({'ok': False, 'erro': 'Usuário não encontrado'}), 401
        
        # Verifica se está ativo
        if not usuario[5]:
            return jsonify({'ok': False, 'erro': 'Usuário inativo'}), 401
        
        # Verifica se é admin
        if usuario[4] != 'admin':
            return jsonify({'ok': False, 'erro': 'Apenas administradores podem acessar'}), 403
        
        # Verifica a senha (texto puro — o sistema atual usa assim)
        # ⚠️ Se no futuro usar hash (bcrypt/werkzeug), troque por: check_password_hash(usuario[3], senha)
        if usuario[3] != senha:
            return jsonify({'ok': False, 'erro': 'Senha incorreta'}), 401
        
        return jsonify({
            'ok': True,
            'usuario': {
                'id': usuario[0],
                'username': usuario[1],
                'nome': usuario[2],
                'perfil': usuario[4]
            }
        }), 200
        
    except Exception as e:
        print(f'❌ Erro em verificar_senha_admin: {e}')
        return jsonify({'ok': False, 'erro': 'Erro interno do servidor'}), 500