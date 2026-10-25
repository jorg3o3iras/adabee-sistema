// ============================================================
// JS/TRANSFERENCIA.JS — Transferência de Alunos (Frontend)
// ============================================================

// ═══ ESTADO DA TRANSFERÊNCIA ═══
let transfAlunosSelecionados = new Set();
let transfAlunosData = [];
let transfOrigemInfo = { escolaId: null, turmaId: null, serie: '' };
let transfDestinoInfo = { escolaId: null, turmaId: null };

// ═══════════════════════════════════════════════════════════════
// CARREGAR ESCOLAS NOS SELECTS DE ORIGEM E DESTINO
// ═══════════════════════════════════════════════════════════════
async function carregarEscolasTransferencia() {
    try {
        const escolas = await carregarEscolasComCache();
        if (!escolas || escolas.erro) return;

        ['transf-escola-origem', 'transf-escola-destino'].forEach(id => {
            const sel = document.getElementById(id);
            if (sel) {
                const current = sel.value;
                sel.innerHTML = '<option value="">Selecione a escola...</option>' +
                    escolas.map(e => `<option value="${e.id}">${escapeHtml(e.nome)}</option>`).join('');
                if (current) sel.value = current;
            }
        });
    } catch (e) {
        console.error('Erro ao carregar escolas para transferência:', e);
    }
}

// ═══════════════════════════════════════════════════════════════
// ORIGEM — TURMAS
// ═══════════════════════════════════════════════════════════════
async function carregarTurmasTransfOrigem(escolaId) {
    const selectTurma = document.getElementById('transf-turma-origem');
    const listaAlunos = document.getElementById('transf-lista-alunos');
    const btnConfirmar = document.getElementById('btn-confirmar-transf');

    if (selectTurma) {
        selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    }
    if (listaAlunos) {
        listaAlunos.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Selecione uma turma de origem para ver os alunos</div>';
    }
    if (btnConfirmar) {
        btnConfirmar.disabled = true;
        btnConfirmar.textContent = '🔄 Transferir 0 aluno(s)';
    }

    transfAlunosSelecionados.clear();
    transfAlunosData = [];
    transfOrigemInfo = { escolaId: escolaId ? parseInt(escolaId) : null, turmaId: null, serie: '' };

    if (!escolaId) return;

    try {
        const turmas = await carregarTurmasComCache(escolaId);
        if (turmas && !turmas.erro) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                opt.dataset.serie = t.serie || '';
                selectTurma.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Erro ao carregar turmas de origem:', e);
        showToast('❌ Erro ao carregar turmas', 'error');
    }
}

// ═══════════════════════════════════════════════════════════════
// ORIGEM — ALUNOS DA TURMA
// ═══════════════════════════════════════════════════════════════
async function carregarAlunosTransf(turmaId) {
    const listaAlunos = document.getElementById('transf-lista-alunos');
    const btnConfirmar = document.getElementById('btn-confirmar-transf');
    const selectTurma = document.getElementById('transf-turma-origem');

    if (btnConfirmar) {
        btnConfirmar.disabled = true;
        btnConfirmar.textContent = '🔄 Transferir 0 aluno(s)';
    }

    transfAlunosSelecionados.clear();
    transfAlunosData = [];

    if (!turmaId) {
        if (listaAlunos) {
            listaAlunos.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Selecione uma turma de origem para ver os alunos</div>';
        }
        return;
    }

    transfOrigemInfo.turmaId = parseInt(turmaId);

    if (selectTurma) {
        const opt = selectTurma.options[selectTurma.selectedIndex];
        if (opt) transfOrigemInfo.serie = opt.dataset.serie || '';
    }

    if (listaAlunos) {
        listaAlunos.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text3);"><div class="spinner" style="margin:0 auto 10px;"></div>Carregando alunos...</div>';
    }

    try {
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        transfAlunosData = (alunos && !alunos.erro) ? alunos : [];

        renderizarListaAlunosTransf();
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
        if (listaAlunos) {
            listaAlunos.innerHTML = '<div style="text-align:center;padding:20px;color:var(--red);">Erro ao carregar alunos</div>';
        }
    }
}

function renderizarListaAlunosTransf() {
    const listaAlunos = document.getElementById('transf-lista-alunos');
    if (!listaAlunos) return;

    if (transfAlunosData.length === 0) {
        listaAlunos.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Nenhum aluno encontrado nesta turma</div>';
        return;
    }

    let html = '<div style="display:flex;flex-direction:column;gap:6px;max-height:400px;overflow-y:auto;">';
    transfAlunosData.forEach(aluno => {
        const checked = transfAlunosSelecionados.has(aluno.id) ? 'checked' : '';
        html += `
            <label style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--surface2);border-radius:8px;border:1px solid var(--border);cursor:pointer;transition:background 0.2s;">
                <input type="checkbox" class="transf-checkbox" value="${aluno.id}" ${checked} onchange="toggleAlunoTransf(${aluno.id}, this.checked)" style="width:18px;height:18px;cursor:pointer;">
                <div style="flex:1;min-width:0;">
                    <strong>${escapeHtml(aluno.nome)}</strong>
                    <span class="badge badge-blue" style="margin-left:8px;">Nº ${escapeHtml(aluno.numero_chamada || '—')}</span>
                    ${aluno.matricula ? `<span class="badge badge-gray" style="margin-left:4px;">${escapeHtml(aluno.matricula)}</span>` : ''}
                </div>
            </label>
        `;
    });
    html += '</div>';
    listaAlunos.innerHTML = html;
}

function toggleAlunoTransf(alunoId, checked) {
    if (checked) transfAlunosSelecionados.add(alunoId);
    else transfAlunosSelecionados.delete(alunoId);
    atualizarBotaoTransf();
}

function selecionarTodosTransf(selecionar) {
    const checkboxes = document.querySelectorAll('.transf-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = selecionar;
        const id = parseInt(cb.value);
        if (selecionar) transfAlunosSelecionados.add(id);
        else transfAlunosSelecionados.delete(id);
    });
    atualizarBotaoTransf();
}

function atualizarBotaoTransf() {
    const btn = document.getElementById('btn-confirmar-transf');
    if (!btn) return;
    const total = transfAlunosSelecionados.size;
    btn.disabled = total === 0;
    btn.textContent = `🔄 Transferir ${total} aluno(s)`;
}

// ═══════════════════════════════════════════════════════════════
// DESTINO — TURMAS
// ═══════════════════════════════════════════════════════════════
async function carregarTurmasTransfDestino(escolaId) {
    const selectTurma = document.getElementById('transf-turma-destino');
    if (selectTurma) {
        selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    }

    transfDestinoInfo = { escolaId: escolaId ? parseInt(escolaId) : null, turmaId: null };

    if (!escolaId) return;

    try {
        const turmas = await carregarTurmasComCache(escolaId);
        if (turmas && !turmas.erro) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                opt.dataset.serie = t.serie || '';
                selectTurma.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Erro ao carregar turmas de destino:', e);
        showToast('❌ Erro ao carregar turmas', 'error');
    }
}

// ═══════════════════════════════════════════════════════════════
// CONFIRMAR TRANSFERÊNCIA
// ═══════════════════════════════════════════════════════════════
async function confirmarTransferencia() {
    const btn = document.getElementById('btn-confirmar-transf');

    if (transfAlunosSelecionados.size === 0) {
        showToast('⚠️ Selecione pelo menos um aluno!', 'warning');
        return;
    }

    const escolaDestinoId = document.getElementById('transf-escola-destino')?.value;
    const turmaDestinoId = document.getElementById('transf-turma-destino')?.value;
    const serieDestino = document.getElementById('transf-serie-destino')?.value || '';

    if (!escolaDestinoId) {
        showToast('❌ Selecione a escola de destino!', 'error');
        return;
    }
    if (!turmaDestinoId) {
        showToast('❌ Selecione a turma de destino!', 'error');
        return;
    }

    // Verifica se origem e destino são iguais
    if (transfOrigemInfo.escolaId === parseInt(escolaDestinoId) &&
        transfOrigemInfo.turmaId === parseInt(turmaDestinoId)) {
        showToast('❌ Origem e destino são iguais!', 'error');
        return;
    }

    const total = transfAlunosSelecionados.size;
    const alunosNomes = transfAlunosData
        .filter(a => transfAlunosSelecionados.has(a.id))
        .map(a => a.nome)
        .slice(0, 3);

    const confirmMsg = `Transferir ${total} aluno(s)?\n\n` +
        alunosNomes.join(', ') + (total > 3 ? `... (e mais ${total - 3})` : '') +
        `\n\nEsta ação altera a escola/turma dos alunos. Correções antigas são preservadas.`;

    if (!confirm(confirmMsg)) return;

    // Guarda o texto original ANTES de desabilitar
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Transferindo...';
    }

    showToast('🔄 Transferindo alunos...', 'info');

    try {
        const payload = {
            alunos_ids: Array.from(transfAlunosSelecionados),
            escola_origem_id: transfOrigemInfo.escolaId,
            turma_origem_id: transfOrigemInfo.turmaId,
            escola_destino_id: parseInt(escolaDestinoId),
            turma_destino_id: parseInt(turmaDestinoId),
            serie_destino: serieDestino,
            motivo: 'Transferência solicitada',
            usuario_responsavel: 'admin'
        };

        const response = await fetch(API_URL + '/api/alunos/transferir', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(data.erro || 'Erro ao transferir');
        }

        showToast(`✅ ${data.transferidos} aluno(s) transferido(s) com sucesso!`, 'success');

        if (data.erros && data.erros.length > 0) {
            console.warn('Erros parciais:', data.erros);
        }

        // Limpa caches para recarregar dados frescos
        limparCache();

        // Limpa seleção e recarrega lista
        transfAlunosSelecionados.clear();
        await carregarAlunosTransf(transfOrigemInfo.turmaId);

        // Recarrega dados em outras telas
        if (typeof carregarAlunos === 'function') carregarAlunos();
        if (typeof carregarTurmas === 'function') carregarTurmas();
        if (typeof carregarEscolas === 'function') carregarEscolas();
        if (typeof carregarDashboard === 'function') carregarDashboard();
        if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
    } catch (e) {
        console.error('Erro ao transferir:', e);
        showToast('❌ Erro: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            // FIX: usar originalText (variável correta), com fallback seguro
            btn.textContent = originalText || `🔄 Transferir ${transfAlunosSelecionados.size} aluno(s)`;
        }
        atualizarBotaoTransf();
    }
}

console.log('✅ js/transferencia.js carregado');
