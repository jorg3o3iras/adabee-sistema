# ============================================================
# ROUTES/STATIC.PY — Servir arquivos estáticos + health
# (Blueprints renomeados para 'static_legacy' evitando conflito
#  com routes/static_files.py)
# ============================================================

import logging
import os

from flask import Blueprint, jsonify, send_file

from core.db import get_db_connection
from services.ia_fallback import (
    OPENAI_AVAILABLE,
    PYZBAR_AVAILABLE as _pyzbar_check,
)
from config import (
    DB_POOL_MAX,
    DB_POOL_MIN,
    OPENAI_MODEL,
    RELAY_AVAILABLE,
)


# ⚠️ IMPORTANTE: nome 'static_legacy' é ÚNICO, evita conflito com
# 'static_files' já registrado em routes/static_files.py
bp = Blueprint('static_legacy', __name__)


MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.eot': 'application/vnd.ms-fontobject',
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.xml': 'application/xml',
}


def _get_mimetype(filename):
    _, ext = os.path.splitext(filename.lower())
    return MIME_TYPES.get(ext, None)


@bp.route('/')
def index():
    try:
        if os.path.isfile('index.html'):
            return send_file('index.html', mimetype='text/html')
        return jsonify({
            'mensagem': 'CorrigePro API',
            'status': 'online',
            'aviso': 'index.html não encontrado'
        }), 200
    except Exception as e:
        logging.error(f"❌ Erro ao servir index.html: {e}")
        return jsonify({'mensagem': 'CorrigePro API', 'status': 'online'}), 200


@bp.route('/style.css')
def serve_css():
    try:
        if os.path.isfile('style.css'):
            logging.info("✅ Servindo style.css")
            return send_file('style.css', mimetype='text/css')
        logging.warning("⚠️ style.css não encontrado")
        return "/* style.css não encontrado */", 404, {'Content-Type': 'text/css'}
    except Exception as e:
        logging.error(f"❌ Erro ao servir style.css: {e}")
        return "/* erro */", 500, {'Content-Type': 'text/css'}


@bp.route('/script.js')
def serve_js():
    try:
        if os.path.isfile('script.js'):
            logging.info("✅ Servindo script.js")
            return send_file('script.js', mimetype='application/javascript')
        logging.warning("⚠️ script.js não encontrado")
        return "// script.js não encontrado", 404, {'Content-Type': 'application/javascript'}
    except Exception as e:
        logging.error(f"❌ Erro ao servir script.js: {e}")
        return "// erro", 500, {'Content-Type': 'application/javascript'}


@bp.route('/<path:filename>')
def serve_static_file(filename):
    try:
        if '..' in filename or filename.startswith('/'):
            logging.warning(f"⚠️ Path traversal bloqueado: {filename}")
            return jsonify({'erro': 'Caminho inválido'}), 400

        mimetype = _get_mimetype(filename)

        if os.path.isfile(filename):
            logging.info(f"✅ Servindo: {filename} ({mimetype})")
            return send_file(filename, mimetype=mimetype)

        logging.warning(f"⚠️ Arquivo não encontrado: {filename}")

        if filename.endswith('.css'):
            return "/* não encontrado */", 404, {'Content-Type': 'text/css'}
        if filename.endswith('.js'):
            return "// não encontrado", 404, {'Content-Type': 'application/javascript'}

        return jsonify({'erro': 'Arquivo não encontrado', 'path': filename}), 404

    except Exception as e:
        logging.error(f"❌ Erro ao servir {filename}: {e}")
        if filename.endswith('.css'):
            return "/* erro */", 500, {'Content-Type': 'text/css'}
        if filename.endswith('.js'):
            return "// erro", 500, {'Content-Type': 'application/javascript'}
        return jsonify({'erro': str(e)}), 500


@bp.route('/health', methods=['GET'])
def health_check():
    conn = get_db_connection()
    db_ok = conn is not None
    if conn:
        conn.close()

    arquivos = {
        'index.html': os.path.isfile('index.html'),
        'style.css': os.path.isfile('style.css'),
        'script.js': os.path.isfile('script.js'),
    }

    return jsonify({
        'status': 'online',
        'openai': 'disponível' if OPENAI_AVAILABLE else 'indisponível',
        'openai_modelo': OPENAI_MODEL if OPENAI_AVAILABLE else None,
        'relay': 'disponível' if RELAY_AVAILABLE else 'indisponível',
        'pyzbar': 'disponível' if _pyzbar_check else 'indisponível',
        'database': 'conectado' if db_ok else 'desconectado',
        'pool': {'min': DB_POOL_MIN, 'max': DB_POOL_MAX},
        'correcao': 'EvalBee v4 (A,B,C / A,B,C,D / A,B,C,D,E)',
        'versao': 'v4.0-EvalBee',
        'arquivos': arquivos
    })
