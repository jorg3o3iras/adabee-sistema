// ============================================================
// CADASTROS.JS — Escolas, Turmas, Alunos (CRUD + filtros)
// Extraído de script.js — Corte 3
// ============================================================

// ═══ CARREGAR ESCOLAS ═══
async function carregarEscolas() {
    try {
        const escolas = await carregarEscolasComCache();
        const tbody = document.getElementById('tb-escola');
        if (!tbody) return;

        if (!escolas || escolas.length === 0 || escolas.erro) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma escola cadastrada</td></tr>';
        } else {
            const turmas = await carregarTurmasComCache();
            const alunos = await carregarAlunosComCache();

            tbody.innerHTML = escolas.map((e, i) => {
                const turmasCount = turmas.filter(t => t.escola_id === e.id).length;
                const alunosCount = alunos.filter(a => a.escola_id === e.id).length;
                return '<tr data-id="' + e.id + '" data-nome="' + escapeAttr(e.nome) + '">' +
                    '<td><span class="badge badge-blue">' + String(i + 1).padStart(3, '0') + '</span></td>' +
                    '<td><strong>' + escapeHtml(e.nome) + '</strong></td>' +
                    '<td>' + escapeHtml(e.municipio || '—') + (e.estado ? ' — ' + escapeHtml(e.estado) : '') + '</td>' +
                    '<td><span class="chip">' + escapeHtml(e.inep || '—') + '</span></td>' +
                    '<td>' + escapeHtml(e.diretor || '—') + '</td>' +
                    '<td>' + turmasCount + '</td>' +
                    '<td>' + alunosCount + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarEscola(' + e.id + ')">✏️ Editar</button><button class="btn-del" onclick="excluirEscola(' + e.id + ', \'' + escapeAttr(e.nome) + '\')" title="Excluir">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar escolas:', erro);
    }
}

// ═══ CARREGAR TURMAS ═══
async function carregarTurmas() {
    try {
        const turmas = await carregarTurmasComCache();
        const tbody = document.getElementById('tb-turmas');
        if (!tbody) return;

        if (!turmas || turmas.length === 0 || turmas.erro) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma turma cadastrada</td></tr>';
        } else {
            const corMap = { '1º Ano': 'badge-purple', '2º Ano': 'badge-purple', '3º Ano': 'badge-blue',
                '4º Ano': 'badge-blue', '5º Ano': 'badge-blue', '6º Ano': 'badge-cyan',
                '7º Ano': 'badge-cyan', '8º Ano': 'badge-orange', '9º Ano': 'badge-orange' };

            const turmasVisiveis = turmas.slice(0, 500);

            tbody.innerHTML = turmasVisiveis.map((t, i) => {
                const totalAlunos = t.total_alunos || 0;
                return '<tr data-id="' + t.id + '" data-nome="' + escapeAttr(t.nome) + '" data-serie="' + escapeAttr(t.serie || '') + '" data-escola="' + (t.escola_id || '') + '">' +
                    '<td><span class="badge badge-gray">' + String(i + 1).padStart(2, '0') + '</span></td>' +
                    '<td><strong>' + escapeHtml(t.nome) + '</strong></td>' +
                    '<td><span class="badge ' + (corMap[t.serie] || 'badge-blue') + '">' + escapeHtml(t.serie || '—') + '</span></td>' +
                    '<td>' + escapeHtml(t.turno || 'Manhã') + '</td>' +
                    '<td>' + escapeHtml(t.escola_nome || '—') + '</td>' +
                    '<td>' + escapeHtml(t.professor || '—') + '</td>' +
                    '<td><span class="badge badge-blue">' + totalAlunos + '</span></td>' +
                    '<td><div class="btn-group">' +
                    '<button class="btn btn-outline btn-sm" onclick="editarTurma(' + t.id + ')">✏️</button>' +
                    '<button class="btn btn-green btn-sm" onclick="verAlunosDaTurma(' + t.id + ')" title="Lista de Alunos">📋</button>' +
                    '<button class="btn-del" onclick="excluirTurma(' + t.id + ', \'' + escapeAttr(t.nome) + '\')">🗑️</button>' +
                    '</div></td></tr>';
            }).join('');

            if (turmas.length > 50) {
                tbody.innerHTML += `<tr><td colspan="8" style="text-align:center;padding:8px;color:var(--text3);font-size:11px;">⚠️ Mostrando 50 de ${turmas.length} turmas. Use o filtro para buscar mais.</td></tr>`;
            }
        }
    } catch (erro) {
        console.error('Erro ao carregar turmas:', erro);
        const tbody = document.getElementById('tb-turmas');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Erro ao carregar turmas</td></tr>';
        }
    }
}

// ═══ FILTROS DE TURMAS ═══
async function carregarFiltroEscolaTurmas() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('filtro-escola-turmas');
        if (select && escolas && !escolas.erro) {
            const current = select.value;
            select.innerHTML = '<option value="">Todas as escolas</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                select.appendChild(opt);
            });
            if (current) select.value = current;
        }
    } catch (erro) {
        console.error('Erro ao carregar filtro de escola para turmas:', erro);
    }
}

function aplicarFiltrosTurmas() {
    const escolaId = document.getElementById('filtro-escola-turmas').value;
    const serie = document.getElementById('filtro-serie-turmas').value;

    document.querySelectorAll('#tb-turmas tr').forEach(row => {
        let mostrar = true;
        if (escolaId) {
            const escolaRow = row.dataset.escola;
            if (escolaRow !== escolaId) mostrar = false;
        }
        if (serie) {
            const serieRow = row.dataset.serie;
            if (serieRow !== serie) mostrar = false;
        }
        row.style.display = mostrar ? '' : 'none';
    });

    const totalVisiveis = document.querySelectorAll('#tb-turmas tr:not([style*="display: none"])').length;
    showToast(`🔍 ${totalVisiveis} turmas encontradas com os filtros aplicados.`, 'info');
}

function limparFiltrosTurmas() {
    document.getElementById('filtro-escola-turmas').value = '';
    document.getElementById('filtro-serie-turmas').value = '';
    document.querySelectorAll('#tb-turmas tr').forEach(row => row.style.display = '');
    showToast('✕ Filtros limpos!', 'info');
}

// ═══ CARREGAR ALUNOS ═══
async function carregarAlunos(escolaId = null) {
    try {
        const filtros = {};
        if (escolaId && escolaId !== '' && escolaId !== 'null' && escolaId !== 'undefined') {
            filtros.escola_id = escolaId;
        }
        const selectTurma = document.getElementById('filtro-turma-alunos');
        if (selectTurma && selectTurma.value && selectTurma.value !== '') {
            filtros.turma_id = selectTurma.value;
        }
        const selectSerie = document.getElementById('filtro-serie-alunos');
        if (selectSerie && selectSerie.value && selectSerie.value !== '') {
            filtros.serie = selectSerie.value;
        }

        const alunos = await carregarAlunosComCache(filtros);
        const tbody = document.getElementById('tb-alunos');
        if (!tbody) return;

        if (!alunos || alunos.length === 0 || alunos.erro) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhum aluno cadastrado com os filtros selecionados</td></tr>';
        } else {
            const corMap = {
                '1º Ano': 'badge-purple', '2º Ano': 'badge-purple', '3º Ano': 'badge-blue',
                '4º Ano': 'badge-blue', '5º Ano': 'badge-blue', '6º Ano': 'badge-cyan',
                '7º Ano': 'badge-cyan', '8º Ano': 'badge-orange', '9º Ano': 'badge-orange'
            };

            const alunosVisiveis = alunos.slice(0, 500);

            tbody.innerHTML = alunosVisiveis.map((a, i) => {
                return '<tr data-id="' + a.id + '" data-nome="' + escapeAttr(a.nome) + '">' +
                    '<td><span class="badge badge-blue">' + String(a.numero_chamada || i + 1).padStart(2, '0') + '</span></td>' +
                    '<td><span class="chip">' + escapeHtml(a.matricula || '—') + '</span></td>' +
                    '<td><strong>' + escapeHtml(a.nome) + '</strong></td>' +
                    '<td><span class="badge ' + (corMap[a.turma_serie] || 'badge-blue') + '">' + escapeHtml(a.turma_serie || '—') + '</span></td>' +
                    '<td>' + escapeHtml(a.turma_nome || '—') + '</td>' +
                    '<td><span class="badge badge-gray">' + escapeHtml(a.escola_nome || '—') + '</span></td>' +
                    '<td>' + (a.data_nascimento ? new Date(a.data_nascimento).toLocaleDateString() : '—') + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarAluno(' + a.id + ')">✏️</button><button class="btn-del" onclick="excluirAluno(' + a.id + ', \'' + escapeAttr(a.nome) + '\')">🗑️</button></div></td></tr>';
            }).join('');

            if (alunos.length > 50) {
                tbody.innerHTML += `<tr><td colspan="8" style="text-align:center;padding:8px;color:var(--text3);font-size:11px;">⚠️ Mostrando 50 de ${alunos.length} alunos. Use os filtros para buscar mais.</td></tr>`;
            }
        }
    } catch (erro) {
        console.error('Erro ao carregar alunos:', erro);
        const tbody = document.getElementById('tb-alunos');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Erro ao carregar alunos</td></tr>';
        }
    }
}

async function carregarEscolasFiltroAlunos() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('filtro-escola-alunos');
        if (select && escolas && !escolas.erro) {
            const current = select.value;
            select.innerHTML = '<option value="">Todas as escolas</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                select.appendChild(opt);
            });
            if (current) {
                select.value = current;
                carregarAlunos(current);
            }
        }
    } catch (erro) {
        console.error('Erro ao carregar escolas para filtro de alunos:', erro);
    }
}

async function filtrarAlunosPorEscola(escolaId) {
    const selectTurma = document.getElementById('filtro-turma-alunos');
    if (selectTurma) {
        selectTurma.innerHTML = '<option value="">Todas as turmas</option>';
        if (escolaId && escolaId !== '') {
            const turmas = await carregarTurmasComCache(escolaId);
            if (turmas && !turmas.erro) {
                turmas.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.nome + ' - ' + (t.serie || '');
                    selectTurma.appendChild(opt);
                });
            }
        }
    }
    carregarAlunos(escolaId);
}

function filtrarAlunosPorSerie(serie) {
    const escolaId = document.getElementById('filtro-escola-alunos')?.value || '';
    carregarAlunos(escolaId);
}

// ═══ FILTRAR TURMAS POR SÉRIE ═══
function filtrarTurmasPorSerie(selectSerie, selectTurma) {
    const serieSelecionada = selectSerie.value;
    let firstVisible = false;

    for (let option of selectTurma.options) {
        if (option.value === '') {
            option.style.display = '';
            continue;
        }
        const serieDaTurma = option.dataset.serie || '';
        if (serieSelecionada === '' || serieDaTurma === serieSelecionada) {
            option.style.display = '';
            if (!firstVisible) {
                selectTurma.value = option.value;
                firstVisible = true;
            }
        } else {
            option.style.display = 'none';
        }
    }

    if (!firstVisible) selectTurma.value = '';
    selectTurma.dispatchEvent(new Event('change'));
}

// ═══ CRUD ESCOLA ═══
async function salvarEscola() {
    const nome = document.getElementById('escola-nome').value.trim();
    if (!nome) { showToast('❌ O nome da escola é obrigatório!', 'error'); return; }

    const dados = {
        nome: nome,
        inep: document.getElementById('escola-inep').value.trim() || null,
        municipio: document.getElementById('escola-municipio').value.trim() || null,
        estado: document.getElementById('escola-estado').value || 'PA',
        telefone: document.getElementById('escola-telefone').value.trim() || null,
        diretor: document.getElementById('escola-diretor').value.trim() || null
    };

    try {
        const btn = document.querySelector('#m-escola .btn-green');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Salvando escola...', 'info');
        const response = await fetch(API_URL + '/api/escolas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        btn.textContent = originalText;
        btn.disabled = false;

        if (result.ok && result.data.id) {
            showToast('✅ Escola "' + nome + '" salva com sucesso!', 'success');
            limparCache();
            closeM('m-escola');

            await carregarEscolas();

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-escola', result.data.id, '✅ Nova!');
            }, 300);

            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao salvar escola: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar escola: ' + erro.message, 'error');
        console.error('Erro ao salvar escola:', erro);
        const btn = document.querySelector('#m-escola .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarEscola(id) {
    showToast('✏️ Carregando dados da escola...', 'info');
    fetch(API_URL + '/api/escolas/' + id)
        .then(r => r.json())
        .then(escola => {
            if (escola.erro) { showToast('❌ ' + escola.erro, 'error'); return; }
            document.getElementById('editar-escola-id').value = escola.id;
            document.getElementById('editar-escola-nome').value = escola.nome || '';
            document.getElementById('editar-escola-inep').value = escola.inep || '';
            document.getElementById('editar-escola-municipio').value = escola.municipio || '';
            document.getElementById('editar-escola-estado').value = escola.estado || 'PA';
            document.getElementById('editar-escola-telefone').value = escola.telefone || '';
            document.getElementById('editar-escola-diretor').value = escola.diretor || '';
            openM('m-editar-escola');
        })
        .catch(e => { showToast('❌ Erro ao carregar escola: ' + e.message, 'error');
            console.error('Erro ao carregar escola:', e); });
}

async function salvarEdicaoEscola() {
    const id = document.getElementById('editar-escola-id').value;
    const nome = document.getElementById('editar-escola-nome').value.trim();
    if (!nome) { showToast('❌ O nome da escola é obrigatório!', 'error'); return; }

    const dados = {
        nome: nome,
        inep: document.getElementById('editar-escola-inep').value.trim() || null,
        municipio: document.getElementById('editar-escola-municipio').value.trim() || null,
        estado: document.getElementById('editar-escola-estado').value || 'PA',
        telefone: document.getElementById('editar-escola-telefone').value.trim() || null,
        diretor: document.getElementById('editar-escola-diretor').value.trim() || null
    };

    try {
        const btn = document.querySelector('#m-editar-escola .btn-primary');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Atualizando escola...', 'info');
        const response = await fetch(API_URL + '/api/escolas/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        btn.textContent = originalText;
        btn.disabled = false;

        if (result.ok) {
            showToast('✅ Escola "' + nome + '" atualizada com sucesso!', 'success');
            limparCache();
            closeM('m-editar-escola');
            carregarEscolas();

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-escola', id, '✅ Atualizada!');
            }, 300);

            carregarCombos();
        } else {
            showToast('❌ Erro ao atualizar escola: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao atualizar escola: ' + erro.message, 'error');
        console.error('Erro ao atualizar escola:', erro);
        const btn = document.querySelector('#m-editar-escola .btn-primary');
        if (btn) { btn.textContent = '💾 Salvar Alterações'; btn.disabled = false; }
    }
}

async function excluirEscola(id, nome) {
    if (!confirm('🗑️ EXCLUIR COMPLETAMENTE a escola "' + nome + '"\n\nIsso irá excluir TODOS os dados vinculados:\n• Turmas\n• Alunos\n\nAs provas NÃO serão afetadas.\n\nEsta ação NÃO pode ser desfeita!')) return;

    try {
        showToast('⏳ Excluindo escola...', 'info');
        const response = await fetch(`${API_URL}/api/escolas/${id}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast(`✅ Escola "${nome}" excluída com sucesso!`, 'success');
            limparCache();
        } else {
            showToast(`❌ Erro ao excluir escola: ${result.data.erro || 'Erro desconhecido'}`, 'error');
            return;
        }
        setTimeout(() => {
            carregarEscolas();
            carregarTurmas();
            carregarAlunos();
            carregarProvas();
            carregarDashboard();
            carregarResultadosComFiltros();
            carregarGabaritos();
            carregarCombos();
            carregarRelatorios();
            carregarUltimasCorrecoes();
            carregarConceitoReal();
            carregarUsuarios();
            carregarEscolasFiltroAlunos();
            carregarEscolasCorrigir();
            carregarEscolasTexto();
            carregarEscolasParaCorrecaoManual();
            carregarFiltrosRelTurma();
            carregarFiltroEscolaTurmas();
            carregarEscolasDesempenho();
        }, 1000);
    } catch (erro) {
        console.error('Erro ao excluir escola:', erro);
        showToast('❌ Erro ao excluir escola: ' + erro.message, 'error');
    }
}

// ═══ CRUD TURMA ═══
async function salvarTurma() {
    const nome = document.getElementById('turma-nome').value.trim();
    if (!nome) { showToast('❌ O nome da turma é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('turma-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }

    const dados = {
        nome: nome,
        escola_id: parseInt(escolaId),
        serie: document.getElementById('turma-serie').value || '1º Ano',
        turno: document.getElementById('turma-turno').value || 'Manhã',
        ano_letivo: parseInt(document.getElementById('turma-ano').value) || 2025,
        capacidade: parseInt(document.getElementById('turma-capacidade').value) || 35,
        professor: document.getElementById('turma-professor').value.trim() || null
    };

    try {
        const btn = document.querySelector('#m-turma .btn-green');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Salvando turma...', 'info');
        const response = await fetch(API_URL + '/api/turmas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        btn.textContent = originalText;
        btn.disabled = false;

        if (result.ok && result.data.id) {
            showToast('✅ Turma "' + nome + '" salva com sucesso!', 'success');
            limparCache();
            closeM('m-turma');
            carregarTurmas();

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-turmas', result.data.id, '✅ Nova!');
            }, 300);

            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao salvar turma: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar turma: ' + erro.message, 'error');
        console.error('Erro ao salvar turma:', erro);
        const btn = document.querySelector('#m-turma .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarTurma(id) {
    showToast('✏️ Carregando dados da turma...', 'info');
    fetch(API_URL + '/api/turmas/' + id)
        .then(r => r.json())
        .then(turma => {
            if (turma.erro) { showToast('❌ ' + turma.erro, 'error'); return; }
            document.getElementById('editar-turma-id').value = turma.id;
            document.getElementById('editar-turma-nome').value = turma.nome || '';
            document.getElementById('editar-turma-serie').value = turma.serie || '1º Ano';
            document.getElementById('editar-turma-turno').value = turma.turno || 'Manhã';
            document.getElementById('editar-turma-ano').value = turma.ano_letivo || 2025;
            document.getElementById('editar-turma-capacidade').value = turma.capacidade || 35;
            document.getElementById('editar-turma-professor').value = turma.professor || '';

            carregarEscolasComCache().then(escolas => {
                const select = document.getElementById('editar-turma-escola');
                select.innerHTML = '<option value="">Selecione a escola</option>';
                if (escolas && !escolas.erro) {
                    escolas.forEach(e => {
                        const opt = document.createElement('option');
                        opt.value = e.id;
                        opt.textContent = e.nome;
                        if (e.id == turma.escola_id) opt.selected = true;
                        select.appendChild(opt);
                    });
                }
                openM('m-editar-turma');
            }).catch(e => console.error('Erro ao carregar escolas:', e));
        })
        .catch(e => { showToast('❌ Erro ao carregar turma: ' + e.message, 'error');
            console.error('Erro ao carregar turma:', e); });
}

async function salvarEdicaoTurma() {
    const id = document.getElementById('editar-turma-id').value;
    const nome = document.getElementById('editar-turma-nome').value.trim();
    if (!nome) { showToast('❌ O nome da turma é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('editar-turma-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }

    const dados = {
        nome: nome,
        escola_id: parseInt(escolaId),
        serie: document.getElementById('editar-turma-serie').value || '1º Ano',
        turno: document.getElementById('editar-turma-turno').value || 'Manhã',
        ano_letivo: parseInt(document.getElementById('editar-turma-ano').value) || 2025,
        capacidade: parseInt(document.getElementById('editar-turma-capacidade').value) || 35,
        professor: document.getElementById('editar-turma-professor').value.trim() || null
    };

    try {
        const btn = document.querySelector('#m-editar-turma .btn-primary');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Atualizando turma...', 'info');
        const response = await fetch(API_URL + '/api/turmas/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        btn.textContent = originalText;
        btn.disabled = false;

        if (result.ok) {
            showToast('✅ Turma "' + nome + '" atualizada com sucesso!', 'success');
            limparCache();
            closeM('m-editar-turma');
            carregarTurmas();

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-turmas', id, '✅ Atualizada!');
            }, 300);

            carregarCombos();
        } else {
            showToast('❌ Erro ao atualizar turma: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao atualizar turma: ' + erro.message, 'error');
        console.error('Erro ao atualizar turma:', erro);
        const btn = document.querySelector('#m-editar-turma .btn-primary');
        if (btn) { btn.textContent = '💾 Salvar Alterações'; btn.disabled = false; }
    }
}

async function excluirTurma(id, nome) {
    if (!confirm('Excluir a turma "' + nome + '" e todos os seus dados?')) return;
    try {
        showToast('🗑️ Excluindo turma...', 'error');
        const response = await fetch(API_URL + '/api/turmas/' + id, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Turma "' + nome + '" excluída com sucesso!', 'success');
            limparCache();
            carregarTurmas();
            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao excluir turma: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        console.error('Erro ao excluir turma:', erro);
        showToast('❌ Erro ao excluir turma: ' + erro.message, 'error');
    }
}

// ═══ CRUD ALUNO ═══
async function salvarAluno() {
    const nome = document.getElementById('aluno-nome').value.trim();
    if (!nome) { showToast('❌ O nome do aluno é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('aluno-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }
    const turmaId = document.getElementById('aluno-turma').value;
    if (!turmaId) { showToast('❌ Selecione uma turma!', 'error'); return; }

    const dados = {
        nome: nome,
        escola_id: parseInt(escolaId),
        turma_id: parseInt(turmaId),
        matricula: document.getElementById('aluno-matricula').value.trim() || null,
        numero_chamada: parseInt(document.getElementById('aluno-numero').value) || null,
        data_nascimento: document.getElementById('aluno-nascimento').value || null,
        genero: document.getElementById('aluno-genero').value || null,
        responsavel: document.getElementById('aluno-responsavel').value.trim() || null,
        telefone: document.getElementById('aluno-telefone').value.trim() || null,
        email: document.getElementById('aluno-email').value.trim() || null,
        observacoes: document.getElementById('aluno-observacoes').value.trim() || null
    };

    try {
        const btn = document.querySelector('#m-aluno .btn-green');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Salvando aluno...', 'info');
        const response = await fetch(API_URL + '/api/alunos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        btn.textContent = originalText;
        btn.disabled = false;

        if (result.ok && result.data.id) {
            showToast('✅ Aluno "' + nome + '" salvo com sucesso!', 'success');
            limparCache();
            closeM('m-aluno');
            document.getElementById('aluno-nome').value = '';
            document.getElementById('aluno-matricula').value = '';
            document.getElementById('aluno-numero').value = '';
            document.getElementById('aluno-nascimento').value = '';
            document.getElementById('aluno-responsavel').value = '';
            document.getElementById('aluno-telefone').value = '';
            document.getElementById('aluno-email').value = '';
            document.getElementById('aluno-observacoes').value = '';
            document.getElementById('multi-alunos-input').value = '';
            document.getElementById('multi-status').style.display = 'none';

            await carregarAlunos();

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-alunos', result.data.id, '✅ Novo!');
            }, 300);

            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao salvar aluno: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar aluno: ' + erro.message, 'error');
        console.error('Erro ao salvar aluno:', erro);
        const btn = document.querySelector('#m-aluno .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarAluno(id) {
    showToast('✏️ Carregando dados do aluno...', 'info');
    fetch(API_URL + '/api/alunos/' + id)
        .then(r => r.json())
        .then(aluno => {
            if (aluno.erro) { showToast('❌ ' + aluno.erro, 'error'); return; }
            document.getElementById('editar-aluno-id').value = aluno.id;
            document.getElementById('editar-aluno-nome').value = aluno.nome || '';
            document.getElementById('editar-aluno-matricula').value = aluno.matricula || '';
            document.getElementById('editar-aluno-numero').value = aluno.numero_chamada || '';
            document.getElementById('editar-aluno-nascimento').value = aluno.data_nascimento || '';
            document.getElementById('editar-aluno-genero').value = aluno.genero || 'Masculino';
            document.getElementById('editar-aluno-responsavel').value = aluno.responsavel || '';
            document.getElementById('editar-aluno-telefone').value = aluno.telefone || '';
            document.getElementById('editar-aluno-email').value = aluno.email || '';
            document.getElementById('editar-aluno-observacoes').value = aluno.observacoes || '';

            carregarEscolasComCache().then(escolas => {
                const selectEscola = document.getElementById('editar-aluno-escola');
                selectEscola.innerHTML = '<option value="">Selecione a escola</option>';
                if (escolas && !escolas.erro) {
                    escolas.forEach(e => {
                        const opt = document.createElement('option');
                        opt.value = e.id;
                        opt.textContent = e.nome;
                        if (e.id == aluno.escola_id) opt.selected = true;
                        selectEscola.appendChild(opt);
                    });
                }
                if (aluno.escola_id) {
                    carregarTurmasPorEscolaParaAluno(aluno.escola_id, 'editar-aluno-turma')
                        .then(() => {
                            const selectTurma = document.getElementById('editar-aluno-turma');
                            if (selectTurma) selectTurma.value = aluno.turma_id;
                        });
                }
                openM('m-editar-aluno');
            }).catch(e => console.error('Erro ao carregar escolas:', e));
        })
        .catch(e => { showToast('❌ Erro ao carregar aluno: ' + e.message, 'error');
            console.error('Erro ao carregar aluno:', e); });
}

async function salvarEdicaoAluno() {
    const id = document.getElementById('editar-aluno-id').value;
    const nome = document.getElementById('editar-aluno-nome').value.trim();
    if (!nome) { showToast('❌ O nome do aluno é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('editar-aluno-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }
    const turmaId = document.getElementById('editar-aluno-turma').value;
    if (!turmaId) { showToast('❌ Selecione uma turma!', 'error'); return; }

    const dados = {
        nome: nome,
        escola_id: parseInt(escolaId),
        turma_id: parseInt(turmaId),
        matricula: document.getElementById('editar-aluno-matricula').value.trim() || null,
        numero_chamada: parseInt(document.getElementById('editar-aluno-numero').value) || null,
        data_nascimento: document.getElementById('editar-aluno-nascimento').value || null,
        genero: document.getElementById('editar-aluno-genero').value || null,
        responsavel: document.getElementById('editar-aluno-responsavel').value.trim() || null,
        telefone: document.getElementById('editar-aluno-telefone').value.trim() || null,
        email: document.getElementById('editar-aluno-email').value.trim() || null,
        observacoes: document.getElementById('editar-aluno-observacoes').value.trim() || null
    };

    try {
        const btn = document.querySelector('#m-editar-aluno .btn-primary');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Atualizando aluno...', 'info');
        const response = await fetch(API_URL + '/api/alunos/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        btn.textContent = originalText;
        btn.disabled = false;

        if (result.ok) {
            showToast('✅ Aluno "' + nome + '" atualizado com sucesso!', 'success');
            limparCache();
            closeM('m-editar-aluno');
            carregarAlunos();

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-alunos', id, '✅ Atualizado!');
            }, 300);

            carregarCombos();
        } else {
            showToast('❌ Erro ao atualizar aluno: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao atualizar aluno: ' + erro.message, 'error');
        console.error('Erro ao atualizar aluno:', erro);
        const btn = document.querySelector('#m-editar-aluno .btn-primary');
        if (btn) { btn.textContent = '💾 Salvar Alterações'; btn.disabled = false; }
    }
}

async function excluirAluno(id, nome) {
    if (!confirm('Excluir o aluno "' + nome + '" e todos os seus dados?')) return;
    try {
        showToast('🗑️ Excluindo aluno...', 'error');
        const response = await fetch(API_URL + '/api/alunos/' + id, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Aluno "' + nome + '" excluído com sucesso!', 'success');
            limparCache();
            carregarAlunos();
            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao excluir aluno: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        console.error('Erro ao excluir aluno:', erro);
        showToast('❌ Erro ao excluir aluno: ' + erro.message, 'error');
    }
}

// ═══ FUNÇÕES AUXILIARES ═══
function verAlunosDaTurma(id) {
    showToast('📋 Visualizando alunos da turma ID ' + id + '...', 'info');
    const selectTurma = document.getElementById('filtro-turma-alunos');
    if (selectTurma) { selectTurma.value = id;
        const event = new Event('change');
        selectTurma.dispatchEvent(event); }
    go('alunos');
}

function processarListaAlunos() {
    const textarea = document.getElementById('multi-alunos-input');
    const linhas = textarea.value.split('\n').filter(l => l.trim() !== '');
    if (linhas.length === 0) { showToast('⚠️ Cole a lista de alunos primeiro!', 'warning'); return; }

    const statusDiv = document.getElementById('multi-status');
    const statusText = document.getElementById('multi-status-text');

    let adicionados = 0,
        erros = 0;

    linhas.forEach(linha => {
        let nome = linha.trim();
        let matricula = '';
        let numero = '';

        const matchVirgula = linha.match(/^([^,]+),\s*([^,]+),\s*(\d+)?/);
        const matchTraco = linha.match(/^([^-]+)\s*-\s*([^-]+)\s*-\s*(\d+)?/);
        const matchParenteses = linha.match(/^([^(]+)\s*\(([^)]+)\)/);

        if (matchVirgula) {
            nome = matchVirgula[1].trim();
            matricula = matchVirgula[2].trim();
            numero = matchVirgula[3] ? matchVirgula[3].trim() : '';
        } else if (matchTraco) {
            nome = matchTraco[1].trim();
            matricula = matchTraco[2].trim();
            numero = matchTraco[3] ? matchTraco[3].trim() : '';
        } else if (matchParenteses) {
            nome = matchParenteses[1].trim();
            matricula = matchParenteses[2].trim();
        }

        if (nome) {
            document.getElementById('aluno-nome').value = nome;
            if (matricula) document.getElementById('aluno-matricula').value = matricula;
            if (numero) document.getElementById('aluno-numero').value = numero;
            salvarAluno();
            adicionados++;
        } else erros++;
    });

    if (adicionados > 0) {
        statusDiv.style.display = 'block';
        statusDiv.className = 'multi-status success';
        statusText.textContent = `✅ ${adicionados} alunos adicionados com sucesso! ${erros > 0 ? `(${erros} erros)` : ''}`;
        textarea.value = '';
    } else {
        statusDiv.style.display = 'block';
        statusDiv.className = 'multi-status error';
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

async function carregarCombos() {
    try {
        const escolas = await carregarEscolasComCache();

        ['turma-escola', 'prova-escola', 'lista-escola', 'editar-turma-escola'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                const current = select.value;
                select.innerHTML = '<option value="">Selecione a escola</option>';
                if (escolas && !escolas.erro) {
                    escolas.forEach(e => {
                        const opt = document.createElement('option');
                        opt.value = e.id;
                        opt.textContent = e.nome;
                        select.appendChild(opt);
                    });
                }
                if (current) select.value = current;
            }
        });

        await carregarEscolasParaAluno();

        const turmas = await carregarTurmasComCache();
        ['aluno-turma', 'modal-prova-turma', 'lista-turma', 'editar-aluno-turma'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                const current = select.value;
                select.innerHTML = '<option value="">Selecione a turma</option>';
                if (turmas && !turmas.erro) {
                    turmas.forEach(t => {
                        const opt = document.createElement('option');
                        opt.value = t.id;
                        opt.textContent = t.nome + ' - ' + (t.serie || '—');
                        select.appendChild(opt);
                    });
                }
                if (current) select.value = current;
            }
        });

        const provas = await carregarProvasComCache();
        ['gab-prova', 'corrigir-prova', 'rel-prova-select', 'txt-prova', 'rel-aluno-prova', 'filtro-prova-desempenho'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                const current = select.value;
                select.innerHTML = '<option value="">Selecione a prova</option>';
                if (provas && !provas.erro) {
                    provas.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p.id;
                        const serie = p.serie || 'Série não definida';
                        opt.textContent = p.titulo + ' - ' + serie + ' - ' + (p.disciplina || '');
                        opt.dataset.serie = serie;
                        opt.dataset.quantidade = p.quantidade_questoes || 20;
                        opt.dataset.gabarito = JSON.stringify(p.gabarito || []);
                        opt.dataset.tipo = p.tipo_questoes || '4';
                        opt.dataset.disciplina = p.disciplina || '';
                        opt.dataset.bncc = JSON.stringify(p.bncc || []);
                        select.appendChild(opt);
                    });
                }
                if (current) select.value = current;
            }
        });

        const alunos = await carregarAlunosComCache();
        ['corrigir-aluno', 'txt-aluno-select', 'rel-aluno-select', 'filtro-aluno-desempenho'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                const current = select.value;
                select.innerHTML = '<option value="">Selecione o aluno</option>';
                if (alunos && !alunos.erro) {
                    alunos.forEach(a => {
                        const opt = document.createElement('option');
                        opt.value = a.id;
                        opt.textContent = a.nome;
                        select.appendChild(opt);
                    });
                }
                if (current) select.value = current;
            }
        });
    } catch (erro) {
        console.error('Erro ao carregar combos:', erro);
    }
}

async function carregarEscolasParaAluno() {
    try {
        console.log('🔄 Carregando escolas para o select de aluno...');

        const escolas = await carregarEscolasComCache();

        if (!escolas || escolas.length === 0 || escolas.erro) {
            console.warn('⚠️ Nenhuma escola encontrada ou erro na API');
            return;
        }

        const selectCadastro = document.getElementById('aluno-escola');
        if (selectCadastro) {
            const current = selectCadastro.value;
            selectCadastro.innerHTML = '<option value="">Selecione a escola</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                selectCadastro.appendChild(opt);
            });
            if (current && escolas.some(e => e.id == current)) {
                selectCadastro.value = current;
                carregarTurmasPorEscolaParaAluno(current, 'aluno-turma');
            } else {
                const selectTurma = document.getElementById('aluno-turma');
                if (selectTurma) selectTurma.innerHTML = '<option value="">Selecione a turma</option>';
            }
            console.log('✅ Select "aluno-escola" atualizado com', escolas.length, 'escolas');
        }

        const selectEdicao = document.getElementById('editar-aluno-escola');
        if (selectEdicao) {
            const current = selectEdicao.value;
            selectEdicao.innerHTML = '<option value="">Selecione a escola</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                selectEdicao.appendChild(opt);
            });
            if (current && escolas.some(e => e.id == current)) {
                selectEdicao.value = current;
                carregarTurmasPorEscolaParaAluno(current, 'editar-aluno-turma');
            }
        }

    } catch (erro) {
        console.error('❌ Erro ao carregar escolas para o select de aluno:', erro);
    }
}

async function carregarTurmasPorEscolaParaAluno(escolaId, selectTurmaId) {
    console.log('🔄 Carregando turmas para escola:', escolaId);
    const selectTurma = document.getElementById(selectTurmaId);
    if (!selectTurma) {
        console.warn('⚠️ Select de turma não encontrado:', selectTurmaId);
        return;
    }

    selectTurma.innerHTML = '<option value="">Selecione a turma</option>';

    if (!escolaId || escolaId === '') {
        console.log('ℹ️ Nenhuma escola selecionada');
        return;
    }

    try {
        const turmas = await carregarTurmasComCache(escolaId);

        if (turmas && !turmas.erro && turmas.length > 0) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                opt.dataset.serie = t.serie || '';
                selectTurma.appendChild(opt);
            });
            console.log(`✅ ${turmas.length} turmas carregadas para a escola`);
        } else {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Nenhuma turma cadastrada';
            opt.disabled = true;
            selectTurma.appendChild(opt);
        }
    } catch (e) {
        console.error('❌ Erro ao carregar turmas:', e);
        showToast('❌ Erro ao carregar turmas: ' + e.message, 'error');
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Erro ao carregar turmas';
        opt.disabled = true;
        selectTurma.appendChild(opt);
    }
}