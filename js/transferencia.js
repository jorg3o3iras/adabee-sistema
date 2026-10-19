// ============================================================
// TRANSFERENCIA.JS — Transferência individual e em lote
// ============================================================

let alunosSelecionadosTransf = new Set();

async function carregarFiltrosTransferencia() {
    try {
        const escolas = await carregarEscolasComCache();
        const sOrigem = document.getElementById('transf-escola-origem');
        const sDestino = document.getElementById('transf-escola-destino');
        if (sOrigem) {
            sOrigem.innerHTML = '<option value="">Selecione a escola...</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                sOrigem.appendChild(opt);
            });
        }
        if (sDestino) {
            sDestino.innerHTML = '<option value="">Selecione a escola...</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                sDestino.appendChild(opt);
            });
        }
    } catch (e) { console.error('Erro filtros transf:', e); }
}

async function carregarTurmasTransfOrigem(escolaId) {
    const sel = document.getElementById('transf-turma-origem');
    sel.innerHTML = '<option value="">Selecione a turma...</option>';
    document.getElementById('transf-lista-alunos').innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Selecione uma turma</div>';
    alunosSelecionadosTransf.clear();
    atualizarBotaoTransf();

    if (!escolaId) return;

    try {
        const turmas = await carregarTurmasComCache(escolaId);
        const serieFiltro = document.getElementById('transf-serie-origem').value;
        turmas.forEach(t => {
            if (serieFiltro && t.serie !== serieFiltro) return;
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.nome + ' - ' + (t.serie || '');
            sel.appendChild(opt);
        });
    } catch (e) { console.error(e); }
}

async function carregarTurmasTransfDestino(escolaId) {
    const sel = document.getElementById('transf-turma-destino');
    sel.innerHTML = '<option value="">Selecione a turma...</option>';
    if (!escolaId) return;
    try {
        const turmas = await carregarTurmasComCache(escolaId);
        const serieFiltro = document.getElementById('transf-serie-destino').value;
        turmas.forEach(t => {
            if (serieFiltro && t.serie !== serieFiltro) return;
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.nome + ' - ' + (t.serie || '');
            opt.dataset.serie = t.serie || '';
            sel.appendChild(opt);
        });
    } catch (e) { console.error(e); }
}

async function carregarAlunosTransf(turmaId) {
    const container = document.getElementById('transf-lista-alunos');
    alunosSelecionadosTransf.clear();
    atualizarBotaoTransf();

    if (!turmaId) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Selecione uma turma</div>';
        return;
    }

    try {
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });

        if (!alunos || alunos.length === 0) {
            container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Nenhum aluno nesta turma</div>';
            return;
        }

        container.innerHTML = alunos.map(a => `
            <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border);cursor:pointer;" onclick="toggleCheckTransf(event, ${a.id})">
                <input type="checkbox" class="transf-checkbox" data-id="${a.id}" style="width:18px;height:18px;cursor:pointer;" onclick="event.stopPropagation(); toggleCheckTransf(event, ${a.id})" />
                <div style="flex:1;">
                    <strong>${escapeHtml(a.nome)}</strong>
                    <div style="font-size:11px;color:var(--text3);">
                        Nº ${a.numero_chamada || '—'} · Matrícula ${a.matricula || '—'} · ${a.serie || ''}
                    </div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
        container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--red);">Erro ao carregar alunos</div>';
    }
}

function toggleCheckTransf(event, alunoId) {
    if (event) event.stopPropagation();
    const cb = document.querySelector(`.transf-checkbox[data-id="${alunoId}"]`);
    if (!cb) return;
    if (event && event.target !== cb) {
        cb.checked = !cb.checked;
    }
    if (cb.checked) alunosSelecionadosTransf.add(alunoId);
    else alunosSelecionadosTransf.delete(alunoId);
    atualizarBotaoTransf();
}

function selecionarTodosTransf(marcar) {
    document.querySelectorAll('.transf-checkbox').forEach(cb => {
        cb.checked = marcar;
        const id = parseInt(cb.dataset.id);
        if (marcar) alunosSelecionadosTransf.add(id);
        else alunosSelecionadosTransf.delete(id);
    });
    atualizarBotaoTransf();
}

function atualizarBotaoTransf() {
    const btn = document.getElementById('btn-confirmar-transf');
    if (!btn) return;
    const total = alunosSelecionadosTransf.size;
    btn.textContent = `🔄 Transferir ${total} aluno(s)`;
    btn.disabled = total === 0;
}

async function confirmarTransferencia() {
    const escolaOrigem = document.getElementById('transf-escola-origem').value;
    const turmaOrigem = document.getElementById('transf-turma-origem').value;
    const escolaDestino = document.getElementById('transf-escola-destino').value;
    const turmaDestino = document.getElementById('transf-turma-destino').value;
    const serieDestino = document.getElementById('transf-serie-destino').value;

    if (!escolaOrigem || !turmaOrigem) { showToast('⚠️ Selecione escola e turma de origem', 'error'); return; }
    if (!escolaDestino || !turmaDestino) { showToast('⚠️ Selecione escola e turma de destino', 'error'); return; }
    if (alunosSelecionadosTransf.size === 0) { showToast('⚠️ Selecione pelo menos 1 aluno', 'error'); return; }

    const total = alunosSelecionadosTransf.size;
    if (!confirm(`🔄 Transferir ${total} aluno(s)?\n\nAs correções antigas serão mantidas.`)) return;

    const btn = document.getElementById('btn-confirmar-transf');
    btn.disabled = true;
    btn.textContent = '⏳ Transferindo...';

    try {
        const response = await fetch(`${API_URL}/api/alunos/transferir`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                alunos_ids: Array.from(alunosSelecionadosTransf),
                escola_origem_id: parseInt(escolaOrigem),
                turma_origem_id: parseInt(turmaOrigem),
                escola_destino_id: parseInt(escolaDestino),
                turma_destino_id: parseInt(turmaDestino),
                serie_destino: serieDestino,
                motivo: 'Transferência em lote',
                usuario_responsavel: 'admin'
            })
        });

        const data = await response.json();

        if (data.ok) {
            showToast(`✅ ${data.transferidos} aluno(s) transferido(s)!`, 'success');
            limparCache();
            carregarAlunosTransf(turmaOrigem);
            if (typeof carregarAlunos === 'function') carregarAlunos();
            if (typeof carregarDados === 'function') carregarDados();
        } else {
            showToast('❌ ' + (data.erro || 'Erro ao transferir'), 'error');
        }
    } catch (e) {
        console.error(e);
        showToast('❌ Erro: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        atualizarBotaoTransf();
    }
}

// Carrega filtros ao entrar na página
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('page-transferir-alunos')) {
        setTimeout(() => carregarFiltrosTransferencia(), 600);
    }
});

// Recarrega ao mudar de série
document.addEventListener('change', function(e) {
    if (e.target.id === 'transf-serie-origem') {
        const escolaId = document.getElementById('transf-escola-origem').value;
        if (escolaId) carregarTurmasTransfOrigem(escolaId);
    }
    if (e.target.id === 'transf-serie-destino') {
        const escolaId = document.getElementById('transf-escola-destino').value;
        if (escolaId) carregarTurmasTransfDestino(escolaId);
    }
});