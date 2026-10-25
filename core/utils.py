# ============================================================
# CORE/UTILS.PY — Funções auxiliares puras + contexto de escola
# ============================================================

import re
import logging

from flask import g, has_request_context, request


# ═══ EXCEÇÃO DE CONTEXTO ESCOLAR ═══
class SemEscolaException(Exception):
    """Levantada quando um usuário não-admin tenta acessar sem escola vinculada."""
    pass


# ═══ CONTEXTO DO USUÁRIO (via header X-Usuario-Username) ═══
def _carregar_usuario_atual():
    """
    Resolve o usuário da requisição atual a partir do header X-Usuario-Username.
    Consulta o banco; se não achar (ou banco indisponível), cai no USUARIOS_FIXOS.
    Cacheia em flask.g para não consultar 2x na mesma request.
    """
    if not has_request_context():
        return None
    if hasattr(g, '_usuario_atual'):
        return g._usuario_atual

    username = (request.headers.get('X-Usuario-Username') or '').strip()
    if not username:
        g._usuario_atual = None
        return None

    # 1) Banco de dados
    try:
        from core.db import get_db_connection
        from psycopg2.extras import RealDictCursor
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT u.id, u.nome, u.username, u.perfil, u.ativo,
                           u.escola_id, e.nome AS escola_nome
                    FROM usuarios u
                    LEFT JOIN escolas e ON e.id = u.escola_id
                    WHERE u.username = %s
                """, (username,))
                row = cur.fetchone()
                cur.close()
                if row:
                    d = dict(row)
                    d['ativo'] = bool(d.get('ativo'))
                    g._usuario_atual = d
                    return d
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    except Exception as e:
        logging.warning("get_usuario_atual: erro no banco: %s", e)

    # 2) Fallback: usuários fixos de DEV/TESTE
    try:
        from config import USUARIOS_FIXOS
        if username in USUARIOS_FIXOS:
            dados = USUARIOS_FIXOS[username]
            g._usuario_atual = {
                'id': 0,
                'nome': dados['nome'],
                'username': username,
                'perfil': dados['perfil'],
                'ativo': True,
                'escola_id': dados.get('escola_id'),
                'escola_nome': None,
            }
            return g._usuario_atual
    except Exception:
        pass

    g._usuario_atual = None
    return None


def get_usuario_atual():
    """Retorna dict {id, nome, username, perfil, escola_id, escola_nome, ativo} ou None."""
    return _carregar_usuario_atual()


def is_admin():
    u = _carregar_usuario_atual()
    return bool(u and u.get('perfil') == 'admin')


def get_escola_id():
    """
    Retorna o escola_id a ser usado como filtro nas queries.

    - Sem header X-Usuario-Username → None
      (compatibilidade: filtro não aplicado, comportamento legado)
    - Admin → None (vê TODAS as escolas)
    - Usuário ativo com escola → int escola_id
    - Usuário ativo SEM escola → levanta SemEscolaException (handler global devolve 403)
    """
    u = _carregar_usuario_atual()
    if not u:
        return None
    if not u.get('ativo', True):
        from werkzeug.exceptions import Forbidden
        raise Forbidden("Usuário inativo")
    if u.get('perfil') == 'admin':
        return None
    eid = u.get('escola_id')
    if not eid:
        raise SemEscolaException(
            "Usuário não possui escola vinculada. "
            "Peça ao administrador para associar uma escola ao seu cadastro."
        )
    return int(eid)


def aplicar_filtro_escola(query, params, escola_id, coluna='escola_id', prefixo='AND'):
    """Adiciona cláusula de filtro por escola. Retorna (query, params)."""
    if escola_id is None:
        return query, params
    query += f" {prefixo} {coluna} = %s"
    params.append(escola_id)
    return query, params


# ═══════════════════════════════════════════════════════════
# FUNÇÕES PURAS (inalteradas)
# ═══════════════════════════════════════════════════════════

def calcular_conceito(porcentagem):
    if porcentagem <= 40:
        return {'nome': 'inicial', 'rotulo': '🔴 Inicial', 'faixa': 'até 40%', 'cor': '#ef4444', 'badge': 'badge-conceito-inicial'}
    elif porcentagem <= 60:
        return {'nome': 'basico', 'rotulo': '🟠 Básico', 'faixa': '41% - 60%', 'cor': '#f59e0b', 'badge': 'badge-conceito-basico'}
    elif porcentagem <= 80:
        return {'nome': 'proficiente', 'rotulo': '🔵 Proficiente', 'faixa': '61% - 80%', 'cor': '#3b82f6', 'badge': 'badge-conceito-proficiente'}
    else:
        return {'nome': 'avancado', 'rotulo': '🟢 Avançado', 'faixa': 'acima de 80%', 'cor': '#10b981', 'badge': 'badge-conceito-avancado'}


def identificar_disciplina(prova_titulo, disciplina, serie):
    disciplina_lower = (disciplina or '').lower().strip()
    if re.search(r'\bportugu[êe]s\b', disciplina_lower) or 'língua' in disciplina_lower:
        return 'Portugues'
    if re.search(r'\bmatem[áa]tica\b', disciplina_lower):
        return 'Matematica'
    if re.search(r'\bprodu[cç][ãa]o\b', disciplina_lower) or 'texto' in disciplina_lower or 'redação' in disciplina_lower or 'redacao' in disciplina_lower:
        return 'Producao'
    if re.search(r'\bch\b', disciplina_lower) or 'ciencias humanas' in disciplina_lower:
        return 'CH'
    if re.search(r'\bcn\b', disciplina_lower) or 'ciencias naturais' in disciplina_lower:
        return 'CN'
    texto = f"{prova_titulo or ''}".lower()
    if re.search(r'\bportugu[êe]s\b', texto) or 'língua' in texto:
        return 'Portugues'
    if re.search(r'\bmatem[áa]tica\b', texto) or re.search(r'\bmat\b', texto):
        return 'Matematica'
    if re.search(r'\bprodu[cç][ãa]o\b', texto) or 'texto' in texto or 'redação' in texto or 'redacao' in texto:
        return 'Producao'
    if re.search(r'\bch\b', texto) or 'ciencias humanas' in texto:
        return 'CH'
    if re.search(r'\bcn\b', texto) or 'ciencias naturais' in texto:
        return 'CN'
    if serie:
        serie_num = re.search(r'(\d+)', serie)
        if serie_num:
            num = int(serie_num.group(1))
            if num <= 5:
                return 'Portugues'
            else:
                return 'Matematica'
    return 'Geral'


def extrair_mimetype(imagem_base64):
    if not imagem_base64:
        return 'image/jpeg'
    match = re.match(r'data:image/(\w+);base64,', imagem_base64)
    if match:
        tipo = match.group(1)
        return f'image/{tipo}'
    return 'image/jpeg'


def gerar_padrao_gabarito(gabarito, tipo_questoes=4):
    alternativas = ['A', 'B', 'C', 'D', 'E'][:tipo_questoes]
    padrao = {
        'total_questoes': len(gabarito),
        'alternativas': alternativas,
        'gabarito_oficial': gabarito,
        'questoes': []
    }
    for i, resp in enumerate(gabarito):
        padrao['questoes'].append({
            'numero': i + 1,
            'resposta_correta': resp.upper() if resp else None,
            'alternativas': alternativas,
            'posicao': i + 1
        })
    return padrao


def validar_gabarito(gabarito, tipo_questoes=4):
    if not gabarito or len(gabarito) == 0:
        return False
    try:
        tipo = int(tipo_questoes)
    except (ValueError, TypeError):
        tipo = 4
    tipo = max(3, min(tipo, 5))
    alternativas_validas = ['A', 'B', 'C', 'D', 'E'][:tipo]
    for g in gabarito:
        if not g or str(g).strip() == '':
            return False
        if str(g).upper().strip() not in alternativas_validas:
            return False
    return True


def validar_respostas(respostas, gabarito, alternativas):
    respostas_validas = []
    for i, resp in enumerate(respostas):
        if not resp or str(resp).strip() == '':
            respostas_validas.append('')
            continue
        resp_str = str(resp).upper().strip()
        if resp_str in alternativas:
            respostas_validas.append(resp_str)
        else:
            for alt in alternativas:
                if alt in resp_str:
                    respostas_validas.append(alt)
                    break
            else:
                respostas_validas.append('')
    while len(respostas_validas) < len(gabarito):
        respostas_validas.append('')
    return respostas_validas[:len(gabarito)]


def calcular_resultado_correcao(respostas, gabarito, aluno_nome, serie, disciplina, tipo_questoes, modo, circulos=None, bncc=None, confiancas=None):
    alternativas = ['A', 'B', 'C', 'D', 'E'][:tipo_questoes]
    acertos = 0
    correcoes = []
    questoes_status = []

    logging.info("=" * 60)
    logging.info(f"🔍 CORREÇÃO (Modo: {modo})")
    logging.info("-" * 60)
    logging.info(f"📋 GABARITO OFICIAL: {gabarito}")
    logging.info(f"📋 RESPOSTAS ALUNO: {respostas}")
    logging.info("-" * 60)

    for i in range(len(gabarito)):
        resp = respostas[i] if i < len(respostas) else ''
        gab = gabarito[i] if i < len(gabarito) else ''
        gab_normalizado = str(gab).strip().upper() if gab else ''

        confianca_q = 80
        if confiancas and i < len(confiancas):
            confianca_q = int(confiancas[i])

        codigo_bncc = ''
        if bncc and i < len(bncc):
            codigo_bncc = bncc[i] if bncc[i] else ''

        is_resposta_valida = resp in alternativas
        is_correto = False
        if is_resposta_valida and gab_normalizado:
            is_correto = (resp == gab_normalizado)
            if is_correto:
                acertos += 1

        if is_correto:
            status_msg = 'ADQUIRIU HABILIDADE ✅'
            status_icone = '✅'
        elif is_resposta_valida:
            status_msg = 'RECOMPOSIÇÃO DE APRENDIZAGEM ❌'
            status_icone = '❌'
        else:
            status_msg = 'NÃO RESPONDEU —'
            status_icone = '—'

        correcoes.append({
            'questao': i + 1, 'resposta': resp if resp else '—',
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'correto': is_correto, 'status': status_msg,
            'confianca': confianca_q if is_resposta_valida else 50, 'bncc': codigo_bncc
        })

        questoes_status.append({
            'numero': i + 1, 'resposta': resp if resp else '—',
            'gabarito': gab_normalizado if gab_normalizado else '—',
            'acertou': is_correto, 'status': status_msg,
            'status_texto': f"{status_icone} {status_msg}",
            'confianca': confianca_q if is_resposta_valida else 50,
            'correta': is_correto, 'bncc': codigo_bncc
        })

    valor_por_questao = 10 / len(gabarito) if len(gabarito) > 0 else 0
    nota = acertos * valor_por_questao
    porcentagem = round((acertos / len(gabarito)) * 100) if len(gabarito) > 0 else 0
    conceito = calcular_conceito(porcentagem)

    confianca_media = 70
    if confiancas:
        confianca_media = int(sum(confiancas) / len(confiancas)) if confiancas else 70

    questoes_suspeitas = []
    if confiancas:
        for i, c in enumerate(confiancas):
            if c < 50:
                questoes_suspeitas.append(i + 1)
    requer_revisao = len(questoes_suspeitas) > 0 or confianca_media < 60

    return {
        'aluno': aluno_nome, 'serie': serie, 'disciplina': disciplina,
        'total': len(gabarito), 'acertos': acertos, 'nota': round(nota, 1),
        'porcentagem': porcentagem, 'conceito': conceito,
        'respostas_detectadas': respostas, 'gabarito': gabarito,
        'correcoes': correcoes, 'questoes_status': questoes_status,
        'tipo_questoes': str(tipo_questoes),
        'confianca': confianca_media,
        'confianca_por_questao': confiancas if confiancas else [80 if r in alternativas else 50 for r in respostas],
        'modo': modo, 'valor_por_questao': round(valor_por_questao, 2),
        'circulos_detectados': len(circulos) if circulos else 0,
        'questoes_ia': 0, 'bncc': bncc if bncc else [],
        'requer_revisao_manual': requer_revisao,
        'questoes_suspeitas': questoes_suspeitas
    }


def erro_correcao(aluno_nome, serie, disciplina, erro_msg):
    conceito = calcular_conceito(0)
    return {
        'erro': erro_msg, 'aluno': aluno_nome, 'serie': serie,
        'disciplina': disciplina, 'total': 0, 'acertos': 0, 'nota': 0,
        'porcentagem': 0, 'conceito': conceito,
        'respostas_detectadas': [], 'gabarito': [], 'correcoes': [],
        'questoes_status': [], 'tipo_questoes': '4', 'confianca': 0,
        'confianca_por_questao': [], 'modo': 'erro',
        'valor_por_questao': 0, 'bncc': [],
        'requer_revisao_manual': False, 'questoes_suspeitas': []
    }
