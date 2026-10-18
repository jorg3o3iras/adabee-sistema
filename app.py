# ============================================================
# APP.PY — Entry point enxuto (após modularização)
# ============================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
cv2.setNumThreads(1)

import logging

from flask_compress import Compress

from config import (
    DB_POOL_MAX,
    DB_POOL_MIN,
    OPENAI_MODEL,
    RELAY_AVAILABLE,
    USUARIOS_FIXOS,
)
from core.cache import init_cache_table, limpar_cache_antigo
from core.db import init_db
from services.ia_fallback import OPENAI_AVAILABLE, PYZBAR_AVAILABLE


# ═══ APP ═══
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
Compress(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# ═══ MIDDLEWARE: garante JSON mesmo em erro ═══
@app.after_request
def after_request(response):
    if request.path.startswith('/api/') and response.status_code != 200:
        if not response.headers.get('Content-Type', '').startswith('application/json'):
            try:
                if 'text/html' in response.headers.get('Content-Type', ''):
                    response = jsonify({
                        'erro': 'Erro interno do servidor',
                        'status': response.status_code,
                        'detalhes': 'A requisição retornou HTML em vez de JSON'
                    })
                    response.status_code = 500
            except Exception:
                pass
    return response


# ═══ BLUEPRINTS ═══
from routes.auth import bp as auth_bp
from routes.cadastros import bp as cadastros_bp
from routes.correcao import bp as correcao_bp
from routes.redacao import bp as redacao_bp
from routes.historico import bp as historico_bp
from routes.gabaritos import bp as gabaritos_bp
from routes.usuarios import bp as usuarios_bp
from routes.dashboard import bp as dashboard_bp
from routes.matrizes import bp as matrizes_bp
from routes.cartao import bp as cartao_bp
from routes.backup import bp as backup_bp
from routes.static_files import bp as static_files_bp

app.register_blueprint(auth_bp)
app.register_blueprint(cadastros_bp)
app.register_blueprint(correcao_bp)
app.register_blueprint(redacao_bp)
app.register_blueprint(historico_bp)
app.register_blueprint(gabaritos_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(matrizes_bp)
app.register_blueprint(cartao_bp)
app.register_blueprint(backup_bp)
app.register_blueprint(static_files_bp)


# ═══ INIT ═══
try:
    init_db()
    init_cache_table()
    limpar_cache_antigo()
except Exception as e:
    logging.error(f"⚠️ Erro na inicialização automática: {e}")


# ═══ RUN ═══
if __name__ == '__main__':
    import os

    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 SERVIDOR CORRIGEPRO v4.1 — MODULARIZADO")
    print("=" * 60)
    print(f"📌 Porta: {port}")
    print(f"📌 Pool de conexões: {DB_POOL_MIN}-{DB_POOL_MAX}")
    print(f"🤖 OpenAI (ChatGPT): {'✅ Disponível' if OPENAI_AVAILABLE else '❌ Indisponível'}")
    if OPENAI_AVAILABLE:
        print(f"📌 Modelo: {OPENAI_MODEL}")
    print(f"📷 pyzbar (QR Code): {'✅ Disponível' if PYZBAR_AVAILABLE else '❌ Indisponível'}")
    print("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)