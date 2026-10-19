// ============================================================
// JS/CADASTROS.JS — Escolas, Turmas, Alunos (Frontend)
// ============================================================

// ═══ VARIÁVEIS GLOBAIS ═══
let escolasCache = null;
let turmasCache = null;
let alunosCache = null;

// ═══ CACHE / FETCH ═══
function limparCache() {
    escolasCache = null;
    turmasCache = null;
    alunosCache = null;
}

async function _fetchJSON(url, opcoes) {
    try {
        const r = await fetch(url, opcoes);
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

// ═══ ESCOLAS ═══
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

    const turmas = await carregarTurmasComCache();
    tbody.innerHTML = escolas.map((e, i) => {
        const totalTurmas = turmas.filter(t => t.escola_id == e.id).length;
        const totalAlunos = turmas
            .filter(t => t.escola_id == e.id)
            .reduce((acc, t) => acc + (parseInt(t.total_alunos) || 0), 0);
        return `<tr>
            <td>${i + 1}</td>
            <td><strong>${escapeHtml(e.nome || '—')}</strong></td>
            <td>${escapeHtml(e.municipio || '—')}</td>
            <td>${escapeHtml(e.inep || '—')}</td>
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
        await _fetchJSON(API_URL + '/api/escolas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Escola "' + nome + '" cadastrada!', 'success');
        limparCache();
        closeM('m-escola');
        carregarEscolas();
        carregarCombos();
    } catch (e) {
        showToast('❌ Erro ao salvar escola: ' + e.message, 'error');
    }
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
    } catch (e) {
        showToast('❌ Erro ao carregar escola: ' + e.message, 'error');
    }
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
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Escola atualizada!', 'success');
        limparCache();
        closeM('m-editar-escola');
        carregarEscolas();
    } catch (e) {
        showToast('❌ Erro ao atualizar: ' + e.message, 'error');
    }
}

async function excluirEscola(id, nome) {
    if (!confirm(`Excluir a escola "${nome}"?\n\nATENÇÃO: Turmas e alunos vinculados também serão removidos!`)) return;
    try {
        await _fetchJSON(API_URL + '/api/escolas/' + id, { method: 'DELETE' });
        showToast('🗑️ Escola excluída!', 'success');
        limparCache();
        carregarEscolas();
        carregarCombos();
    } catch (e) {
        showToast('❌ Erro ao excluir: ' + e.message, 'error');
    }
}

// ═══ TURMAS ═══
async function carregarTurmasComCache(escolaId, forceRefresh) {
    if (!forceRefresh && turmasCache && !escolaId) return turmasCache;
    try {
        const url = API_URL + '/api/turmas' + (escolaId ? `?escola_id=${escolaId}` : '');
        const turmas = await _fetchJSON(url);
        if (!escolaId) turmasCache = turmas || [];
        return turmas || [];
    } catch (e) {
        console.error('Erro ao carregar turmas:', e);
        return [];
    }
}

async function carregarTurmas() {
    const turmas = await carregarTurmasComCache(null, true);
    const tbody = document.getElementById('tb-turmas');
    if (!tbody) return;

    if (!turmas || turmas.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma turma cadastrada</td></tr>';
        return;
    }

    tbody.innerHTML = turmas.map((t, i) => {
        const totalAlunos = parseInt(t.total_alunos) || 0;
        return `<tr data-serie="${escapeAttr(t.serie || '')}" data-escola="${t.escola_id}">
            <td>${i + 1}</td>
            <td><strong>${escapeHtml(t.nome || '—')}</strong></td>
            <td><span class="badge badge-purple">${escapeHtml(t.serie || '—')}</span></td>
            <td>${escapeHtml(t.turno || '—')}</td>
            <td>${escapeHtml(t.escola_nome || '—')}</td>
            <td>${escapeHtml(t.professor || '—')}</td>
            <td><span class="badge badge-blue">${totalAlunos}</span></td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="editarTurma(${t.id})" title="Editar">✏️</button>
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
        nome,
        escola_id: parseInt(escolaId),
        serie: document.getElementById('turma-serie')?.value || '1º Ano',
        turno: document.getElementById('turma-turno')?.value || 'Manhã',
        professor: document.getElementById('turma-professor')?.value.trim() || '',
        capacidade: parseInt(document.getElementById('turma-capacidade')?.value || 35),
        ano_letivo: parseInt(document.getElementById('turma-ano')?.value || 2025)
    };

    try {
        await _fetchJSON(API_URL + '/api/turmas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Turma criada!', 'success');
        limparCache();
        closeM('m-turma');
        carregarTurmas();
        carregarCombos();
    } catch (e) {
        showToast('❌ Erro: ' + e.message, 'error');
    }
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
    } catch (e) {
        showToast('❌ Erro ao carregar: ' + e.message, 'error');
    }
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
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Turma atualizada!', 'success');
        limparCache();
        closeM('m-editar-turma');
        carregarTurmas();
    } catch (e) {
        showToast('❌ Erro: ' + e.message, 'error');
    }
}

async function excluirTurma(id, nome) {
    if (!confirm(`Excluir a turma "${nome}"?\n\nAlunos vinculados também serão removidos!`)) return;
    try {
        await _fetchJSON(API_URL + '/api/turmas/' + id, { method: 'DELETE' });
        showToast('🗑️ Turma excluída!', 'success');
        limparCache();
        carregarTurmas();
        carregarCombos();
    } catch (e) {
        showToast('❌ Erro: ' + e.message, 'error');
    }
}

// ═══ ALUNOS ═══
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
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
        return [];
    }
}

async function carregarAlunos(escolaId) {
    const turmaId = document.getElementById('filtro-turma-alunos')?.value;
    const filtros = {};
    if (escolaId) filtros.escola_id = escolaId;
    if (turmaId) filtros.turma_id = turmaId;

    const alunos = await carregarAlunosComCache(filtros, true);
    const tbody = document.getElementById('tb-alunos');
    if (!tbody) return;

    if (!alunos || alunos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhum aluno encontrado</td></tr>';
        return;
    }

    tbody.innerHTML = alunos.map((a, i) => {
        const dataNasc = a.data_nascimento ? formatarData(a.data_nascimento) : '—';
        return `<tr data-escola="${a.escola_id}" data-serie="${escapeAttr(a.turma_serie || '')}">
            <td>${a.numero_chamada || (i + 1)}</td>
            <td>${escapeHtml(a.matricula || '—')}</td>
            <td><strong>${escapeHtml(a.nome || '—')}</strong></td>
            <td><span class="badge badge-purple">${escapeHtml(a.turma_serie || '—')}</span></td>
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
        nome,
        escola_id: parseInt(escolaId),
        turma_id: parseInt(turmaId),
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
        await _fetchJSON(API_URL + '/api/alunos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Aluno cadastrado!', 'success');
        limparCache();
        closeM('m-aluno');
        carregarAlunos(escolaId);
        carregarCombos();
    } catch (e) {
        showToast('❌ Erro: ' + e.message, 'error');
    }
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
    } catch (e) {
        showToast('❌ Erro ao carregar aluno: ' + e.message, 'error');
    }
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
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        showToast('✅ Aluno atualizado!', 'success');
        limparCache();
        closeM('m-editar-aluno');
        carregarAlunos();
    } catch (e) {
        showToast('❌ Erro: ' + e.message, 'error');
    }
}

async function excluirAluno(id, nome) {
    if (!confirm(`Excluir o aluno "${nome}"?`)) return;
    try {
        await _fetchJSON(API_URL + '/api/alunos/' + id, { method: 'DELETE' });
        showToast('🗑️ Aluno excluído!', 'success');
        limparCache();
        carregarAlunos();
        carregarCombos();
    } catch (e) {
        showToast('❌ Erro: ' + e.message, 'error');
    }
}

// ═══ FILTROS / COMBOS ═══
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
        turmas.map(t => `<option value="${t.id}">${escapeHtml(t.nome)} - ${escapeHtml(t.serie || '')}</option>`).join('');
}

// ═══ FILTROS DE ALUNOS (CORRIGIDO — popula select de turmas) ═══
async function carregarTurmasFiltroAlunos(escolaId) {
    const sel = document.getElementById('filtro-turma-alunos');
    if (!sel) return;

    if (!escolaId) {
        sel.innerHTML = '<option value="">Todas as turmas</option>';
        return;
    }

    try {
        const turmas = await carregarTurmasComCache(escolaId);
        sel.innerHTML = '<option value="">Todas as turmas</option>' +
            turmas.map(t => `<option value="${t.id}">${escapeHtml(t.nome)}</option>`).join('');
    } catch (e) {
        console.error('❌ Erro ao carregar turmas para filtro:', e);
        sel.innerHTML = '<option value="">Todas as turmas</option>';
    }
}

function filtrarAlunosPorEscola(escolaId) {
    carregarTurmasFiltroAlunos(escolaId);
    carregarAlunos(escolaId);
}

function filtrarAlunosPorSerie(serie) {
    const rows = document.querySelectorAll('#tb-alunos tr');
    rows.forEach(row => {
        if (!serie) { row.style.display = ''; return; }
        row.style.display = row.dataset.serie === serie ? '' : 'none';
    });
}

// ═══ FILTROS DE TURMAS ═══
function aplicarFiltrosTurmas() {
    const escolaId = document.getElementById('filtro-escola-turmas')?.value || '';
    const serie = document.getElementById('filtro-serie-turmas')?.value || '';
    const rows = document.querySelectorAll('#tb-turmas tr');

    rows.forEach(row => {
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

// ═══ COMBOS UNIFICADOS (chamado no DOMContentLoaded) ═══
async function carregarCombos() {
    try {
        const escolas = await carregarEscolasComCache();
        const turmas = await carregarTurmasComCache();
        const alunos = await carregarAlunosComCache();

        ['turma-escola', 'aluno-escola', 'editar-turma-escola', 'editar-aluno-escola'].forEach(id => {
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
    } catch (e) {
        console.error('Erro em carregarCombos:', e);
    }
}

// ═══ FUNÇÕES FALTANTES (chamadas por script.js) ═══
async function carregarEscolasParaAluno() {
    try {
        const escolas = await carregarEscolasComCache();
        ['aluno-escola', 'editar-aluno-escola'].forEach(id => {
            const sel = document.getElementById(id);
            if (sel && sel.options.length <= 1) {
                sel.innerHTML = '<option value="">Selecione a escola</option>' +
                    escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
            }
        });
        console.log('✅ Escolas para aluno carregadas:', escolas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar escolas para aluno:', e);
    }
}

async function carregarEscolasParaCorrecaoManual() {
    try {
        const escolas = await carregarEscolasComCache();
        const sel = document.getElementById('cm-escola-select');
        if (sel && sel.options.length <= 1) {
            sel.innerHTML = '<option value="">Selecione a escola...</option>' +
                escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
        }
        console.log('✅ Escolas para correção manual:', escolas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar escolas para correção manual:', e);
    }
}

async function carregarEscolasDesempenho() {
    try {
        const escolas = await carregarEscolasComCache();
        const sel = document.getElementById('filtro-escola-desempenho');
        if (sel) {
            sel.innerHTML = '<option value="">Selecione a escola...</option>' +
                escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
        }
        console.log('✅ Escolas para desempenho:', escolas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar escolas para desempenho:', e);
    }
}

// ═══ UTILITÁRIOS ═══
function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
}

function formatarData(d) {
    if (!d) return '—';
    try {
        const dt = new Date(d);
        return dt.toLocaleDateString('pt-BR');
    } catch { return d; }
}

console.log('✅ js/cadastros.js carregado — funções exportadas para o escopo global');
