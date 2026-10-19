// ============================================================
// JS/PROVAS.JS — Provas + Gabaritos (CRUD + editor + produção)
// Extraído de script.js — Corte 4
// ============================================================

// ═══ DADOS DE PRODUÇÃO DE TEXTO ═══
let gabProducaoData = {
    questoes: []
};

let visualizarProvaId = null;
let visualizarProvaData = null;

// ═══════════════════════════════════════════════════════════════
// CARREGAR PROVAS (com cache próprio local)
// ═══════════════════════════════════════════════════════════════
async function carregarProvasComCache(forceRefresh) {
    if (!forceRefresh && window._provasCache) return window._provasCache;
    try {
        const r = await fetch(API_URL + '/api/provas');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const provas = await r.json();
        window._provasCache = provas || [];
        return window._provasCache;
    } catch (e) {
        console.error('❌ Erro ao carregar provas:', e);
        return [];
    }
}

async function carregarProvas() {
    try {
        const provas = await carregarProvasComCache(true);
        const tbody = document.getElementById('tb-provas');
        if (!tbody) return;

        if (!provas || provas.length === 0 || provas.erro) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma prova cadastrada</td></tr>';
        } else {
            tbody.innerHTML = provas.map((p, i) => {
                return '<tr data-id="' + p.id + '" data-nome="' + escapeAttr(p.titulo) + '">' +
                    '<td><span class="badge badge-blue">' + String(i + 1).padStart(3, '0') + '</span></td>' +
                    '<td><strong>' + escapeHtml(p.titulo) + '</strong></td>' +
                    '<td><span class="badge badge-purple">' + escapeHtml(p.serie || '—') + '</span></td>' +
                    '<td><span class="badge badge-gray">' + escapeHtml(p.disciplina || '—') + '</span></td>' +
                    '<td>' + escapeHtml(p.data_prova || '—') + '</td>' +
                    '<td><span class="badge ' + (p.gabarito && p.gabarito.length > 0 ? 'badge-green' : 'badge-orange') + '">' + (p.gabarito && p.gabarito.length > 0 ? 'Com Gabarito' : 'Sem Gabarito') + '</span></td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="visualizarProva(' + p.id + ')">👁️</button>' + (p.gabarito && p.gabarito.length > 0 ? '' : '<button class="btn btn-primary btn-sm" onclick="go(\'gabarito\')">+ Gabarito</button>') + '<button class="btn-del" onclick="excluirProva(' + p.id + ', \'' + escapeAttr(p.titulo) + '\')">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar provas:', erro);
    }
}

// ═══════════════════════════════════════════════════════════════
// VISUALIZAR PROVA
// ═══════════════════════════════════════════════════════════════
async function visualizarProva(id) {
    showToast('👁️ Carregando dados da prova...', 'info');
    try {
        const response = await fetch(`${API_URL}/api/provas/${id}`);
        const prova = await response.json();
        if (!prova || prova.erro) {
            showToast('❌ Erro ao carregar prova: ' + (prova.erro || 'Desconhecido'), 'error');
            return;
        }

        visualizarProvaId = id;
        visualizarProvaData = prova;

        const conteudo = document.getElementById('visualizar-prova-conteudo');
        if (!conteudo) return;

        const gabarito = prova.gabarito || [];
        const bncc = prova.bncc || [];
        const total = prova.quantidade_questoes || 20;
        const isProducao = (prova.disciplina === 'Produção de Texto');

        let gabHtml = '';
        if (gabarito.length > 0) {
            gabHtml = '<div style="margin-top:12px;"><strong style="color:var(--text2);">📋 Gabarito:</strong>';

            if (isProducao) {
                gabHtml += '<div style="display:flex; flex-direction:column; gap:12px; margin-top:6px;">';
                for (let i = 0; i < Math.min(gabarito.length, total); i++) {
                    const texto = gabarito[i] || '—';
                    const codigo = (i < bncc.length && bncc[i]) ? bncc[i] : '';
                    gabHtml += `
                        <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;border:1px solid var(--border);">
                            <div style="font-size:12px;font-weight:700;color:var(--text2);margin-bottom:4px;">Q${i+1}</div>
                            <div style="font-weight:700;font-size:14px;color:var(--green);">${escapeHtml(texto)}</div>
                            ${codigo ? `<div style="font-size:10px;color:var(--purple);margin-top:4px;">BNCC: ${escapeHtml(codigo)}</div>` : ''}
                        </div>
                    `;
                }
                gabHtml += '</div>';
            } else {
                gabHtml += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px;margin-top:6px;">';
                for (let i = 0; i < Math.min(gabarito.length, total); i++) {
                    const texto = gabarito[i] || '—';
                    const codigo = (i < bncc.length && bncc[i]) ? bncc[i] : '';
                    gabHtml += `<div style="background:var(--bg2);border-radius:6px;padding:4px 6px;text-align:center;border:1px solid var(--border);">
                        <div style="font-size:8px;color:var(--text3);font-weight:700;">Q${i+1}</div>
                        <div style="font-weight:700;font-size:12px;color:var(--green);">${escapeHtml(texto)}</div>
                        ${codigo ? `<div style="font-size:7px;color:var(--purple);margin-top:2px;">BNCC: ${escapeHtml(codigo)}</div>` : ''}
                    </div>`;
                }
                gabHtml += '</div>';
            }
            gabHtml += '</div>';
        } else {
            gabHtml = '<div style="margin-top:12px;color:var(--text3);font-size:13px;">⚠️ Nenhum gabarito cadastrado para esta prova.</div>';
        }

        conteudo.innerHTML = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
                <div><strong style="color:var(--text2);">📝 Título</strong><br>${escapeHtml(prova.titulo || '—')}</div>
                <div><strong style="color:var(--text2);">📚 Disciplina</strong><br>${escapeHtml(prova.disciplina || '—')}</div>
                <div><strong style="color:var(--text2);">🎓 Série</strong><br>${escapeHtml(prova.serie || '—')}</div>
                <div><strong style="color:var(--text2);">📅 Data</strong><br>${escapeHtml(prova.data_prova || '—')}</div>
                <div><strong style="color:var(--text2);">📊 Bimestre</strong><br>${escapeHtml(prova.bimestre || '—')}</div>
                <div><strong style="color:var(--text2);">🔢 Questões</strong><br>${prova.quantidade_questoes || 20}</div>
                <div><strong style="color:var(--text2);">📈 Nota Máxima</strong><br>${prova.nota_maxima || 10}</div>
                <div><strong style="color:var(--text2);">📋 Tipo</strong><br>${isProducao ? '📝 Produção de Texto' : (prova.tipo_questoes == '3' ? 'A, B, C' : 'A, B, C, D')}</div>
            </div>
            ${gabHtml}
        `;

        openM('m-visualizar-prova');
    } catch (erro) {
        console.error('Erro ao visualizar prova:', erro);
        showToast('❌ Erro ao carregar prova: ' + erro.message, 'error');
    }
}

function editarProvaDireto() {
    if (visualizarProvaId) {
        closeM('m-visualizar-prova');
        editarGabarito(visualizarProvaId);
    } else {
        showToast('❌ Nenhuma prova selecionada para editar.', 'error');
    }
}

// ═══════════════════════════════════════════════════════════════
// CRUD PROVA
// ═══════════════════════════════════════════════════════════════
async function salvarProva() {
    const titulo = document.getElementById('prova-titulo').value.trim();
    if (!titulo) { showToast('❌ O título da prova é obrigatório!', 'error'); return; }
    const serie = document.getElementById('prova-serie').value;
    if (!serie) { showToast('❌ Selecione a série!', 'error'); return; }

    const dados = {
        titulo: titulo,
        serie: serie,
        disciplina: document.getElementById('prova-disciplina').value || 'Matemática',
        bimestre: document.getElementById('prova-bimestre').value || '1º e 2º bimestre',
        data_prova: document.getElementById('prova-data').value || null,
        quantidade_questoes: parseInt(document.getElementById('prova-questoes').value) || 20,
        nota_maxima: parseFloat(document.getElementById('prova-nota').value) || 10,
        tipo_questoes: '4'
    };

    try {
        const btn = document.querySelector('#page-prova-upload .btn-green');
        const originalText = btn ? btn.textContent : '';
        if (btn) { btn.textContent = '⏳ Salvando...'; btn.disabled = true; }

        showToast('💾 Salvando prova...', 'info');
        const response = await fetch(API_URL + '/api/provas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);

        if (btn) { btn.textContent = originalText; btn.disabled = false; }

        if (result.ok && result.data.id) {
            showToast('✅ Prova "' + titulo + '" salva com sucesso para a série ' + serie + '!', 'success');
            limparCache();
            window._provasCache = null;
            document.getElementById('prova-titulo').value = '';
            const upOk = document.getElementById('up-ok');
            if (upOk) { upOk.style.display = 'block'; setTimeout(() => { upOk.style.display = 'none'; }, 3000); }
            carregarProvas();

            if (typeof tableFeedback !== 'undefined') {
                setTimeout(() => tableFeedback.destacarLinha('tb-provas', result.data.id, '✅ Nova!'), 300);
            }
            if (typeof carregarDashboard === 'function') carregarDashboard();
            if (typeof carregarCombos === 'function') carregarCombos();

            // Recarrega selects de prova em todas as telas
            if (typeof carregarProvasParaGabarito === 'function') carregarProvasParaGabarito();
            if (typeof carregarProvasParaTexto === 'function') carregarProvasParaTexto();
            if (typeof carregarProvasParaFiltro === 'function') carregarProvasParaFiltro();
            if (typeof carregarProvasParaDesempenho === 'function') carregarProvasParaDesempenho();
        } else {
            showToast('❌ Erro ao salvar prova: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar prova: ' + erro.message, 'error');
        console.error('Erro ao salvar prova:', erro);
        const btn = document.querySelector('#page-prova-upload .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarProva(id) {
    showToast('👁️ Visualizando prova ID ' + id + '...', 'info');
}

async function excluirProva(id, nome) {
    if (!confirm('Excluir a prova "' + nome + '" e todos os seus dados?')) return;
    try {
        showToast('🗑️ Excluindo prova...', 'error');
        const response = await fetch(API_URL + '/api/provas/' + id, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Prova "' + nome + '" excluída com sucesso!', 'success');
            limparCache();
            window._provasCache = null;
            carregarProvas();
            if (typeof carregarDashboard === 'function') carregarDashboard();
            if (typeof carregarCombos === 'function') carregarCombos();

            if (typeof carregarProvasParaGabarito === 'function') carregarProvasParaGabarito();
            if (typeof carregarProvasParaTexto === 'function') carregarProvasParaTexto();
            if (typeof carregarProvasParaFiltro === 'function') carregarProvasParaFiltro();
            if (typeof carregarProvasParaDesempenho === 'function') carregarProvasParaDesempenho();
        } else {
            showToast('❌ Erro ao excluir prova: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        console.error('Erro ao excluir prova:', erro);
        showToast('❌ Erro ao excluir prova: ' + erro.message, 'error');
    }
}

// Salvar prova pelo modal rápido (m-prova)
function salvarProvaModal() {
    const titulo = document.getElementById('modal-prova-titulo').value.trim();
    if (!titulo) { showToast('❌ O título da prova é obrigatório!', 'error'); return; }
    showToast('✅ Prova "' + titulo + '" salva com sucesso!', 'success');
    closeM('m-prova');
    carregarProvas();
    if (typeof carregarCombos === 'function') carregarCombos();
}

// ═══════════════════════════════════════════════════════════════
// GABARITOS
// ═══════════════════════════════════════════════════════════════
async function carregarGabaritos() {
    try {
        const provas = await carregarProvasComCache(true);
        const tbody = document.getElementById('tb-gabaritos');
        if (!tbody) return;
        const comGabarito = provas.filter(p => p.gabarito && p.gabarito.length > 0);
        if (!comGabarito || comGabarito.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Nenhum gabarito cadastrado</td></tr>';
        } else {
            tbody.innerHTML = comGabarito.map((p, i) => {
                let bnccText = '—';
                if (p.bncc && p.bncc.length > 0) {
                    const codigos = p.bncc.filter(c => c && c.trim() !== '');
                    if (codigos.length > 0) bnccText = codigos.join(', ');
                }
                const tipoTexto = p.disciplina === 'Produção de Texto' ? 'Texto' : (p.tipo_questoes == '3' ? 'A, B, C' : 'A, B, C, D');
                return '<tr data-id="' + p.id + '" data-nome="' + escapeAttr(p.titulo) + '">' +
                    '<td><span class="badge badge-blue">' + String(i + 1).padStart(3, '0') + '</span></td>' +
                    '<td>' + escapeHtml(p.titulo) + '</td>' +
                    '<td><span class="badge badge-purple">' + escapeHtml(p.serie || '—') + '</span></td>' +
                    '<td>' + (p.quantidade_questoes || (p.gabarito ? p.gabarito.length : 0) || 0) + '</td>' +
                    '<td><span class="badge ' + (tipoTexto === 'Texto' ? 'badge-purple' : (p.tipo_questoes == '3' ? 'badge-purple' : 'badge-blue')) + '">' + tipoTexto + '</span></td>' +
                    '<td style="font-size:9px; max-width:120px; word-wrap:break-word;">' + escapeHtml(bnccText) + '</td>' +
                    '<td>' + escapeHtml(p.data_prova || '—') + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarGabarito(' + p.id + ')">✏️</button><button class="btn-del" onclick="excluirGabarito(' + p.id + ', \'' + escapeAttr(p.titulo) + '\')">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar gabaritos:', erro);
    }
}

// ═══════════════════════════════════════════════════════════════
// BUILD GAB GRID
// ═══════════════════════════════════════════════════════════════
function buildGabGrid() {
    const grid = document.getElementById('gab-grid');
    const headerContainer = document.getElementById('gab-header-container');
    const infoAlts = document.getElementById('gab-info-alts');
    const ptsRow = document.getElementById('gab-pts-row');
    if (!grid) return;

    const serieEl = document.getElementById('gab-serie');
    const totalEl = document.getElementById('gab-total');
    const provaSelect = document.getElementById('gab-prova');

    if (!serieEl || !totalEl || !provaSelect) return;

    const selectedOption = provaSelect.options[provaSelect.selectedIndex];
    const provaNome = selectedOption ? selectedOption.text || 'Gabarito' : 'Gabarito';
    const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
    const isProducao = (disciplina === 'Produção de Texto');

    if (ptsRow) {
        ptsRow.style.display = isProducao ? 'none' : 'grid';
    }

    if (headerContainer) {
        const disciplinaLabel = disciplina || 'Disciplina';
        headerContainer.innerHTML = `
            <div class="gab-header-title">
                <span class="icon">📝</span>
                <span>Gabarito: <span class="prova-nome">${escapeHtml(provaNome)}</span></span>
                <span class="badge-disciplina">${escapeHtml(disciplinaLabel)}</span>
            </div>
        `;
    }

    if (infoAlts) {
        if (isProducao) {
            infoAlts.innerHTML = '<div style="padding:8px 14px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;font-size:12px;font-weight:700;color:var(--orange);">📝 PRODUÇÃO DE TEXTO — Título + Cabeçalho + Alternativas A/B/C</div>';
        } else {
            infoAlts.innerHTML = '<div style="padding:8px 14px;background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.3);border-radius:8px;font-size:12px;font-weight:700;color:#a78bfa;">📝 Gabarito com 4 alternativas: A, B, C, D</div>';
        }
    }

    const total = parseInt(totalEl.value) || 20;

    if (isProducao) {
        grid.style.display = 'flex';
        grid.style.flexDirection = 'column';
        grid.style.gap = '16px';
        grid.innerHTML = '';

        if (!gabProducaoData.questoes || gabProducaoData.questoes.length === 0) {
            gabProducaoData.questoes = [];
            for (let i = 0; i < total; i++) {
                gabProducaoData.questoes.push({
                    titulo: `Q${i + 1}`,
                    cabecalho: '',
                    alternativas: { A: '', B: '', C: '' },
                    situacao: ''
                });
            }
        } else {
            while (gabProducaoData.questoes.length < total) {
                const idx = gabProducaoData.questoes.length + 1;
                gabProducaoData.questoes.push({
                    titulo: `Q${idx}`,
                    cabecalho: '',
                    alternativas: { A: '', B: '', C: '' },
                    situacao: ''
                });
            }
            if (gabProducaoData.questoes.length > total) {
                gabProducaoData.questoes = gabProducaoData.questoes.slice(0, total);
            }
        }

        for (let i = 0; i < total; i++) {
            const q = gabProducaoData.questoes[i];
            const card = document.createElement('div');
            card.className = 'gab-producao-questao';
            card.dataset.index = i;

            const header = document.createElement('div');
            header.className = 'gab-producao-header';
            header.innerHTML = `
                <input class="gab-titulo-editavel" type="text" value="${escapeAttr(q.titulo || 'Q' + (i+1))}"
                       data-index="${i}" onchange="atualizarTituloProducao(this)" placeholder="Ex: Q1 / Tema 1">
                <textarea class="gab-cabecalho" data-index="${i}"
                          onchange="atualizarCabecalhoProducao(this)"
                          placeholder="Escreva o cabeçalho/tema da questão aqui...">${escapeHtml(q.cabecalho || '')}</textarea>
            `;
            card.appendChild(header);

            const altsLista = document.createElement('div');
            altsLista.className = 'gab-alternativas-lista';
            altsLista.id = `gab-alts-${i}`;
            renderizarAlternativasProducao(i, altsLista);
            card.appendChild(altsLista);

            grid.appendChild(card);
        }
        return;
    }

    const alts = ['A', 'B', 'C', 'D'];
    const lbl = document.getElementById('gab-label');
    if (lbl) {
        lbl.textContent = '📝 Gabarito com 4 alternativas: A, B, C, D';
    }

    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(120px, 1fr))';
    grid.style.gap = '14px';

    grid.innerHTML = '';
    for (let i = 1; i <= total; i++) {
        const div = document.createElement('div');
        div.className = 'gab-item';
        let opts = '<option value="">—</option>';
        alts.forEach(a => { opts += '<option>' + a + '</option>'; });
        div.innerHTML = `
            <div class="gab-num">Q${i}</div>
            <select class="gab-select" onchange="this.classList.toggle('filled', this.value!='')">${opts}</select>
            <input class="gab-bncc" placeholder="BNCC" style="width:100%; margin-top:2px; padding:5px 8px; background:var(--bg); border:2px solid var(--border2); border-radius:6px; color:var(--text); font-size:10px; text-align:center;" />
        `;
        grid.appendChild(div);
    }
}

// ═══════════════════════════════════════════════════════════════
// ALTERNATIVAS DE PRODUÇÃO
// ═══════════════════════════════════════════════════════════════
function renderizarAlternativasProducao(index, container) {
    const q = gabProducaoData.questoes[index];
    if (!q) return;
    const altsOrdenadas = Object.keys(q.alternativas).sort();
    container.innerHTML = '';

    altsOrdenadas.forEach(letra => {
        const item = document.createElement('div');
        item.className = 'gab-alternativa-item';
        item.innerHTML = `
            <div class="alt-letra">${escapeHtml(letra)}</div>
            <textarea class="alt-texto" placeholder="Digite a resposta esperada para ${escapeHtml(letra)}..."
                      data-index="${index}" data-letra="${letra}"
                      onchange="atualizarAlternativaProducao(this)">${escapeHtml(q.alternativas[letra] || '')}</textarea>
            ${altsOrdenadas.length > 1 ? `<button class="btn-remover-alt" onclick="removerAlternativaProducao(${index}, '${letra}')" title="Remover alternativa">×</button>` : ''}
        `;
        container.appendChild(item);
    });

    const letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const ultimaLetra = altsOrdenadas[altsOrdenadas.length - 1] || 'C';
    const proximaLetra = letras[letras.indexOf(ultimaLetra) + 1];

    if (proximaLetra && letras.indexOf(ultimaLetra) < 25) {
        const btnAdd = document.createElement('button');
        btnAdd.className = 'btn btn-outline btn-sm';
        btnAdd.style.cssText = 'align-self:flex-start; margin-top:4px;';
        btnAdd.textContent = `➕ Adicionar alternativa ${proximaLetra}`;
        btnAdd.onclick = () => adicionarAlternativaProducao(index);
        container.appendChild(btnAdd);
    }
}

function atualizarTituloProducao(input) {
    const idx = parseInt(input.dataset.index);
    if (gabProducaoData.questoes[idx]) {
        gabProducaoData.questoes[idx].titulo = input.value;
    }
}

function atualizarCabecalhoProducao(textarea) {
    const idx = parseInt(textarea.dataset.index);
    if (gabProducaoData.questoes[idx]) {
        gabProducaoData.questoes[idx].cabecalho = textarea.value;
    }
}

function atualizarAlternativaProducao(textarea) {
    const idx = parseInt(textarea.dataset.index);
    const letra = textarea.dataset.letra;
    if (gabProducaoData.questoes[idx]) {
        gabProducaoData.questoes[idx].alternativas[letra] = textarea.value;

        const letras = Object.keys(gabProducaoData.questoes[idx].alternativas).sort();
        const ultimaLetra = letras[letras.length - 1];
        if (letra === ultimaLetra && textarea.value.trim() !== '') {
            const letras26 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
            const proxima = letras26[letras26.indexOf(ultimaLetra) + 1];
            if (proxima && !gabProducaoData.questoes[idx].alternativas[proxima]) {
                gabProducaoData.questoes[idx].alternativas[proxima] = '';
                const container = document.getElementById(`gab-alts-${idx}`);
                if (container) renderizarAlternativasProducao(idx, container);
            }
        }
    }
}

function atualizarSituacaoProducao(select) {
    const idx = parseInt(select.dataset.index);
    if (gabProducaoData.questoes[idx]) {
        gabProducaoData.questoes[idx].situacao = select.value;
    }
}

function adicionarAlternativaProducao(index) {
    const q = gabProducaoData.questoes[index];
    if (!q) return;
    const letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const atual = Object.keys(q.alternativas).sort();
    const ultima = atual[atual.length - 1] || 'A';
    const proxima = letras[letras.indexOf(ultima) + 1];
    if (proxima) {
        q.alternativas[proxima] = '';
        const container = document.getElementById(`gab-alts-${index}`);
        if (container) renderizarAlternativasProducao(index, container);
    }
}

function removerAlternativaProducao(index, letra) {
    const q = gabProducaoData.questoes[index];
    if (!q) return;
    if (Object.keys(q.alternativas).length <= 1) {
        showToast('⚠️ Deve haver pelo menos uma alternativa!', 'warning');
        return;
    }
    delete q.alternativas[letra];
    const container = document.getElementById(`gab-alts-${index}`);
    if (container) renderizarAlternativasProducao(index, container);
}

// ═══════════════════════════════════════════════════════════════
// AÇÕES DO GABARITO
// ═══════════════════════════════════════════════════════════════
function fillGabRand() {
    const provaSelect = document.getElementById('gab-prova');
    const selectedOption = provaSelect.options[provaSelect.selectedIndex];
    const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
    if (disciplina === 'Produção de Texto') {
        showToast('🎲 Preenchimento automático não disponível para produção de texto.', 'warning');
        return;
    }
    const alts = ['A', 'B', 'C', 'D'];
    document.querySelectorAll('.gab-select').forEach(s => { s.value = alts[Math.floor(Math.random() * alts.length)]; s.classList.add('filled'); });
    showToast('🎲 Gabarito de teste preenchido!');
}

function clearGab() {
    const provaSelect = document.getElementById('gab-prova');
    const selectedOption = provaSelect.options[provaSelect.selectedIndex];
    const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
    const isProducao = (disciplina === 'Produção de Texto');
    if (isProducao) {
        document.querySelectorAll('.gab-titulo-editavel').forEach((inp, i) => inp.value = 'Q' + (i+1));
        document.querySelectorAll('.gab-cabecalho').forEach(ta => ta.value = '');
        document.querySelectorAll('.alt-texto').forEach(ta => ta.value = '');
        document.querySelectorAll('.gab-situacao').forEach(sel => sel.value = '');
        gabProducaoData.questoes.forEach(q => {
            q.cabecalho = '';
            q.situacao = '';
            Object.keys(q.alternativas).forEach(k => q.alternativas[k] = '');
        });
    } else {
        document.querySelectorAll('.gab-select').forEach(s => { s.value = ''; s.classList.remove('filled'); });
        document.querySelectorAll('.gab-bncc').forEach(inp => inp.value = '');
    }
}

async function saveGab() {
    try {
        const provaSelect = document.getElementById('gab-prova');
        const selectedOption = provaSelect.options[provaSelect.selectedIndex];
        const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
        const isProducao = (disciplina === 'Produção de Texto');

        const provaId = provaSelect.value;
        if (!provaId) { showToast('❌ Selecione uma prova primeiro!', 'error'); return; }

        if (isProducao) {
            const total = gabProducaoData.questoes.length;
            if (total === 0) {
                showToast('⚠️ Nenhuma questão para salvar!', 'error');
                return;
            }

            const textos_questoes = gabProducaoData.questoes.map(q => ({
                titulo: q.titulo || '',
                cabecalho: q.cabecalho || '',
                alternativas: q.alternativas || {}
            }));

            const respostas = gabProducaoData.questoes.map(q => {
                const alts = q.alternativas || {};
                return Object.keys(alts).sort().map(k => `${k}) ${alts[k] || ''}`).join('\n');
            });

            const niveis = gabProducaoData.questoes.map(q => q.situacao || '');
            const bncc = gabProducaoData.questoes.map(() => '');

            showToast('💾 Salvando gabarito de Produção...', 'info');
            const response = await fetch(`${API_URL}/api/gabaritos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prova_id: parseInt(provaId),
                    respostas: respostas,
                    bncc: bncc,
                    textos_questoes: textos_questoes,
                    niveis: niveis
                })
            });
            const result = await response.json();

            if (response.ok && result.id) {
                showToast(`✅ ${result.mensagem || 'Gabarito salvo!'}`, 'success');
                limparCache();
                window._provasCache = null;
                carregarGabaritos();
                if (typeof carregarCombos === 'function') carregarCombos();
                carregarProvas();
            } else {
                showToast(`❌ ${result.erro || 'Erro desconhecido'}`, 'error');
            }
            return;
        }

        const respostas = [];
        const bncc = [];

        const selects = document.querySelectorAll('.gab-select');
        const bnccInputs = document.querySelectorAll('.gab-bncc');
        selects.forEach((s, idx) => {
            respostas.push(s.value || '');
            if (bnccInputs[idx]) bncc.push(bnccInputs[idx].value.trim() || '');
        });

        const respostasValidas = respostas.filter(r => r !== '');
        if (respostasValidas.length === 0) { showToast('⚠️ Preencha pelo menos uma questão do gabarito!', 'error'); return; }

        showToast('💾 Salvando gabarito...', 'info');
        const payload = { prova_id: parseInt(provaId), respostas: respostas, bncc: bncc };
        const response = await fetch(`${API_URL}/api/gabaritos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (response.ok && result.id) {
            showToast(`✅ ${result.mensagem || 'Gabarito salvo com sucesso!'}`, 'success');
            limparCache();
            window._provasCache = null;
            carregarGabaritos();
            if (typeof carregarCombos === 'function') carregarCombos();
            carregarProvas();
        } else {
            showToast(`❌ ${result.erro || 'Erro desconhecido'}`, 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar gabarito: ' + erro.message, 'error');
        console.error('Erro saveGab:', erro);
    }
}

function editarGabarito(id) {
    showToast('✏️ Carregando gabarito...', 'info');
    fetch(API_URL + '/api/provas/' + id)
        .then(r => r.json())
        .then(prova => {
            if (prova.erro) { showToast('❌ ' + prova.erro, 'error'); return; }
            if (prova.gabarito && prova.gabarito.length > 0) {
                const gabarito = prova.gabarito;
                const bncc = prova.bncc || [];
                const disciplina = prova.disciplina || '';
                const isProducao = (disciplina === 'Produção de Texto');

                go('gabarito');

                setTimeout(() => {
                    const serieMap = { '1º Ano': '1', '2º Ano': '2', '3º Ano': '3', '4º Ano': '4', '5º Ano': '5', '6º Ano': '6', '7º Ano': '7', '8º Ano': '8', '9º Ano': '9' };
                    const serieVal = serieMap[prova.serie] || '2';
                    document.getElementById('gab-serie').value = serieVal;
                    document.getElementById('gab-total').value = prova.quantidade_questoes || 20;

                    const selectProva = document.getElementById('gab-prova');
                    if (selectProva) selectProva.value = id;

                    if (isProducao) {
                        const textos = prova.textos_questoes || [];
                        const niveis = prova.niveis || [];
                        const total = prova.quantidade_questoes || gabarito.length || 20;

                        gabProducaoData.questoes = [];
                        for (let i = 0; i < total; i++) {
                            const tq = textos[i] || {};
                            gabProducaoData.questoes.push({
                                titulo: (tq && tq.titulo) ? tq.titulo : `Q${i + 1}`,
                                cabecalho: (tq && tq.cabecalho) ? tq.cabecalho : '',
                                alternativas: (tq && tq.alternativas) ? { ...tq.alternativas } : { A: '', B: '', C: '' },
                                situacao: niveis[i] || ''
                            });
                        }
                    }

                    buildGabGrid();

                    setTimeout(() => {
                        if (isProducao) {
                            showToast('📋 Gabarito de Produção carregado para edição!', 'success');
                        } else {
                            const selects = document.querySelectorAll('.gab-select');
                            const bnccInputs = document.querySelectorAll('.gab-bncc');
                            selects.forEach((s, i) => {
                                if (i < gabarito.length && gabarito[i]) { s.value = gabarito[i]; s.classList.add('filled'); }
                            });
                            bnccInputs.forEach((inp, i) => {
                                if (i < bncc.length && bncc[i]) inp.value = bncc[i];
                            });
                            showToast('📋 Gabarito carregado para edição!', 'success');
                        }
                    }, 100);
                }, 150);
            } else {
                showToast('⚠️ Esta prova não tem gabarito cadastrado', 'warning');
                go('gabarito');
            }
        })
        .catch(e => { showToast('❌ Erro ao carregar gabarito: ' + e.message, 'error'); console.error('Erro ao carregar gabarito:', e); });
}

async function excluirGabarito(id, nome) {
    if (!confirm('Excluir o gabarito da prova "' + nome + '"?')) return;
    try {
        showToast('🗑️ Excluindo gabarito...', 'error');
        const response = await fetch(API_URL + '/api/gabaritos/' + id, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Gabarito excluído com sucesso!', 'success');
            limparCache();
            window._provasCache = null;
            carregarGabaritos();
            carregarProvas();
        } else {
            showToast('❌ Erro ao excluir gabarito: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        console.error('Erro ao excluir gabarito:', erro);
        showToast('❌ Erro ao excluir gabarito: ' + erro.message, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════
// AUXILIARES DE PROVA
// ═══════════════════════════════════════════════════════════════

// Popula o grid de gabarito dentro do modal de prova (m-prova)
function gerarGabaritoModal(tipo) {
    const grid = document.getElementById('modal-gabarito-grid');
    if (!grid) return;
    const numQuestoes = 20;
    const alts = tipo == '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
    grid.innerHTML = '';
    for (let i = 1; i <= numQuestoes; i++) {
        const input = document.createElement('input');
        input.type = 'text';
        input.maxLength = 1;
        input.style.width = '40px';
        input.style.height = '35px';
        input.style.textAlign = 'center';
        input.style.background = 'var(--bg2)';
        input.style.border = '1.5px solid var(--border2)';
        input.style.borderRadius = '6px';
        input.style.color = 'var(--text)';
        input.style.fontWeight = 'bold';
        input.style.fontSize = '14px';
        input.style.textTransform = 'uppercase';
        input.placeholder = i;
        input.title = 'Questão ' + i;
        input.addEventListener('input', function() {
            this.value = this.value.toUpperCase().replace(/[^A-D]/g, '');
            if (this.value && !alts.includes(this.value)) this.value = '';
        });
        grid.appendChild(input);
    }
}

// Atualiza o aviso "Gabarito com N alternativas" no cadastro de prova
function atualizarInfoAlts() {
    const disciplina = document.getElementById('prova-disciplina')?.value || '';
    const info = document.getElementById('info-alts');
    if (!info) return;
    if (disciplina === 'Produção de Texto') {
        info.textContent = '📝 Produção de Texto — Gabarito com resposta descritiva e níveis BNCC';
        info.style.color = '#a78bfa';
        info.style.borderColor = 'rgba(139,92,246,.25)';
        info.style.background = 'rgba(139,92,246,.07)';
    } else {
        info.textContent = '📝 Gabarito com 4 alternativas: A, B, C, D';
        info.style.color = 'var(--blue)';
        info.style.borderColor = 'rgba(59,130,246,.25)';
        info.style.background = 'rgba(59,130,246,.07)';
    }
}

// Popula o select de turma no modal de prova (cadastro rápido)
function carregarTurmasProva() {
    const escolaId = document.getElementById('prova-escola')?.value;
    if (!escolaId) return;
    const select = document.getElementById('prova-turma');
    if (!select) return;
    select.innerHTML = '<option value="">Selecione a turma</option>';
    carregarTurmasComCache(escolaId).then(turmas => {
        if (turmas && !turmas.erro) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '—');
                select.appendChild(opt);
            });
        }
    }).catch(e => console.error(e));
}

// Popula o select de número de questões no cadastro de prova
function popularSelectQuestoes() {
    const select = document.getElementById('prova-questoes');
    if (!select) return;
    select.innerHTML = '';
    for (let i = 1; i <= 30; i++) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = i;
        if (i === 20) opt.selected = true;
        select.appendChild(opt);
    }
}

// Popula o select de número de questões no gabarito
function popularSelectGabTotal() {
    const select = document.getElementById('gab-total');
    if (!select) return;
    select.innerHTML = '';
    for (let i = 1; i <= 30; i++) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = i;
        if (i === 20) opt.selected = true;
        select.appendChild(opt);
    }
}

// ═══════════════════════════════════════════════════════════════
// POPULAR SELECTS DE PROVA EM TODAS AS TELAS
// ═══════════════════════════════════════════════════════════════

// 1) Gabarito — popula #gab-prova
async function carregarProvasParaGabarito() {
    const sel = document.getElementById('gab-prova');
    if (!sel) return;

    try {
        const provas = await carregarProvasComCache();
        sel.innerHTML = '<option value="">Selecione...</option>' +
            provas.map(p => `<option value="${p.id}" data-disciplina="${escapeAttr(p.disciplina || '')}">${escapeHtml(p.titulo)} — ${escapeHtml(p.serie || '')} (${escapeHtml(p.disciplina || 'Sem disciplina')})</option>`).join('');
        console.log('✅ Provas para gabarito carregadas:', provas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar provas para gabarito:', e);
        sel.innerHTML = '<option value="">Erro ao carregar provas</option>';
    }
}

// 2) Correção de Texto — popula #txt-prova
async function carregarProvasParaTexto() {
    const sel = document.getElementById('txt-prova');
    if (!sel) return;

    try {
        const provas = await carregarProvasComCache();
        sel.innerHTML = '<option value="">Selecione...</option>' +
            provas.map(p => `<option value="${p.id}">${escapeHtml(p.titulo)} — ${escapeHtml(p.serie || '')}</option>`).join('');
        console.log('✅ Provas para texto carregadas:', provas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar provas para texto:', e);
    }
}

// 3) Filtros de Resultados/Rel. Turma — popula #filtro-prova e #rel-turma-prova
async function carregarProvasParaFiltro() {
    const ids = ['filtro-prova', 'rel-turma-prova'];

    try {
        const provas = await carregarProvasComCache();
        ids.forEach(id => {
            const sel = document.getElementById(id);
            if (sel) {
                sel.innerHTML = '<option value="">Todas as provas</option>' +
                    provas.map(p => `<option value="${p.id}" data-disciplina="${escapeAttr(p.disciplina || '')}">${escapeHtml(p.titulo)}</option>`).join('');
            }
        });
        console.log('✅ Provas para filtros carregadas:', provas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar provas para filtros:', e);
    }
}

// 4) Desempenho — popula #filtro-prova-desempenho
async function carregarProvasParaDesempenho() {
    const sel = document.getElementById('filtro-prova-desempenho');
    if (!sel) return;

    try {
        const provas = await carregarProvasComCache();
        sel.innerHTML = '<option value="">Selecione a prova...</option>' +
            provas.map(p => `<option value="${p.id}" data-disciplina="${escapeAttr(p.disciplina || '')}">${escapeHtml(p.titulo)} — ${escapeHtml(p.serie || '')}</option>`).join('');
        console.log('✅ Provas para desempenho carregadas:', provas.length);
    } catch (e) {
        console.error('❌ Erro ao carregar provas para desempenho:', e);
    }
}

console.log('✅ js/provas.js carregado');
