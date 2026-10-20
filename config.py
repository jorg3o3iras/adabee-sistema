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


# ═══ USUÁRIOS FIXOS (apenas DEV/TESTE) ═══
# ⚠️ IMPORTANTE:
#   - 'admin' com escola_id=None  → perfil admin vê TODAS as escolas
#   - 'usuario' / 'professor1' SEM escola → serão BLOQUEADOS pelo
#     get_escola_id() (retorna 403). Isso é intencional: força o cadastro
#     correto via banco (com escola_id) em produção.
#   - Em produção, remova este dicionário e use apenas a tabela `usuarios`.
USUARIOS_FIXOS = {
    'admin': {
        'senha': 'admin',
        'perfil': 'admin',
        'nome': 'Administrador',
        'escola_id': None,          # admin → sem filtro (vê tudo)
    },
    'usuario': {
        'senha': '123',
        'perfil': 'usuario',
        'nome': 'Usuário',
        'escola_id': None,          # ⚠️ sem escola → bloqueado
    },
    'professor1': {
        'senha': '123',
        'perfil': 'usuario',
        'nome': 'Professor 1',
        'escola_id': None,          # ⚠️ sem escola → bloqueado
    },
}
