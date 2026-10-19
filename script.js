// ============================================
// CONFIGURAÇÃO DA API
// ============================================
const API_URL = 'https://adabee-sistema-wg2a.onrender.com';
let camStream = null;
let camFacing = 'environment';
let delTarget = null;
let ultimaImagem = null;
let gerandoDocumento = false;
let paginaAtual = 'dashboard';

// ============================================
// ═══ SEGURANÇA — ESCAPE HTML (anti-XSS) ═══
// ============================================
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function escapeAttr(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ============================================
// SISTEMA DE PROGRESSO VISUAL
// ============================================
class ProgressManager {
    constructor() {
        this.modal = null;
        this.barra = null;
        this.textoEtapa = null;
        this.textoTempo = null;
        this.etapas = [];
        this.etapaAtual = 0;
        this.tempoInicio = null;
        this.timer = null;
        this.criarModal();
    }

    criarModal() {
        this.modal = document.getElementById('progress-modal');
        this.barra = document.getElementById('progress-barra');
        this.textoEtapa = document.getElementById('progress-status');
        this.textoTempo = document.getElementById('progress-tempo');
        this.porcentagem = document.getElementById('progress-porcentagem');
        this.containerEtapas = document.getElementById('progress-etapas');
        this.titulo = document.getElementById('progress-titulo');
        this.icone = document.getElementById('progress-icone');
        this.fecharBtn = document.getElementById('progress-fechar');
        this.cancelarBtn = document.getElementById('progress-cancelar');
    }

    iniciar(titulo, etapas, icone = '🤖') {
        this.etapas = etapas.map(e => ({ ...e, concluida: false }));
        this.etapaAtual = 0;
        this.tempoInicio = Date.now();
        this.timer = null;

        this.titulo.textContent = titulo;
        this.icone.textContent = icone;
        this.barra.style.width = '0%';
        this.barra.style.background = 'linear-gradient(90deg, #8b5cf6, #6d28d9)';
        this.porcentagem.textContent = '0%';
        this.textoTempo.textContent = '⏱️ estimando...';
        this.fecharBtn.style.display = 'none';
        this.cancelarBtn.style.display = 'inline-flex';

        this.containerEtapas.innerHTML = '';
        this.etapas.forEach((etapa, index) => {
            const div = document.createElement('div');
            div.id = `progress-etapa-${index}`;
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.gap = '8px';
            div.style.padding = '4px 8px';
            div.style.borderRadius = '4px';
            div.style.opacity = index === 0 ? '1' : '0.5';
            div.innerHTML = `
                <span style="font-size: 14px;" id="progress-icon-${index}">${index === 0 ? '⏳' : '○'}</span>
                <span>${etapa.nome}</span>
                <span style="margin-left: auto; font-size: 11px; color: var(--text3);" id="progress-status-${index}">
                    ${index === 0 ? '⏳ em andamento...' : '⏳ aguardando'}
                </span>
            `;
            this.containerEtapas.appendChild(div);
        });

        this.modal.style.display = 'flex';
        this.modal.classList.add('show');
        this.atualizarEtapa(0);
    }

    atualizarEtapa(index) {
        this.etapaAtual = index;
        const progresso = (index / this.etapas.length) * 100;
        this.barra.style.width = progresso + '%';
        this.porcentagem.textContent = Math.round(progresso) + '%';

        if (index < this.etapas.length) {
            this.textoEtapa.textContent = this.etapas[index].descricao || this.etapas[index].nome;

            if (index > 0) {
                const etapaAnterior = document.getElementById(`progress-etapa-${index-1}`);
                if (etapaAnterior) {
                    etapaAnterior.style.opacity = '0.7';
                    const icon = document.getElementById(`progress-icon-${index-1}`);
                    if (icon) icon.textContent = '✅';
                    const status = document.getElementById(`progress-status-${index-1}`);
                    if (status) status.textContent = '✅ concluído';
                }
            }

            const etapaAtualEl = document.getElementById(`progress-etapa-${index}`);
            if (etapaAtualEl) {
                etapaAtualEl.style.opacity = '1';
                etapaAtualEl.style.background = 'rgba(139, 92, 246, 0.1)';
                const icon = document.getElementById(`progress-icon-${index}`);
                if (icon) icon.textContent = '⏳';
                const status = document.getElementById(`progress-status-${index}`);
                if (status) status.textContent = '⏳ em andamento...';
            }
        }

        this.atualizarTempoEstimado();
    }

    atualizarTempoEstimado() {
        if (this.tempoInicio) {
            const elapsed = (Date.now() - this.tempoInicio) / 1000;
            const total = this.etapas.length;
            const atual = this.etapaAtual + 1;

            if (atual > 0 && atual <= total) {
                const mediaPorEtapa = elapsed / atual;
                const restante = (total - atual) * mediaPorEtapa;

                if (restante > 0) {
                    const minutos = Math.floor(restante / 60);
                    const segundos = Math.floor(restante % 60);
                    this.textoTempo.textContent = `⏱️ ~${minutos > 0 ? minutos + 'm ' : ''}${segundos}s restantes`;
                }
            }
        }
    }

    concluirEtapa(index) {
        if (index < this.etapas.length) {
            const etapaEl = document.getElementById(`progress-etapa-${index}`);
            if (etapaEl) {
                etapaEl.style.opacity = '0.7';
                const icon = document.getElementById(`progress-icon-${index}`);
                if (icon) icon.textContent = '✅';
                const status = document.getElementById(`progress-status-${index}`);
                if (status) status.textContent = '✅ concluído';
            }
        }
    }

    proximaEtapa() {
        const proxima = this.etapaAtual + 1;
        if (proxima < this.etapas.length) {
            this.atualizarEtapa(proxima);
        }
        return proxima;
    }

    finalizar(mensagem = '✅ Processamento concluído com sucesso!') {
        this.barra.style.width = '100%';
        this.porcentagem.textContent = '100%';
        this.textoEtapa.textContent = mensagem;
        this.textoTempo.textContent = '✅ concluído!';
        this.fecharBtn.style.display = 'inline-flex';
        this.cancelarBtn.style.display = 'none';

        this.etapas.forEach((_, index) => {
            this.concluirEtapa(index);
        });

        setTimeout(() => {
            this.fechar();
        }, 2000);
    }

    fechar() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        this.modal.style.display = 'none';
        this.modal.classList.remove('show');
    }

    erro(mensagem) {
        this.barra.style.width = '100%';
        this.barra.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';
        this.porcentagem.textContent = '❌ ERRO';
        this.textoEtapa.textContent = '❌ ' + mensagem;
        this.icone.textContent = '❌';
        this.textoTempo.textContent = '❌ falhou';
        this.fecharBtn.style.display = 'inline-flex';
        this.cancelarBtn.style.display = 'none';

        const etapaAtualEl = document.getElementById(`progress-etapa-${this.etapaAtual}`);
        if (etapaAtualEl) {
            const icon = document.getElementById(`progress-icon-${this.etapaAtual}`);
            if (icon) icon.textContent = '❌';
            const status = document.getElementById(`progress-status-${this.etapaAtual}`);
            if (status) {
                status.textContent = '❌ erro';
                status.style.color = 'var(--red)';
            }
        }
    }
}

const progressManager = new ProgressManager();

// ============================================
// SISTEMA DE FEEDBACK VISUAL PARA TABELAS
// ============================================
class TableFeedback {
    constructor() {
        this.animations = new Map();
    }

    destacarLinha(tableId, rowId, message = '✅ Salvo!') {
        const table = document.getElementById(tableId);
        if (!table) return;

        const row = table.querySelector(`tr[data-id="${rowId}"]`);
        if (!row) return;

        if (this.animations.has(rowId)) {
            clearTimeout(this.animations.get(rowId));
            this.animations.delete(rowId);
        }

        row.style.transition = 'all 0.3s ease';
        row.style.background = 'rgba(16, 185, 129, 0.15)';
        row.style.borderLeft = '4px solid var(--green)';
        row.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.1)';

        const firstCell = row.querySelector('td:first-child');
        if (firstCell && !firstCell.querySelector('.save-badge')) {
            const badge = document.createElement('span');
            badge.className = 'save-badge badge badge-green';
            badge.textContent = message;
            badge.style.marginLeft = '8px';
            badge.style.fontSize = '8px';
            firstCell.appendChild(badge);
        }

        const timeout = setTimeout(() => {
            row.style.background = '';
            row.style.borderLeft = '';
            row.style.boxShadow = '';

            const badge = firstCell?.querySelector('.save-badge');
            if (badge) {
                badge.style.transition = 'opacity 0.5s ease';
                badge.style.opacity = '0';
                setTimeout(() => badge.remove(), 500);
            }

            this.animations.delete(rowId);
        }, 3000);

        this.animations.set(rowId, timeout);
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

const tableFeedback = new TableFeedback();

// ============================================
// FUNÇÃO AUXILIAR SLEEP
// ============================================
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================
// SISTEMA DE CACHE
// ============================================
const cache = {
    escolas: null,
    turmas: {},
    alunos: {},
    provas: null,
    ultima_atualizacao: {}
};

const TEMPO_CACHE = 30000;

function isCacheValido(chave) {
    if (!cache.ultima_atualizacao[chave]) return false;
    return (Date.now() - cache.ultima_atualizacao[chave]) < TEMPO_CACHE;
}

async function carregarEscolasComCache(forceRefresh = false) {
    if (!forceRefresh && cache.escolas && isCacheValido('escolas')) return cache.escolas;
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
    if (!forceRefresh && cache.turmas[chave] && isCacheValido(chave)) return cache.turmas[chave];
    try {
        let url = `${API_URL}/api/turmas`;
        if (escolaId && escolaId !== '') url += `?escola_id=${escolaId}`;
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
    if (!forceRefresh && cache.alunos[chave] && isCacheValido(chave)) return cache.alunos[chave];
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
    if (!forceRefresh && cache.provas && isCacheValido('provas')) return cache.provas;
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

function limparCache() {
    cache.escolas = null;
    cache.turmas = {};
    cache.alunos = {};
    cache.provas = null;
    cache.ultima_atualizacao = {};
}

// ============================================
// FUNÇÕES AUXILIARES
// ============================================
function setText(id, valor) {
    const el = document.getElementById(id);
    if (el) el.textContent = valor;
}

function setHTML(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

let correcaoManualData = {
    alunoId: null, alunoNome: '', provaId: null, provaTitulo: '',
    gabarito: [], respostasAluno: [], quantidade: 20,
    alternativas: ['A', 'B', 'C', 'D'],
    notaMaxima: 10, notaMinima: 5, valorPorQuestao: 0.5,
    serie: '1º Ano', disciplina: '',
    confianca_por_questao: [], questoes_suspeitas: []
};

let cmStandaloneData = {
    escolaId: null, turmaId: null, provaId: null, alunoId: null,
    alunoNome: '', turmaNome: '', serie: '', escolaNome: '',
    gabarito: [], respostas: [], quantidade: 20,
    alternativas: ['A', 'B', 'C', 'D'],
    notaMaxima: 10, notaMinima: 5, valorPorQuestao: 0.5,
    provaTitulo: '', provaData: '', disciplina: '',
    confianca_por_questao: [], questoes_suspeitas: []
};

let usuarioEditandoId = null;
let gabProducaoData = { questoes: [] };
let autoModoAtivo = false;

// ============================================
// PROCESSAR RESPOSTAS DA API
// ============================================
async function processarRespostaAPI(response) {
    let result;
    const contentType = response.headers.get('content-type');

    if (contentType && contentType.includes('application/json')) {
        try { result = await response.json(); }
        catch (e) { result = { erro: 'Erro ao processar JSON' }; }
    } else {
        const text = await response.text();
        try { result = JSON.parse(text); }
        catch (e) {
            if (response.ok) result = { sucesso: true, mensagem: 'Operação realizada com sucesso' };
            else result = { sucesso: false, erro: 'Erro ' + response.status + ': ' + text.substring(0, 100) };
        }
    }

    return { ok: response.ok || result.sucesso === true, data: result, status: response.status };
}

// ============================================
// ATUALIZAR DATAS DE IMPRESSÃO
// ============================================
function atualizarDatasImpressao() {
    const agora = new Date();
    const dataFormatada = agora.toLocaleDateString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
    ['print-data-dash', 'print-data-resultados', 'print-data-rel-turma',
     'print-data-rel-escola', 'print-data-u-dash', 'print-data-u-rel',
     'print-data-desempenho'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = dataFormatada;
    });
}

// ============================================
// POPULAR SELECTS
// ============================================
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

// ============================================
// MENU TOGGLE
// ============================================
function toggleMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('menuOverlay');
    const toggle = document.getElementById('menuToggle');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('show');
    toggle.classList.toggle('active');
    toggle.innerHTML = sidebar.classList.contains('open') ? '✕' : '☰';
}

// ============================================
// NAVEGAÇÃO
// ============================================
function go(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const el = document.getElementById('page-' + page);
    if (el) el.classList.add('active');
    document.querySelectorAll('.sb-item').forEach(s => s.classList.toggle('active', s.dataset.p === page));

    switch (page) {
        case 'escola': carregarEscolas(); break;
        case 'turmas': carregarFiltroEscolaTurmas(); carregarTurmas(); break;
        case 'alunos':
            const escolaId = document.getElementById('filtro-escola-alunos')?.value || '';
            carregarAlunos(escolaId);
            break;
        case 'provas': carregarProvas(); break;
        case 'gabaritos': carregarGabaritos(); break;
        case 'rel-turma': carregarFiltrosRelTurma(); carregarRelatorioTurmaFiltrado(); break;
        case 'dashboard': carregarDashboard(); carregarUltimasCorrecoes(); break;
        case 'corrigir-ia': carregarEscolasCorrigir(); break;
        case 'config': carregarUsuarios(); break;
    }

    atualizarDatasImpressao();
    paginaAtual = page;

    if (window.innerWidth <= 900) {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('menuOverlay');
        const toggle = document.getElementById('menuToggle');
        if (sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            toggle.classList.remove('active');
            toggle.innerHTML = '☰';
        }
    }
}

// ============================================
// CALCULAR CONCEITO
// ============================================
function calcularConceito(porcentagem) {
    if (porcentagem <= 40) return 'inicial';
    if (porcentagem <= 60) return 'basico';
    if (porcentagem <= 80) return 'proficiente';
    return 'avancado';
}

// ============================================
// FILTRAR TURMAS POR SÉRIE
// ============================================
function filtrarTurmasPorSerie(selectSerie, selectTurma) {
    const serieSelecionada = selectSerie.value;
    let firstVisible = false;

    for (let option of selectTurma.options) {
        if (option.value === '') { option.style.display = ''; continue; }
        const serieDaTurma = option.dataset.serie || '';
        if (serieSelecionada === '' || serieDaTurma === serieSelecionada) {
            option.style.display = '';
            if (!firstVisible) { selectTurma.value = option.value; firstVisible = true; }
        } else {
            option.style.display = 'none';
        }
    }
    if (!firstVisible) selectTurma.value = '';
    selectTurma.dispatchEvent(new Event('change'));
}

// ============================================
// CARREGAR ESCOLAS PARA CORRIGIR (IA)
// ============================================
async function carregarEscolasCorrigir() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('corrigir-escola');
        if (select && escolas && !escolas.erro) {
            const current = select.value;
            select.innerHTML = '<option value="">Selecione a escola...</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                select.appendChild(opt);
            });
            if (current) { select.value = current; carregarTurmasPorEscolaCorrigir(current); }
        }
    } catch (erro) { console.error(erro); }
}

async function carregarTurmasPorEscolaCorrigir(escolaId) {
    const selectTurma = document.getElementById('corrigir-turma');
    const selectProva = document.getElementById('corrigir-prova');
    const selectAluno = document.getElementById('corrigir-aluno');

    selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    selectProva.innerHTML = '<option value="">Selecione...</option>';
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
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
    } catch (e) { console.error(e); }
}

async function carregarAlunosPorTurmaCorrigir(turmaId) {
    const selectAluno = document.getElementById('corrigir-aluno');
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
    if (!turmaId) return;
    try {
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        if (alunos && !alunos.erro) {
            alunos.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.nome + ' (Nº ' + (a.numero_chamada || '—') + ')';
                selectAluno.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

async function carregarProvasPorTurmaCorrigir(turmaId) {
    const selectProva = document.getElementById('corrigir-prova');
    selectProva.innerHTML = '<option value="">Selecione...</option>';
    if (!turmaId) return;
    try {
        const provas = await carregarProvasComCache();
        const turma = await carregarTurmasComCache();
        const turmaData = turma.find(t => t.id == turmaId);
        const serieTurma = turmaData?.serie || '';
        if (provas && !provas.erro) {
            let provasFiltradas = provas.filter(p => p.serie === serieTurma);
            if (provasFiltradas.length === 0) provasFiltradas = provas;
            provasFiltradas.forEach(p => {
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
                selectProva.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

async function carregarAlunosPorProvaFiltrados(provaId) {
    const selectAluno = document.getElementById('corrigir-aluno');
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
    if (!provaId) return;
    try {
        const provaResp = await fetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) { showToast('❌ Erro ao carregar dados da prova', 'error'); return; }
        const turmaId = document.getElementById('corrigir-turma').value;
        if (!turmaId) {
            const alunos = await carregarAlunosComCache({ serie: prova.serie || '' });
            if (alunos && !alunos.erro) {
                alunos.forEach(a => {
                    const opt = document.createElement('option');
                    opt.value = a.id;
                    const turmaInfo = a.turma_nome ? ' - ' + a.turma_nome : '';
                    opt.textContent = a.nome + ' (Nº ' + (a.numero_chamada || '—') + ')' + turmaInfo;
                    selectAluno.appendChild(opt);
                });
            }
            return;
        }
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        if (alunos && !alunos.erro) {
            alunos.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.nome + ' (Nº ' + (a.numero_chamada || '—') + ')';
                selectAluno.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

// ============================================
// CARREGAR ESCOLAS / TURMAS / ALUNOS / PROVAS
// ============================================
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
    } catch (erro) { console.error(erro); }
}

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
        console.error(erro);
        const tbody = document.getElementById('tb-turmas');
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Erro ao carregar turmas</td></tr>';
    }
}

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
    } catch (erro) { console.error(erro); }
}

function aplicarFiltrosTurmas() {
    const escolaId = document.getElementById('filtro-escola-turmas').value;
    const serie = document.getElementById('filtro-serie-turmas').value;
    document.querySelectorAll('#tb-turmas tr').forEach(row => {
        let mostrar = true;
        if (escolaId && row.dataset.escola !== escolaId) mostrar = false;
        if (serie && row.dataset.serie !== serie) mostrar = false;
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

async function carregarAlunos(escolaId = null) {
    try {
        const filtros = {};
        if (escolaId && escolaId !== '' && escolaId !== 'null' && escolaId !== 'undefined') filtros.escola_id = escolaId;
        const selectTurma = document.getElementById('filtro-turma-alunos');
        if (selectTurma && selectTurma.value && selectTurma.value !== '') filtros.turma_id = selectTurma.value;
        const selectSerie = document.getElementById('filtro-serie-alunos');
        if (selectSerie && selectSerie.value && selectSerie.value !== '') filtros.serie = selectSerie.value;

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
        console.error(erro);
        const tbody = document.getElementById('tb-alunos');
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text3);">Erro ao carregar alunos</td></tr>';
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
            if (current) { select.value = current; carregarAlunos(current); }
        }
    } catch (erro) { console.error(erro); }
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

async function carregarProvas() {
    try {
        const provas = await carregarProvasComCache();
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
    } catch (erro) { console.error(erro); }
}

// ============================================
// VISUALIZAR PROVA
// ============================================
let visualizarProvaId = null;
let visualizarProvaData = null;

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
                            <div style="font-size:9px;color:var(--text3);margin-top:4px;border-top:1px solid var(--border);padding-top:4px;">Nível BNCC: ${escapeHtml(codigo || 'Não definido')}</div>
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
        console.error(erro);
        showToast('❌ Erro ao carregar prova: ' + erro.message, 'error');
    }
}

function editarProvaDireto() {
    if (visualizarProvaId) { closeM('m-visualizar-prova'); editarGabarito(visualizarProvaId); }
    else showToast('❌ Nenhuma prova selecionada para editar.', 'error');
}

// ============================================
// DASHBOARD
// ============================================
async function carregarDashboard() {
    try {
        const response = await fetch(`${API_URL}/api/dashboard`);
        const dados = await response.json();
        setText('totalEscolas', dados.total_escolas || 0);
        setText('totalTurmas', dados.total_turmas || 0);
        setText('totalAlunos', dados.total_alunos || 0);
        setText('totalProvas', dados.total_provas || 0);
    } catch (erro) { console.error(erro); }
}

async function carregarUltimasCorrecoes() {
    try {
        const response = await fetch(API_URL + '/api/historico?limit=10');
        const historico = await response.json();
        const tbody = document.getElementById('ultimas-correcoes');
        if (!tbody) return;
        if (!historico || historico.length === 0 || historico.erro) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text3);">Nenhuma correção recente</td></tr>';
        } else {
            const recentes = historico.slice(0, 10);
            tbody.innerHTML = recentes.map(item => {
                const acertos = item.acertos || 0;
                const total = item.total || 20;
                const porcentagem = total > 0 ? Math.round((acertos / total) * 100) : 0;
                const conceito = calcularConceito(porcentagem);
                const badgeMap = {
                    'inicial': 'badge-conceito-inicial', 'basico': 'badge-conceito-basico',
                    'proficiente': 'badge-conceito-proficiente', 'avancado': 'badge-conceito-avancado'
                };
                const nomeConceito = {
                    'inicial': '🔴 Inicial', 'basico': '🟠 Básico',
                    'proficiente': '🔵 Proficiente', 'avancado': '🟢 Avançado'
                };
                const badge = badgeMap[conceito] || 'badge-gray';
                const label = nomeConceito[conceito] || 'Indefinido';
                return `<tr>
                    <td><strong>${escapeHtml(item.aluno_nome || 'Aluno')}</strong></td>
                    <td>${escapeHtml(item.prova_titulo || 'Prova')}</td>
                    <td><strong>${porcentagem}%</strong></td>
                    <td><span class="badge ${badge}">${label}</span></td>
                </tr>`;
            }).join('');
        }
    } catch (erro) { console.error(erro); }
}

// ============================================
// GABARITOS
// ============================================
async function carregarGabaritos() {
    try {
        const provas = await carregarProvasComCache();
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
                    '<td>' + (p.quantidade_questoes || p.gabarito?.length || 0) + '</td>' +
                    '<td><span class="badge ' + (tipoTexto === 'Texto' ? 'badge-purple' : (p.tipo_questoes == '3' ? 'badge-purple' : 'badge-blue')) + '">' + tipoTexto + '</span></td>' +
                    '<td style="font-size:9px; max-width:120px; word-wrap:break-word;">' + escapeHtml(bnccText) + '</td>' +
                    '<td>' + escapeHtml(p.data_prova || '—') + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarGabarito(' + p.id + ')">✏️</button><button class="btn-del" onclick="excluirGabarito(' + p.id + ', \'' + escapeAttr(p.titulo) + '\')">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) { console.error(erro); }
}

// ============================================
// CORREÇÃO MANUAL — DENTRO DA IA
// ============================================
function abrirCorrecaoManual() {
    if (!correcaoManualData.respostasAluno || correcaoManualData.respostasAluno.length === 0) {
        showToast('❌ Nenhuma correção para editar. Faça uma correção com IA primeiro!', 'error');
        return;
    }
    if (!correcaoManualData.gabarito || !Array.isArray(correcaoManualData.gabarito) || correcaoManualData.gabarito.length === 0) {
        showToast('❌ Gabarito não disponível para esta prova!', 'error');
        return;
    }
    const temGabaritoValido = correcaoManualData.gabarito.some(g => g && g.trim() !== '');
    if (!temGabaritoValido) { showToast('❌ Gabarito vazio ou inválido para esta prova!', 'error'); return; }
    setText('cm-aluno-nome', correcaoManualData.alunoNome || 'Aluno');
    setText('cm-prova-titulo', correcaoManualData.provaTitulo || 'Prova');
    setText('cm-turma-info', correcaoManualData.serie + ' | Turma: —');
    setText('cm-data-correcao', new Date().toLocaleDateString('pt-BR'));
    gerarGridCorrecaoManual();
    atualizarResumoCorrecaoManual();
    openM('m-correcao-manual');
    setTimeout(() => destacarQuestoesDuvidosas(), 300);
}

function destacarQuestoesDuvidosas() {
    const confiancas = correcaoManualData.confianca_por_questao || [];
    const suspeitas = correcaoManualData.questoes_suspeitas || [];
    const itens = document.querySelectorAll('.correcao-manual-item');
    let totalDuvidosas = 0;
    itens.forEach((item, index) => {
        const confianca = confiancas[index] || 100;
        const numQuestao = index + 1;
        item.style.borderColor = ''; item.style.borderWidth = ''; item.style.boxShadow = '';
        const oldBadge = item.querySelector('.confianca-badge');
        if (oldBadge) oldBadge.remove();
        const isSuspeita = suspeitas.includes(numQuestao) || confianca < 70;
        if (isSuspeita) {
            totalDuvidosas++;
            item.style.borderColor = 'var(--orange)';
            item.style.borderWidth = '2px';
            item.style.boxShadow = '0 0 20px rgba(245,158,11,0.2)';
            const badge = document.createElement('div');
            badge.className = 'confianca-badge confianca-baixa';
            badge.style.cssText = 'font-size:8px; font-weight:700; margin-top:4px; padding:2px 8px; border-radius:12px; background:rgba(239,68,68,0.15); color:#ef4444;';
            badge.textContent = `⚠️ Confiança: ${confianca}%`;
            const select = item.querySelector('.q-select');
            if (select) item.insertBefore(badge, select);
            else item.appendChild(badge);
        } else if (confianca < 80) {
            item.style.borderColor = 'rgba(245,158,11,0.3)';
        }
    });
    if (totalDuvidosas > 0) showToast(`🔍 ${totalDuvidosas} questões com baixa confiança (destacadas em laranja)`, 'warning');
    else showToast('✅ Todas as questões têm alta confiança!', 'success');
}

function revisarApenasDuvidosas() {
    const confiancas = correcaoManualData.confianca_por_questao || [];
    const suspeitas = correcaoManualData.questoes_suspeitas || [];
    const itens = document.querySelectorAll('.correcao-manual-item');
    let totalDuvidosas = 0;
    itens.forEach((item, index) => {
        const confianca = confiancas[index] || 100;
        const numQuestao = index + 1;
        const isSuspeita = suspeitas.includes(numQuestao) || confianca < 70;
        if (isSuspeita) {
            item.style.display = '';
            totalDuvidosas++;
            if (totalDuvidosas === 1) item.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else item.style.display = 'none';
    });
    if (totalDuvidosas === 0) {
        showToast('✅ Nenhuma questão com baixa confiança!', 'success');
        itens.forEach(item => item.style.display = '');
    } else showToast(`🔍 Mostrando apenas ${totalDuvidosas} questões com baixa confiança`, 'info');
}

function gerarGridCorrecaoManual() {
    const grid = document.getElementById('cm-grid');
    if (!grid) return;
    const qtd = correcaoManualData.quantidade || 20;
    const alternativas = correcaoManualData.alternativas || ['A', 'B', 'C', 'D'];
    const respostas = correcaoManualData.respostasAluno || [];
    const gabarito = correcaoManualData.gabarito || [];
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');

    if (isProducao) {
        grid.style.display = 'flex'; grid.style.flexDirection = 'column';
        grid.style.gap = '12px'; grid.style.maxHeight = 'none'; grid.style.overflowY = 'visible';
    } else {
        grid.style.display = 'grid'; grid.style.gridTemplateColumns = 'repeat(10, 1fr)';
        grid.style.gap = '6px'; grid.style.maxHeight = '280px'; grid.style.overflowY = 'auto';
    }

    grid.innerHTML = '';
    for (let i = 0; i < qtd; i++) {
        const div = document.createElement('div');
        div.className = 'correcao-manual-item';
        const respostaAluno = (i < respostas.length) ? respostas[i] : '';
        const respostaGabarito = (i < gabarito.length) ? gabarito[i] : '';
        const isCorreto = respostaAluno && respostaGabarito && respostaAluno.toUpperCase() === respostaGabarito.toUpperCase();

        if (isProducao) {
            div.style.cssText = 'background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;text-align:left;display:flex;flex-direction:column;gap:6px;';
            div.innerHTML = `
                <input class="gab-titulo" type="text" value="Q${i+1}" style="width:100%; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:12px; font-weight:bold;" />
                <div style="font-size:10px;color:var(--text3);">Gabarito: ${escapeHtml(respostaGabarito || '—')}</div>
                <textarea class="q-resposta-texto" placeholder="Resposta do aluno..." style="width:100%; min-height:50px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:11px; resize:vertical;">${escapeHtml(respostaAluno)}</textarea>
            `;
            const textarea = div.querySelector('.q-resposta-texto');
            textarea.dataset.questao = i;
            textarea.addEventListener('input', function() {
                correcaoManualData.respostasAluno[i] = this.value;
                atualizarResumoCorrecaoManual();
            });
        } else {
            let options = '<option value="">—</option>';
            alternativas.forEach(alt => {
                const selected = respostaAluno && respostaAluno.toUpperCase() === alt ? 'selected' : '';
                options += `<option value="${alt}" ${selected}>${alt}</option>`;
            });
            let statusClass = ''; let statusText = '';
            if (respostaAluno) {
                if (isCorreto) { statusClass = 'correta'; statusText = '✅'; }
                else { statusClass = 'errada'; statusText = '❌'; }
            }
            div.innerHTML = `
                <div class="q-num">Q${i+1}</div>
                <div class="q-resposta" style="color:${isCorreto ? 'var(--green)' : (respostaAluno ? 'var(--red)' : 'var(--text3)')}">${escapeHtml(respostaAluno || '—')}</div>
                <select class="q-select" data-questao="${i}" onchange="atualizarRespostaManual(this)">${options}</select>
                <div class="q-status ${statusClass}">${statusText}</div>
            `;
            const select = div.querySelector('.q-select');
            if (select) {
                if (respostaAluno && isCorreto) select.className = 'q-select correta';
                else if (respostaAluno) select.className = 'q-select errada';
            }
        }
        grid.appendChild(div);
    }
}

function atualizarRespostaManual(select) {
    const questaoIndex = parseInt(select.dataset.questao);
    const novaResposta = select.value;
    if (novaResposta) correcaoManualData.respostasAluno[questaoIndex] = novaResposta.toUpperCase();
    else correcaoManualData.respostasAluno[questaoIndex] = '';
    const item = select.closest('.correcao-manual-item');
    const qResposta = item.querySelector('.q-resposta');
    const qStatus = item.querySelector('.q-status');
    const gabarito = correcaoManualData.gabarito[questaoIndex] || '';
    const resposta = correcaoManualData.respostasAluno[questaoIndex] || '';
    const isCorreto = resposta && gabarito && resposta.toUpperCase() === gabarito.toUpperCase();
    qResposta.textContent = resposta || '—';
    qResposta.style.color = isCorreto ? 'var(--green)' : (resposta ? 'var(--red)' : 'var(--text3)');
    if (resposta) {
        if (isCorreto) { qStatus.textContent = '✅'; qStatus.className = 'q-status correta'; select.className = 'q-select correta'; }
        else { qStatus.textContent = '❌'; qStatus.className = 'q-status errada'; select.className = 'q-select errada'; }
    } else { qStatus.textContent = ''; qStatus.className = 'q-status'; select.className = 'q-select'; }
    atualizarResumoCorrecaoManual();
}

function atualizarResumoCorrecaoManual() {
    const qtd = correcaoManualData.quantidade || 20;
    const respostas = correcaoManualData.respostasAluno || [];
    const gabarito = correcaoManualData.gabarito || [];
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');
    let acertos = 0, respondidas = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp) {
            respondidas++;
            if (isProducao) { if (resp.trim().toLowerCase() === gab.trim().toLowerCase()) acertos++; }
            else { if (resp.toUpperCase() === gab.toUpperCase()) acertos++; }
        }
    }
    const erros = respondidas - acertos;
    const nota = (acertos * correcaoManualData.valorPorQuestao) || 0;
    const notaFinal = Math.min(nota, correcaoManualData.notaMaxima || 10);
    const porcentagem = qtd > 0 ? Math.round((acertos / qtd) * 100) : 0;
    setText('cm-acertos', acertos);
    setText('cm-erros', erros);
    setText('cm-nota', notaFinal.toFixed(1));
    const statusBadge = document.getElementById('cm-status-badge');
    const statusAtual = document.getElementById('cm-status-atual');
    if (notaFinal >= (correcaoManualData.notaMinima || 5)) {
        statusBadge.textContent = '✅ APROVADO'; statusBadge.className = 'badge badge-green';
        statusAtual.textContent = 'Aprovado'; statusAtual.style.color = 'var(--green)';
    } else if (notaFinal >= (correcaoManualData.notaMinima || 5) * 0.8) {
        statusBadge.textContent = '⚠️ RECUPERAÇÃO'; statusBadge.className = 'badge badge-orange';
        statusAtual.textContent = 'Recuperação'; statusAtual.style.color = 'var(--orange)';
    } else {
        statusBadge.textContent = '❌ REPROVADO'; statusBadge.className = 'badge badge-red';
        statusAtual.textContent = 'Reprovado'; statusAtual.style.color = 'var(--red)';
    }
    setText('cm-porcentagem', porcentagem + '% de aproveitamento');
}

function preencherGabaritoCM() {
    const qtd = correcaoManualData.quantidade || 20;
    const gabarito = correcaoManualData.gabarito || [];
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid .q-resposta-texto');
        inputs.forEach((input, i) => {
            if (i < gabarito.length) { input.value = gabarito[i] || ''; correcaoManualData.respostasAluno[i] = gabarito[i] || ''; }
        });
    } else {
        for (let i = 0; i < qtd; i++) if (i < gabarito.length && gabarito[i]) correcaoManualData.respostasAluno[i] = gabarito[i];
        gerarGridCorrecaoManual();
    }
    atualizarResumoCorrecaoManual();
    showToast('📋 Respostas preenchidas com o gabarito!', 'success');
}

function limparRespostasCM() {
    const qtd = correcaoManualData.quantidade || 20;
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid .q-resposta-texto');
        inputs.forEach((input, i) => { input.value = ''; correcaoManualData.respostasAluno[i] = ''; });
    } else {
        for (let i = 0; i < qtd; i++) correcaoManualData.respostasAluno[i] = '';
        gerarGridCorrecaoManual();
    }
    atualizarResumoCorrecaoManual();
    showToast('🗑️ Respostas limpas!', 'info');
}

function salvarCorrecaoManual() {
    const qtd = correcaoManualData.quantidade || 20;
    const respostas = correcaoManualData.respostasAluno || [];
    const gabarito = correcaoManualData.gabarito || [];
    let acertos = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp && resp.toUpperCase() === gab.toUpperCase()) acertos++;
    }
    const nota = Math.min((acertos * correcaoManualData.valorPorQuestao), correcaoManualData.notaMaxima || 10);

    const etapas = [
        { nome: '📝 Processando respostas', descricao: 'Validando respostas do aluno...' },
        { nome: '📊 Calculando nota', descricao: 'Calculando aproveitamento...' },
        { nome: '💾 Salvando no sistema', descricao: 'Persistindo correção...' }
    ];
    progressManager.iniciar('💾 Salvando Correção Manual', etapas, '✏️');

    const dadosCorrecao = {
        prova_id: correcaoManualData.provaId,
        aluno_id: correcaoManualData.alunoId,
        respostas: respostas, acertos: acertos, nota: nota, total: qtd
    };

    fetch(API_URL + '/api/corrigir_manual', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dadosCorrecao)
    })
    .then(response => {
        progressManager.concluirEtapa(0);
        progressManager.proximaEtapa();
        return response.json();
    })
    .then(data => {
        progressManager.concluirEtapa(1);
        progressManager.proximaEtapa();
        if (data.sucesso) {
            progressManager.concluirEtapa(2);
            progressManager.finalizar(`✅ Correção salva! Nota: ${nota.toFixed(1)}`);
            limparCache();
            setTimeout(() => {
                carregarDashboard();
                carregarUltimasCorrecoes();
            }, 500);
        } else {
            progressManager.erro(data.erro || 'Erro ao salvar');
            showToast('❌ Erro ao salvar: ' + (data.erro || 'Erro desconhecido'), 'error');
        }
    })
    .catch(erro => {
        progressManager.erro(erro.message);
        showToast('❌ Erro ao salvar correção: ' + erro.message, 'error');
        console.error(erro);
    });
}

// ============================================
// CORREÇÃO MANUAL STANDALONE (sidebar)
// ============================================
function ajustarUIporDisciplina() {
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    const cmNotaContainer = document.getElementById('cm-nota-manual-container');
    if (cmNotaContainer) cmNotaContainer.style.display = isProducao ? 'block' : 'none';
    const resumo = document.getElementById('cm-sa-resumo');
    if (resumo) resumo.style.display = isProducao ? 'none' : 'grid';
    const badges = document.getElementById('cm-sa-badges');
    if (badges) badges.style.display = isProducao ? 'none' : 'flex';
    const btnSalvar = document.getElementById('btn-salvar-correcao-manual');
    if (btnSalvar) btnSalvar.style.display = isProducao ? 'none' : 'inline-flex';
    const botoesAcao = document.querySelector('#cm-grid-standalone-container > div[style*="justify-content:space-between"]');
    if (botoesAcao) botoesAcao.style.display = isProducao ? 'none' : 'flex';
}

function abrirCorrecaoManualStandalone() {
    document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
    document.getElementById('cm-sa-aluno').textContent = '—';
    document.getElementById('cm-sa-turma').textContent = '—';
    document.getElementById('cm-sa-prova').textContent = '—';
    document.getElementById('cm-sa-data').textContent = '—';
    document.getElementById('cm-sa-acertos').textContent = '0';
    document.getElementById('cm-sa-erros').textContent = '0';
    document.getElementById('cm-sa-nota').textContent = '0,0';
    document.getElementById('cm-sa-status-badge').textContent = 'AGUARDANDO';
    document.getElementById('cm-sa-status-badge').className = 'badge badge-gray';
    document.getElementById('cm-sa-porcentagem').textContent = '0% de aproveitamento';
    document.getElementById('cm-grid-standalone-container').style.display = 'none';
    document.getElementById('cm-info-standalone').style.display = 'none';
    document.getElementById('btn-salvar-correcao-manual').style.display = 'none';
    document.getElementById('cm-grid-standalone').innerHTML = '';
    document.getElementById('cm-selects-container').style.display = 'block';

    const cmNotaContainer = document.getElementById('cm-nota-manual-container');
    if (cmNotaContainer) cmNotaContainer.style.display = 'none';
    const notaValor = document.getElementById('cm-nota-valor');
    if (notaValor) notaValor.value = '';
    const statusDiv = document.getElementById('cm-nota-status');
    if (statusDiv) { statusDiv.style.display = 'none'; statusDiv.textContent = ''; }

    carregarEscolasParaCorrecaoManual();
    document.getElementById('m-correcao-manual-standalone').style.display = 'flex';
}

async function carregarEscolasParaCorrecaoManual() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('cm-escola-select');
        if (select && escolas && !escolas.erro) {
            const current = select.value;
            select.innerHTML = '<option value="">Selecione a escola...</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                select.appendChild(opt);
            });
            if (current) { select.value = current; carregarTurmasParaCorrecaoManual(current); }
        }
    } catch (erro) { console.error(erro); }
}

async function carregarTurmasParaCorrecaoManual(escolaId) {
    const selectTurma = document.getElementById('cm-turma-select');
    const selectProva = document.getElementById('cm-prova-select');
    const selectAluno = document.getElementById('cm-aluno-select');
    selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    selectProva.innerHTML = '<option value="">Selecione a prova...</option>';
    selectAluno.innerHTML = '<option value="">Selecione o aluno...</option>';
    if (!escolaId) return;
    cmStandaloneData.escolaId = parseInt(escolaId);
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
    } catch (e) { console.error(e); }
}

async function carregarAlunosParaCorrecaoManual(turmaId) {
    const selectAluno = document.getElementById('cm-aluno-select');
    selectAluno.innerHTML = '<option value="">Selecione o aluno...</option>';
    if (!turmaId) return;
    cmStandaloneData.turmaId = parseInt(turmaId);
    const selectTurma = document.getElementById('cm-turma-select');
    const turmaOption = selectTurma.options[selectTurma.selectedIndex];
    if (turmaOption) {
        cmStandaloneData.turmaNome = turmaOption.text || '';
        cmStandaloneData.serie = turmaOption.dataset.serie || '';
    }
    try {
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        if (alunos && !alunos.erro) {
            alunos.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.nome + ' (Nº ' + (a.numero_chamada || '—') + ')';
                selectAluno.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

async function carregarProvasParaCorrecaoManualPorTurma(turmaId) {
    const selectProva = document.getElementById('cm-prova-select');
    selectProva.innerHTML = '<option value="">Selecione a prova...</option>';
    if (!turmaId) return;
    try {
        const provas = await carregarProvasComCache();
        if (provas && !provas.erro) {
            provas.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                const serie = p.serie || '';
                opt.textContent = p.titulo + ' - ' + serie + ' - ' + (p.disciplina || '');
                opt.dataset.serie = serie;
                opt.dataset.quantidade = p.quantidade_questoes || 20;
                opt.dataset.tipo = p.tipo_questoes || '4';
                opt.dataset.data = p.data_prova || '';
                opt.dataset.gabarito = JSON.stringify(p.gabarito || []);
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

function carregarGabaritoParaCorrecaoManual() {
    const select = document.getElementById('cm-prova-select');
    const option = select.options[select.selectedIndex];
    if (!option || !option.value) {
        cmStandaloneData.provaId = null;
        cmStandaloneData.provaTitulo = '';
        cmStandaloneData.provaData = '';
        cmStandaloneData.gabarito = [];
        cmStandaloneData.quantidade = 20;
        cmStandaloneData.alternativas = ['A', 'B', 'C', 'D'];
        cmStandaloneData.disciplina = '';
        return;
    }
    try {
        const gabarito = JSON.parse(option.dataset.gabarito || '[]');
        const quantidade = parseInt(option.dataset.quantidade) || 20;
        const tipo = option.dataset.tipo || '4';
        cmStandaloneData.provaId = parseInt(option.value);
        cmStandaloneData.provaTitulo = option.text.split(' - ')[0] || 'Prova';
        cmStandaloneData.provaData = option.dataset.data || '';
        cmStandaloneData.gabarito = gabarito;
        cmStandaloneData.quantidade = quantidade;
        cmStandaloneData.alternativas = tipo === '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        cmStandaloneData.disciplina = option.dataset.disciplina || '';
        cmStandaloneData.valorPorQuestao = 10 / quantidade;
        cmStandaloneData.respostas = new Array(quantidade).fill('');
        if (!cmStandaloneData.serie) cmStandaloneData.serie = option.dataset.serie || '';
        showToast('✅ Gabarito carregado! Selecione o aluno e clique em "Iniciar Correção"', 'success');
    } catch (e) {
        console.error(e);
        showToast('❌ Erro ao carregar gabarito da prova', 'error');
    }
}

async function iniciarCorrecaoManualStandalone() {
    const escolaSelect = document.getElementById('cm-escola-select');
    const turmaSelect = document.getElementById('cm-turma-select');
    const provaSelect = document.getElementById('cm-prova-select');
    const alunoSelect = document.getElementById('cm-aluno-select');
    if (!escolaSelect.value) { showToast('❌ Selecione uma escola!', 'error'); return; }
    if (!turmaSelect.value) { showToast('❌ Selecione uma turma!', 'error'); return; }
    if (!provaSelect.value) { showToast('❌ Selecione uma prova!', 'error'); return; }
    if (!alunoSelect.value) { showToast('❌ Selecione um aluno!', 'error'); return; }

    const alunoOption = alunoSelect.options[alunoSelect.selectedIndex];
    cmStandaloneData.alunoId = parseInt(alunoSelect.value);
    cmStandaloneData.alunoNome = alunoOption.text.split(' (')[0] || 'Aluno';
    const escolaOption = escolaSelect.options[escolaSelect.selectedIndex];
    cmStandaloneData.escolaNome = escolaOption.text || '';
    cmStandaloneData.escolaId = parseInt(escolaSelect.value);

    const provaId = parseInt(provaSelect.value);
    try {
        showToast('🔄 Carregando dados da prova...', 'info');
        const provaResp = await fetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) { showToast('❌ Erro ao carregar prova: ' + (prova.erro || 'Desconhecido'), 'error'); return; }
        cmStandaloneData.provaId = provaId;
        cmStandaloneData.gabarito = prova.gabarito || [];
        cmStandaloneData.quantidade = prova.quantidade_questoes || 20;
        const tipo = prova.tipo_questoes || '4';
        cmStandaloneData.alternativas = tipo == '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        cmStandaloneData.valorPorQuestao = 10 / cmStandaloneData.quantidade;
        cmStandaloneData.respostas = new Array(cmStandaloneData.quantidade).fill('');
        cmStandaloneData.disciplina = prova.disciplina || '';
        cmStandaloneData.provaTitulo = prova.titulo || 'Prova';
        cmStandaloneData.provaData = prova.data_prova || '';
        cmStandaloneData.serie = prova.serie || cmStandaloneData.serie || '';
        cmStandaloneData.textos_questoes = prova.textos_questoes || [];
        cmStandaloneData.situacoes = new Array(cmStandaloneData.quantidade).fill('');
        if (prova.niveis && Array.isArray(prova.niveis)) {
            for (let i = 0; i < cmStandaloneData.quantidade; i++) cmStandaloneData.situacoes[i] = prova.niveis[i] || '';
        }
    } catch (e) { console.error(e); showToast('❌ Erro ao carregar dados da prova: ' + e.message, 'error'); return; }

    const temGabarito = cmStandaloneData.gabarito.some(g => g && g.trim() !== '');
    if (!temGabarito) { showToast('⚠️ Esta prova não tem gabarito cadastrado!', 'warning'); return; }

    setText('cm-sa-aluno', cmStandaloneData.alunoNome);
    setText('cm-sa-turma', cmStandaloneData.serie + ' - ' + cmStandaloneData.turmaNome);
    setText('cm-sa-prova', cmStandaloneData.provaTitulo);
    setText('cm-sa-data', cmStandaloneData.provaData || new Date().toLocaleDateString('pt-BR'));
    document.getElementById('cm-info-standalone').style.display = 'grid';
    document.getElementById('cm-grid-standalone-container').style.display = 'block';
    ajustarUIporDisciplina();
    gerarGridCorrecaoManualSA();
    atualizarResumoCorrecaoManualSA();
    showToast('📝 Correção manual iniciada para ' + cmStandaloneData.alunoNome, 'success');
}

function gerarGridCorrecaoManualSA() {
    const grid = document.getElementById('cm-grid-standalone');
    if (!grid) return;
    const qtd = cmStandaloneData.quantidade || 20;
    const alternativas = cmStandaloneData.alternativas || ['A', 'B', 'C', 'D'];
    const gabarito = cmStandaloneData.gabarito || [];
    const respostas = cmStandaloneData.respostas || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    const textosQuestoes = cmStandaloneData.textos_questoes || [];
    const situacoes = cmStandaloneData.situacoes || [];

    ajustarUIporDisciplina();
    if (isProducao) {
        grid.style.cssText = 'display:flex;flex-direction:column;gap:14px;max-height:none;overflow-y:visible;';
    } else {
        grid.style.cssText = 'display:grid;grid-template-columns:repeat(10, 1fr);gap:6px;max-height:280px;overflow-y:auto;';
    }
    grid.innerHTML = '';

    for (let i = 0; i < qtd; i++) {
        const div = document.createElement('div');
        const gab = (i < gabarito.length) ? gabarito[i] : '';
        const resp = (i < respostas.length) ? respostas[i] : '';

        if (isProducao) {
            div.className = 'cm-item-producao';
            let cabecalho = '';
            if (textosQuestoes && textosQuestoes[i] && textosQuestoes[i].cabecalho) cabecalho = textosQuestoes[i].cabecalho;
            const tituloQ = (textosQuestoes && textosQuestoes[i] && textosQuestoes[i].titulo) ? textosQuestoes[i].titulo : `Q${i + 1}`;
            const headerTexto = cabecalho ? `${tituloQ} - ${cabecalho}` : tituloQ;

            let gabFormatadoHTML = '';
            if (gab && gab.trim() !== '') {
                const blocos = gab.split(/\n(?=[A-Z]\))/);
                blocos.forEach(bloco => {
                    const match = bloco.match(/^([A-Z])\)\s*([\s\S]*)$/);
                    if (match) {
                        gabFormatadoHTML += `<div class="alt-bloco"><span class="alt-letra-gab">${escapeHtml(match[1])}</span><span class="alt-texto-gab">${escapeHtml(match[2].trim())}</span></div>`;
                    } else if (bloco.trim()) {
                        gabFormatadoHTML += `<div class="alt-bloco">${escapeHtml(bloco.trim())}</div>`;
                    }
                });
            } else gabFormatadoHTML = '<div style="color:var(--text3);font-style:italic;">Sem gabarito cadastrado</div>';

            const situacaoAtual = (i < situacoes.length) ? (situacoes[i] || '') : '';
            const opcoesSit = ['', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'];
            let optsSitHTML = '';
            opcoesSit.forEach(op => {
                const sel = (situacaoAtual === op) ? 'selected' : '';
                optsSitHTML += `<option value="${op}" ${sel}>${op === '' ? '—' : op}</option>`;
            });

            div.innerHTML = `
                <div class="cm-q-cabecalho-inline">${escapeHtml(headerTexto)}</div>
                <div>
                    <div class="cm-q-resposta-label">📋 Situação de Correção:</div>
                    <div class="cm-gabarito-formatado">${gabFormatadoHTML}</div>
                </div>
                <div>
                    <div class="cm-q-resposta-label">✍️ Observação do Professor:</div>
                    <textarea class="cm-q-resposta-texto" placeholder="Escreva sua avaliação/observação..." data-questao="${i}">${escapeHtml(resp || '')}</textarea>
                </div>
                <div class="cm-q-situacao-wrapper">
                    <label class="cm-q-situacao-label">📊 Situação de Correção Alternativa:</label>
                    <select class="cm-q-situacao-select" data-questao="${i}" onchange="atualizarSituacaoCM(this)">${optsSitHTML}</select>
                </div>
            `;
            const textarea = div.querySelector('.cm-q-resposta-texto');
            textarea.addEventListener('input', function() { cmStandaloneData.respostas[i] = this.value; });
        } else {
            div.className = 'cm-item-standalone';
            let options = '<option value="">—</option>';
            alternativas.forEach(alt => {
                const selected = resp && resp.toUpperCase() === alt ? 'selected' : '';
                options += `<option value="${alt}" ${selected}>${alt}</option>`;
            });
            const isCorreto = resp && gab && resp.toUpperCase() === gab.toUpperCase();
            let statusIcon = '';
            if (resp) statusIcon = isCorreto ? '✅' : '❌';
            let selectClass = 'q-select-manual';
            if (resp) selectClass += isCorreto ? ' correta' : ' errada';
            div.innerHTML = `
                <div class="q-num">Q${i+1}</div>
                <div class="q-gabarito">${escapeHtml(gab || '—')}</div>
                <select class="${selectClass}" data-questao="${i}" onchange="atualizarRespostaManualSA(this)">${options}</select>
                <div class="q-status-icon">${statusIcon}</div>
            `;
        }
        grid.appendChild(div);
    }
}

function atualizarSituacaoCM(select) {
    const idx = parseInt(select.dataset.questao);
    if (!cmStandaloneData.situacoes) cmStandaloneData.situacoes = [];
    cmStandaloneData.situacoes[idx] = select.value;
}

function atualizarRespostaManualSA(select) {
    const questaoIndex = parseInt(select.dataset.questao);
    const novaResposta = select.value;
    if (novaResposta) cmStandaloneData.respostas[questaoIndex] = novaResposta.toUpperCase();
    else cmStandaloneData.respostas[questaoIndex] = '';
    const item = select.closest('.cm-item-standalone');
    const statusIcon = item.querySelector('.q-status-icon');
    const gabarito = cmStandaloneData.gabarito[questaoIndex] || '';
    const resposta = cmStandaloneData.respostas[questaoIndex] || '';
    const isCorreto = resposta && gabarito && resposta.toUpperCase() === gabarito.toUpperCase();
    select.className = 'q-select-manual';
    if (resposta) select.className += isCorreto ? ' correta' : ' errada';
    if (resposta) statusIcon.textContent = isCorreto ? '✅' : '❌';
    else statusIcon.textContent = '';
    atualizarResumoCorrecaoManualSA();
}

function atualizarResumoCorrecaoManualSA() {
    const qtd = cmStandaloneData.quantidade || 20;
    const respostas = cmStandaloneData.respostas || [];
    const gabarito = cmStandaloneData.gabarito || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    let acertos = 0, respondidas = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp) {
            respondidas++;
            if (isProducao) { if (resp.trim().toLowerCase() === gab.trim().toLowerCase()) acertos++; }
            else { if (resp.toUpperCase() === gab.toUpperCase()) acertos++; }
        }
    }
    const erros = respondidas - acertos;
    const nota = (acertos * cmStandaloneData.valorPorQuestao) || 0;
    const notaFinal = Math.min(nota, cmStandaloneData.notaMaxima || 10);
    const porcentagem = qtd > 0 ? Math.round((acertos / qtd) * 100) : 0;
    setText('cm-sa-acertos', acertos);
    setText('cm-sa-erros', erros);
    setText('cm-sa-nota', notaFinal.toFixed(1));
    const statusBadge = document.getElementById('cm-sa-status-badge');
    if (notaFinal >= (cmStandaloneData.notaMinima || 5)) { statusBadge.textContent = '✅ APROVADO'; statusBadge.className = 'badge badge-green'; }
    else if (notaFinal >= (cmStandaloneData.notaMinima || 5) * 0.8) { statusBadge.textContent = '⚠️ RECUPERAÇÃO'; statusBadge.className = 'badge badge-orange'; }
    else { statusBadge.textContent = '❌ REPROVADO'; statusBadge.className = 'badge badge-red'; }
    setText('cm-sa-porcentagem', porcentagem + '% de aproveitamento');
}

function preencherGabaritoManualSA() {
    const gabarito = cmStandaloneData.gabarito || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid-standalone .cm-q-resposta-texto');
        inputs.forEach((input, i) => { if (i < gabarito.length) { input.value = gabarito[i] || ''; cmStandaloneData.respostas[i] = gabarito[i] || ''; } });
    } else {
        const selects = document.querySelectorAll('#cm-grid-standalone .q-select-manual');
        selects.forEach((select, i) => { if (i < gabarito.length && gabarito[i]) { select.value = gabarito[i]; cmStandaloneData.respostas[i] = gabarito[i]; } });
    }
    atualizarResumoCorrecaoManualSA();
    showToast('📋 Respostas preenchidas com o gabarito!', 'success');
}

function limparRespostasManualSA() {
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid-standalone .cm-q-resposta-texto');
        inputs.forEach((input, i) => { input.value = ''; cmStandaloneData.respostas[i] = ''; });
    } else {
        const selects = document.querySelectorAll('#cm-grid-standalone .q-select-manual');
        selects.forEach((select, i) => { select.value = ''; cmStandaloneData.respostas[i] = ''; });
    }
    atualizarResumoCorrecaoManualSA();
    showToast('🗑️ Respostas limpas!', 'info');
}

function revisarApenasDuvidosasSA() {
    const confiancas = cmStandaloneData.confianca_por_questao || [];
    const suspeitas = cmStandaloneData.questoes_suspeitas || [];
    const itens = document.querySelectorAll('.cm-item-standalone, .cm-item-producao');
    let totalDuvidosas = 0;
    itens.forEach((item, index) => {
        const confianca = confiancas[index] || 100;
        const numQuestao = index + 1;
        const isSuspeita = suspeitas.includes(numQuestao) || confianca < 70;
        if (isSuspeita) { item.style.display = ''; totalDuvidosas++; if (totalDuvidosas === 1) item.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        else item.style.display = 'none';
    });
    if (totalDuvidosas === 0) { showToast('✅ Nenhuma questão com baixa confiança!', 'success'); itens.forEach(item => item.style.display = ''); }
    else showToast(`🔍 Mostrando apenas ${totalDuvidosas} questões com baixa confiança`, 'info');
}

function salvarCorrecaoManualStandalone() {
    if (!cmStandaloneData) { showToast('❌ Dados não encontrados!', 'error'); return; }
    if (cmStandaloneData.disciplina === 'Produção de Texto') {
        showToast('⚠️ Use o botão "💾 SALVAR NOTA" para Produção de Texto.', 'warning');
        return;
    }
    const provaId = parseInt(cmStandaloneData.provaId);
    const alunoId = parseInt(cmStandaloneData.alunoId);
    if (!provaId || isNaN(provaId) || provaId <= 0) { showToast('❌ ID da prova inválido!', 'error'); return; }
    if (!alunoId || isNaN(alunoId) || alunoId <= 0) { showToast('❌ ID do aluno inválido!', 'error'); return; }

    const qtd = cmStandaloneData.quantidade || 20;
    const respostas = cmStandaloneData.respostas || [];
    const gabarito = cmStandaloneData.gabarito || [];
    const temResposta = respostas.some(r => r && r.trim() !== '');
    if (!temResposta) { showToast('⚠️ Marque pelo menos uma resposta do aluno!', 'warning'); return; }

    let acertos = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp && gab && resp.toUpperCase() === gab.toUpperCase()) acertos++;
    }
    const valorPorQuestao = cmStandaloneData.valorPorQuestao || (10 / qtd);
    const nota = Math.min((acertos * valorPorQuestao), cmStandaloneData.notaMaxima || 10);

    showToast('💾 Salvando correção manual...', 'info');
    const dadosCorrecao = {
        prova_id: provaId, aluno_id: alunoId,
        respostas: respostas.map(r => r || ''),
        acertos: acertos, nota: nota, total: qtd
    };

    fetch(API_URL + '/api/corrigir_manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dadosCorrecao)
    })
    .then(async response => {
        let data;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) data = await response.json();
        else {
            const text = await response.text();
            try { data = JSON.parse(text); } catch (e) { data = { erro: text || 'Erro desconhecido' }; }
        }
        if (!response.ok) throw new Error(data.erro || data.mensagem || `Erro ${response.status}`);
        return data;
    })
    .then(data => {
        if (data.sucesso) {
            showToast(`✅ Correção salva! Nota: ${nota.toFixed(1)}`, 'success');
            limparCache();
            setTimeout(() => {
                const paginaAtual = document.querySelector('.page.active');
                if (paginaAtual) {
                    const pageId = paginaAtual.id.replace('page-', '');
                    if (pageId === 'rel-turma') carregarRelatorioTurmaFiltrado();
                    else if (pageId === 'dashboard') { carregarDashboard(); carregarUltimasCorrecoes(); }
                    else { carregarDashboard(); carregarUltimasCorrecoes(); }
                } else { carregarDashboard(); carregarUltimasCorrecoes(); }
                carregarUltimasCorrecoes();
            }, 300);
        } else showToast('❌ Erro ao salvar: ' + (data.erro || 'Erro desconhecido'), 'error');
    })
    .catch(erro => {
        console.error(erro);
        showToast('❌ Erro ao salvar: ' + erro.message, 'error');
    });
}

async function salvarNotaProducaoCM() {
    const notaInput = document.getElementById('cm-nota-valor');
    const statusDiv = document.getElementById('cm-nota-status');
    const btn = document.getElementById('btn-salvar-nota-cm');
    const nota = notaInput ? notaInput.value : '';
    const alunoId = cmStandaloneData.alunoId;
    const provaId = cmStandaloneData.provaId;

    if (!alunoId || !provaId) { showToast('❌ Dados incompletos: aluno ou prova ausentes!', 'error'); return; }
    if (!nota || nota === '') { showToast('❌ Digite a nota!', 'error'); if (notaInput) notaInput.focus(); return; }
    const notaNum = parseFloat(nota);
    if (isNaN(notaNum) || notaNum < 0 || notaNum > 10) { showToast('❌ Nota deve estar entre 0 e 10!', 'error'); return; }

    if (statusDiv) {
        statusDiv.className = 'sucesso';
        statusDiv.textContent = '💾 Salvando nota...';
        statusDiv.style.display = 'block';
        statusDiv.style.background = 'rgba(59,130,246,0.12)';
        statusDiv.style.color = 'var(--blue)';
        statusDiv.style.border = '1.5px solid rgba(59,130,246,0.3)';
    }
    if (btn) btn.disabled = true;

    try {
        const questoesStatus = [];
        const qtd = cmStandaloneData.quantidade || 20;
        const gabarito = cmStandaloneData.gabarito || [];
        const respostas = cmStandaloneData.respostas || [];
        const textosQuestoes = cmStandaloneData.textos_questoes || [];
        const situacoes = cmStandaloneData.situacoes || [];
        for (let i = 0; i < qtd; i++) {
            const gab = (i < gabarito.length) ? gabarito[i] : '';
            const resp = (i < respostas.length) ? respostas[i] : '';
            const sit = (i < situacoes.length) ? situacoes[i] : '';
            const titulo = (textosQuestoes[i] && textosQuestoes[i].titulo) ? textosQuestoes[i].titulo : `Q${i+1}`;
            const cabecalho = (textosQuestoes[i] && textosQuestoes[i].cabecalho) ? textosQuestoes[i].cabecalho : '';
            questoesStatus.push({
                numero: i + 1, titulo: titulo, cabecalho: cabecalho,
                resposta: resp || '—', gabarito: gab || '—', situacao: sit || '',
                acertou: false, respondida: !!resp, bncc: '',
                status: `Situação: ${sit || '—'}`, status_texto: `📝 Situação ${sit || '—'}`
            });
        }
        const response = await fetch(`${API_URL}/api/salvar_nota_producao`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                aluno_id: parseInt(alunoId),
                prova_id: parseInt(provaId),
                nota: notaNum, observacao: '',
                questoes_status: questoesStatus
            })
        });
        const dados = await response.json();
        if (dados.sucesso) {
            showToast(`✅ Nota ${notaNum.toFixed(1)} salva para ${dados.aluno}!`, 'success');
            if (statusDiv) {
                statusDiv.className = 'sucesso';
                statusDiv.textContent = `✅ Nota ${notaNum.toFixed(1)} salva! Já aparece em Rel. Turma e Desempenho.`;
                statusDiv.style.background = 'rgba(16,185,129,0.12)';
                statusDiv.style.color = 'var(--green)';
                statusDiv.style.border = '1.5px solid rgba(16,185,129,0.3)';
            }
            if (notaInput) notaInput.value = '';
            limparCache();
            setTimeout(() => { carregarDashboard(); carregarUltimasCorrecoes(); }, 500);
        } else {
            showToast('❌ ' + (dados.erro || 'Erro desconhecido'), 'error');
            if (statusDiv) {
                statusDiv.className = 'erro';
                statusDiv.textContent = '❌ ' + (dados.erro || 'Erro ao salvar nota');
                statusDiv.style.background = 'rgba(239,68,68,0.12)';
                statusDiv.style.color = 'var(--red)';
                statusDiv.style.border = '1.5px solid rgba(239,68,68,0.3)';
            }
        }
    } catch (erro) {
        console.error(erro);
        showToast('❌ Erro ao salvar nota: ' + erro.message, 'error');
        if (statusDiv) {
            statusDiv.className = 'erro';
            statusDiv.textContent = '❌ Erro ao salvar: ' + erro.message;
            statusDiv.style.background = 'rgba(239,68,68,0.12)';
            statusDiv.style.color = 'var(--red)';
        }
    } finally { if (btn) btn.disabled = false; }
}

// ============================================
// USUÁRIOS
// ============================================
function abrirModalUsuario() {
    usuarioEditandoId = null;
    document.getElementById('editar-usuario-id').value = '';
    document.getElementById('usuario-nome').value = '';
    document.getElementById('usuario-username').value = '';
    document.getElementById('usuario-senha').value = '';
    document.getElementById('usuario-email').value = '';
    document.getElementById('usuario-perfil').value = 'usuario';
    document.getElementById('usuario-ativo').checked = true;
    document.querySelector('#m-usuario .modal-header h3').textContent = '👤 Cadastrar Usuário';
    openM('m-usuario');
}

function editarUsuario(id) {
    showToast('✏️ Carregando dados do usuário...', 'info');
    fetch(API_URL + '/api/usuarios/' + id).then(r => r.json()).then(usuario => {
        if (usuario.erro) { showToast('❌ ' + usuario.erro, 'error'); return; }
        usuarioEditandoId = id;
        document.getElementById('editar-usuario-id').value = id;
        document.getElementById('usuario-nome').value = usuario.nome || '';
        document.getElementById('usuario-username').value = usuario.username || '';
        document.getElementById('usuario-senha').value = '';
        document.getElementById('usuario-email').value = usuario.email || '';
        document.getElementById('usuario-perfil').value = usuario.perfil || 'usuario';
        document.getElementById('usuario-ativo').checked = usuario.ativo !== false;
        document.querySelector('#m-usuario .modal-header h3').textContent = '✏️ Editar Usuário';
        openM('m-usuario');
    }).catch(e => { showToast('❌ Erro ao carregar usuário: ' + e.message, 'error'); console.error(e); });
}

async function salvarUsuario() {
    const nome = document.getElementById('usuario-nome').value.trim();
    const username = document.getElementById('usuario-username').value.trim();
    const senha = document.getElementById('usuario-senha').value.trim();
    const email = document.getElementById('usuario-email').value.trim();
    const perfil = document.getElementById('usuario-perfil').value;
    const ativo = document.getElementById('usuario-ativo').checked;
    const id = document.getElementById('editar-usuario-id').value;

    if (!nome) { showToast('❌ Nome do usuário é obrigatório!', 'error'); return; }
    if (!username) { showToast('❌ Usuário (login) é obrigatório!', 'error'); return; }
    if (username.length < 3) { showToast('❌ Usuário deve ter pelo menos 3 caracteres!', 'error'); return; }
    if (!id && !senha) { showToast('❌ Senha é obrigatória para novos usuários!', 'error'); return; }
    if (senha && senha.length < 4) { showToast('❌ Senha deve ter pelo menos 4 caracteres!', 'error'); return; }
    if (email && !email.includes('@')) { showToast('❌ E-mail inválido!', 'error'); return; }

    const dados = { nome, username, email, perfil, ativo };
    if (senha) dados.senha = senha;

    try {
        let url = API_URL + '/api/usuarios';
        let method = 'POST';
        if (id) { url += '/' + id; method = 'PUT'; }
        const btn = document.querySelector('#m-usuario .btn-green');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;
        showToast('💾 Salvando usuário...', 'info');
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);
        btn.textContent = originalText;
        btn.disabled = false;
        if (result.ok) {
            showToast('✅ Usuário "' + username + '" salvo com sucesso!', 'success');
            limparCache();
            closeM('m-usuario');
            carregarUsuarios();
        } else showToast('❌ Erro ao salvar usuário: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao salvar: ' + erro.message, 'error');
        console.error(erro);
        const btn = document.querySelector('#m-usuario .btn-green');
        if (btn) { btn.textContent = '💾 Salvar Usuário'; btn.disabled = false; }
    }
}

async function excluirUsuario(id, username) {
    if (username === 'admin') { showToast('⚠️ Não é possível excluir o usuário administrador principal!', 'error'); return; }
    if (!confirm('Excluir o usuário "' + username + '"? Esta ação não pode ser desfeita.')) return;
    try {
        const response = await fetch(API_URL + '/api/usuarios/' + id, { method: 'DELETE' });
        const result = await processarRespostaAPI(response);
        if (result.ok) { showToast('🗑️ Usuário "' + username + '" excluído!', 'error'); carregarUsuarios(); }
        else showToast('Erro: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) { showToast('Erro ao excluir: ' + erro.message, 'error'); }
}

async function carregarUsuarios() {
    try {
        const response = await fetch(API_URL + '/api/usuarios');
        const usuarios = await response.json();
        const tbody = document.getElementById('tb-usuarios');
        if (!tbody) return;
        if (!usuarios || usuarios.length === 0 || usuarios.erro) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text3);">Nenhum usuário cadastrado</td></tr>';
            return;
        }
        tbody.innerHTML = usuarios.map(u => {
            const perfilBadge = u.perfil === 'admin' ? 'badge-orange' : 'badge-blue';
            const statusBadge = u.ativo ? 'badge-green' : 'badge-red';
            const statusText = u.ativo ? 'Ativo' : 'Inativo';
            const isAdmin = u.username === 'admin';
            return '<tr data-id="' + u.id + '" data-username="' + escapeAttr(u.username) + '">' +
                '<td><strong>' + escapeHtml(u.username) + '</strong><br><small style="color:var(--text3);font-size:10px;">' + escapeHtml(u.nome || '') + '</small></td>' +
                '<td><span class="badge ' + perfilBadge + '">' + (u.perfil === 'admin' ? 'Admin' : 'Usuário') + '</span></td>' +
                '<td><span class="badge ' + statusBadge + '">' + statusText + '</span></td>' +
                '<td><div class="btn-group">' +
                (isAdmin ? '<span style="font-size:10px;color:var(--text3);">Sistema</span>' : '<button class="btn btn-outline btn-sm" onclick="editarUsuario(' + u.id + ')">✏️</button><button class="btn-del" onclick="excluirUsuario(' + u.id + ', \'' + escapeAttr(u.username) + '\')">🗑️</button>') +
                '</div></td></tr>';
        }).join('');
    } catch (erro) { console.error(erro); }
}

// ============================================
// TEXTO COM IA
// ============================================
async function prevTexto(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async e => {
        const base64 = e.target.result;
        document.getElementById('txt-img-prev').style.display = 'block';
        document.getElementById('txt-img').src = base64;
        showToast('🔍 Lendo texto da redação...', 'info');
        try {
            const response = await fetch(API_URL + '/api/extrair_texto_redacao', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ imagem: base64 })
            });
            const dados = await response.json();
            if (dados.sucesso && dados.texto) {
                document.getElementById('txt-aluno').value = dados.texto;
                showToast(`✅ Texto extraído! ${dados.caracteres} caracteres.`, 'success');
            } else showToast('❌ ' + (dados.erro || 'Não foi possível ler a imagem'), 'error');
        } catch (err) { showToast('❌ Erro ao processar imagem: ' + err.message, 'error'); }
    };
    reader.readAsDataURL(file);
}

async function avaliarTexto() {
    let texto = document.getElementById('txt-aluno').value;
    const alunoId = document.getElementById('txt-aluno-select').value;
    const preview = document.getElementById('txt-img-prev');
    const imgEl = document.getElementById('txt-img');
    const temImagem = preview && preview.style.display !== 'none' && imgEl && imgEl.src;

    if ((!texto || texto.trim().length < 5) && temImagem) {
        showToast('🔍 Lendo texto da imagem...', 'info');
        try {
            const response = await fetch(API_URL + '/api/extrair_texto_redacao', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ imagem: imgEl.src })
            });
            const dados = await response.json();
            if (dados.sucesso && dados.texto) { texto = dados.texto; document.getElementById('txt-aluno').value = texto; }
            else { showToast('❌ ' + (dados.erro || 'Não foi possível ler a imagem'), 'error'); return; }
        } catch (err) { showToast('❌ Erro ao processar imagem: ' + err.message, 'error'); return; }
    }
    if (!texto || texto.trim().length < 5) { showToast('❌ Digite um texto, selecione uma foto ou cole o conteúdo!', 'error'); return; }

    const etapas = [
        { nome: '📝 Preparando texto', descricao: 'Validando e preparando o texto...' },
        { nome: '🤖 Analisando com IA', descricao: 'OpenAI avaliando critérios textuais...' },
        { nome: '📊 Gerando resultados', descricao: 'Calculando nota e gerando feedback...' }
    ];
    progressManager.iniciar('📝 Avaliando Texto com IA', etapas, '🤖');
    document.getElementById('txt-waiting').style.display = 'none';
    document.getElementById('txt-loading').style.display = 'block';
    document.getElementById('txt-res').style.display = 'none';

    try {
        progressManager.concluirEtapa(0);
        progressManager.proximaEtapa();
        const response = await fetch(API_URL + '/api/corrigir_redacao', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto: texto, aluno_id: alunoId || null })
        });
        progressManager.concluirEtapa(1);
        progressManager.proximaEtapa();
        const dados = await response.json();
        document.getElementById('txt-loading').style.display = 'none';
        document.getElementById('txt-res').style.display = 'block';
        if (dados.erro) { progressManager.erro(dados.erro); showToast('❌ ' + dados.erro, 'error'); return; }
        progressManager.concluirEtapa(2);
        progressManager.finalizar('✅ Avaliação concluída com sucesso!');
        setText('txt-nota', dados.nota || 0);
        const statusEl = document.getElementById('txt-status');
        if (statusEl) {
            statusEl.textContent = dados.nota >= 6 ? 'APROVADO' : 'REPROVADO';
            statusEl.className = 'badge ' + (dados.nota >= 6 ? 'badge-green' : 'badge-red');
        }
        if (dados.metricas) {
            setText('c-coe', dados.metricas.nota_coerencia || 0);
            setText('c-tema', dados.metricas.nota_estrutura || 0);
            setText('c-ort', dados.metricas.nota_gramatica || 0);
            setText('c-voc', dados.metricas.nota_vocabulario || 0);
            const bCoe = document.getElementById('b-coe'); if (bCoe) bCoe.style.width = ((dados.metricas.nota_coerencia || 0) / 10 * 100) + '%';
            const bTema = document.getElementById('b-tema'); if (bTema) bTema.style.width = ((dados.metricas.nota_estrutura || 0) / 10 * 100) + '%';
            const bOrt = document.getElementById('b-ort'); if (bOrt) bOrt.style.width = ((dados.metricas.nota_gramatica || 0) / 10 * 100) + '%';
            const bVoc = document.getElementById('b-voc'); if (bVoc) bVoc.style.width = ((dados.metricas.nota_vocabulario || 0) / 10 * 100) + '%';
        }
        const fb = document.getElementById('txt-fb');
        if (fb) fb.innerHTML = escapeHtml(dados.feedback || 'Feedback gerado automaticamente.');
        if (alunoId) {
            try {
                const alunos = await carregarAlunosComCache();
                const aluno = alunos.find(a => a.id == alunoId);
                setText('txt-aluno-nome', aluno ? aluno.nome : '—');
            } catch (e) {}
        }
        showToast('✅ Avaliação concluída!', 'success');
    } catch (erro) {
        document.getElementById('txt-loading').style.display = 'none';
        progressManager.erro(erro.message);
        showToast('❌ Erro: ' + erro.message, 'error');
    }
}

async function salvarAvaliacaoTexto() {
    const alunoId = document.getElementById('txt-aluno-select').value;
    const provaId = document.getElementById('txt-prova').value;
    const texto = document.getElementById('txt-aluno').value;
    const nota = parseFloat(document.getElementById('txt-nota').textContent) || 0;
    const feedback = document.getElementById('txt-fb').innerHTML || '';
    const metricas = {
        nota_coerencia: parseFloat(document.getElementById('c-coe').textContent) || 0,
        nota_estrutura: parseFloat(document.getElementById('c-tema').textContent) || 0,
        nota_gramatica: parseFloat(document.getElementById('c-ort').textContent) || 0,
        nota_vocabulario: parseFloat(document.getElementById('c-voc').textContent) || 0
    };
    if (!alunoId) { showToast('⚠️ Selecione o aluno antes de salvar!', 'error'); return; }
    if (!texto || texto.trim().length < 5) { showToast('⚠️ Nenhum texto para salvar!', 'error'); return; }
    if (!nota || nota === 0) { showToast('⚠️ Avalie o texto antes de salvar!', 'error'); return; }

    showToast('💾 Salvando avaliação...', 'info');
    try {
        const response = await fetch(API_URL + '/api/salvar_correcao_texto', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                aluno_id: parseInt(alunoId),
                prova_id: provaId ? parseInt(provaId) : null,
                texto: texto, nota: nota, metricas: metricas, feedback: feedback
            })
        });
        const dados = await response.json();
        if (dados.sucesso) showToast(`✅ Avaliação salva! Nota: ${nota.toFixed(1)}`, 'success');
        else showToast('❌ Erro ao salvar: ' + (dados.erro || 'Erro desconhecido'), 'error');
    } catch (err) { showToast('❌ Erro ao salvar: ' + err.message, 'error'); }
}

async function carregarTurmasTexto(escolaId) {
    const selectTurma = document.getElementById('txt-turma');
    const selectAluno = document.getElementById('txt-aluno-select');
    selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
    if (!escolaId) return;
    try {
        const turmas = await carregarTurmasComCache(escolaId);
        if (turmas && !turmas.erro) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                selectTurma.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

async function carregarAlunosPorTurmaTexto(turmaId) {
    const selectAluno = document.getElementById('txt-aluno-select');
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
    if (!turmaId) return;
    try {
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        if (alunos && !alunos.erro) {
            alunos.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.nome + ' (Nº ' + (a.numero_chamada || '—') + ')';
                selectAluno.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

async function carregarEscolasTexto() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('txt-escola');
        if (select && escolas && !escolas.erro) {
            const current = select.value;
            select.innerHTML = '<option value="">Selecione a escola...</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                select.appendChild(opt);
            });
            if (current) select.value = current;
        }
    } catch (erro) { console.error(erro); }
}

// ============================================
// CÂMERA
// ============================================
async function abrirCamera() {
    document.getElementById('cam-modal').classList.add('show');
    try {
        if (camStream) camStream.getTracks().forEach(t => t.stop());
        camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: camFacing, width: { ideal: 1280 }, height: { ideal: 720 } } });
        document.getElementById('cam-video').srcObject = camStream;
    } catch (e) { showToast('❌ Câmera não disponível: ' + e.message, 'error'); fecharCamera(); }
}

function trocarCamera() { camFacing = camFacing === 'environment' ? 'user' : 'environment'; abrirCamera(); }

function fecharCamera() {
    document.getElementById('cam-modal').classList.remove('show');
    if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null; }
}

function capturarFoto() {
    const vid = document.getElementById('cam-video');
    const canvas = document.getElementById('cam-canvas');
    canvas.width = vid.videoWidth || 640;
    canvas.height = vid.videoHeight || 480;
    canvas.getContext('2d').drawImage(vid, 0, 0);
    const foto = canvas.toDataURL('image/jpeg', 0.9);
    fecharCamera();
    showToast('📸 Foto capturada!', 'ai');
    if (autoModoAtivo) {
        autoModoAtivo = false;
        window._autoImagem = foto;
        go('corrigir-ia');
        setTimeout(() => {
            const preview = document.getElementById('auto-preview');
            const img = document.getElementById('auto-img-prev');
            if (preview && img) { img.src = foto; preview.style.display = 'block'; }
            corrigirAutomatico();
        }, 500);
        return;
    }
    ultimaImagem = foto;
    processarComIA(foto);
    go('corrigir-ia');
}

function abrirArquivo() { document.getElementById('inp-arq').click(); }

function processarArq(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
        showToast('📂 Arquivo carregado!', 'ai');
        ultimaImagem = e.target.result;
        processarComIA(e.target.result);
        go('corrigir-ia');
    };
    reader.readAsDataURL(file);
}

// ============================================
// CORREÇÃO COM IA
// ============================================
async function processarComIA(imagemBase64) {
    const escolaId = document.getElementById('corrigir-escola')?.value;
    const turmaId = document.getElementById('corrigir-turma')?.value;
    const provaId = document.getElementById('corrigir-prova')?.value;
    const alunoId = document.getElementById('corrigir-aluno')?.value;
    if (!escolaId || !turmaId || !provaId || !alunoId) { showToast('❌ Selecione escola, turma, prova e aluno!', 'error'); return; }
    if (!imagemBase64) { showToast('❌ Nenhuma imagem foi fornecida!', 'error'); return; }

    const etapas = [
        { nome: '📸 Preparando imagem', descricao: 'Processando a imagem do cartão resposta...' },
        { nome: '🎯 Template + Marcadores', descricao: 'Detectando marcadores e aplicando template...' },
        { nome: '🔍 Validação OpenCV', descricao: 'Cruzando com HoughCircles...' },
        { nome: '🤖 IA (se necessário)', descricao: 'Analisando casos difíceis com OpenAI...' },
        { nome: '📊 Processando resultados', descricao: 'Comparando com o gabarito e calculando nota...' },
        { nome: '💾 Finalizando', descricao: 'Salvando os resultados...' }
    ];
    progressManager.iniciar('🤖 Corrigindo com IA', etapas, '🤖');

    try {
        progressManager.atualizarEtapa(0);
        await sleep(500);
        let imagemEnvio = imagemBase64;
        if (imagemBase64.startsWith('data:image')) {
            const partes = imagemBase64.split(',');
            if (partes.length > 1) imagemEnvio = partes[1];
        }
        progressManager.atualizarEtapa(1);
        await sleep(300);
        const prova = await buscarProva(provaId);
        if (!prova) throw new Error('Prova não encontrada');
        const gabarito = prova.gabarito || [];
        const totalQuestoes = prova.quantidade_questoes || 20;
        const tipoQuestoes = prova.tipo_questoes || 4;
        const isProducao = (prova.disciplina === 'Produção de Texto');
        const alternativas = tipoQuestoes == 3 ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        if (!gabarito || gabarito.length === 0) throw new Error('Esta prova não tem gabarito cadastrado!');
        const aluno = await buscarAluno(alunoId);
        if (!aluno) throw new Error('Aluno não encontrado');
        progressManager.atualizarEtapa(2);
        await sleep(300);
        const respostaIA = await enviarParaCorrecao(imagemEnvio, provaId, alunoId);
        if (respostaIA.erro) throw new Error(respostaIA.erro);
        progressManager.atualizarEtapa(3);
        await sleep(200);

        let respostasDetectadas = respostaIA.respostas_detectadas || [];
        let confiancas = respostaIA.confianca_por_questao || [];
        const { respostasNormalizadas, confiancasNormalizadas } = normalizarRespostas(
            respostasDetectadas, confiancas, totalQuestoes, isProducao, tipoQuestoes
        );

        let acertos = 0;
        const resultadoQuestoes = [];
        for (let i = 0; i < totalQuestoes; i++) {
            const resp = respostasNormalizadas[i] || '';
            const gab = (i < gabarito.length) ? (gabarito[i] || '') : '';
            const confianca = confiancasNormalizadas[i] || 0;
            let isCorreto = false, statusMsg = 'NÃO RESPONDEU';
            if (isProducao) {
                if (resp && gab) {
                    const respLimpa = resp.trim().toLowerCase();
                    const gabLimpo = gab.trim().toLowerCase();
                    isCorreto = respLimpa === gabLimpo || respLimpa.includes(gabLimpo) || gabLimpo.includes(respLimpa);
                    statusMsg = isCorreto ? '✅ ACERTOU' : '❌ ERROU';
                }
            } else {
                const respNormalizada = resp.toString().toUpperCase().trim();
                const gabNormalizado = gab.toString().toUpperCase().trim();
                if (respNormalizada && gabNormalizado) {
                    isCorreto = respNormalizada === gabNormalizado;
                    statusMsg = isCorreto ? '✅ ACERTOU' : '❌ ERROU';
                } else if (respNormalizada) statusMsg = '❌ RESPOSTA INVÁLIDA';
            }
            if (isCorreto) acertos++;
            resultadoQuestoes.push({
                numero: i + 1, resposta: resp || '—', gabarito: gab || '—',
                acertou: isCorreto, status: statusMsg, confianca: confianca, respondida: !!resp
            });
        }

        const valorPorQuestao = 10 / totalQuestoes;
        const nota = Math.min(acertos * valorPorQuestao, 10);
        const porcentagem = Math.round((acertos / totalQuestoes) * 100);
        const conceito = calcularConceito(porcentagem);
        progressManager.atualizarEtapa(4);
        await sleep(300);

        correcaoManualData = {
            alunoId: parseInt(alunoId), alunoNome: aluno.nome || 'Aluno',
            provaId: parseInt(provaId), provaTitulo: prova.titulo || 'Prova',
            gabarito: gabarito, respostasAluno: respostasNormalizadas,
            quantidade: totalQuestoes, alternativas: alternativas,
            notaMaxima: 10, notaMinima: 5, valorPorQuestao: valorPorQuestao,
            serie: prova.serie || '1º Ano', disciplina: prova.disciplina || '',
            confianca_por_questao: confiancasNormalizadas,
            questoes_suspeitas: respostaIA.questoes_suspeitas || []
        };

        const metodoUsado = respostaIA.metodo_usado || respostaIA.modo || 'desconhecido';
        atualizarInterfaceCorrecao({
            aluno: aluno, prova: prova, resultadoQuestoes: resultadoQuestoes,
            acertos: acertos, totalQuestoes: totalQuestoes, nota: nota,
            porcentagem: porcentagem, conceito: conceito,
            confiancas: confiancasNormalizadas, metodoUsado: metodoUsado,
            requerRevisao: respostaIA.requer_revisao_manual || false,
            questoesSuspeitas: respostaIA.questoes_suspeitas || []
        });

        progressManager.atualizarEtapa(5);
        await sleep(200);
        progressManager.finalizar(`✅ Correção concluída! ${acertos}/${totalQuestoes} acertos — Nota: ${nota.toFixed(1)}`);
        carregarDashboard();
        carregarUltimasCorrecoes();
    } catch (erro) {
        console.error(erro);
        progressManager.erro(erro.message || 'Erro ao processar correção');
        showToast('❌ Erro ao processar correção: ' + erro.message, 'error');
    }
}

async function buscarProva(provaId) {
    try { const provas = await carregarProvasComCache(); return provas.find(p => p.id == provaId); }
    catch (e) { throw new Error('Erro ao buscar dados da prova'); }
}

async function buscarAluno(alunoId) {
    try { const alunos = await carregarAlunosComCache(); return alunos.find(a => a.id == alunoId); }
    catch (e) { throw new Error('Erro ao buscar dados do aluno'); }
}

async function enviarParaCorrecao(imagemBase64, provaId, alunoId) {
    const response = await fetch(`${API_URL}/api/corrigir`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            imagem: imagemBase64,
            prova_id: parseInt(provaId),
            aluno_id: parseInt(alunoId)
        })
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Erro ${response.status}: ${errorText.substring(0, 100)}`);
    }
    const dados = await response.json();
    if (dados.erro) throw new Error(dados.erro);
    if (!dados.respostas_detectadas && !dados.questoes_status) {
        throw new Error('A IA não conseguiu detectar as respostas. Tire uma foto mais nítida com boa iluminação.');
    }
    return dados;
}

function normalizarRespostas(respostas, confiancas, totalQuestoes, isProducao, tipoQuestoes = 4) {
    let respostasNormalizadas = [], confiancasNormalizadas = [];
    const alternativasValidas = tipoQuestoes == 3 ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
    for (let i = 0; i < totalQuestoes; i++) {
        let resp = (i < respostas.length) ? (respostas[i] || '') : '';
        let conf = (i < confiancas.length) ? (confiancas[i] || 0) : 0;
        if (isProducao) resp = resp.toString().trim();
        else {
            let s = resp.toString().trim().toUpperCase();
            s = s.replace(/^[\(\[]*/, '').replace(/[\)\]\.\,\;\:\-]*$/, '');
            let encontrou = '';
            if (alternativasValidas.includes(s)) encontrou = s;
            else for (const alt of alternativasValidas) if (s.includes(alt)) { encontrou = alt; break; }
            resp = encontrou;
        }
        respostasNormalizadas.push(resp);
        confiancasNormalizadas.push(Math.min(Math.max(conf, 0), 100));
    }
    return { respostasNormalizadas, confiancasNormalizadas };
}

function atualizarInterfaceCorrecao(dados) {
    const box = document.getElementById('ia-result');
    if (box) box.style.display = 'block';
    setText('ia-aluno', dados.aluno.nome || 'Aluno');
    setText('ia-turma', dados.prova.titulo || 'Prova');
    setText('ia-nota', dados.nota.toFixed(1));

    const statusEl = document.getElementById('ia-status');
    if (statusEl) {
        const aprovado = dados.nota >= 6;
        statusEl.textContent = aprovado ? '✅ APROVADO' : '❌ REPROVADO';
        statusEl.className = 'badge ' + (aprovado ? 'badge-green' : 'badge-red');
    }

    const metodo = dados.metodoUsado || 'desconhecido';
    const metodoBadge = document.getElementById('ia-metodo');
    if (metodoBadge) {
        const metodoLabels = {
            'template': '🎯 Template', 'template+cv': '🎯 Template+CV',
            'ia': '🤖 IA', 'ia+circulos': '🤖 IA + Círculos',
            'ia_parcial': '🤖 IA (Parcial)', 'circulos': '⭕ Círculos',
            'circulos_parcial': '⭕ Círculos (Parcial)', 'manual': '✏️ Manual'
        };
        metodoBadge.textContent = metodoLabels[metodo] || `📌 ${metodo}`;
        const classe = metodo === 'template' || metodo === 'template+cv' ? 'badge-green' :
                       metodo === 'ia' ? 'badge-purple' :
                       metodo.includes('circulos') ? 'badge-orange' : 'badge-gray';
        metodoBadge.className = `badge ${classe}`;
    }

    const confiancaMedia = dados.confiancas.reduce((a, b) => a + b, 0) / dados.confiancas.length || 0;
    const badgeConfianca = document.getElementById('confianca-badge');
    if (badgeConfianca) {
        badgeConfianca.textContent = `${confiancaMedia.toFixed(1)}% conf.`;
        badgeConfianca.className = `badge ${confiancaMedia >= 70 ? 'badge-green' : confiancaMedia >= 50 ? 'badge-orange' : 'badge-red'}`;
    }

    const resumoConfianca = document.getElementById('ia-resumo-confianca');
    if (resumoConfianca) {
        const totalDuvidosas = dados.questoesSuspeitas.length || dados.confiancas.filter(c => c < 70).length;
        resumoConfianca.style.display = 'flex';
        let alertaRevisao = '';
        if (dados.requerRevisao) alertaRevisao = `<span style="color:var(--orange);font-weight:700;">⚠️ REVISÃO MANUAL RECOMENDADA</span>`;
        resumoConfianca.innerHTML = `
            <span>📊 Confiança média: <strong style="color:${confiancaMedia >= 70 ? 'var(--green)' : confiancaMedia >= 50 ? 'var(--orange)' : 'var(--red)'};">${confiancaMedia.toFixed(1)}%</strong></span>
            ${totalDuvidosas > 0 ? `<span>⚠️ ${totalDuvidosas} questões com baixa confiança (<70%)</span>` : '<span>✅ Todas as questões têm alta confiança!</span>'}
            <span>🎯 Acertos: <strong style="color:var(--green);">${dados.acertos}</strong> / ${dados.totalQuestoes}</span>
            <span>📌 Método: <strong>${metodo}</strong></span>
            ${alertaRevisao}
        `;
    }

    const rd = document.getElementById('ia-resp');
    if (rd) {
        rd.innerHTML = dados.resultadoQuestoes.map(q => {
            const cor = q.acertou ? 'rgba(16,185,129,.2)' : 'rgba(239,68,68,.2)';
            const corTexto = q.acertou ? 'var(--green)' : 'var(--red)';
            const icone = q.acertou ? '✅' : (q.respondida ? '❌' : '—');
            const confColor = q.confianca < 70 ? 'var(--orange)' : 'var(--text2)';
            return `<span style="background:${cor};border:1px solid ${q.acertou ? 'rgba(16,185,129,.4)' : 'rgba(239,68,68,.4)'};padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;color:${corTexto};">Q${q.numero}:${escapeHtml(q.resposta || '—')} ${icone}<span style="font-size:8px;color:${confColor};">${q.confianca}%</span></span>`;
        }).join('');
    }

    const grid = document.getElementById('ia-comp');
    if (grid) {
        grid.innerHTML = '';
        const totalQuestoes = dados.resultadoQuestoes.length;
        let colunasPorLinha = 5;
        if (totalQuestoes > 25) colunasPorLinha = 6;

        const tituloOficial = document.createElement('div');
        tituloOficial.style.cssText = `grid-column: 1 / -1; text-align: center; padding: 6px 0; background: linear-gradient(135deg, rgba(59,130,246,0.10), rgba(139,92,246,0.10)); border-radius: 6px; border: 1px solid rgba(59,130,246,0.15); margin-bottom: 2px; margin-top: 6px;`;
        tituloOficial.innerHTML = `<span style="font-size:12px;font-weight:800;color:var(--blue);">📋 GABARITO OFICIAL</span>`;
        grid.appendChild(tituloOficial);

        const gridOficial = document.createElement('div');
        gridOficial.style.cssText = `grid-column: 1 / -1; display: grid; grid-template-columns: repeat(${colunasPorLinha}, 1fr); gap: 4px; padding: 4px 0;`;
        dados.resultadoQuestoes.forEach(q => {
            const div = document.createElement('div');
            div.style.cssText = `background: rgba(59,130,246,0.05); border-radius: 4px; padding: 3px 2px; text-align: center; border: 1px solid rgba(59,130,246,0.10);`;
            div.innerHTML = `<div style="font-size:6px;color:var(--text3);">Q${q.numero}</div><div style="font-size:16px;font-weight:900;color:var(--green);">${escapeHtml(q.gabarito || '—')}</div>`;
            gridOficial.appendChild(div);
        });
        grid.appendChild(gridOficial);

        const tituloAluno = document.createElement('div');
        tituloAluno.style.cssText = `grid-column: 1 / -1; text-align: center; padding: 6px 0; background: linear-gradient(135deg, rgba(139,92,246,0.10), rgba(59,130,246,0.10)); border-radius: 6px; margin-top: 8px;`;
        tituloAluno.innerHTML = `<span style="font-size:12px;font-weight:800;color:var(--purple);">📋 GABARITO DO ALUNO</span>`;
        grid.appendChild(tituloAluno);

        const gridAluno = document.createElement('div');
        gridAluno.style.cssText = `grid-column: 1 / -1; display: grid; grid-template-columns: repeat(${colunasPorLinha}, 1fr); gap: 4px; padding: 4px 0;`;
        dados.resultadoQuestoes.forEach((q) => {
            const acertou = q.acertou;
            const resposta = q.resposta || '—';
            const confianca = q.confianca || 100;
            let corBg, corTexto, icone;
            if (acertou) { corBg = 'rgba(16,185,129,0.10)'; corTexto = 'var(--green)'; icone = '✅'; }
            else if (q.respondida) { corBg = 'rgba(239,68,68,0.10)'; corTexto = 'var(--red)'; icone = '❌'; }
            else { corBg = 'rgba(100,116,139,0.05)'; corTexto = 'var(--text3)'; icone = '—'; }
            const confColor = confianca < 70 ? 'var(--orange)' : 'var(--text3)';
            const div = document.createElement('div');
            div.style.cssText = `background: ${corBg}; border-radius: 4px; padding: 3px 2px; text-align: center; border: 1px solid ${acertou ? 'rgba(16,185,129,0.20)' : (q.respondida ? 'rgba(239,68,68,0.20)' : 'rgba(100,116,139,0.10)')};`;
            div.innerHTML = `
                <div style="font-size:6px;color:var(--text3);">Q${q.numero}</div>
                <div style="font-size:16px;font-weight:900;color:${corTexto};">${escapeHtml(resposta)}</div>
                <div style="font-size:6px;color:${corTexto};">${icone}</div>
                <div style="font-size:6px;color:${confColor};">${Math.round(confianca)}%</div>
            `;
            gridAluno.appendChild(div);
        });
        grid.appendChild(gridAluno);
    }
}

async function salvarCorrecao() {
    if (!correcaoManualData || !correcaoManualData.respostasAluno) { showToast('❌ Nenhuma correção para salvar!', 'error'); return; }
    const provaId = correcaoManualData.provaId;
    const alunoId = correcaoManualData.alunoId;
    const respostas = correcaoManualData.respostasAluno;
    const gabarito = correcaoManualData.gabarito;
    const total = correcaoManualData.quantidade;
    if (!provaId || !alunoId) { showToast('❌ Dados da correção incompletos!', 'error'); return; }

    let acertos = 0;
    for (let i = 0; i < total; i++) {
        const resp = (i < respostas.length) ? (respostas[i] || '') : '';
        const gab = (i < gabarito.length) ? (gabarito[i] || '') : '';
        if (resp && gab && resp.toUpperCase() === gab.toUpperCase()) acertos++;
    }
    const nota = Math.min(acertos * (correcaoManualData.valorPorQuestao || (10/total)), 10);

    try {
        showToast('💾 Salvando correção...', 'info');
        const response = await fetch(`${API_URL}/api/corrigir_manual`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prova_id: provaId, aluno_id: alunoId, respostas: respostas,
                acertos: acertos, nota: nota, total: total
            })
        });
        const data = await response.json();
        if (data.sucesso) {
            showToast(`✅ Correção salva! Nota: ${nota.toFixed(1)}`, 'success');
            limparCache();
            carregarDashboard();
            carregarUltimasCorrecoes();
        } else showToast('❌ Erro ao salvar: ' + (data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) { console.error(erro); showToast('❌ Erro ao salvar: ' + erro.message, 'error'); }
}

// ============================================
// CRUD ESCOLA
// ============================================
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
            method: 'POST', headers: { 'Content-Type': 'application/json' },
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
            setTimeout(() => tableFeedback.destacarLinha('tb-escola', result.data.id, '✅ Nova!'), 300);
            carregarDashboard();
            carregarCombos();
        } else showToast('❌ Erro ao salvar escola: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao salvar escola: ' + erro.message, 'error');
        console.error(erro);
        const btn = document.querySelector('#m-escola .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarEscola(id) {
    showToast('✏️ Carregando dados da escola...', 'info');
    fetch(API_URL + '/api/escolas/' + id).then(r => r.json()).then(escola => {
        if (escola.erro) { showToast('❌ ' + escola.erro, 'error'); return; }
        document.getElementById('editar-escola-id').value = escola.id;
        document.getElementById('editar-escola-nome').value = escola.nome || '';
        document.getElementById('editar-escola-inep').value = escola.inep || '';
        document.getElementById('editar-escola-municipio').value = escola.municipio || '';
        document.getElementById('editar-escola-estado').value = escola.estado || 'PA';
        document.getElementById('editar-escola-telefone').value = escola.telefone || '';
        document.getElementById('editar-escola-diretor').value = escola.diretor || '';
        openM('m-editar-escola');
    }).catch(e => { showToast('❌ Erro ao carregar escola: ' + e.message, 'error'); console.error(e); });
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
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
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
            setTimeout(() => tableFeedback.destacarLinha('tb-escola', id, '✅ Atualizada!'), 300);
            carregarCombos();
        } else showToast('❌ Erro ao atualizar escola: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao atualizar escola: ' + erro.message, 'error');
        console.error(erro);
        const btn = document.querySelector('#m-editar-escola .btn-primary');
        if (btn) { btn.textContent = '💾 Salvar Alterações'; btn.disabled = false; }
    }
}

async function excluirEscola(id, nome) {
    if (!confirm('🗑️ EXCLUIR COMPLETAMENTE a escola "' + nome + '"\n\nIsso irá excluir TODOS os dados vinculados:\n• Turmas\n• Alunos\n\nAs provas NÃO serão afetadas.\n\nEsta ação NÃO pode ser desfeita!')) return;
    try {
        showToast('⏳ Excluindo escola...', 'info');
        const response = await fetch(`${API_URL}/api/escolas/${id}`, {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast(`✅ Escola "${nome}" excluída com sucesso!`, 'success');
            limparCache();
        } else { showToast(`❌ Erro ao excluir escola: ${result.data.erro || 'Erro desconhecido'}`, 'error'); return; }

        setTimeout(() => {
            carregarEscolas();
            carregarTurmas();
            carregarAlunos();
            carregarProvas();
            carregarDashboard();
            carregarGabaritos();
            carregarCombos();
            carregarUltimasCorrecoes();
            carregarUsuarios();
            carregarEscolasFiltroAlunos();
            carregarEscolasCorrigir();
            carregarEscolasTexto();
            carregarEscolasParaCorrecaoManual();
            carregarFiltrosRelTurma();
            carregarFiltroEscolaTurmas();
        }, 1000);
    } catch (erro) { console.error(erro); showToast('❌ Erro ao excluir escola: ' + erro.message, 'error'); }
}

// ============================================
// CRUD TURMA
// ============================================
async function salvarTurma() {
    const nome = document.getElementById('turma-nome').value.trim();
    if (!nome) { showToast('❌ O nome da turma é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('turma-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }
    const dados = {
        nome: nome, escola_id: parseInt(escolaId),
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
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);
        btn.textContent = originalText;
        btn.disabled = false;
        if (result.ok && result.data.id) {
            showToast('✅ Turma "' + nome + '" salva com sucesso!', 'success');
            limparCache(); closeM('m-turma'); carregarTurmas();
            setTimeout(() => tableFeedback.destacarLinha('tb-turmas', result.data.id, '✅ Nova!'), 300);
            carregarDashboard(); carregarCombos();
        } else showToast('❌ Erro ao salvar turma: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao salvar turma: ' + erro.message, 'error');
        const btn = document.querySelector('#m-turma .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarTurma(id) {
    showToast('✏️ Carregando dados da turma...', 'info');
    fetch(API_URL + '/api/turmas/' + id).then(r => r.json()).then(turma => {
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
        }).catch(e => console.error(e));
    }).catch(e => { showToast('❌ Erro ao carregar turma: ' + e.message, 'error'); console.error(e); });
}

async function salvarEdicaoTurma() {
    const id = document.getElementById('editar-turma-id').value;
    const nome = document.getElementById('editar-turma-nome').value.trim();
    if (!nome) { showToast('❌ O nome da turma é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('editar-turma-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }
    const dados = {
        nome: nome, escola_id: parseInt(escolaId),
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
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);
        btn.textContent = originalText;
        btn.disabled = false;
        if (result.ok) {
            showToast('✅ Turma "' + nome + '" atualizada com sucesso!', 'success');
            limparCache(); closeM('m-editar-turma'); carregarTurmas();
            setTimeout(() => tableFeedback.destacarLinha('tb-turmas', id, '✅ Atualizada!'), 300);
            carregarCombos();
        } else showToast('❌ Erro ao atualizar turma: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao atualizar turma: ' + erro.message, 'error');
        const btn = document.querySelector('#m-editar-turma .btn-primary');
        if (btn) { btn.textContent = '💾 Salvar Alterações'; btn.disabled = false; }
    }
}

async function excluirTurma(id, nome) {
    if (!confirm('Excluir a turma "' + nome + '" e todos os seus dados?')) return;
    try {
        showToast('🗑️ Excluindo turma...', 'error');
        const response = await fetch(API_URL + '/api/turmas/' + id, {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Turma "' + nome + '" excluída com sucesso!', 'success');
            limparCache(); carregarTurmas(); carregarDashboard(); carregarCombos();
        } else showToast('❌ Erro ao excluir turma: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
    } catch (erro) { console.error(erro); showToast('❌ Erro ao excluir turma: ' + erro.message, 'error'); }
}

// ============================================
// CRUD ALUNO
// ============================================
async function salvarAluno() {
    const nome = document.getElementById('aluno-nome').value.trim();
    if (!nome) { showToast('❌ O nome do aluno é obrigatório!', 'error'); return; }
    const escolaId = document.getElementById('aluno-escola').value;
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }
    const turmaId = document.getElementById('aluno-turma').value;
    if (!turmaId) { showToast('❌ Selecione uma turma!', 'error'); return; }
    const dados = {
        nome: nome, escola_id: parseInt(escolaId), turma_id: parseInt(turmaId),
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
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);
        btn.textContent = originalText;
        btn.disabled = false;
        if (result.ok && result.data.id) {
            showToast('✅ Aluno "' + nome + '" salvo com sucesso!', 'success');
            limparCache(); closeM('m-aluno');
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
            setTimeout(() => tableFeedback.destacarLinha('tb-alunos', result.data.id, '✅ Novo!'), 300);
            carregarDashboard(); carregarCombos();
        } else showToast('❌ Erro ao salvar aluno: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao salvar aluno: ' + erro.message, 'error');
        const btn = document.querySelector('#m-aluno .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

function editarAluno(id) {
    showToast('✏️ Carregando dados do aluno...', 'info');
    fetch(API_URL + '/api/alunos/' + id).then(r => r.json()).then(aluno => {
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
                carregarTurmasPorEscolaParaAluno(aluno.escola_id, 'editar-aluno-turma').then(() => {
                    const selectTurma = document.getElementById('editar-aluno-turma');
                    if (selectTurma) selectTurma.value = aluno.turma_id;
                });
            }
            openM('m-editar-aluno');
        }).catch(e => console.error(e));
    }).catch(e => { showToast('❌ Erro ao carregar aluno: ' + e.message, 'error'); console.error(e); });
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
        nome: nome, escola_id: parseInt(escolaId), turma_id: parseInt(turmaId),
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
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);
        btn.textContent = originalText;
        btn.disabled = false;
        if (result.ok) {
            showToast('✅ Aluno "' + nome + '" atualizado com sucesso!', 'success');
            limparCache(); closeM('m-editar-aluno'); carregarAlunos();
            setTimeout(() => tableFeedback.destacarLinha('tb-alunos', id, '✅ Atualizado!'), 300);
            carregarCombos();
        } else showToast('❌ Erro ao atualizar aluno: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao atualizar aluno: ' + erro.message, 'error');
        const btn = document.querySelector('#m-editar-aluno .btn-primary');
        if (btn) { btn.textContent = '💾 Salvar Alterações'; btn.disabled = false; }
    }
}

async function excluirAluno(id, nome) {
    if (!confirm('Excluir o aluno "' + nome + '" e todos os seus dados?')) return;
    try {
        showToast('🗑️ Excluindo aluno...', 'error');
        const response = await fetch(API_URL + '/api/alunos/' + id, {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Aluno "' + nome + '" excluído com sucesso!', 'success');
            limparCache(); carregarAlunos(); carregarDashboard(); carregarCombos();
        } else showToast('❌ Erro ao excluir aluno: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
    } catch (erro) { console.error(erro); showToast('❌ Erro ao excluir aluno: ' + erro.message, 'error'); }
}

// ============================================
// CRUD PROVA
// ============================================
async function salvarProva() {
    const titulo = document.getElementById('prova-titulo').value.trim();
    if (!titulo) { showToast('❌ O título da prova é obrigatório!', 'error'); return; }
    const serie = document.getElementById('prova-serie').value;
    if (!serie) { showToast('❌ Selecione a série!', 'error'); return; }
    const dados = {
        titulo: titulo, serie: serie,
        disciplina: document.getElementById('prova-disciplina').value || 'Matemática',
        bimestre: document.getElementById('prova-bimestre').value || '1º e 2º bimestre',
        data_prova: document.getElementById('prova-data').value || null,
        quantidade_questoes: parseInt(document.getElementById('prova-questoes').value) || 20,
        nota_maxima: parseFloat(document.getElementById('prova-nota').value) || 10,
        tipo_questoes: '4'
    };
    try {
        const btn = document.querySelector('#page-prova-upload .btn-green');
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;
        showToast('💾 Salvando prova...', 'info');
        const response = await fetch(API_URL + '/api/provas', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const result = await processarRespostaAPI(response);
        btn.textContent = originalText;
        btn.disabled = false;
        if (result.ok && result.data.id) {
            showToast('✅ Prova "' + titulo + '" salva com sucesso para a série ' + serie + '!', 'success');
            limparCache();
            document.getElementById('prova-titulo').value = '';
            document.getElementById('up-ok').style.display = 'block';
            setTimeout(() => { document.getElementById('up-ok').style.display = 'none'; }, 3000);
            carregarProvas();
            setTimeout(() => tableFeedback.destacarLinha('tb-provas', result.data.id, '✅ Nova!'), 300);
            carregarDashboard(); carregarCombos();
        } else showToast('❌ Erro ao salvar prova: ' + (result.data.erro || 'Erro desconhecido'), 'error');
    } catch (erro) {
        showToast('❌ Erro ao salvar prova: ' + erro.message, 'error');
        const btn = document.querySelector('#page-prova-upload .btn-green');
        if (btn) { btn.textContent = '💾 Salvar'; btn.disabled = false; }
    }
}

async function excluirProva(id, nome) {
    if (!confirm('Excluir a prova "' + nome + '" e todos os seus dados?')) return;
    try {
        showToast('🗑️ Excluindo prova...', 'error');
        const response = await fetch(API_URL + '/api/provas/' + id, {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Prova "' + nome + '" excluída com sucesso!', 'success');
            limparCache(); carregarProvas(); carregarDashboard(); carregarCombos();
        } else showToast('❌ Erro ao excluir prova: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
    } catch (erro) { console.error(erro); showToast('❌ Erro ao excluir prova: ' + erro.message, 'error'); }
}

function salvarProvaModal() {
    const titulo = document.getElementById('modal-prova-titulo').value.trim();
    if (!titulo) { showToast('❌ O título da prova é obrigatório!', 'error'); return; }
    showToast('✅ Prova "' + titulo + '" salva com sucesso!', 'success');
    closeM('m-prova');
    carregarProvas();
}

// ============================================
// FUNÇÕES ADICIONAIS
// ============================================
function verAlunosDaTurma(id) {
    showToast('📋 Visualizando alunos da turma ID ' + id + '...', 'info');
    const selectTurma = document.getElementById('filtro-turma-alunos');
    if (selectTurma) { selectTurma.value = id; selectTurma.dispatchEvent(new Event('change')); }
    go('alunos');
}

function processarListaAlunos() {
    const textarea = document.getElementById('multi-alunos-input');
    const linhas = textarea.value.split('\n').filter(l => l.trim() !== '');
    if (linhas.length === 0) { showToast('⚠️ Cole a lista de alunos primeiro!', 'warning'); return; }
    const statusDiv = document.getElementById('multi-status');
    const statusText = document.getElementById('multi-status-text');
    let adicionados = 0, erros = 0;
    linhas.forEach(linha => {
        let nome = linha.trim(), matricula = '', numero = '';
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
    closeM('m-aluno');
    go('lista-turma');
}

async function carregarTurmasLista(escolaId) {
    const select = document.getElementById('lista-turma');
    select.innerHTML = '<option value="">Selecione a turma</option>';
    if (!escolaId) return;
    try {
        const turmas = await carregarTurmasComCache(escolaId);
        if (turmas && !turmas.erro) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                select.appendChild(opt);
            });
        }
    } catch (e) { console.error(e); }
}

async function gerarListaTurma() {
    const escolaId = document.getElementById('lista-escola').value;
    const turmaId = document.getElementById('lista-turma').value;
    const provaId = document.getElementById('lista-prova-select')?.value || '';
    if (!turmaId) { showToast('❌ Selecione uma turma!', 'error'); return; }
    if (!escolaId) { showToast('❌ Selecione uma escola!', 'error'); return; }
    try {
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        const turmas = await carregarTurmasComCache();
        const turma = turmas.find(t => t.id == turmaId);
        const container = document.getElementById('lista-resultado');
        if (!container) return;
        if (!alunos || alunos.length === 0 || alunos.erro) {
            container.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text3);">Nenhum aluno encontrado nesta turma</div>';
            showToast('❌ Nenhum aluno na turma!', 'error');
            return;
        }
        const provas = await carregarProvasComCache();
        const serieTurma = turma?.serie || '';
        let provasDisponiveis = provas.filter(p => p.serie === serieTurma);
        if (provasDisponiveis.length === 0) provasDisponiveis = provas;
        let prova = null;
        if (provaId) prova = provas.find(p => p.id == provaId);
        if (!prova && provasDisponiveis.length > 0) prova = provasDisponiveis[0];
        if (!prova) {
            container.innerHTML = `
                <div style="text-align:center;padding:30px;color:var(--orange);">
                    <div style="font-size:40px;margin-bottom:10px;">📝</div>
                    <p style="font-weight:700;">Nenhuma prova cadastrada para esta turma</p>
                    <button class="btn btn-primary" style="margin-top:10px;" onclick="go('prova-upload')">➕ Cadastrar Prova</button>
                </div>`;
            showToast('❌ Nenhuma prova para esta turma!', 'error');
            return;
        }
        const escolas = await carregarEscolasComCache();
        const escola = escolas.find(e => e.id == turma?.escola_id);
        let provasOptions = '';
        provasDisponiveis.forEach(p => {
            const selected = p.id == prova.id ? 'selected' : '';
            provasOptions += `<option value="${p.id}" ${selected}>${escapeHtml(p.titulo)} (${escapeHtml(p.disciplina || 'Sem disciplina')})</option>`;
        });

        let html = `
            <div style="text-align:center;padding:12px 0 18px;border-bottom:1px solid var(--border);margin-bottom:14px;">
                <div style="font-size:16px;font-weight:800;">${escapeHtml(escola?.nome || 'Escola')}</div>
                <div style="color:var(--text2);font-size:13px;margin-top:4px;">
                    Turma: ${escapeHtml(turma?.nome || '—')} | Série: ${escapeHtml(turma?.serie || '—')}
                </div>
                <div style="margin-top:10px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <label style="font-size:12px;font-weight:600;color:var(--text2);">📖 Prova:</label>
                        <select id="lista-prova-select" class="form-control" style="width:250px;padding:6px 10px;font-size:12px;" onchange="gerarListaTurma()">${provasOptions}</select>
                    </div>
                    <button class="btn btn-green" onclick="gerarCartoesTodosAlunos(${escolaId}, ${turmaId}, ${prova.id})">📄 GERAR TODOS OS CARTOES</button>
                    <button class="btn btn-primary" onclick="gerarListaTurma()">🔄 Atualizar</button>
                </div>
            </div>
        `;
        html += '<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px;max-height:400px;overflow-y:auto;">';
        for (let i = 0; i < alunos.length; i++) {
            const aluno = alunos[i];
            html += `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--surface2);border-radius:8px;border:1px solid var(--border);">
                    <div><strong>${escapeHtml(aluno.nome)}</strong> <span class="badge badge-blue">Nº ${escapeHtml(aluno.numero_chamada || '—')}</span></div>
                    <button class="btn btn-primary btn-sm" onclick="gerarCartaoResposta(${escolaId}, ${turmaId}, ${aluno.id}, ${prova.id})">📄 Gerar Cartão</button>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
        showToast(`📋 ${alunos.length} alunos encontrados. Clique em "GERAR TODOS OS CARTOES" para gerar todos!`, 'info');
    } catch (erro) { console.error(erro); showToast('❌ Erro: ' + erro.message, 'error'); }
}

async function gerarCartaoResposta(escolaId, turmaId, alunoId, provaId) {
    try {
        const novaAba = window.open('', '_blank');
        if (!novaAba) { showToast('❌ Permita pop-ups para gerar o cartão resposta!', 'error'); return; }
        novaAba.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Gerando...</title></head><body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Arial,sans-serif;background:#f0f2f5;"><div style="text-align:center;"><div style="font-size:60px;margin-bottom:20px;">⏳</div><h2>Gerando cartão resposta...</h2></div></body></html>`);
        novaAba.document.close();
        const response = await fetch(`${API_URL}/api/gerar_gabarito`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                escola_id: parseInt(escolaId), turma_id: parseInt(turmaId),
                aluno_id: parseInt(alunoId), prova_id: parseInt(provaId)
            })
        });
        if (!response.ok) throw new Error(`Erro ${response.status} ao gerar cartão`);
        const htmlCartao = await response.text();
        novaAba.document.open();
        novaAba.document.write(htmlCartao);
        novaAba.document.close();
        showToast('✅ Cartão resposta gerado com sucesso!', 'success');
    } catch (erro) { console.error(erro); showToast('❌ Erro ao gerar cartão: ' + erro.message, 'error'); }
}

async function gerarCartoesTodosAlunos(escolaId, turmaId, provaId) {
    try {
        showToast('📄 Gerando cartões para todos os alunos...', 'info');
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        if (!alunos || alunos.length === 0) { showToast('❌ Nenhum aluno encontrado nesta turma!', 'error'); return; }
        for (let i = 0; i < alunos.length; i++) {
            const aluno = alunos[i];
            setTimeout(() => { gerarCartaoResposta(escolaId, turmaId, aluno.id, provaId); }, i * 300);
        }
        showToast(`✅ Gerando ${alunos.length} cartões...`, 'success');
    } catch (erro) { console.error(erro); showToast('❌ Erro: ' + erro.message, 'error'); }
}

// ============================================
// AUXILIARES
// ============================================
function switchTab(idx, btn) {
    const parent = btn.closest('.tab-nav');
    if (parent) { parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); }
    const card = btn.closest('.card');
    if (card) { card.querySelectorAll('.tab-c').forEach((tc, i) => { tc.style.display = i === idx ? 'block' : 'none'; }); }
}

function closeM(id) {
    const modal = document.getElementById(id);
    if (modal) { modal.style.display = 'none'; modal.classList.remove('show'); }
}

function openM(id) {
    const modal = document.getElementById(id);
    if (modal) { modal.style.display = 'flex'; modal.classList.add('show'); }
    if (id === 'm-turma' || id === 'm-aluno') { carregarCombos(); if (id === 'm-aluno') carregarEscolasParaAluno(); }
    if (id === 'm-prova') { carregarCombos(); const tipo = document.getElementById('modal-prova-tipo').value; gerarGabaritoModal(tipo); }
}

document.querySelectorAll('.modal-overlay').forEach(m => { m.addEventListener('click', e => { if (e.target === m) m.classList.remove('show'); }); });

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
        input.style.cssText = 'width:40px;height:35px;text-align:center;background:var(--bg2);border:1.5px solid var(--border2);border-radius:6px;color:var(--text);font-weight:bold;font-size:14px;text-transform:uppercase;';
        input.placeholder = i;
        input.title = 'Questão ' + i;
        input.addEventListener('input', function() {
            this.value = this.value.toUpperCase().replace(/[^A-D]/g, '');
            if (this.value && !alts.includes(this.value)) this.value = '';
        });
        grid.appendChild(input);
    }
}

function excluir(btn, tipo, nome) {
    const row = btn.closest('tr');
    delTarget = { row, tipo, nome };
    document.getElementById('del-nome-txt').textContent = '"' + nome + '"';
    document.getElementById('del-modal').classList.add('show');
}

function cancelarDel() { document.getElementById('del-modal').classList.remove('show'); delTarget = null; }

function confirmarDel() {
    document.getElementById('del-modal').classList.remove('show');
    if (!delTarget) return;
    const { row, tipo, nome } = delTarget;
    row.classList.add('deleting');
    setTimeout(() => {
        row.remove();
        showToast('🗑️ ' + tipo.charAt(0).toUpperCase() + tipo.slice(1) + ' "' + nome + '" excluído(a).', 'error');
        delTarget = null; limparCache(); renumerarTabela(row.closest('tbody'));
    }, 350);
}

function renumerarTabela(tbody) {
    if (!tbody) return;
    tbody.querySelectorAll('tr').forEach((tr, i) => {
        const badge = tr.querySelector('.badge-blue, .badge-gray');
        if (badge) {
            const num = String(i + 1).padStart(2, '0');
            if (badge.textContent.match(/^\d+$/)) badge.textContent = num;
        }
    });
}

function filtrarTabela(input, tbodyId) {
    const val = input.value.toLowerCase();
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(val) ? '' : 'none';
    });
}

function showToast(msg, type) {
    type = type || 'info';
    const c = document.getElementById('toast-c');
    if (!c) return;
    const t = document.createElement('div');
    t.className = 'toast toast-' + type;
    const icons = { info: 'ℹ️', success: '✅', error: '❌', ai: '🤖', warning: '⚠️' };
    t.innerHTML = '<span>' + (icons[type] || 'ℹ️') + '</span><span>' + escapeHtml(msg) + '</span>';
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, 3200);
}

function simUpload() { setTimeout(() => { document.getElementById('up-ok').style.display = 'block'; showToast('✅ Arquivo enviado!', 'success'); }, 600); }

function atualizarInfoAlts() {
    const disciplina = document.getElementById('prova-disciplina').value;
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

function salvarConfiguracoes() { showToast('✅ Configurações salvas!', 'success'); }

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
        ['gab-prova', 'corrigir-prova', 'txt-prova'].forEach(id => {
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
        ['corrigir-aluno', 'txt-aluno-select'].forEach(id => {
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
    } catch (erro) { console.error(erro); }
}

async function carregarEscolasParaAluno() {
    try {
        const escolas = await carregarEscolasComCache();
        if (!escolas || escolas.length === 0 || escolas.erro) return;
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
    } catch (erro) { console.error(erro); }
}

async function carregarTurmasPorEscolaParaAluno(escolaId, selectTurmaId) {
    const selectTurma = document.getElementById(selectTurmaId);
    if (!selectTurma) return;
    selectTurma.innerHTML = '<option value="">Selecione a turma</option>';
    if (!escolaId || escolaId === '') return;
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
        } else {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Nenhuma turma cadastrada';
            opt.disabled = true;
            selectTurma.appendChild(opt);
        }
    } catch (e) {
        console.error(e);
        showToast('❌ Erro ao carregar turmas: ' + e.message, 'error');
    }
}

// ============================================
// RELATÓRIO POR TURMA
// ============================================
async function carregarFiltrosRelTurma() {
    try {
        const escolas = await carregarEscolasComCache();
        const selectEscola = document.getElementById('rel-turma-escola');
        if (selectEscola && escolas && !escolas.erro) {
            const current = selectEscola.value;
            selectEscola.innerHTML = '<option value="">Todas as escolas</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                selectEscola.appendChild(opt);
            });
            if (current) { selectEscola.value = current; if (current && current !== '') carregarTurmasRelTurma(current); }
        }
        const provas = await carregarProvasComCache();
        const selectProva = document.getElementById('rel-turma-prova');
        if (selectProva && provas && !provas.erro) {
            const current = selectProva.value;
            selectProva.innerHTML = '<option value="">Todas as provas</option>';
            provas.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.titulo + ' - ' + (p.serie || '') + ' - ' + (p.disciplina || '');
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
            if (current) selectProva.value = current;
        }
    } catch (erro) { console.error(erro); }
}

async function carregarTurmasRelTurma(escolaId) {
    const selectTurma = document.getElementById('rel-turma-turma');
    const selectSerie = document.getElementById('rel-turma-serie');
    if (!selectTurma) return;
    selectTurma.innerHTML = '<option value="">Todas as turmas</option>';

    if (!escolaId || escolaId === '') {
        try {
            const turmas = await carregarTurmasComCache();
            if (turmas && !turmas.erro) {
                turmas.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.nome + ' - ' + (t.serie || '');
                    opt.dataset.serie = t.serie || '';
                    selectTurma.appendChild(opt);
                });
                if (selectSerie) filtrarTurmasPorSerie(selectSerie, selectTurma);
            }
        } catch (erro) { console.error(erro); }
        carregarRelatorioTurmaFiltrado();
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
        } else {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Nenhuma turma encontrada';
            opt.disabled = true;
            selectTurma.appendChild(opt);
        }
        if (selectSerie) filtrarTurmasPorSerie(selectSerie, selectTurma);
    } catch (erro) { console.error(erro); }
    carregarRelatorioTurmaFiltrado();
}

function imprimirRelatorioTurma() { showToast('🖨️ Imprimindo relatório...', 'info'); window.print(); }

async function carregarRelatorioTurmaFiltrado() {
    try {
        const escolaId = document.getElementById('rel-turma-escola').value;
        const serie = document.getElementById('rel-turma-serie').value;
        const turmaId = document.getElementById('rel-turma-turma').value;
        const provaId = document.getElementById('rel-turma-prova').value;

        let disciplinaSelecionada = 'Português';
        let tipoAvaliacao = 'portugues';
        let corDisciplina = '#3b82f6';
        let bgDisciplina = 'rgba(59,130,246,0.05)';
        let iconDisciplina = '📖';

        const selectProva = document.getElementById('rel-turma-prova');
        const optionProva = selectProva.options[selectProva.selectedIndex];
        if (optionProva && optionProva.dataset.disciplina) disciplinaSelecionada = optionProva.dataset.disciplina;

        const disciplinaMap = {
            'Português': { chave: 'portugues', cor: '#3b82f6', bg: 'rgba(59,130,246,0.05)', label: 'Português', icon: '📖' },
            'Matemática': { chave: 'matematica', cor: '#10b981', bg: 'rgba(16,185,129,0.05)', label: 'Matemática', icon: '🔢' },
            'Produção de Texto': { chave: 'producao', cor: '#8b5cf6', bg: 'rgba(139,92,246,0.05)', label: 'Produção de Texto', icon: '✍️' },
            'Ciências Humanas': { chave: 'ch', cor: '#f59e0b', bg: 'rgba(245,158,11,0.05)', label: 'Ciências Humanas', icon: '🌍' },
            'Ciências Naturais': { chave: 'cn', cor: '#14b8a6', bg: 'rgba(20,184,166,0.05)', label: 'Ciências Naturais', icon: '🔬' },
            'História': { chave: 'ch', cor: '#f59e0b', bg: 'rgba(245,158,11,0.05)', label: 'História', icon: '📜' },
            'Geografia': { chave: 'ch', cor: '#f59e0b', bg: 'rgba(245,158,11,0.05)', label: 'Geografia', icon: '🗺️' },
            'Inglês': { chave: 'portugues', cor: '#3b82f6', bg: 'rgba(59,130,246,0.05)', label: 'Inglês', icon: '🇬🇧' }
        };
        const infoDisciplina = disciplinaMap[disciplinaSelecionada] || disciplinaMap['Português'];
        tipoAvaliacao = infoDisciplina.chave;
        corDisciplina = infoDisciplina.cor;
        bgDisciplina = infoDisciplina.bg;
        const labelDisciplina = infoDisciplina.label;
        iconDisciplina = infoDisciplina.icon;

        let alunosDaTurma = [];
        let totalAlunos = 0;
        if (turmaId) {
            try {
                const alunosData = await carregarAlunosComCache({ turma_id: turmaId });
                if (alunosData && !alunosData.erro && Array.isArray(alunosData)) {
                    alunosDaTurma = alunosData; totalAlunos = alunosData.length;
                }
            } catch (e) { console.warn(e); }
        }

        let url = API_URL + '/api/historico/agrupado';
        const params = new URLSearchParams();
        if (escolaId && escolaId !== '') params.append('escola', escolaId);
        if (serie && serie !== '') params.append('serie', serie);
        if (turmaId && turmaId !== '') params.append('turma', turmaId);
        if (provaId && provaId !== '') params.append('prova', provaId);
        if (params.toString()) url += '?' + params.toString();

        const response = await fetch(url);
        const dadosAgrupados = await response.json();

        const alunosComCorrecao = [];
        const alunosSemCorrecao = [];

        if (dadosAgrupados && !dadosAgrupados.erro && Array.isArray(dadosAgrupados)) {
            dadosAgrupados.forEach(aluno => {
                const discData = aluno[tipoAvaliacao];
                if (discData && typeof discData === 'object') {
                    const acertos = discData.acertos || 0;
                    const total = discData.total || 20;
                    const erros = total - acertos;
                    const pct = total > 0 ? Math.round((acertos / total) * 100) : 0;
                    const conceito = calcularConceito(pct);
                    alunosComCorrecao.push({
                        ...aluno,
                        disciplinaData: { acertos, erros, total, porcentagem: pct, conceito, nota: discData.nota || 0 }
                    });
                }
            });
        }

        if (totalAlunos > 0) {
            const idsComCorrecao = new Set(alunosComCorrecao.map(a => a.aluno_id));
            alunosDaTurma.forEach(aluno => {
                if (!idsComCorrecao.has(aluno.id)) {
                    alunosSemCorrecao.push({
                        aluno_id: aluno.id, aluno_nome: aluno.nome,
                        serie: aluno.turma_serie || serie, turma: aluno.turma_nome || '',
                        escola: aluno.escola_nome || '',
                        disciplinaData: { acertos: 0, erros: 0, total: 20, porcentagem: 0, conceito: calcularConceito(0), nota: 0 }
                    });
                }
            });
        }

        const totalComCorrecao = alunosComCorrecao.length;
        document.getElementById('rel-total-alunos-conceitos').textContent = totalComCorrecao + ' alunos';
        document.getElementById('rel-total-alunos-tabela').textContent = totalComCorrecao + ' alunos';

        let somaPorcentagem = 0, totalAcertos = 0, totalErros = 0;
        alunosComCorrecao.forEach(aluno => {
            const d = aluno.disciplinaData;
            somaPorcentagem += d.porcentagem;
            totalAcertos += d.acertos; totalErros += d.erros;
        });
        const media = totalComCorrecao > 0 ? Math.round(somaPorcentagem / totalComCorrecao) : 0;
        const conceitoGeral = calcularConceito(media);

        document.getElementById('rel-media').textContent = media + '%';
        document.getElementById('rel-disciplina-nome-card').textContent = `Disciplina: ${disciplinaSelecionada}`;
        document.getElementById('rel-total-correcoes').textContent = totalComCorrecao + ' correções';
        document.getElementById('rel-disciplina-nome').textContent = disciplinaSelecionada;

        const conceitoGeralEl = document.getElementById('rel-conceito-geral');
        if (conceitoGeralEl) {
            const labels = { 'inicial': '🔴 Inicial', 'basico': '🟠 Básico', 'proficiente': '🔵 Proficiente', 'avancado': '🟢 Avançado' };
            const badgeClasses = {
                'inicial': 'badge-conceito-inicial', 'basico': 'badge-conceito-basico',
                'proficiente': 'badge-conceito-proficiente', 'avancado': 'badge-conceito-avancado'
            };
            conceitoGeralEl.textContent = labels[conceitoGeral] || '—';
            conceitoGeralEl.className = `badge ${badgeClasses[conceitoGeral] || 'badge-gray'}`;
        }

        const contagemConceitos = { inicial: 0, basico: 0, proficiente: 0, avancado: 0 };
        alunosComCorrecao.forEach(aluno => {
            const conceito = aluno.disciplinaData.conceito;
            if (contagemConceitos[conceito] !== undefined) contagemConceitos[conceito]++;
        });
        const totalConceitos = alunosComCorrecao.length || 1;
        ['inicial', 'basico', 'proficiente', 'avancado'].forEach(conceito => {
            const count = contagemConceitos[conceito] || 0;
            let pct = (count / totalConceitos) * 100;
            pct = Math.max(pct, 2);
            document.getElementById(`rel-conceito-${conceito}-count`).textContent = count;
            const bar = document.getElementById(`rel-conceito-${conceito}-bar`);
            if (bar) bar.style.width = pct + '%';
        });

        const table = document.querySelector('#tb-rel-alunos')?.closest('table');
        const thead = table?.querySelector('thead');
        if (thead) {
            thead.innerHTML = `
                <tr>
                    <th>POS.</th>
                    <th>Nº</th>
                    <th>NOME</th>
                    <th>SÉRIE</th>
                    <th colspan="3" style="background:${bgDisciplina};border-bottom:2px solid ${corDisciplina};font-size:10px;color:${corDisciplina};">
                        ${iconDisciplina} ${labelDisciplina.toUpperCase()}
                    </th>
                    <th style="background:${bgDisciplina};border-bottom:2px solid ${corDisciplina};font-size:8px;">ESCOLA</th>
                    <th style="background:${bgDisciplina};border-bottom:2px solid ${corDisciplina};font-size:8px;">TURMA</th>
                </tr>
                <tr>
                    <th style="font-size:7px;"></th>
                    <th style="font-size:7px;"></th>
                    <th style="font-size:7px;"></th>
                    <th style="font-size:7px;"></th>
                    <th style="background:${bgDisciplina};font-size:7px;color:${corDisciplina};">ACERTOS</th>
                    <th style="background:${bgDisciplina};font-size:7px;color:${corDisciplina};">ERROS</th>
                    <th style="background:${bgDisciplina};font-size:7px;color:${corDisciplina};">CONCEITO</th>
                    <th style="font-size:7px;"></th>
                    <th style="font-size:7px;"></th>
                </tr>
            `;
        }

        const tbody = document.getElementById('tb-rel-alunos');
        if (!tbody) return;
        const todosAlunos = [...alunosComCorrecao, ...alunosSemCorrecao];

        if (todosAlunos.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:30px;color:var(--text3);">Nenhum aluno encontrado com os filtros selecionados.</td></tr>`;
            document.getElementById('rel-total-alunos-tabela').textContent = '0 alunos';
            return;
        }

        todosAlunos.sort((a, b) => (b.disciplinaData.porcentagem || 0) - (a.disciplinaData.porcentagem || 0));

        const badgeConceitoFn = c => ({
            'inicial': 'badge-conceito-inicial-sm', 'basico': 'badge-conceito-basico-sm',
            'proficiente': 'badge-conceito-proficiente-sm', 'avancado': 'badge-conceito-avancado-sm'
        }[c] || 'badge-gray');

        tbody.innerHTML = todosAlunos.map((aluno, index) => {
            const d = aluno.disciplinaData;
            let medalha = '';
            if (index === 0) medalha = '🥇';
            else if (index === 1) medalha = '🥈';
            else if (index === 2) medalha = '🥉';
            else medalha = (index + 1);
            const conceitoBadge = `<span class="badge ${badgeConceitoFn(d.conceito)}">${d.conceito}</span>`;
            return `<tr>
                <td style="font-size:14px;">${medalha}</td>
                <td>${index + 1}</td>
                <td style="text-align:left;font-weight:600;">${escapeHtml(aluno.aluno_nome || 'Aluno')}</td>
                <td><span class="badge badge-purple" style="font-size:9px;">${escapeHtml(aluno.serie || '—')}</span></td>
                ${tipoAvaliacao === 'producao' ?
                    `<td style="text-align:center;background:${bgDisciplina};padding:4px;">
                        <div style="font-size:9px;font-weight:700;color:var(--text3);">NOTA</div>
                        <div style="font-size:16px;font-weight:900;color:var(--purple);">${d.total > 0 && d.nota !== undefined && d.nota !== null ? Number(d.nota).toFixed(1) : '—'}</div>
                    </td>` :
                    `<td style="text-align:center;background:${bgDisciplina};font-weight:700;color:var(--green);">${d.acertos}</td>
                    <td style="text-align:center;background:${bgDisciplina};font-weight:700;color:var(--red);">${d.erros}</td>
                    <td style="text-align:center;background:${bgDisciplina};">${conceitoBadge}</td>`
                }
                <td style="font-size:9px;color:var(--text2);">${escapeHtml(aluno.escola || '—')}</td>
                <td style="font-size:9px;color:var(--text2);">${escapeHtml(aluno.turma || '—')}</td>
            </tr>`;
        }).join('');

        atualizarGraficoAcertosPorQuestao(dadosAgrupados, disciplinaSelecionada, tipoAvaliacao);
        document.getElementById('rel-disc-acertos').textContent = totalAcertos;
        document.getElementById('rel-disc-erros').textContent = totalErros;
        document.getElementById('rel-disc-media').textContent = totalComCorrecao > 0 ? (totalAcertos / totalComCorrecao).toFixed(1) : '0.0';
        document.getElementById('rel-disc-conceito').textContent = conceitoGeral || '—';
    } catch (erro) {
        console.error(erro);
        showToast('❌ Erro ao carregar relatório: ' + erro.message, 'error');
    }
}

function limparFiltrosRelTurma() {
    document.getElementById('rel-turma-escola').value = '';
    document.getElementById('rel-turma-serie').value = '';
    document.getElementById('rel-turma-prova').value = '';
    const selectTurma = document.getElementById('rel-turma-turma');
    selectTurma.innerHTML = '<option value="">Todas as turmas</option>';
    carregarTurmasComCache().then(turmas => {
        if (turmas && !turmas.erro) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                opt.dataset.serie = t.serie || '';
                selectTurma.appendChild(opt);
            });
            carregarRelatorioTurmaFiltrado();
        }
    }).catch(e => console.error(e));
    const selectProva = document.getElementById('rel-turma-prova');
    carregarProvasComCache(true).then(provas => {
        if (provas && !provas.erro) {
            selectProva.innerHTML = '<option value="">Todas as provas</option>';
            provas.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.titulo + ' - ' + (p.serie || '') + ' - ' + (p.disciplina || '');
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
            carregarRelatorioTurmaFiltrado();
        }
    }).catch(e => console.error(e));
}

function atualizarGraficoAcertosPorQuestao(dadosAgrupados, disciplinaSelecionada, tipoAvaliacao) {
    try {
        const container = document.getElementById('rel-acertos-grid');
        const totalQuestoesEl = document.getElementById('rel-total-questoes');
        const disciplinaTitulo = document.getElementById('rel-acertos-disciplina');
        const totalAcertosEl = document.getElementById('rel-total-acertos-disciplina');
        const totalErrosEl = document.getElementById('rel-total-erros-disciplina');
        const mediaEl = document.getElementById('rel-media-disciplina');
        if (disciplinaTitulo) disciplinaTitulo.textContent = disciplinaSelecionada;

        if (!dadosAgrupados || dadosAgrupados.erro || !Array.isArray(dadosAgrupados) || dadosAgrupados.length === 0) {
            container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--text3);">Nenhum dado disponível para esta disciplina.</div>`;
            totalQuestoesEl.textContent = '0 questões';
            totalAcertosEl.textContent = '0'; totalErrosEl.textContent = '0'; mediaEl.textContent = '0%';
            return;
        }

        const questoesMap = new Map();
        let totalAcertos = 0, totalErros = 0, totalAlunos = 0;
        const bnccMap = new Map();

        dadosAgrupados.forEach(aluno => {
            const discData = aluno[tipoAvaliacao];
            if (!discData || typeof discData !== 'object') return;
            const questoesStatus = discData.questoes_status || [];
            const bnccList = discData.bncc || [];
            totalAlunos++;

            if (Array.isArray(questoesStatus) && questoesStatus.length > 0) {
                questoesStatus.forEach((q, idx) => {
                    const num = q.numero || q.questao || (idx + 1);
                    if (!questoesMap.has(num)) questoesMap.set(num, { acertos: 0, erros: 0 });
                    const data = questoesMap.get(num);
                    if (!bnccMap.has(num)) bnccMap.set(num, q.bncc || q.codigo_bncc || (bnccList[idx] || 'N/A'));
                    const resp = q.resposta || '', gab = q.gabarito || '';
                    const isRespondida = resp && resp !== '' && resp !== '—' && resp !== '-';
                    const isCorreta = isRespondida && resp.toUpperCase() === gab.toUpperCase();
                    if (isCorreta || q.acertou === true || q.correta === true) { data.acertos++; totalAcertos++; }
                    else { data.erros++; totalErros++; }
                });
            } else {
                const respostas = discData.respostas || [];
                const gabarito = discData.gabarito || [];
                const total = discData.total || 20;
                for (let i = 0; i < Math.min(respostas.length, gabarito.length, total); i++) {
                    const num = i + 1;
                    if (!questoesMap.has(num)) questoesMap.set(num, { acertos: 0, erros: 0 });
                    const data = questoesMap.get(num);
                    if (!bnccMap.has(num)) bnccMap.set(num, (bnccList[i] || 'N/A'));
                    const resp = String(respostas[i] || '').trim().toUpperCase();
                    const gab = String(gabarito[i] || '').trim().toUpperCase();
                    const isValida = resp && resp !== '' && resp !== '—' && resp !== '-';
                    const isCorreta = isValida && resp === gab && gab !== '';
                    if (isCorreta) { data.acertos++; totalAcertos++; }
                    else { data.erros++; totalErros++; }
                }
            }
        });

        const totalQuestoes = questoesMap.size || 20;
        totalQuestoesEl.textContent = totalQuestoes + ' questões';
        totalAcertosEl.textContent = totalAcertos;
        totalErrosEl.textContent = totalErros;
        const media = totalAlunos > 0 && totalQuestoes > 0 ? Math.round((totalAcertos / (totalAlunos * totalQuestoes)) * 100) : 0;
        mediaEl.textContent = media + '%';

        container.innerHTML = '';
        const sortedKeys = Array.from(questoesMap.keys()).sort((a, b) => a - b);
        if (sortedKeys.length === 0) {
            container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--text3);">Nenhum dado disponível.</div>`;
            return;
        }

        sortedKeys.forEach(num => {
            const data = questoesMap.get(num);
            const total = data.acertos + data.erros;
            const bnccCode = bnccMap.get(num) || 'N/A';
            const pctAcertos = total > 0 ? Math.round((data.acertos / total) * 100) : 0;
            const pctErros = total > 0 ? Math.round((data.erros / total) * 100) : 0;
            const div = document.createElement('div');
            div.className = 'acertos-por-questao-item';
            div.style.cssText = 'background:var(--surface);border-radius:10px;padding:12px 10px;border:1px solid var(--border);text-align:center;';
            let corBarra = '#ef4444';
            if (pctAcertos >= 80) corBarra = '#10b981';
            else if (pctAcertos >= 60) corBarra = '#f59e0b';
            else if (pctAcertos >= 40) corBarra = '#f59e0b';
            div.innerHTML = `
                <div style="font-size:14px;font-weight:800;color:var(--text1);margin-bottom:4px;">Q${num}</div>
                <div style="display:flex;justify-content:center;align-items:center;gap:4px;font-size:16px;font-weight:700;margin:4px 0;">
                    <span style="color:var(--green);">${data.acertos}</span>
                    <span style="color:var(--text3);font-weight:300;">/</span>
                    <span style="color:var(--red);">${data.erros}</span>
                </div>
                <div style="font-size:9px;color:var(--text3);font-weight:600;margin-bottom:4px;">Acertos / Erros</div>
                <div style="font-size:11px;font-weight:700;color:#8b5cf6;background:rgba(139,92,246,0.12);padding:3px 12px;border-radius:8px;display:inline-block;margin-bottom:4px;font-family:'Courier New',monospace;">${escapeHtml(bnccCode)}</div>
                <div class="progress" style="height:8px;background:var(--bg2);border-radius:6px;overflow:hidden;margin:6px 0;">
                    <div class="progress-fill" style="width:${Math.max(pctAcertos, 2)}%;background:${corBarra};border-radius:6px;"></div>
                </div>
                <div style="display:flex;justify-content:center;gap:10px;font-size:11px;font-weight:700;">
                    <span style="color:var(--green);">${pctAcertos}%</span>
                    <span style="color:var(--text3);font-weight:300;">|</span>
                    <span style="color:var(--red);">${pctErros}%</span>
                </div>
            `;
            container.appendChild(div);
        });
    } catch (erro) { console.error(erro); }
}

// ============================================
// CARREGAMENTO INICIAL
// ============================================
async function carregarDados() {
    try {
        await Promise.all([
            carregarEscolas(),
            carregarTurmas(),
            carregarAlunos(),
            carregarProvas(),
            carregarDashboard()
        ]);
        atualizarDatasImpressao();
        setTimeout(() => carregarDadosSecundarios(), 300);
    } catch (erro) {
        console.error('Erro ao carregar dados essenciais:', erro);
        showToast('⚠️ Erro ao carregar dados essenciais. Recarregue a página.', 'error');
    }
}

async function carregarDadosSecundarios() {
    try {
        await Promise.all([
            carregarGabaritos(),
            carregarUltimasCorrecoes(),
            carregarUsuarios(),
            carregarCombos()
        ]);
        await Promise.all([
            carregarEscolasFiltroAlunos(),
            carregarEscolasCorrigir(),
            carregarEscolasTexto(),
            carregarEscolasParaCorrecaoManual(),
            carregarFiltrosRelTurma(),
            carregarFiltroEscolaTurmas()
        ]);
    } catch (erro) { console.warn('Erro ao carregar dados secundários:', erro); }
}

// ============================================
// IMPRESSÃO DE ALUNOS
// ============================================
function imprimirAlunos() {
    const tbody = document.getElementById('tb-alunos');
    const rows = tbody.querySelectorAll('tr');
    if (rows.length === 0 || (rows.length === 1 && rows[0].textContent.includes('Nenhum aluno'))) {
        showToast('⚠️ Nenhum aluno para imprimir.', 'error');
        return;
    }
    const escolaSelect = document.getElementById('filtro-escola-alunos');
    const turmaSelect = document.getElementById('filtro-turma-alunos');
    const serieSelect = document.getElementById('filtro-serie-alunos');
    const escolaNome = escolaSelect.options[escolaSelect.selectedIndex]?.text || 'Todas';
    const turmaNome = turmaSelect.options[turmaSelect.selectedIndex]?.text || 'Todas';
    const serieNome = serieSelect.options[serieSelect.selectedIndex]?.text || 'Todas';

    let html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Lista de Alunos</title><style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 30px; background: #fff; }
        h1 { text-align: center; font-size: 24px; margin-bottom: 8px; }
        .filtros { text-align: center; color: #555; margin-bottom: 20px; font-size: 14px; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th, td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; }
        th { background: #f2f2f2; font-weight: 700; }
        tr:nth-child(even) { background: #fafafa; }
        .footer { text-align: center; margin-top: 20px; color: #999; font-size: 12px; }
    </style></head><body>
        <h1>📋 Lista de Alunos</h1>
        <div class="filtros"><strong>Escola:</strong> ${escapeHtml(escolaNome)} &nbsp;|&nbsp; <strong>Turma:</strong> ${escapeHtml(turmaNome)} &nbsp;|&nbsp; <strong>Série:</strong> ${escapeHtml(serieNome)}</div>
        <table><thead><tr><th>Nº</th><th>Matrícula</th><th>Nome Completo</th><th>Série</th><th>Turma</th><th>Escola</th><th>Data Nasc.</th></tr></thead><tbody>`;

    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
            html += `<tr>
                <td>${escapeHtml(cells[0].textContent.trim())}</td>
                <td>${escapeHtml(cells[1].textContent.trim())}</td>
                <td>${escapeHtml(cells[2].textContent.trim())}</td>
                <td>${escapeHtml(cells[3].textContent.trim())}</td>
                <td>${escapeHtml(cells[4].textContent.trim())}</td>
                <td>${escapeHtml(cells[5].textContent.trim())}</td>
                <td>${escapeHtml(cells[6].textContent.trim())}</td>
            </tr>`;
        }
    });
    html += `</tbody></table><div class="footer">Gerado em ${new Date().toLocaleString('pt-BR')}</div></body></html>`;
    const win = window.open('', '_blank');
    if (!win) { showToast('⚠️ Permita pop-ups para imprimir.', 'error'); return; }
    win.document.write(html);
    win.document.close();
    win.focus();
    win.print();
}

// ============================================
// EXPORTAR RELATÓRIO PDF (Rel. por Turma)
// ============================================
function exportarRelatorioPDF() {
    const tbody = document.getElementById('tb-rel-alunos');
    if (!tbody) { showToast('❌ Nenhum dado para exportar!', 'error'); return; }
    const rows = tbody.querySelectorAll('tr');
    if (rows.length === 0 || (rows.length === 1 && rows[0].textContent.includes('Nenhum aluno'))) {
        showToast('⚠️ Nenhum dado disponível para gerar o PDF.', 'error');
        return;
    }
    showToast('📄 Gerando PDF...', 'info');

    const escolaSelect = document.getElementById('rel-turma-escola');
    const serieSelect = document.getElementById('rel-turma-serie');
    const turmaSelect = document.getElementById('rel-turma-turma');
    const provaSelect = document.getElementById('rel-turma-prova');
    const escolaNome = escolaSelect?.options[escolaSelect.selectedIndex]?.text || 'Não informado';
    const serieNome = serieSelect?.options[serieSelect.selectedIndex]?.text || 'Não informado';
    const turmaNome = turmaSelect?.options[turmaSelect.selectedIndex]?.text || 'Não informado';
    let disciplinaNome = 'Português';
    const provaOption = provaSelect?.options[provaSelect.selectedIndex];
    if (provaOption && provaOption.dataset.disciplina) disciplinaNome = provaOption.dataset.disciplina;
    const media = document.getElementById('rel-media')?.textContent || '0%';
    const conceito = document.getElementById('rel-conceito-geral')?.textContent || '—';

    const alunosData = [];
    let totalAcertosGeral = 0, totalErrosGeral = 0;
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 9) {
            const acertos = parseInt(cells[4]?.textContent.trim() || '0') || 0;
            const erros = parseInt(cells[5]?.textContent.trim() || '0') || 0;
            totalAcertosGeral += acertos;
            totalErrosGeral += erros;
            alunosData.push({
                posicao: cells[0]?.textContent.trim() || '',
                numero: cells[1]?.textContent.trim() || '',
                nome: cells[2]?.textContent.trim() || '',
                serie: cells[3]?.textContent.trim() || '',
                acertos, erros,
                conceito: cells[6]?.textContent.trim() || '',
                escola: cells[7]?.textContent.trim() || '',
                turma: cells[8]?.textContent.trim() || ''
            });
        }
    });
    const totalAlunos = alunosData.length;

    const acertosPorQuestao = [];
    const acertosGrid = document.getElementById('rel-acertos-grid');
    if (acertosGrid) {
        const items = acertosGrid.querySelectorAll('.acertos-por-questao-item');
        items.forEach(item => {
            let qNum = '';
            const texto = item.textContent || '';
            const match = texto.match(/Q(\d+)/);
            if (match) qNum = 'Q' + match[1];
            let acertos = '0', erros = '0';
            const matchNum = texto.match(/(\d+)\s*\/\s*(\d+)/);
            if (matchNum) { acertos = matchNum[1] || '0'; erros = matchNum[2] || '0'; }
            let bncc = 'N/A';
            const matchBncc = texto.match(/(EF\d+[A-Z]+\d+)/);
            if (matchBncc) bncc = matchBncc[1];
            if (qNum) acertosPorQuestao.push({ numero: qNum, acertos, erros, total: parseInt(acertos) + parseInt(erros), bncc });
        });
    }

    const dataAtual = new Date().toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

    let html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Relatório por Turma - ${escapeHtml(disciplinaNome)}</title><style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #fff; padding: 20px; color: #1e293b; }
        .header { border-bottom: 3px solid #1e293b; padding-bottom: 16px; margin-bottom: 20px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
        .header-left .prefeitura { font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; }
        .header-left .secretaria { font-size: 13px; font-weight: 800; color: #1e293b; }
        .header-left .departamento { font-size: 10px; color: #475569; font-weight: 600; }
        .header-left .sisam { font-size: 14px; font-weight: 900; color: #2563eb; }
        .header-right { text-align: right; }
        .header-right .titulo { font-size: 18px; font-weight: 800; }
        .header-right .subtitulo { font-size: 11px; color: #475569; font-weight: 600; }
        .info-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px 16px; background: #f8fafc; padding: 12px 20px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 16px; }
        .info-grid .item .label { font-size: 8px; font-weight: 700; color: #94a3b8; text-transform: uppercase; }
        .info-grid .item .value { font-size: 12px; font-weight: 700; color: #0f172a; }
        .section-title { font-size: 14px; font-weight: 800; margin: 16px 0 10px; }
        .questoes-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 12px; }
        .questao-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; text-align: center; }
        .questao-card .q-num { font-size: 13px; font-weight: 800; background: #e2e8f0; display: inline-block; padding: 0 12px; border-radius: 8px; }
        .questao-card .q-result { font-size: 15px; font-weight: 700; margin: 4px 0; }
        .questao-card .acertos { color: #10b981; } .questao-card .erros { color: #ef4444; }
        .questao-card .q-bncc { font-size: 10px; font-weight: 700; color: #8b5cf6; background: #f5f3ff; padding: 3px 12px; border-radius: 8px; display: inline-block; }
        .resumo-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0 16px; }
        .resumo-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; text-align: center; }
        .resumo-card .valor { font-size: 24px; font-weight: 900; }
        .resumo-card .valor.green { color: #10b981; } .resumo-card .valor.red { color: #ef4444; }
        .resumo-card .valor.blue { color: #3b82f6; } .resumo-card .valor.purple { color: #8b5cf6; }
        .resumo-card .label { font-size: 9px; color: #94a3b8; font-weight: 600; text-transform: uppercase; }
        .table-wrap { overflow-x: auto; margin: 12px 0; border: 1px solid #e2e8f0; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; font-size: 10px; }
        thead { background: #f1f5f9; }
        th { padding: 8px 6px; font-weight: 700; color: #475569; border-bottom: 2px solid #e2e8f0; font-size: 8px; text-transform: uppercase; }
        td { padding: 6px 4px; border-bottom: 1px solid #f1f5f9; text-align: center; font-size: 9px; }
        tr:nth-child(even) td { background: #fafbfc; }
        .nome-aluno { font-weight: 600; text-align: left; padding-left: 8px; }
        .badge-conceito { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 8px; font-weight: 700; text-transform: uppercase; }
        .badge-inicial { background: #fef2f2; color: #ef4444; } .badge-basico { background: #fffbeb; color: #f59e0b; }
        .badge-proficiente { background: #eff6ff; color: #3b82f6; } .badge-avancado { background: #ecfdf5; color: #10b981; }
        .assinaturas { display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center; }
        .assinatura-item .linha { width: 180px; border-bottom: 1.5px solid #1e293b; margin-bottom: 4px; }
        .assinatura-item .cargo { font-size: 9px; color: #64748b; font-weight: 600; }
        .footer { margin-top: 20px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 8px; color: #94a3b8; }
        @media print { body { padding: 10px; } @page { size: A4 landscape; margin: 8mm 6mm; } }
    </style></head><body>
        <div class="header">
            <div class="header-left">
                <div class="prefeitura">PREFEITURA MUNICIPAL DE</div>
                <div class="secretaria">SÃO SEBASTIÃO DA BOA VISTA</div>
                <div class="departamento">SECRETARIA MUNICIPAL DE EDUCAÇÃO — DGP</div>
                <div class="sisam">SISAM 2026</div>
            </div>
            <div class="header-right">
                <div class="titulo">📊 RELATÓRIO POR TURMA</div>
                <div class="subtitulo">Desempenho dos alunos - ${escapeHtml(disciplinaNome)}</div>
            </div>
        </div>
        <div class="info-grid">
            <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escolaNome)}</span></div>
            <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${escapeHtml(serieNome)}</span></div>
            <div class="item"><span class="label">📖 DISCIPLINA</span><span class="value">${escapeHtml(disciplinaNome)}</span></div>
            <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml(turmaNome)}</span></div>
            <div class="item"><span class="label">📅 DATA</span><span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
            <div class="item"><span class="label">📊 BIMESTRE</span><span class="value">1º e 2º bimestre</span></div>
        </div>
        <div class="section-title">📊 Acertos por Questão — ${escapeHtml(disciplinaNome)}</div>
        <div class="questoes-grid">
            ${acertosPorQuestao.length > 0 ? acertosPorQuestao.map(q => `
                <div class="questao-card">
                    <div class="q-num">${escapeHtml(q.numero)}</div>
                    <div class="q-result"><span class="acertos">${escapeHtml(q.acertos)}</span> / <span class="erros">${escapeHtml(q.erros)}</span></div>
                    <div class="q-bncc">${escapeHtml(q.bncc)}</div>
                </div>`).join('') : '<div style="grid-column:1/-1;text-align:center;padding:20px;color:#94a3b8;">Nenhum dado disponível.</div>'}
        </div>
        <div class="resumo-grid">
            <div class="resumo-card"><div class="valor green">${totalAcertosGeral}</div><div class="label">✅ Total de Acertos</div></div>
            <div class="resumo-card"><div class="valor red">${totalErrosGeral}</div><div class="label">❌ Total de Erros</div></div>
            <div class="resumo-card"><div class="valor blue">${escapeHtml(media)}</div><div class="label">📊 Média da Turma</div></div>
            <div class="resumo-card"><div class="valor purple">${escapeHtml(conceito)}</div><div class="label">📊 Conceito</div></div>
        </div>
        <div class="section-title">📋 Lista de Alunos (${totalAlunos} alunos)</div>
        <div class="table-wrap"><table>
            <thead><tr><th>POS.</th><th>Nº</th><th style="text-align:left;">NOME</th><th>SÉRIE</th><th>ACERTOS</th><th>ERROS</th><th>CONCEITO</th><th>ESCOLA</th><th>TURMA</th></tr></thead>
            <tbody>
                ${alunosData.map(a => {
                    const conceitoClass = a.conceito ? `badge-${a.conceito.toLowerCase()}` : 'badge-inicial';
                    return `<tr>
                        <td>${escapeHtml(a.posicao)}</td><td>${escapeHtml(a.numero)}</td>
                        <td class="nome-aluno">${escapeHtml(a.nome)}</td><td>${escapeHtml(a.serie)}</td>
                        <td style="color:#10b981;font-weight:700;">${a.acertos}</td>
                        <td style="color:#ef4444;font-weight:700;">${a.erros}</td>
                        <td><span class="badge-conceito ${conceitoClass}">${escapeHtml(a.conceito || '—')}</span></td>
                        <td>${escapeHtml(a.escola)}</td><td>${escapeHtml(a.turma)}</td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table></div>
        <div class="assinaturas">
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Professor(a) Responsável</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Diretor(a)</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Secretaria Municipal de Educação</div></div>
        </div>
        <div class="footer"><span>📄 Documento gerado pelo sistema <strong>CorrigePro</strong></span><span>${dataAtual}</span></div>
    </body></html>`;

    const win = window.open('', '_blank');
    if (!win) { showToast('⚠️ Permita pop-ups para gerar o PDF.', 'error'); return; }
    win.document.write(html);
    win.document.close();
    win.onload = function() { setTimeout(() => { win.focus(); win.print(); }, 500); };
    showToast('📄 PDF gerado com sucesso!', 'success');
}

// ============================================
// GABARITO
// ============================================
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

    if (ptsRow) ptsRow.style.display = isProducao ? 'none' : 'grid';

    if (headerContainer) {
        headerContainer.innerHTML = `
            <div class="gab-header-title">
                <span class="icon">📝</span>
                <span>Gabarito: <span class="prova-nome">${escapeHtml(provaNome)}</span></span>
                <span class="badge-disciplina">${escapeHtml(disciplina || 'Disciplina')}</span>
            </div>
        `;
    }

    if (infoAlts) {
        infoAlts.innerHTML = isProducao ?
            '<div style="padding:8px 14px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;font-size:12px;font-weight:700;color:var(--orange);">📝 PRODUÇÃO DE TEXTO — Título + Cabeçalho + Alternativas A/B/C</div>' :
            '<div style="padding:8px 14px;background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.3);border-radius:8px;font-size:12px;font-weight:700;color:#a78bfa;">📝 Gabarito com 4 alternativas: A, B, C, D</div>';
    }

    const total = parseInt(totalEl.value) || 20;

    if (isProducao) {
        grid.style.cssText = 'display:flex;flex-direction:column;gap:16px;';
        grid.innerHTML = '';
        if (!gabProducaoData.questoes || gabProducaoData.questoes.length === 0) {
            gabProducaoData.questoes = [];
            for (let i = 0; i < total; i++) {
                gabProducaoData.questoes.push({ titulo: `Q${i + 1}`, cabecalho: '', alternativas: { A: '', B: '', C: '' }, situacao: '' });
            }
        } else {
            while (gabProducaoData.questoes.length < total) {
                const idx = gabProducaoData.questoes.length + 1;
                gabProducaoData.questoes.push({ titulo: `Q${idx}`, cabecalho: '', alternativas: { A: '', B: '', C: '' }, situacao: '' });
            }
            if (gabProducaoData.questoes.length > total) gabProducaoData.questoes = gabProducaoData.questoes.slice(0, total);
        }
        for (let i = 0; i < total; i++) {
            const q = gabProducaoData.questoes[i];
            const card = document.createElement('div');
            card.className = 'gab-producao-questao';
            card.dataset.index = i;
            card.innerHTML = `
                <div class="gab-producao-header">
                    <input class="gab-titulo-editavel" type="text" value="${escapeAttr(q.titulo || 'Q' + (i+1))}" data-index="${i}" onchange="atualizarTituloProducao(this)" placeholder="Ex: Q1 / Tema 1">
                    <textarea class="gab-cabecalho" data-index="${i}" onchange="atualizarCabecalhoProducao(this)" placeholder="Escreva o cabeçalho/tema da questão aqui...">${escapeHtml(q.cabecalho || '')}</textarea>
                </div>
                <div class="gab-alternativas-lista" id="gab-alts-${i}"></div>
            `;
            grid.appendChild(card);
            renderizarAlternativasProducao(i, document.getElementById(`gab-alts-${i}`));
        }
        return;
    }

    const alts = ['A', 'B', 'C', 'D'];
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill, minmax(120px, 1fr));gap:14px;';
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

function renderizarAlternativasProducao(index, container) {
    const q = gabProducaoData.questoes[index];
    if (!q || !container) return;
    const altsOrdenadas = Object.keys(q.alternativas).sort();
    container.innerHTML = '';
    altsOrdenadas.forEach(letra => {
        const item = document.createElement('div');
        item.className = 'gab-alternativa-item';
        item.innerHTML = `
            <div class="alt-letra">${escapeHtml(letra)}</div>
            <textarea class="alt-texto" placeholder="Digite a resposta esperada para ${escapeHtml(letra)}..." data-index="${index}" data-letra="${letra}" onchange="atualizarAlternativaProducao(this)">${escapeHtml(q.alternativas[letra] || '')}</textarea>
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
    if (gabProducaoData.questoes[idx]) gabProducaoData.questoes[idx].titulo = input.value;
}

function atualizarCabecalhoProducao(textarea) {
    const idx = parseInt(textarea.dataset.index);
    if (gabProducaoData.questoes[idx]) gabProducaoData.questoes[idx].cabecalho = textarea.value;
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
    if (gabProducaoData.questoes[idx]) gabProducaoData.questoes[idx].situacao = select.value;
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
    if (Object.keys(q.alternativas).length <= 1) { showToast('⚠️ Deve haver pelo menos uma alternativa!', 'warning'); return; }
    delete q.alternativas[letra];
    const container = document.getElementById(`gab-alts-${index}`);
    if (container) renderizarAlternativasProducao(index, container);
}

function fillGabRand() {
    const provaSelect = document.getElementById('gab-prova');
    const selectedOption = provaSelect.options[provaSelect.selectedIndex];
    const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
    if (disciplina === 'Produção de Texto') { showToast('🎲 Preenchimento automático não disponível para produção de texto.', 'warning'); return; }
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
        gabProducaoData.questoes.forEach(q => {
            q.cabecalho = ''; q.situacao = '';
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
            if (total === 0) { showToast('⚠️ Nenhuma questão para salvar!', 'error'); return; }
            const textos_questoes = gabProducaoData.questoes.map(q => ({
                titulo: q.titulo || '', cabecalho: q.cabecalho || '', alternativas: q.alternativas || {}
            }));
            const respostas = gabProducaoData.questoes.map(q => {
                const alts = q.alternativas || {};
                return Object.keys(alts).sort().map(k => `${k}) ${alts[k] || ''}`).join('\n');
            });
            const niveis = gabProducaoData.questoes.map(q => q.situacao || '');
            const bncc = gabProducaoData.questoes.map(() => '');
            showToast('💾 Salvando gabarito de Produção...', 'info');
            const response = await fetch(`${API_URL}/api/gabaritos`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prova_id: parseInt(provaId), respostas, bncc, textos_questoes, niveis })
            });
            const result = await response.json();
            if (response.ok && result.id) {
                showToast(`✅ ${result.mensagem || 'Gabarito salvo!'}`, 'success');
                limparCache(); carregarGabaritos(); carregarCombos(); carregarProvas();
            } else showToast(`❌ ${result.erro || 'Erro desconhecido'}`, 'error');
            return;
        }

        const respostas = [], bncc = [];
        const selects = document.querySelectorAll('.gab-select');
        const bnccInputs = document.querySelectorAll('.gab-bncc');
        selects.forEach((s, idx) => {
            respostas.push(s.value || '');
            if (bnccInputs[idx]) bncc.push(bnccInputs[idx].value.trim() || '');
        });
        if (respostas.filter(r => r !== '').length === 0) { showToast('⚠️ Preencha pelo menos uma questão do gabarito!', 'error'); return; }

        showToast('💾 Salvando gabarito...', 'info');
        const response = await fetch(`${API_URL}/api/gabaritos`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prova_id: parseInt(provaId), respostas, bncc })
        });
        const result = await response.json();
        if (response.ok && result.id) {
            showToast(`✅ ${result.mensagem || 'Gabarito salvo com sucesso!'}`, 'success');
            limparCache(); carregarGabaritos(); carregarCombos(); carregarProvas();
        } else showToast(`❌ ${result.erro || 'Erro desconhecido'}`, 'error');
    } catch (erro) { showToast('❌ Erro ao salvar gabarito: ' + erro.message, 'error'); console.error(erro); }
}

function editarGabarito(id) {
    showToast('✏️ Carregando gabarito...', 'info');
    fetch(API_URL + '/api/provas/' + id).then(r => r.json()).then(prova => {
        if (prova.erro) { showToast('❌ ' + prova.erro, 'error'); return; }
        if (prova.gabarito && prova.gabarito.length > 0) {
            const gabarito = prova.gabarito;
            const bncc = prova.bncc || [];
            const disciplina = prova.disciplina || '';
            const isProducao = (disciplina === 'Produção de Texto');
            go('gabarito');
            setTimeout(() => {
                const serieMap = { '1º Ano': '1', '2º Ano': '2', '3º Ano': '3', '4º Ano': '4', '5º Ano': '5', '6º Ano': '6', '7º Ano': '7', '8º Ano': '8', '9º Ano': '9' };
                document.getElementById('gab-serie').value = serieMap[prova.serie] || '2';
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
                    if (isProducao) showToast('📋 Gabarito de Produção carregado para edição!', 'success');
                    else {
                        const selects = document.querySelectorAll('.gab-select');
                        const bnccInputs = document.querySelectorAll('.gab-bncc');
                        selects.forEach((s, i) => { if (i < gabarito.length && gabarito[i]) { s.value = gabarito[i]; s.classList.add('filled'); } });
                        bnccInputs.forEach((inp, i) => { if (i < bncc.length && bncc[i]) inp.value = bncc[i]; });
                        showToast('📋 Gabarito carregado para edição!', 'success');
                    }
                }, 100);
            }, 150);
        } else {
            showToast('⚠️ Esta prova não tem gabarito cadastrado', 'warning');
            go('gabarito');
        }
    }).catch(e => { showToast('❌ Erro ao carregar gabarito: ' + e.message, 'error'); console.error(e); });
}

async function excluirGabarito(id, nome) {
    if (!confirm('Excluir o gabarito da prova "' + nome + '"?')) return;
    try {
        showToast('🗑️ Excluindo gabarito...', 'error');
        const response = await fetch(API_URL + '/api/gabaritos/' + id, {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' }
        });
        const result = await processarRespostaAPI(response);
        if (result.ok) {
            showToast('🗑️ Gabarito excluído com sucesso!', 'success');
            limparCache(); carregarGabaritos(); carregarProvas();
        } else showToast('❌ Erro ao excluir gabarito: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
    } catch (erro) { console.error(erro); showToast('❌ Erro ao excluir gabarito: ' + erro.message, 'error'); }
}

// ============================================
// CORREÇÃO AUTOMÁTICA POR QR CODE
// ============================================
function abrirCameraAutomatico() { autoModoAtivo = true; abrirCamera(); }

function processarArqAutomatico(input) {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) { showToast('❌ Imagem muito grande (máx. 20MB)', 'error'); return; }
    const reader = new FileReader();
    reader.onload = function(e) {
        const base64 = e.target.result;
        const preview = document.getElementById('auto-preview');
        const img = document.getElementById('auto-img-prev');
        if (preview && img) { img.src = base64; preview.style.display = 'block'; }
        const resultado = document.getElementById('auto-resultado');
        if (resultado) resultado.style.display = 'none';
        window._autoImagem = base64;
        showToast('✅ Imagem carregada! Clique em "CORRIGIR AUTOMATICAMENTE"', 'success');
    };
    reader.readAsDataURL(file);
}

async function corrigirAutomatico() {
    const imagem = window._autoImagem;
    if (!imagem) { showToast('❌ Nenhuma imagem carregada', 'error'); return; }
    const resultadoDiv = document.getElementById('auto-resultado');
    const conteudoDiv = document.getElementById('auto-resultado-conteudo');
    if (resultadoDiv) resultadoDiv.style.display = 'block';
    if (conteudoDiv) {
        conteudoDiv.innerHTML = `<div style="text-align:center; padding:20px;"><div class="spinner" style="margin:0 auto 14px;"></div><p style="font-size:15px; font-weight:700;">🔍 Lendo o QR Code do cartão...</p></div>`;
    }
    try {
        const response = await fetch(`${API_URL}/api/corrigir-automatico`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ imagem: imagem, salvar_auto: false })
        });
        const dados = await response.json();
        if (!response.ok || !dados.sucesso) { mostrarErroAutomatico(dados.erro || 'Erro na correção automática', dados.dicas); return; }
        mostrarResultadoAutomatico(dados);
        window._autoImagem = null;
        const preview = document.getElementById('auto-preview');
        if (preview) preview.style.display = 'none';
    } catch (erro) { console.error(erro); mostrarErroAutomatico('Erro de conexão: ' + erro.message); }
}

function mostrarErroAutomatico(mensagem, dicas) {
    const conteudoDiv = document.getElementById('auto-resultado-conteudo');
    if (!conteudoDiv) return;
    let dicasHtml = '';
    if (dicas && Array.isArray(dicas)) {
        dicasHtml = '<div style="margin-top:14px;padding:12px;background:rgba(245,158,11,0.1);border-radius:8px;border-left:3px solid var(--orange);"><strong style="color:var(--orange);">Dicas:</strong><ul style="margin-top:6px;padding-left:20px;font-size:13px;color:var(--text2);line-height:1.7;">';
        dicas.forEach(d => { dicasHtml += `<li>${escapeHtml(d)}</li>`; });
        dicasHtml += '</ul></div>';
    }
    conteudoDiv.innerHTML = `<div style="padding:16px; background:rgba(239,68,68,0.08); border-radius:10px; border-left:4px solid var(--red);"><div style="font-size:15px; font-weight:700; color:var(--red); margin-bottom:8px;">❌ ${escapeHtml(mensagem)}</div>${dicasHtml}</div>`;
}

function mostrarResultadoAutomatico(dados) {
    const conteudoDiv = document.getElementById('auto-resultado-conteudo');
    if (!conteudoDiv) return;
    if (dados.sucesso || !dados.erro) {
        const gabarito = dados.gabarito || [];
        const respostas = dados.respostas_detectadas || [];
        const quantidade = dados.total || gabarito.length || 20;
        const tipoQuestoes = parseInt(dados.tipo_questoes) || 4;
        const alternativas = tipoQuestoes === 3 ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        const valorPorQuestao = quantidade > 0 ? (10 / quantidade) : 0.5;
        correcaoManualData = {
            alunoId: dados.aluno_id || dados.qr_lido?.aluno_id,
            alunoNome: dados.aluno || 'Aluno',
            provaId: dados.prova_id || dados.qr_lido?.prova_id,
            provaTitulo: dados.prova_titulo || 'Prova',
            gabarito: gabarito, respostasAluno: respostas.slice(),
            quantidade: quantidade, alternativas: alternativas,
            notaMaxima: 10, notaMinima: 5, valorPorQuestao: valorPorQuestao,
            serie: dados.serie || '', disciplina: dados.disciplina || '',
            confianca_por_questao: dados.confianca_por_questao || [],
            questoes_suspeitas: dados.questoes_suspeitas || [],
            bncc: dados.bncc || [], questoes_status: dados.questoes_status || []
        };
        window.ultimoResultadoAuto = dados;
    }

    const nota = dados.nota || 0;
    const acertos = dados.acertos || 0;
    const total = dados.total || 0;
    const porcentagem = dados.porcentagem || 0;
    const conceito = dados.conceito?.nome || 'inicial';
    const aluno = dados.aluno || 'Aluno';
    const prova = dados.prova_titulo || 'Prova';
    const escola = dados.escola_nome || '';
    const turma = dados.turma_nome || '';

    const cor = { 'inicial': '#ef4444', 'basico': '#f59e0b', 'proficiente': '#3b82f6', 'avancado': '#10b981' }[conceito] || '#94a3b8';
    const conceitoLabel = { 'inicial': '🔴 Inicial', 'basico': '🟠 Básico', 'proficiente': '🔵 Proficiente', 'avancado': '🟢 Avançado' }[conceito] || conceito;

    let questoesHtml = '';
    if (dados.questoes_status && Array.isArray(dados.questoes_status)) {
        questoesHtml = '<div style="display:grid; grid-template-columns:repeat(10,1fr); gap:4px; margin-top:12px;">';
        dados.questoes_status.forEach(q => {
            const acertou = q.acertou;
            const resp = q.resposta || '—';
            const bg = acertou ? 'rgba(16,185,129,0.15)' : (q.resposta !== '—' ? 'rgba(239,68,68,0.15)' : 'rgba(100,116,139,0.1)');
            const corTexto = acertou ? 'var(--green)' : (q.resposta !== '—' ? 'var(--red)' : 'var(--text3)');
            const icone = acertou ? '✅' : (q.resposta !== '—' ? '❌' : '—');
            questoesHtml += `<div style="background:${bg};border-radius:6px;padding:5px 2px;text-align:center;"><div style="font-size:8px;font-weight:700;color:var(--text3);">Q${q.numero}</div><div style="font-size:13px;font-weight:800;color:${corTexto};">${escapeHtml(resp)}</div><div style="font-size:8px;">${icone}</div></div>`;
        });
        questoesHtml += '</div>';
    }

    let alertaHtml = '';
    if (dados.requer_revisao_manual) {
        alertaHtml = `<div style="margin-top:12px;padding:10px;background:rgba(245,158,11,0.12);border-radius:8px;border-left:3px solid var(--orange);font-size:12px;color:var(--orange);">⚠️ <strong>Revisão manual recomendada</strong></div>`;
    }

    conteudoDiv.innerHTML = `
        <div style="background:linear-gradient(135deg, rgba(139,92,246,0.08), rgba(6,182,212,0.08)); border-radius:12px; padding:16px; border:2px solid rgba(139,92,246,0.3);">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:14px;">
                <div style="font-size:16px;font-weight:800;color:#a78bfa;">✅ Correção Automática Concluída!</div>
                <span class="badge badge-purple" style="font-size:10px;">VIA QR CODE</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:14px;font-size:13px;">
                <div style="background:var(--surface2);border-radius:8px;padding:10px;"><div style="color:var(--text3);font-size:9px;font-weight:700;margin-bottom:3px;">ALUNO</div><div style="font-weight:700;">${escapeHtml(aluno)}</div></div>
                <div style="background:var(--surface2);border-radius:8px;padding:10px;"><div style="color:var(--text3);font-size:9px;font-weight:700;margin-bottom:3px;">PROVA</div><div style="font-weight:700;">${escapeHtml(prova)}</div></div>
                <div style="background:var(--surface2);border-radius:8px;padding:10px;"><div style="color:var(--text3);font-size:9px;font-weight:700;margin-bottom:3px;">ESCOLA</div><div style="font-weight:700;font-size:12px;">${escapeHtml(escola)}</div></div>
                <div style="background:var(--surface2);border-radius:8px;padding:10px;"><div style="color:var(--text3);font-size:9px;font-weight:700;margin-bottom:3px;">TURMA</div><div style="font-weight:700;font-size:12px;">${escapeHtml(turma)}</div></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:14px;">
                <div style="background:var(--surface2);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:26px;font-weight:900;color:var(--green);">${acertos}</div><div style="font-size:10px;color:var(--text3);font-weight:700;">✅ ACERTOS</div></div>
                <div style="background:var(--surface2);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:26px;font-weight:900;color:var(--red);">${total - acertos}</div><div style="font-size:10px;color:var(--text3);font-weight:700;">❌ ERROS</div></div>
                <div style="background:var(--surface2);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:26px;font-weight:900;color:var(--blue);">${porcentagem}%</div><div style="font-size:10px;color:var(--text3);font-weight:700;">📊 APROVEIT.</div></div>
                <div style="background:var(--surface2);border-radius:8px;padding:10px;text-align:center;"><div style="font-size:26px;font-weight:900;color:${cor};">${nota.toFixed(1)}</div><div style="font-size:10px;color:var(--text3);font-weight:700;">⭐ NOTA</div></div>
            </div>
            <div style="text-align:center;margin-bottom:10px;"><span style="background:${cor}20;color:${cor};padding:6px 18px;border-radius:20px;font-size:13px;font-weight:800;">${conceitoLabel}</span></div>
            ${questoesHtml}
            ${alertaHtml}
            <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap;justify-content:center;">
                <button class="btn btn-orange btn-sm no-print" onclick="abrirCorrecaoManualAuto()">✏️ Correção Manual</button>
                <button class="btn btn-green btn-sm no-print" onclick="salvarCorrecaoAuto()">💾 Salvar</button>
                <button class="btn btn-outline btn-sm" onclick="limparResultadoAutomatico()">🔄 Nova Correção</button>
            </div>
        </div>
    `;
    conteudoDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
    showToast(`✅ Corrigido! ${aluno} — Nota ${nota.toFixed(1)}`, 'success');
}

function limparResultadoAutomatico() {
    const resultado = document.getElementById('auto-resultado');
    const preview = document.getElementById('auto-preview');
    const img = document.getElementById('auto-img-prev');
    const input = document.getElementById('inp-arq-auto');
    if (resultado) resultado.style.display = 'none';
    if (preview) preview.style.display = 'none';
    if (img) img.src = '';
    if (input) input.value = '';
    window._autoImagem = null;
    showToast('🔄 Pronto para nova correção', 'info');
}

function abrirCorrecaoManualAuto() {
    if (!correcaoManualData || !correcaoManualData.respostasAluno || correcaoManualData.respostasAluno.length === 0) { showToast('❌ Nenhuma correção para editar!', 'error'); return; }
    if (!correcaoManualData.gabarito || correcaoManualData.gabarito.length === 0) { showToast('❌ Gabarito não disponível para esta prova!', 'error'); return; }
    abrirCorrecaoManual();
}

async function salvarCorrecaoAuto() {
    if (!correcaoManualData || !correcaoManualData.respostasAluno) { showToast('❌ Nenhuma correção para salvar!', 'error'); return; }
    if (!correcaoManualData.provaId || !correcaoManualData.alunoId) { showToast('❌ Dados incompletos!', 'error'); return; }
    await salvarCorrecao();
}

// ============================================
// INICIALIZAÇÃO
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    const tipoSelect = document.getElementById('modal-prova-tipo');
    if (tipoSelect) tipoSelect.addEventListener('change', function() { gerarGabaritoModal(this.value); });

    buildGabGrid();
    carregarCombos();
    carregarDados();
    carregarEscolasFiltroAlunos();
    const tipoProva = document.getElementById('modal-prova-tipo');
    if (tipoProva) gerarGabaritoModal(tipoProva.value);
    atualizarDatasImpressao();
    carregarEscolasParaCorrecaoManual();
    carregarFiltrosRelTurma();
    carregarFiltroEscolaTurmas();
    carregarEscolasParaAluno();
    popularSelectQuestoes();
    popularSelectGabTotal();

    const disciplinaSelect = document.getElementById('prova-disciplina');
    if (disciplinaSelect) disciplinaSelect.addEventListener('change', atualizarInfoAlts);

    const gabProvaSelect = document.getElementById('gab-prova');
    if (gabProvaSelect) gabProvaSelect.addEventListener('change', buildGabGrid);
});

document.getElementById('del-modal')?.addEventListener('click', e => { if (e.target === e.currentTarget) cancelarDel(); });

window.addEventListener('resize', function() {
    if (window.innerWidth > 900) {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('menuOverlay');
        const toggle = document.getElementById('menuToggle');
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        toggle.classList.remove('active');
        toggle.innerHTML = '☰';
    }
});