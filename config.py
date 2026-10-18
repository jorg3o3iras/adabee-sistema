# ============================================================
# CONFIG.PY — Configuração central (env vars, constantes, usuários)
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

# ═══ CACHE DE CORREÇÕES ═══
CORRECOES_CACHE_TTL_HORAS = 168  # 7 dias

# ═══ SUPABASE / POSTGRESQL ═══
SUPABASE_URL = os.getenv('SUPABASE_URL')
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '5'))
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '30'))

# ═══ OPENAI ═══
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# ═══ RELAY (fallback) ═══
RELAY_API_URL = os.getenv('RELAY_API_URL', '')
RELAY_API_KEY = os.getenv('RELAY_API_KEY', '')
RELAY_MODEL = os.getenv('RELAY_MODEL', 'gemini-1.5-flash')
RELAY_AVAILABLE = bool(RELAY_API_URL)

# ═══ USUÁRIOS FIXOS ═══
USUARIOS_FIXOS = {
    'admin': {'senha': 'admin', 'perfil': 'admin', 'nome': 'Administrador'},
    'usuario': {'senha': '123', 'perfil': 'usuario', 'nome': 'Usuário'},
    'professor1': {'senha': '123', 'perfil': 'usuario', 'nome': 'Professor 1'}
}
