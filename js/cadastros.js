// ============================================================
// JS/CADASTROS.JS — Escolas, Turmas, Alunos (Frontend)
// ============================================================

let escolasCache = null;
let turmasCache = null;
let alunosCache = null;

function limparCache() {
    escolasCache = null;
    turmasCache = null;
    alunosCache = null;
    if (typeof cache !== 'undefined' && cache) {
        cache.escolas = null;
        cache.turmas = {};
        cache.alunos = {};
        cache.provas = null;
        cache.ultima_atualizacao = {};
    }
}

async function _fetchJSON(url, opcoes) {
    try {
        const r = await apiFetch(url, opcoes);
        if (!r.ok) {
            const txt = await r.text();
            throw new Error(`HTTP ${r.status}: ${txt.slice(0, 200)}`);
        }
        return await r.json();
    } catch (e) {
        console.error('❌ fetch falhou:', url, e.message);
        throw e;
    }
}

/* ───────── ESCOLAS ───────── */
async function carregarEscolasComCache(forceRefresh) {
    if (!forceRefresh && escolasCache) return escolasCache;
    try {
        const escolas = await _fetchJSON(API_URL + '/api/escolas');
        escolasCache = escolas || [];
        return escolasCache;
    } catch (e) {
        console.error('Erro ao carregar escolas:', e);
        return [];
    }
}

async function carregarEscolas() {
    const escolas = await carregarEscolasComCache(true);
    const tbody = document.getElementById('tb-escola');
    if (!tbody) return;
    if (!escolas || escolas.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma escola cadastrada</td></tr>';
        return;
    }
    let turmas = [];
    try { turmas = await carregarTurmasComCache(); } catch (e) {}

    tbody.innerHTML = escolas.map((e, i) => {
        const totalTurmas = turmas.filter(t => t.escola_id == e.id).length;
        const totalAlunos = turmas.filter(t => t.escola_id == e.id)
            .reduce((acc, t) => acc + (parseInt(t.total_alunos) || 0), 0);
        return `<tr data-id="${e.id}" data-nome="${escapeAttr(e.nome || '')}">
            <td><span class="badge badge-blue">${String(i + 1).padStart(3, '0')}</span></td>
            <td><strong>${escapeHtml(e.nome || '—')}</strong></td>
            <td>${escapeHtml(e.municipio || '—')}</td>
            <td><span class="chip">${escapeHtml(e.inep || '—')}</span></td>
            <td>${escapeHtml(e.diretor || '—')}</td>
            <td><span class="badge badge-blue">${totalTurmas}</span></td>
            <td><span class="badge badge-green">${totalAlunos}</span></td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="editarEscola(${e.id})" title="Editar">✏️</button>
                    <button class="btn-del" onclick="excluirEscola(${e.id}, '${escapeAttr(e.nome || '')}')" title="Excluir">🗑️</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

async function salvarEscola() {
    const nome = document.getElementById('escola-nome')?.value.trim();
    if (!nome) { showToast('❌ Nome é obrigatório!', 'error'); return; }
    const dados = {
        nome,
        inep: document.getElementById('escola-inep')?.value.trim() || '',
        municipio: document.getElementById('escola-municipio')?.value.trim() || '',
        estado: document.getElementById('escola-estado')?.value || 'PA',
        telefone: document.getElementById('escola-telefone')?.value.trim() || '',
        diretor: document.getElementById('escola-diretor')?.value.trim() || ''
    };
    try {
        const result = await _fetchJSON(API_URL + '/api/escolas', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Escola "' + nome + '" cadastrada!', 'success');
        limparCache(); closeM('m-escola'); carregarEscolas();
        if (typeof carregarCombos === 'function') carregarCombos();
        if (typeof carregarDashboard === 'function') carregarDashboard();
        if (result && result.id && typeof tableFeedback !== 'undefined') {
            setTimeout(() => tableFeedback.destacarLinha('tb-escola', result.id, '✅ Nova!'), 300);
        }
    } catch (e) { showToast('❌ Erro ao salvar escola: ' + e.message, 'error'); }
}

async function editarEscola(id) {
    try {
        const escola = await _fetchJSON(API_URL + '/api/escolas/' + id);
        document.getElementById('editar-escola-id').value = id;
        document.getElementById('editar-escola-nome').value = escola.nome || '';
        document.getElementById('editar-escola-inep').value = escola.inep || '';
        document.getElementById('editar-escola-municipio').value = escola.municipio || '';
        document.getElementById('editar-escola-estado').value = escola.estado || 'PA';
        document.getElementById('editar-escola-telefone').value = escola.telefone || '';
        document.getElementById('editar-escola-diretor').value = escola.diretor || '';
        openM('m-editar-escola');
    } catch (e) { showToast('❌ Erro ao carregar escola: ' + e.message, 'error'); }
}

async function salvarEdicaoEscola() {
    const id = document.getElementById('editar-escola-id').value;
    const dados = {
        nome: document.getElementById('editar-escola-nome').value.trim(),
        inep: document.getElementById('editar-escola-inep').value.trim(),
        municipio: document.getElementById('editar-escola-municipio').value.trim(),
        estado: document.getElementById('editar-escola-estado').value,
        telefone: document.getElementById('editar-escola-telefone').value.trim(),
        diretor: document.getElementById('editar-escola-diretor').value.trim()
    };
    if (!dados.nome) { showToast('❌ Nome é obrigatório!', 'error'); return; }
    try {
        await _fetchJSON(API_URL + '/api/escolas/' + id, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Escola atualizada!', 'success');
        limparCache(); closeM('m-editar-escola'); carregarEscolas();
        if (typeof carregarCombos === 'function') carregarCombos();
    } catch (e) { showToast('❌ Erro ao atualizar: ' + e.message, 'error'); }
}

async function excluirEscola(id, nome) {
    if (!confirm(`Excluir a escola "${nome}"?\n\nATENÇÃO: Turmas e alunos vinculados também serão removidos!`)) return;
    try {
        await _fetchJSON(API_URL + '/api/escolas/' + id, { method: 'DELETE' });
        showToast('🗑️ Escola excluída!', 'success');
        limparCache(); carregarEscolas();
        if (typeof carregarTurmas === 'function') carregarTurmas();
        if (typeof carregarAlunos === 'function') carregarAlunos();
        if (typeof carregarCombos === 'function') carregarCombos();
        if (typeof carregarDashboard === 'function') carregarDashboard();
    } catch (e) { showToast('❌ Erro ao excluir: ' + e.message, 'error'); }
}

/* ───────── TURMAS ───────── */
async function carregarTurmasComCache(escolaId, forceRefresh) {
    if (!forceRefresh && turmasCache && !escolaId) return turmasCache;
    try {
        const url = API_URL + '/api/turmas' + (escolaId ? `?escola_id=${escolaId}` : '');
        const turmas = await _fetchJSON(url);
        if (!escolaId) turmasCache = turmas || [];
        return turmas || [];
    } catch (e) { console.error('Erro ao carregar turmas:', e); return []; }
}

async function carregarTurmas() {
    const turmas = await carregarTurmasComCache(null, true);
    const tbody = document.getElementById('tb-turmas');
    if (!tbody) return;
    if (!turmas || turmas.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma turma cadastrada</td></tr>';
        return;
    }
    const corMap = {
        '1º Ano': 'badge-purple', '2º Ano': 'badge-purple', '3º Ano': 'badge-blue',
        '4º Ano': 'badge-blue', '5º Ano': 'badge-blue', '6º Ano': 'badge-cyan',
        '7º Ano': 'badge-cyan', '8º Ano': 'badge-orange', '9º Ano': 'badge-orange'
    };
    tbody.innerHTML = turmas.map((t, i) => {
        const totalAlunos = parseInt(t.total_alunos) || 0;
        return `<tr data-id="${t.id}" data-nome="${escapeAttr(t.nome || '')}" data-serie="${escapeAttr(t.serie || '')}" data-escola="${t.escola_id}">
            <td><span class="badge badge-gray">${String(i + 1).padStart(2, '0')}</span></td>
            <td><strong>${escapeHtml(t.nome || '—')}</strong></td>
            <td><span class="badge ${corMap[t.serie] || 'badge-blue'}">${escapeHtml(t.serie || '—')}</span></td>
            <td>${escapeHtml(t.turno || '—')}</td>
            <td>${escapeHtml(t.escola_nome || '—')}</td>
            <td>${escapeHtml(t.professor || '—')}</td>
            <td><span class="badge badge-blue">${totalAlunos}</span></td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="editarTurma(${t.id})" title="Editar">✏️</button>
                    <button class="btn btn-green btn-sm" onclick="verAlunosDaTurma(${t.id})" title="Lista de Alunos">📋</button>
                    <button class="btn-del" onclick="excluirTurma(${t.id}, '${escapeAttr(t.nome || '')}')" title="Excluir">🗑️</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

async function salvarTurma() {
    const nome = document.getElementById('turma-nome')?.value.trim();
    const escolaId = document.getElementById('turma-escola')?.value;
    if (!nome) { showToast('❌ Nome é obrigatório!', 'error'); return; }
    if (!escolaId) { showToast('❌ Selecione a escola!', 'error'); return; }
    const dados = {
        nome, escola_id: parseInt(escolaId),
        serie: document.getElementById('turma-serie')?.value || '1º Ano',
        turno: document.getElementById('turma-turno')?.value || 'Manhã',
        professor: document.getElementById('turma-professor')?.value.trim() || '',
        capacidade: parseInt(document.getElementById('turma-capacidade')?.value || 35),
        ano_letivo: parseInt(document.getElementById('turma-ano')?.value || 2025)
    };
    try {
        const result = await _fetchJSON(API_URL + '/api/turmas', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Turma criada!', 'success');
        limparCache(); closeM('m-turma'); carregarTurmas();
        if (typeof carregarCombos === 'function') carregarCombos();
        if (typeof carregarDashboard === 'function') carregarDashboard();
        if (result && result.id && typeof tableFeedback !== 'undefined') {
            setTimeout(() => tableFeedback.destacarLinha('tb-turmas', result.id, '✅ Nova!'), 300);
        }
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

async function editarTurma(id) {
    try {
        const turma = await _fetchJSON(API_URL + '/api/turmas/' + id);
        await carregarEscolasComCache();
        const selEscola = document.getElementById('editar-turma-escola');
        if (selEscola) {
            selEscola.innerHTML = '<option value="">Selecione</option>' +
                escolasCache.map(e => `<option value="${e.id}" ${e.id == turma.escola_id ? 'selected' : ''}>${escapeHtml(e.nome)}</option>`).join('');
        }
        document.getElementById('editar-turma-id').value = id;
        document.getElementById('editar-turma-nome').value = turma.nome || '';
        document.getElementById('editar-turma-serie').value = turma.serie || '1º Ano';
        document.getElementById('editar-turma-turno').value = turma.turno || 'Manhã';
        document.getElementById('editar-turma-professor').value = turma.professor || '';
        document.getElementById('editar-turma-capacidade').value = turma.capacidade || 35;
        document.getElementById('editar-turma-ano').value = turma.ano_letivo || 2025;
        openM('m-editar-turma');
    } catch (e) { showToast('❌ Erro ao carregar: ' + e.message, 'error'); }
}

async function salvarEdicaoTurma() {
    const id = document.getElementById('editar-turma-id').value;
    const dados = {
        nome: document.getElementById('editar-turma-nome').value.trim(),
        escola_id: parseInt(document.getElementById('editar-turma-escola').value),
        serie: document.getElementById('editar-turma-serie').value,
        turno: document.getElementById('editar-turma-turno').value,
        professor: document.getElementById('editar-turma-professor').value.trim(),
        capacidade: parseInt(document.getElementById('editar-turma-capacidade').value || 35),
        ano_letivo: parseInt(document.getElementById('editar-turma-ano').value || 2025)
    };
    if (!dados.nome || !dados.escola_id) { showToast('❌ Preencha todos os campos!', 'error'); return; }
    try {
        await _fetchJSON(API_URL + '/api/turmas/' + id, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Turma atualizada!', 'success');
        limparCache(); closeM('m-editar-turma'); carregarTurmas();
        if (typeof carregarCombos === 'function') carregarCombos();
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

async function excluirTurma(id, nome) {
    if (!confirm(`Excluir a turma "${nome}"?\n\nAlunos vinculados também serão removidos!`)) return;
    try {
        await _fetchJSON(API_URL + '/api/turmas/' + id, { method: 'DELETE' });
        showToast('🗑️ Turma excluída!', 'success');
        limparCache(); carregarTurmas();
        if (typeof carregarAlunos === 'function') carregarAlunos();
        if (typeof carregarCombos === 'function') carregarCombos();
        if (typeof carregarDashboard === 'function') carregarDashboard();
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

function verAlunosDaTurma(turmaId) {
    const selTurma = document.getElementById('filtro-turma-alunos');
    if (selTurma) {
        const opt = Array.from(selTurma.options).find(o => o.value == turmaId);
        if (opt) selTurma.value = turmaId;
    }
    go('alunos');
}

/* ───────── ALUNOS ───────── */
async function carregarAlunosComCache(filtros, forceRefresh) {
    if (!forceRefresh && !filtros && alunosCache) return alunosCache;
    try {
        let url = API_URL + '/api/alunos';
        const params = [];
        if (filtros) {
            if (filtros.escola_id) params.push('escola_id=' + filtros.escola_id);
            if (filtros.turma_id) params.push('turma_id=' + filtros.turma_id);
            if (filtros.serie) params.push('serie=' + encodeURIComponent(filtros.serie));
        }
        if (params.length) url += '?' + params.join('&');
        const alunos = await _fetchJSON(url);
        if (!filtros) alunosCache = alunos || [];
        return alunos || [];
    } catch (e) { console.error('Erro ao carregar alunos:', e); return []; }
}

async function carregarAlunos(escolaId) {
    const turmaId = document.getElementById('filtro-turma-alunos')?.value;
    const serie = document.getElementById('filtro-serie-alunos')?.value;
    const filtros = {};
    if (escolaId) filtros.escola_id = escolaId;
    if (turmaId) filtros.turma_id = turmaId;
    if (serie) filtros.serie = serie;
    const alunos = await carregarAlunosComCache(filtros, true);
    const tbody = document.getElementById('tb-alunos');
    if (!tbody) return;
    if (!alunos || alunos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhum aluno encontrado</td></tr>';
        return;
    }
    const corMap = {
        '1º Ano': 'badge-purple', '2º Ano': 'badge-purple', '3º Ano': 'badge-blue',
        '4º Ano': 'badge-blue', '5º Ano': 'badge-blue', '6º Ano': 'badge-cyan',
        '7º Ano': 'badge-cyan', '8º Ano': 'badge-orange', '9º Ano': 'badge-orange'
    };
    tbody.innerHTML = alunos.map((a, i) => {
        const dataNasc = a.data_nascimento ? formatarData(a.data_nascimento) : '—';
        return `<tr data-id="${a.id}" data-escola="${a.escola_id}" data-serie="${escapeAttr(a.turma_serie || '')}">
            <td><span class="badge badge-blue">${String(a.numero_chamada || (i + 1)).padStart(2, '0')}</span></td>
            <td><span class="chip">${escapeHtml(a.matricula || '—')}</span></td>
            <td><strong>${escapeHtml(a.nome || '—')}</strong></td>
            <td><span class="badge ${corMap[a.turma_serie] || 'badge-blue'}">${escapeHtml(a.turma_serie || '—')}</span></td>
            <td>${escapeHtml(a.turma_nome || '—')}</td>
            <td>${escapeHtml(a.escola_nome || '—')}</td>
            <td>${dataNasc}</td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="editarAluno(${a.id})" title="Editar">✏️</button>
                    <button class="btn-del" onclick="excluirAluno(${a.id}, '${escapeAttr(a.nome || '')}')" title="Excluir">🗑️</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

async function salvarAluno() {
    const nome = document.getElementById('aluno-nome')?.value.trim();
    const escolaId = document.getElementById('aluno-escola')?.value;
    const turmaId = document.getElementById('aluno-turma')?.value;
    if (!nome) { showToast('❌ Nome é obrigatório!', 'error'); return; }
    if (!escolaId) { showToast('❌ Selecione a escola!', 'error'); return; }
    if (!turmaId) { showToast('❌ Selecione a turma!', 'error'); return; }
    const dados = {
        nome, escola_id: parseInt(escolaId), turma_id: parseInt(turmaId),
        matricula: document.getElementById('aluno-matricula')?.value.trim() || '',
        numero_chamada: parseInt(document.getElementById('aluno-numero')?.value) || null,
        data_nascimento: document.getElementById('aluno-nascimento')?.value || null,
        genero: document.getElementById('aluno-genero')?.value || 'Masculino',
        responsavel: document.getElementById('aluno-responsavel')?.value.trim() || '',
        telefone: document.getElementById('aluno-telefone')?.value.trim() || '',
        email: document.getElementById('aluno-email')?.value.trim() || '',
        observacoes: document.getElementById('aluno-observacoes')?.value.trim() || ''
    };
    try {
        const result = await _fetchJSON(API_URL + '/api/alunos', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Aluno cadastrado!', 'success');
        limparCache(); closeM('m-aluno'); carregarAlunos(escolaId);
        if (typeof carregarCombos === 'function') carregarCombos();
        if (typeof carregarDashboard === 'function') carregarDashboard();
        if (result && result.id && typeof tableFeedback !== 'undefined') {
            setTimeout(() => tableFeedback.destacarLinha('tb-alunos', result.id, '✅ Novo!'), 300);
        }
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

async function editarAluno(id) {
    try {
        const aluno = await _fetchJSON(API_URL + '/api/alunos/' + id);
        await carregarEscolasComCache();
        const selEscola = document.getElementById('editar-aluno-escola');
        if (selEscola) {
            selEscola.innerHTML = '<option value="">Selecione</option>' +
                escolasCache.map(e => `<option value="${e.id}" ${e.id == aluno.escola_id ? 'selected' : ''}>${escapeHtml(e.nome)}</option>`).join('');
        }
        const turmas = await carregarTurmasComCache(aluno.escola_id);
        const selTurma = document.getElementById('editar-aluno-turma');
        if (selTurma) {
            selTurma.innerHTML = '<option value="">Selecione</option>' +
                turmas.map(t => `<option value="${t.id}" ${t.id == aluno.turma_id ? 'selected' : ''}>${escapeHtml(t.nome)} - ${escapeHtml(t.serie || '')}</option>`).join('');
        }
        document.getElementById('editar-aluno-id').value = id;
        document.getElementById('editar-aluno-nome').value = aluno.nome || '';
        document.getElementById('editar-aluno-matricula').value = aluno.matricula || '';
        document.getElementById('editar-aluno-numero').value = aluno.numero_chamada || '';
        document.getElementById('editar-aluno-nascimento').value = aluno.data_nascimento ? aluno.data_nascimento.slice(0, 10) : '';
        document.getElementById('editar-aluno-genero').value = aluno.genero || 'Masculino';
        document.getElementById('editar-aluno-responsavel').value = aluno.responsavel || '';
        document.getElementById('editar-aluno-telefone').value = aluno.telefone || '';
        document.getElementById('editar-aluno-email').value = aluno.email || '';
        document.getElementById('editar-aluno-observacoes').value = aluno.observacoes || '';
        openM('m-editar-aluno');
    } catch (e) { showToast('❌ Erro ao carregar aluno: ' + e.message, 'error'); }
}

async function salvarEdicaoAluno() {
    const id = document.getElementById('editar-aluno-id').value;
    const dados = {
        nome: document.getElementById('editar-aluno-nome').value.trim(),
        escola_id: parseInt(document.getElementById('editar-aluno-escola').value),
        turma_id: parseInt(document.getElementById('editar-aluno-turma').value),
        matricula: document.getElementById('editar-aluno-matricula').value.trim(),
        numero_chamada: parseInt(document.getElementById('editar-aluno-numero').value) || null,
        data_nascimento: document.getElementById('editar-aluno-nascimento').value || null,
        genero: document.getElementById('editar-aluno-genero').value,
        responsavel: document.getElementById('editar-aluno-responsavel').value.trim(),
        telefone: document.getElementById('editar-aluno-telefone').value.trim(),
        email: document.getElementById('editar-aluno-email').value.trim(),
        observacoes: document.getElementById('editar-aluno-observacoes').value.trim()
    };
    if (!dados.nome || !dados.escola_id || !dados.turma_id) { showToast('❌ Preencha todos os campos obrigatórios!', 'error'); return; }
    try {
        await _fetchJSON(API_URL + '/api/alunos/' + id, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Aluno atualizado!', 'success');
        limparCache(); closeM('m-editar-aluno'); carregarAlunos();
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

async function excluirAluno(id, nome) {
    if (!confirm(`Excluir o aluno "${nome}"?`)) return;
    try {
        await _fetchJSON(API_URL + '/api/alunos/' + id, { method: 'DELETE' });
        showToast('🗑️ Aluno excluído!', 'success');
        limparCache(); carregarAlunos();
        if (typeof carregarCombos === 'function') carregarCombos();
        if (typeof carregarDashboard === 'function') carregarDashboard();
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

/* ───────── COMBOS ───────── */
async function carregarEscolasFiltroAlunos() {
    const escolas = await carregarEscolasComCache();
    const sel = document.getElementById('filtro-escola-alunos');
    if (!sel) return;
    sel.innerHTML = '<option value="">Todas as escolas</option>' +
        escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
}

async function carregarFiltroEscolaTurmas() {
    const escolas = await carregarEscolasComCache();
    const sel = document.getElementById('filtro-escola-turmas');
    if (!sel) return;
    sel.innerHTML = '<option value="">Todas as escolas</option>' +
        escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
}

async function carregarTurmasPorEscolaParaAluno(escolaId, targetId) {
    const sel = document.getElementById(targetId);
    if (!sel) return;
    if (!escolaId) { sel.innerHTML = '<option value="">Selecione a escola primeiro</option>'; return; }
    const turmas = await carregarTurmasComCache(escolaId);
    sel.innerHTML = '<option value="">Selecione a turma</option>' +
        turmas.map(t => `<option value="${t.id}" data-serie="${escapeAttr(t.serie || '')}">${escapeHtml(t.nome)} - ${escapeHtml(t.serie || '')}</option>`).join('');
}

async function carregarTurmasFiltroAlunos(escolaId) {
    const sel = document.getElementById('filtro-turma-alunos');
    if (!sel) return;
    if (!escolaId) { sel.innerHTML = '<option value="">Todas as turmas</option>'; return; }
    try {
        const turmas = await carregarTurmasComCache(escolaId);
        sel.innerHTML = '<option value="">Todas as turmas</option>' +
            turmas.map(t => `<option value="${t.id}">${escapeHtml(t.nome)}</option>`).join('');
    } catch (e) { sel.innerHTML = '<option value="">Todas as turmas</option>'; }
}

function filtrarAlunosPorEscola(escolaId) {
    carregarTurmasFiltroAlunos(escolaId);
    carregarAlunos(escolaId);
}

function filtrarAlunosPorSerie(serie) {
    const escolaId = document.getElementById('filtro-escola-alunos')?.value || '';
    carregarAlunos(escolaId);
}

function aplicarFiltrosTurmas() {
    const escolaId = document.getElementById('filtro-escola-turmas')?.value || '';
    const serie = document.getElementById('filtro-serie-turmas')?.value || '';
    document.querySelectorAll('#tb-turmas tr').forEach(row => {
        let ok = true;
        if (escolaId && row.dataset.escola !== escolaId) ok = false;
        if (serie && row.dataset.serie !== serie) ok = false;
        row.style.display = ok ? '' : 'none';
    });
}

function limparFiltrosTurmas() {
    const f1 = document.getElementById('filtro-escola-turmas');
    const f2 = document.getElementById('filtro-serie-turmas');
    if (f1) f1.value = '';
    if (f2) f2.value = '';
    document.querySelectorAll('#tb-turmas tr').forEach(r => r.style.display = '');
}

async function carregarTurmasLista(escolaId) {
    const sel = document.getElementById('lista-turma');
    if (!sel) return;
    if (!escolaId) { sel.innerHTML = '<option value="">Selecione a turma</option>'; return; }
    try {
        const turmas = await carregarTurmasComCache(escolaId);
        sel.innerHTML = '<option value="">Selecione a turma</option>' +
            turmas.map(t => `<option value="${t.id}">${escapeHtml(t.nome)} - ${escapeHtml(t.serie || '')}</option>`).join('');
    } catch (e) { sel.innerHTML = '<option value="">Selecione a turma</option>'; }
}

async function carregarEscolasTexto() {
    try {
        const escolas = await carregarEscolasComCache();
        const sel = document.getElementById('txt-escola');
        if (!sel) return;
        sel.innerHTML = '<option value="">Selecione a escola...</option>' +
            escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
    } catch (e) { console.error('Erro ao carregar escolas para texto:', e); }
}

async function carregarCombos() {
    try {
        const escolas = await carregarEscolasComCache();
        const turmas = await carregarTurmasComCache();
        const alunos = await carregarAlunosComCache();
        const idsEscola = [
            'turma-escola', 'aluno-escola', 'editar-turma-escola', 'editar-aluno-escola',
            'lista-escola', 'transf-escola-origem', 'transf-escola-destino',
            'rel-turma-escola', 'prova-escola', 'corrigir-escola'
        ];
        idsEscola.forEach(id => {
            const sel = document.getElementById(id);
            if (sel && sel.options.length <= 1) {
                sel.innerHTML = '<option value="">Selecione a escola</option>' +
                    escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
            }
        });
        const selTurmaAluno = document.getElementById('aluno-turma');
        if (selTurmaAluno && selTurmaAluno.options.length <= 1) {
            selTurmaAluno.innerHTML = '<option value="">Selecione a escola primeiro</option>';
        }
        console.log('✅ Combos carregados:', escolas.length, 'escolas,', turmas.length, 'turmas,', alunos.length, 'alunos');
    } catch (e) { console.error('Erro em carregarCombos:', e); }
}

async function carregarEscolasParaAluno() {
    try {
        const escolas = await carregarEscolasComCache();
        const ids = [
            'aluno-escola', 'editar-aluno-escola', 'lista-escola',
            'transf-escola-origem', 'transf-escola-destino', 'rel-turma-escola'
        ];
        ids.forEach(id => {
            const sel = document.getElementById(id);
            if (sel && sel.options.length <= 1) {
                sel.innerHTML = '<option value="">Selecione a escola</option>' +
                    escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
            }
        });
    } catch (e) { console.error('❌ Erro ao carregar escolas para aluno:', e); }
}

async function carregarEscolasParaCorrecaoManual() {
    try {
        const escolas = await carregarEscolasComCache();
        const sel = document.getElementById('cm-escola-select');
        if (sel && sel.options.length <= 1) {
            sel.innerHTML = '<option value="">Selecione a escola...</option>' +
                escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
        }
    } catch (e) { console.error('❌ Erro ao carregar escolas para correção manual:', e); }
}

function processarListaAlunos() {
    const textarea = document.getElementById('multi-alunos-input');
    const linhas = textarea.value.split('\n').filter(l => l.trim() !== '');
    if (linhas.length === 0) { showToast('⚠️ Cole a lista de alunos primeiro!', 'warning'); return; }
    const statusDiv = document.getElementById('multi-status');
    const statusText = document.getElementById('multi-status-text');
    let adicionados = 0, erros = 0;
    linhas.forEach(linha => {
        let nome = linha.trim(); let matricula = ''; let numero = '';
        const matchVirgula = linha.match(/^([^,]+),\s*([^,]+),\s*(\d+)?/);
        const matchTraco = linha.match(/^([^-]+)\s*-\s*([^-]+)\s*-\s*(\d+)?/);
        const matchParenteses = linha.match(/^([^(]+)\s*\(([^)]+)\)/);
        if (matchVirgula) { nome = matchVirgula[1].trim(); matricula = matchVirgula[2].trim(); numero = matchVirgula[3] ? matchVirgula[3].trim() : ''; }
        else if (matchTraco) { nome = matchTraco[1].trim(); matricula = matchTraco[2].trim(); numero = matchTraco[3] ? matchTraco[3].trim() : ''; }
        else if (matchParenteses) { nome = matchParenteses[1].trim(); matricula = matchParenteses[2].trim(); }
        if (nome) {
            document.getElementById('aluno-nome').value = nome;
            if (matricula) document.getElementById('aluno-matricula').value = matricula;
            if (numero) document.getElementById('aluno-numero').value = numero;
            salvarAluno(); adicionados++;
        } else { erros++; }
    });
    if (adicionados > 0) {
        statusDiv.style.display = 'block'; statusDiv.className = 'multi-status success';
        statusText.textContent = `✅ ${adicionados} alunos adicionados com sucesso! ${erros > 0 ? `(${erros} erros)` : ''}`;
        textarea.value = '';
    } else {
        statusDiv.style.display = 'block'; statusDiv.className = 'multi-status error';
        statusText.textContent = '❌ Nenhum aluno válido encontrado. Verifique o formato.';
    }
    setTimeout(() => { statusDiv.style.display = 'none'; }, 5000);
}

function fecharAbaMulti() {
    showToast('📋 Lista de alunos gerada!', 'success');
    const modal = document.getElementById('m-aluno');
    if (modal) modal.classList.remove('show');
    go('lista-turma');
}

// ═══════════════════════════════════════════════════════════════
// 👤 USUÁRIOS (com escola)
// ═══════════════════════════════════════════════════════════════

function atualizarObrigatorioEscolaUsuario() {
    const perfilSel = document.getElementById('usuario-perfil');
    const escolaSel = document.getElementById('usuario-escola');
    const reqEl     = document.getElementById('usuario-escola-req');
    if (!perfilSel) return;
    const isUsuario = perfilSel.value !== 'admin';
    if (escolaSel) {
        escolaSel.required = isUsuario;
        if (!isUsuario) escolaSel.value = '';
    }
    if (reqEl) reqEl.style.display = isUsuario ? 'inline' : 'none';
}

async function abrirModalUsuario(usuarioId) {
    const sel = document.getElementById('usuario-escola');
    if (sel) {
        sel.innerHTML = '<option value="">Carregando escolas...</option>';
        try {
            const escolas = await carregarEscolasComCache(true);
            sel.innerHTML = '<option value="">Selecione a escola...</option>' +
                escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
        } catch (e) {
            sel.innerHTML = '<option value="">Erro ao carregar escolas</option>';
        }
    }
    document.getElementById('editar-usuario-id').value = usuarioId || '';
    document.getElementById('usuario-nome').value = '';
    document.getElementById('usuario-username').value = '';
    document.getElementById('usuario-senha').value = '';
    document.getElementById('usuario-email').value = '';
    document.getElementById('usuario-perfil').value = 'usuario';
    document.getElementById('usuario-ativo').checked = true;
    if (sel) sel.value = '';
    const h3 = document.querySelector('#m-usuario .modal-header h3');
    if (h3) h3.textContent = usuarioId ? '✏️ Editar Usuário' : '👤 Cadastrar Usuário';
    if (usuarioId) {
        try {
            const u = await _fetchJSON(API_URL + '/api/usuarios/' + usuarioId);
            document.getElementById('usuario-nome').value = u.nome || '';
            document.getElementById('usuario-username').value = u.username || '';
            document.getElementById('usuario-email').value = u.email || '';
            document.getElementById('usuario-perfil').value = u.perfil || 'usuario';
            document.getElementById('usuario-ativo').checked = !!u.ativo;
            if (sel) sel.value = (u.escola_id != null) ? String(u.escola_id) : '';
        } catch (e) {
            showToast('❌ Erro ao carregar usuário: ' + e.message, 'error');
        }
    }
    atualizarObrigatorioEscolaUsuario();
    openM('m-usuario');
}

async function salvarUsuario() {
    const id = document.getElementById('editar-usuario-id').value;
    const perfil = document.getElementById('usuario-perfil').value;
    const escolaVal = document.getElementById('usuario-escola')?.value;
    const payload = {
        nome: document.getElementById('usuario-nome').value.trim(),
        username: document.getElementById('usuario-username').value.trim(),
        senha: document.getElementById('usuario-senha').value,
        email: document.getElementById('usuario-email').value.trim(),
        perfil: perfil,
        ativo: document.getElementById('usuario-ativo').checked,
        escola_id: perfil === 'admin' ? null : (escolaVal ? parseInt(escolaVal) : null)
    };
    if (!payload.nome || !payload.username) { showToast('❌ Nome e usuário são obrigatórios!', 'error'); return; }
    if (!id && !payload.senha) { showToast('❌ Senha é obrigatória para novo usuário!', 'error'); return; }
    if (payload.senha && payload.senha.length < 4) { showToast('❌ Senha deve ter 4+ caracteres!', 'error'); return; }
    if (payload.perfil !== 'admin' && !payload.escola_id) {
        showToast('❌ Escola é obrigatória para usuários não administradores!', 'error'); return;
    }
    try {
        const url = id ? API_URL + '/api/usuarios/' + id : API_URL + '/api/usuarios';
        const method = id ? 'PUT' : 'POST';
        await _fetchJSON(url, {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        showToast(id ? '✅ Usuário atualizado!' : '✅ Usuário criado!', 'success');
        closeM('m-usuario');
        if (typeof carregarUsuarios === 'function') carregarUsuarios();
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

async function carregarUsuarios() {
    try {
        const usuarios = await _fetchJSON(API_URL + '/api/usuarios');
        const tbody = document.getElementById('tb-usuarios');
        if (!tbody) return;
        if (!usuarios || usuarios.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text3);">Nenhum usuário</td></tr>';
            return;
        }
        tbody.innerHTML = usuarios.map(u => `
            <tr data-id="${u.id}">
                <td><strong>${escapeHtml(u.nome || u.username || '—')}</strong><br>
                    <span style="font-size:10px;color:var(--text3);">${escapeHtml(u.username || '')}</span>
                    ${u.escola_nome ? '<br><span style="font-size:10px;color:var(--blue);">🏫 ' + escapeHtml(u.escola_nome) + '</span>' : ''}
                </td>
                <td><span class="badge ${u.perfil === 'admin' ? 'badge-purple' : 'badge-blue'}">${escapeHtml(u.perfil || 'usuario')}</span></td>
                <td>${u.ativo ? '<span class="badge badge-green">Ativo</span>' : '<span class="badge badge-red">Inativo</span>'}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-outline btn-sm" onclick="abrirModalUsuario(${u.id})">✏️</button>
                        <button class="btn-del" onclick="excluirUsuario(${u.id}, '${escapeAttr(u.username || '')}')">🗑️</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Erro ao carregar usuários:', e);
    }
}

async function excluirUsuario(id, nome) {
    if (!confirm(`Excluir o usuário "${nome}"?`)) return;
    try {
        await _fetchJSON(API_URL + '/api/usuarios/' + id, { method: 'DELETE' });
        showToast('🗑️ Usuário excluído!', 'success');
        carregarUsuarios();
    } catch (e) { showToast('❌ Erro: ' + e.message, 'error'); }
}

function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escapeAttr(s) { return escapeHtml(s).replace(/'/g, '&#39;'); }

function formatarData(d) {
    if (!d) return '—';
    try { const dt = new Date(d); return dt.toLocaleDateString('pt-BR'); }
    catch { return d; }
}

// ═══════════════════════════════════════════════════════════════
// 🔧 FIX: populate dos selects de PROVA nos filtros
// (Resultados, Rel. por Turma, Desempenho do Aluno)
// ═══════════════════════════════════════════════════════════════
(function fixProvasDropdowns() {
    const DROPDOWNS = [
        { id: 'filtro-prova',            placeholder: 'Todas as provas',       curto: false },
        { id: 'rel-turma-prova',         placeholder: 'Todas as provas',       curto: false },
        { id: 'filtro-prova-desempenho', placeholder: 'Selecione a prova...',   curto: true  }
    ];

    async function popular() {
        try {
            let provas = window._provasCache;
            if (!provas || !Array.isArray(provas) || provas.length === 0) {
                const r = await apiFetch(API_URL + '/api/provas');
                if (r.ok) {
                    provas = await r.json();
                    window._provasCache = provas;
                }
            }
            if (!provas || provas.length === 0) return;

            DROPDOWNS.forEach(d => {
                const sel = document.getElementById(d.id);
                if (!sel) return;
                // Só popula se ainda estiver com placeholder (<= 1 option)
                if (sel.options.length <= 1) {
                    const html = provas.map(p => {
                        const txt = d.curto
                            ? `${escapeHtml(p.titulo)} — ${escapeHtml(p.serie || '')}`
                            : `${escapeHtml(p.titulo)} - ${escapeHtml(p.serie || '')} - ${escapeHtml(p.disciplina || '')}`;
                        return `<option value="${p.id}" data-disciplina="${escapeAttr(p.disciplina || '')}">${txt}</option>`;
                    }).join('');
                    sel.innerHTML = `<option value="">${d.placeholder}</option>` + html;
                    console.log(`✅ [fixProvas] ${d.id}: ${provas.length} provas`);
                }
            });
        } catch (e) {
            console.warn('fixProvasDropdowns erro:', e);
        }
    }

    // 1ª execução após o sistema carregar
    setTimeout(popular, 1500);

    // Reexecuta ao clicar nas abas relevantes
    document.addEventListener('click', (e) => {
        const item = e.target.closest('.sb-item');
        if (!item) return;
        const page = item.dataset.p;
        if (page === 'resultados' || page === 'rel-turma' || page === 'desempenho') {
            setTimeout(popular, 300);
        }
    }, true);

    // Reexecuta quando o usuário volta pra tela (via go())
    window.addEventListener('load', () => setTimeout(popular, 2500));
})();

console.log('✅ js/cadastros.js carregado');
