# ============================================================
# CORE/CACHE.PY — Cache persistente de correções (PostgreSQL)
# ⚠️ CORRIGIDO: CACHE_VERSION força invalidação de cache antigo
# ============================================================

import json
import logging

from psycopg2.extras import RealDictCursor

from core.db import get_db_connection
from config import CORRECOES_CACHE_TTL_HORAS


# ⚠️ Incrementar SEMPRE que a lógica de correção mudar.
# v2 = correção de MÚLTIPLA MARCAÇÃO (bug de dupla marcação = acerto)
CACHE_VERSION = 2


def init_cache_table():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS correcoes_cache (
                id SERIAL PRIMARY KEY,
                chave_hash TEXT NOT NULL,
                resultado JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_correcoes_cache_hash 
            ON correcoes_cache(chave_hash, created_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_correcoes_cache_created 
            ON correcoes_cache(created_at DESC)
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"✅ Tabela de cache de correções pronta (v{CACHE_VERSION})")
    except Exception as e:
        logging.warning(f"⚠️ Erro ao criar tabela de cache: {e}")


def get_cache_key(imagem_hash, prova_id, aluno_id):
    # Prefixo vN_ invalida automaticamente caches de versões anteriores
    return f"v{CACHE_VERSION}_{imagem_hash}_{prova_id}_{aluno_id}"


def get_cache_correcao(chave):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT resultado FROM correcoes_cache
            WHERE chave_hash = %s
            AND created_at > NOW() - INTERVAL '%s hours'
            ORDER BY created_at DESC
            LIMIT 1
        """, (chave, CORRECOES_CACHE_TTL_HORAS))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row['resultado'] if isinstance(row['resultado'], dict) else json.loads(row['resultado'])
        return None
    except Exception as e:
        logging.warning(f"⚠️ Erro ao buscar cache: {e}")
        return None


def set_cache_correcao(chave, resultado):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO correcoes_cache (chave_hash, resultado)
            VALUES (%s, %s::jsonb)
        """, (chave, json.dumps(resultado, default=str)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.warning(f"⚠️ Erro ao salvar cache: {e}")


def limpar_cache_antigo():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM correcoes_cache
            WHERE created_at < NOW() - INTERVAL '%s hours'
        """, (CORRECOES_CACHE_TTL_HORAS,))
        removidas = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if removidas > 0:
            logging.info(f"🧹 Cache antigo limpo: {removidas} entradas")
    except Exception as e:
        logging.warning(f"⚠️ Erro ao limpar cache: {e}")
