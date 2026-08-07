// ============================================
// SISTEMA DE CACHE PARA REDUZIR REQUISIÇÕES
// ============================================

const cache = {
    escolas: null,
    turmas: {},
    alunos: {},
    provas: null,
    ultima_atualizacao: {}
};

const TEMPO_CACHE = 30000; // 30 segundos

function isCacheValido(chave) {
    if (!cache.ultima_atualizacao[chave]) return false;
    return (Date.now() - cache.ultima_atualizacao[chave]) < TEMPO_CACHE;
}

async function carregarEscolasComCache(forceRefresh = false) {
    if (!forceRefresh && cache.escolas && isCacheValido('escolas')) {
        return cache.escolas;
    }

    try {
        const response = await fetch(`${API_URL}/api/escolas`);
        const escolas = await response.json();
        cache.escolas = escolas;
        cache.ultima_atualizacao['escolas'] = Date.now();
        return escolas;
    } catch (erro) {
        console.error('Erro ao carregar escolas:', erro);
        return cache.escolas || [];
    }
}

async function carregarTurmasComCache(escolaId, forceRefresh = false) {
    const chave = `turmas_${escolaId}`;
    if (!forceRefresh && cache.turmas[chave] && isCacheValido(chave)) {
        return cache.turmas[chave];
    }

    try {
        let url = `${API_URL}/api/turmas`;
        if (escolaId && escolaId !== '') {
            url += `?escola_id=${escolaId}`;
        }
        const response = await fetch(url);
        const turmas = await response.json();
        cache.turmas[chave] = turmas;
        cache.ultima_atualizacao[chave] = Date.now();
        return turmas;
    } catch (erro) {
        console.error('Erro ao carregar turmas:', erro);
        return cache.turmas[chave] || [];
    }
}

async function carregarAlunosComCache(filtros = {}, forceRefresh = false) {
    const chave = JSON.stringify(filtros);
    if (!forceRefresh && cache.alunos[chave] && isCacheValido(chave)) {
        return cache.alunos[chave];
    }

    try {
        const params = new URLSearchParams();
        if (filtros.escola_id) params.append('escola_id', filtros.escola_id);
        if (filtros.turma_id) params.append('turma_id', filtros.turma_id);
        if (filtros.serie) params.append('serie', filtros.serie);

        let url = `${API_URL}/api/alunos`;
        if (params.toString()) url += '?' + params.toString();

        const response = await fetch(url);
        const alunos = await response.json();
        cache.alunos[chave] = alunos;
        cache.ultima_atualizacao[chave] = Date.now();
        return alunos;
    } catch (erro) {
        console.error('Erro ao carregar alunos:', erro);
        return cache.alunos[chave] || [];
    }
}

async function carregarProvasComCache(forceRefresh = false) {
    if (!forceRefresh && cache.provas && isCacheValido('provas')) {
        return cache.provas;
    }

    try {
        const response = await fetch(`${API_URL}/api/provas`);
        const provas = await response.json();
        cache.provas = provas;
        cache.ultima_atualizacao['provas'] = Date.now();
        return provas;
    } catch (erro) {
        console.error('Erro ao carregar provas:', erro);
        return cache.provas || [];
    }
}

// Função para limpar o cache (útil após salvar/editar/excluir)
function limparCache() {
    cache.escolas = null;
    cache.turmas = {};
    cache.alunos = {};
    cache.provas = null;
    cache.ultima_atualizacao = {};
    console.log('🧹 Cache limpo!');
}
