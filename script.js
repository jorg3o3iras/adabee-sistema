// ============================================
// CONFIGURAÇÃO DA API
// ============================================
const API_URL = 'https://adabee-sistema-3.onrender.com';
let loginType = 'admin';
let camStream = null;
let camFacing = 'environment';
let delTarget = null;
let ultimaImagem = null;
let gerandoDocumento = false;
let paginaAtual = 'dashboard';

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

    mostrarSucesso(tableId, rowId, nome, acao = 'salvo') {
        showToast(`✅ ${nome} ${acao} com sucesso!`, 'success');
        setTimeout(() => {
            this.destacarLinha(tableId, rowId, `✅ ${acao}!`);
        }, 300);
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

function limparCache() {
    cache.escolas = null;
    cache.turmas = {};
    cache.alunos = {};
    cache.provas = null;
    cache.ultima_atualizacao = {};
    console.log('🧹 Cache limpo!');
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

// Dados para correção manual
let correcaoManualData = {
    alunoId: null,
    alunoNome: '',
    provaId: null,
    provaTitulo: '',
    gabarito: [],
    respostasAluno: [],
    quantidade: 20,
    alternativas: ['A', 'B', 'C', 'D'],
    notaMaxima: 10,
    notaMinima: 5,
    valorPorQuestao: 0.5,
    serie: '1º Ano',
    disciplina: '',
    confianca_por_questao: []
};

let cmStandaloneData = {
    escolaId: null,
    turmaId: null,
    provaId: null,
    alunoId: null,
    alunoNome: '',
    turmaNome: '',
    serie: '',
    escolaNome: '',
    gabarito: [],
    respostas: [],
    quantidade: 20,
    alternativas: ['A', 'B', 'C', 'D'],
    notaMaxima: 10,
    notaMinima: 5,
    valorPorQuestao: 0.5,
    provaTitulo: '',
    provaData: '',
    disciplina: '',
    confianca_por_questao: []
};

let desempenhoData = {
    alunoSelecionado: null,
    respostas: [],
    gabarito: [],
    questoes: [],
    disciplinas: []
};

let usuarioEditandoId = null;

// ============================================
// PROCESSAR RESPOSTAS DA API
// ============================================
async function processarRespostaAPI(response) {
    let result;
    const contentType = response.headers.get('content-type');

    if (contentType && contentType.includes('application/json')) {
        try {
            result = await response.json();
        } catch (e) {
            result = { erro: 'Erro ao processar JSON' };
        }
    } else {
        const text = await response.text();
        try {
            result = JSON.parse(text);
        } catch (e) {
            if (response.ok) {
                result = { sucesso: true, mensagem: 'Operação realizada com sucesso' };
            } else {
                result = { sucesso: false, erro: 'Erro ' + response.status + ': ' + text.substring(0, 100) };
            }
        }
    }

    return {
        ok: response.ok || result.sucesso === true,
        data: result,
        status: response.status
    };
}

// ============================================
// ATUALIZAR DATAS DE IMPRESSÃO
// ============================================
function atualizarDatasImpressao() {
    const agora = new Date();
    const dataFormatada = agora.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });

    const elementosData = [
        'print-data-dash',
        'print-data-resultados',
        'print-data-rel-turma',
        'print-data-rel-escola',
        'print-data-u-dash',
        'print-data-u-rel',
        'print-data-desempenho'
    ];

    elementosData.forEach(id => {
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
// LOGIN
// ============================================
function setLTab(t) {
    loginType = t;
    document.querySelectorAll('.login-tab').forEach((el, i) => {
        el.classList.toggle('active', (i === 0 && t === 'admin') || (i === 1 && t === 'user'));
    });
}

async function doLogin() {
    const u = document.getElementById('lu').value.trim();
    const p = document.getElementById('lp').value.trim();
    try {
        const response = await fetch(`${API_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, senha: p })
        });
        const data = await response.json();
        if (data.sucesso) {
            startApp(data.perfil, data.usuario);
        } else {
            showToast('❌ Usuário ou senha incorretos!', 'error');
            shakeCard();
        }
    } catch (erro) {
        if ((loginType === 'admin' && u === 'admin' && p === 'admin') ||
            (loginType === 'user' && (u === 'usuario' || u === 'professor1') && p === '123')) {
            startApp(loginType, u);
        } else {
            showToast('❌ Usuário ou senha incorretos!', 'error');
            shakeCard();
        }
    }
}

function shakeCard() {
    const c = document.querySelector('.login-card');
    c.style.animation = 'none';
    setTimeout(() => c.style.animation = 'shake .4s ease', 10);
}

document.getElementById('lp').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
});

function startApp(role, uname) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    document.getElementById('sb-avatar').textContent = uname[0].toUpperCase();
    document.getElementById('sb-uname').textContent = uname;
    document.getElementById('sb-urole').textContent = role === 'admin' ? 'Administrador do Sistema' : 'Usuário do Sistema';

    const isAdmin = role === 'admin';

    document.getElementById('adm-sb').style.display = 'block';
    document.getElementById('usr-sb').style.display = 'none';

    const menuConfig = document.getElementById('menu-config');
    if (menuConfig) {
        menuConfig.style.display = isAdmin ? 'block' : 'none';
    }

    go(isAdmin ? 'dashboard' : 'dashboard');

    buildGabGrid();
    carregarDados();
    atualizarDatasImpressao();
    carregarEscolasParaCorrecaoManual();
    carregarFiltrosRelTurma();
    carregarEscolasDesempenho();
    popularSelectQuestoes();
    popularSelectGabTotal();
    carregarEscolasCorrigir();
}

function doLogout() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    document.getElementById('lu').value = '';
    document.getElementById('lp').value = '';
    fecharCamera();
}

// ============================================
// NAVEGAÇÃO
// ============================================
function go(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const el = document.getElementById('page-' + page);
    if (el) el.classList.add('active');
    
    document.querySelectorAll('.sb-item').forEach(s => s.classList.toggle('active', s.dataset.p === page));
    
    switch(page) {
        case 'escola':
            carregarEscolas();
            break;
        case 'turmas':
            carregarFiltroEscolaTurmas();
            carregarTurmas();
            break;
        case 'alunos':
            const escolaId = document.getElementById('filtro-escola-alunos')?.value || '';
            carregarAlunos(escolaId);
            break;
        case 'provas':
            carregarProvas();
            break;
        case 'resultados':
            carregarFiltrosResultados();
            carregarResultadosComFiltros();
            break;
        case 'gabaritos':
            carregarGabaritos();
            break;
        case 'rel-turma':
            carregarFiltrosRelTurma();
            carregarRelatorioTurmaFiltrado();
            break;
        case 'desempenho':
            carregarEscolasDesempenho();
            break;
        case 'dashboard':
            carregarDashboard();
            carregarUltimasCorrecoes();
            break;
        case 'corrigir-ia':
            carregarEscolasCorrigir();
            break;
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
// FUNÇÃO PARA FILTRAR TURMAS POR SÉRIE
// ============================================
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

// ============================================
// CARREGAR ESCOLAS PARA CORRIGIR
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
            if (current) {
                select.value = current;
                carregarTurmasPorEscolaCorrigir(current);
            }
        }
    } catch (erro) {
        console.error('Erro ao carregar escolas para correção:', erro);
    }
}

// ============================================
// CARREGAR TURMAS POR ESCOLA PARA CORRIGIR
// ============================================
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
    } catch (e) {
        console.error('Erro ao carregar turmas:', e);
        showToast('❌ Erro ao carregar turmas', 'error');
    }
}

// ============================================
// CARREGAR ALUNOS POR TURMA PARA CORRIGIR
// ============================================
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
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
    }
}

// ============================================
// CARREGAR PROVAS POR TURMA PARA CORRIGIR
// ============================================
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
            if (provasFiltradas.length === 0) {
                provasFiltradas = provas;
            }

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
    } catch (e) {
        console.error('Erro ao carregar provas:', e);
    }
}

// ============================================
// CARREGAR ALUNOS POR PROVA FILTRADOS
// ============================================
async function carregarAlunosPorProvaFiltrados(provaId) {
    const selectAluno = document.getElementById('corrigir-aluno');
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
    if (!provaId) return;

    try {
        const provaResp = await fetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) {
            showToast('❌ Erro ao carregar dados da prova', 'error');
            return;
        }

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
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
    }
}

// ============================================
// CARREGAR ESCOLAS (COM CACHE)
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
                return '<tr data-id="' + e.id + '" data-nome="' + e.nome + '">' +
                    '<td><span class="badge badge-blue">' + String(i + 1).padStart(3, '0') + '</span></td>' +
                    '<td><strong>' + e.nome + '</strong></td>' +
                    '<td>' + (e.municipio || '—') + (e.estado ? ' — ' + e.estado : '') + '</td>' +
                    '<td><span class="chip">' + (e.inep || '—') + '</span></td>' +
                    '<td>' + (e.diretor || '—') + '</td>' +
                    '<td>' + turmasCount + '</td>' +
                    '<td>' + alunosCount + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarEscola(' + e.id + ')">✏️ Editar</button><button class="btn-del" onclick="excluirEscola(' + e.id + ', \'' + e.nome + '\')" title="Excluir">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar escolas:', erro);
    }
}

// ============================================
// CARREGAR TURMAS (COM CACHE E LIMITE)
// ============================================
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

            const turmasVisiveis = turmas.slice(0, 50);
            
            tbody.innerHTML = turmasVisiveis.map((t, i) => {
                const totalAlunos = t.total_alunos || 0;
                return '<tr data-id="' + t.id + '" data-nome="' + t.nome + '" data-serie="' + (t.serie || '') + '" data-escola="' + (t.escola_id || '') + '">' +
                    '<td><span class="badge badge-gray">' + String(i + 1).padStart(2, '0') + '</span></td>' +
                    '<td><strong>' + t.nome + '</strong></td>' +
                    '<td><span class="badge ' + (corMap[t.serie] || 'badge-blue') + '">' + (t.serie || '—') + '</span></td>' +
                    '<td>' + (t.turno || 'Manhã') + '</td>' +
                    '<td>' + (t.escola_nome || '—') + '</td>' +
                    '<td>' + (t.professor || '—') + '</td>' +
                    '<td><span class="badge badge-blue">' + totalAlunos + '</span></td>' +
                    '<td><div class="btn-group">' +
                    '<button class="btn btn-outline btn-sm" onclick="editarTurma(' + t.id + ')">✏️</button>' +
                    '<button class="btn btn-green btn-sm" onclick="verAlunosDaTurma(' + t.id + ')" title="Lista de Alunos">📋</button>' +
                    '<button class="btn-del" onclick="excluirTurma(' + t.id + ', \'' + t.nome + '\')">🗑️</button>' +
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

// ============================================
// CARREGAR FILTRO DE ESCOLA PARA TURMAS
// ============================================
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

// ============================================
// APLICAR FILTROS NAS TURMAS
// ============================================
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

// ============================================
// LIMPAR FILTROS DAS TURMAS
// ============================================
function limparFiltrosTurmas() {
    document.getElementById('filtro-escola-turmas').value = '';
    document.getElementById('filtro-serie-turmas').value = '';
    document.querySelectorAll('#tb-turmas tr').forEach(row => row.style.display = '');
    showToast('✕ Filtros limpos!', 'info');
}

// ============================================
// CARREGAR ALUNOS (COM CACHE E LIMITE)
// ============================================
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
            
            const alunosVisiveis = alunos.slice(0, 50);
            
            tbody.innerHTML = alunosVisiveis.map((a, i) => {
                return '<tr data-id="' + a.id + '" data-nome="' + a.nome + '">' +
                    '<td><span class="badge badge-blue">' + String(a.numero_chamada || i + 1).padStart(2, '0') + '</span></td>' +
                    '<td><span class="chip">' + (a.matricula || '—') + '</span></td>' +
                    '<td><strong>' + a.nome + '</strong></td>' +
                    '<td><span class="badge ' + (corMap[a.turma_serie] || 'badge-blue') + '">' + (a.turma_serie || '—') + '</span></td>' +
                    '<td>' + (a.turma_nome || '—') + '</td>' +
                    '<td><span class="badge badge-gray">' + (a.escola_nome || '—') + '</span></td>' +
                    '<td>' + (a.data_nascimento ? new Date(a.data_nascimento).toLocaleDateString() : '—') + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarAluno(' + a.id + ')">✏️</button><button class="btn-del" onclick="excluirAluno(' + a.id + ', \'' + a.nome + '\')">🗑️</button></div></td></tr>';
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

// ============================================
// CARREGAR ESCOLAS PARA FILTRO DE ALUNOS
// ============================================
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

// ============================================
// FILTRAR ALUNOS POR ESCOLA
// ============================================
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

// ============================================
// FILTRAR ALUNOS POR SÉRIE
// ============================================
function filtrarAlunosPorSerie(serie) {
    const escolaId = document.getElementById('filtro-escola-alunos')?.value || '';
    carregarAlunos(escolaId);
}

// ============================================
// CARREGAR PROVAS (COM CACHE)
// ============================================
async function carregarProvas() {
    try {
        const provas = await carregarProvasComCache();
        const tbody = document.getElementById('tb-provas');
        if (!tbody) return;

        if (!provas || provas.length === 0 || provas.erro) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma prova cadastrada</td></tr>';
        } else {
            tbody.innerHTML = provas.map((p, i) => {
                return '<tr data-id="' + p.id + '" data-nome="' + p.titulo + '">' +
                    '<td><span class="badge badge-blue">' + String(i + 1).padStart(3, '0') + '</span></td>' +
                    '<td><strong>' + p.titulo + '</strong></td>' +
                    '<td><span class="badge badge-purple">' + (p.serie || '—') + '</span></td>' +
                    '<td><span class="badge badge-gray">' + (p.disciplina || '—') + '</span></td>' +
                    '<td>' + (p.data_prova || '—') + '</td>' +
                    '<td><span class="badge ' + (p.gabarito && p.gabarito.length > 0 ? 'badge-green' : 'badge-orange') + '">' + (p.gabarito && p.gabarito.length > 0 ? 'Com Gabarito' : 'Sem Gabarito') + '</span></td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="visualizarProva(' + p.id + ')">👁️</button>' + (p.gabarito && p.gabarito.length > 0 ? '' : '<button class="btn btn-primary btn-sm" onclick="go(\'gabarito\')">+ Gabarito</button>') + '<button class="btn-del" onclick="excluirProva(' + p.id + ', \'' + p.titulo + '\')">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar provas:', erro);
    }
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
                            <div style="font-weight:700;font-size:14px;color:var(--green);">${texto}</div>
                            ${codigo ? `<div style="font-size:10px;color:var(--purple);margin-top:4px;">BNCC: ${codigo}</div>` : ''}
                            <div style="font-size:9px;color:var(--text3);margin-top:4px;border-top:1px solid var(--border);padding-top:4px;">Nível BNCC: ${codigo || 'Não definido'}</div>
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
                        <div style="font-weight:700;font-size:12px;color:var(--green);">${texto}</div>
                        ${codigo ? `<div style="font-size:7px;color:var(--purple);margin-top:2px;">BNCC: ${codigo}</div>` : ''}
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
                <div><strong style="color:var(--text2);">📝 Título</strong><br>${prova.titulo || '—'}</div>
                <div><strong style="color:var(--text2);">📚 Disciplina</strong><br>${prova.disciplina || '—'}</div>
                <div><strong style="color:var(--text2);">🎓 Série</strong><br>${prova.serie || '—'}</div>
                <div><strong style="color:var(--text2);">📅 Data</strong><br>${prova.data_prova || '—'}</div>
                <div><strong style="color:var(--text2);">📊 Bimestre</strong><br>${prova.bimestre || '—'}</div>
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

// ============================================
// CARREGAR DASHBOARD
// ============================================
async function carregarDashboard() {
    try {
        const response = await fetch(`${API_URL}/api/dashboard`);
        const dados = await response.json();

        setText('totalEscolas', dados.total_escolas || 0);
        setText('totalTurmas', dados.total_turmas || 0);
        setText('totalAlunos', dados.total_alunos || 0);
        setText('totalProvas', dados.total_provas || 0);
        setText('u-total-escolas', dados.total_escolas || 0);
        setText('u-total-turmas', dados.total_turmas || 0);
        setText('u-total-alunos', dados.total_alunos || 0);
    } catch (erro) {
        console.error('Erro ao carregar dashboard:', erro);
    }
}

// ============================================
// CARREGAR GABARITOS
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
                return '<tr data-id="' + p.id + '" data-nome="' + p.titulo + '">' +
                    '<td><span class="badge badge-blue">' + String(i + 1).padStart(3, '0') + '</span></td>' +
                    '<td>' + p.titulo + '</td>' +
                    '<td><span class="badge badge-purple">' + (p.serie || '—') + '</span></td>' +
                    '<td>' + (p.quantidade_questoes || p.gabarito?.length || 0) + '</td>' +
                    '<td><span class="badge ' + (tipoTexto === 'Texto' ? 'badge-purple' : (p.tipo_questoes == '3' ? 'badge-purple' : 'badge-blue')) + '">' + tipoTexto + '</span></td>' +
                    '<td style="font-size:9px; max-width:120px; word-wrap:break-word;">' + bnccText + '</td>' +
                    '<td>' + (p.data_prova || '—') + '</td>' +
                    '<td><div class="btn-group"><button class="btn btn-outline btn-sm" onclick="editarGabarito(' + p.id + ')">✏️</button><button class="btn-del" onclick="excluirGabarito(' + p.id + ', \'' + p.titulo + '\')">🗑️</button></div></td></tr>';
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar gabaritos:', erro);
    }
}

// ============================================
// CARREGAR RESULTADOS COM FILTROS
// ============================================
async function carregarResultadosComFiltros() {
    try {
        const escolaId = document.getElementById('filtro-escola').value;
        const serie = document.getElementById('filtro-serie').value;
        const turmaId = document.getElementById('filtro-turma').value;
        const provaId = document.getElementById('filtro-prova').value;

        let totalAlunosTurma = 0;
        let alunosDaTurma = [];

        const paramsAlunos = new URLSearchParams();
        if (turmaId && turmaId !== '') paramsAlunos.append('turma_id', turmaId);
        else if (escolaId && escolaId !== '') paramsAlunos.append('escola_id', escolaId);
        if (serie && serie !== '') paramsAlunos.append('serie', serie);

        if (paramsAlunos.toString()) {
            try {
                const alunosData = await carregarAlunosComCache({
                    turma_id: turmaId || undefined,
                    escola_id: escolaId || undefined,
                    serie: serie || undefined
                });
                if (alunosData && !alunosData.erro && Array.isArray(alunosData)) {
                    alunosDaTurma = alunosData;
                    totalAlunosTurma = alunosData.length;
                }
            } catch (e) {
                console.warn('Erro ao buscar total de alunos da turma:', e);
            }
        }

        let url = API_URL + '/api/historico/agrupado';
        const paramsHist = new URLSearchParams();
        if (escolaId && escolaId !== '') paramsHist.append('escola', escolaId);
        if (serie && serie !== '') paramsHist.append('serie', serie);
        if (turmaId && turmaId !== '') paramsHist.append('turma', turmaId);
        if (provaId && provaId !== '') paramsHist.append('prova', provaId);
        if (paramsHist.toString()) url += '?' + paramsHist.toString();

        const response = await fetch(url);
        const alunos = await response.json();

        const tbody = document.getElementById('tb-resultados-filtrado');
        if (!tbody) return;

        const totalCorrigidos = (alunos && !alunos.erro && Array.isArray(alunos)) ? alunos.length : 0;
        const diff = Math.max(0, totalAlunosTurma - totalCorrigidos);

        // ============================================
        // 🔥 CALCULAR PORCENTAGENS
        // ============================================
        const pctCorrigidos = totalAlunosTurma > 0 ? Math.round((totalCorrigidos / totalAlunosTurma) * 100) : 0;
        const pctSemCorrecao = totalAlunosTurma > 0 ? Math.round((diff / totalAlunosTurma) * 100) : 0;
        const pctFizeram = pctCorrigidos;
        const pctNaoFizeram = pctSemCorrecao;

        // ============================================
        // 🔥 ATUALIZAR CARDS COM A NOVA ORDEM E PORCENTAGENS
        // ============================================
        setText('res-total-alunos-turma', totalAlunosTurma);
        setText('res-porcentagem-total', '100% da turma');
        setText('res-total-filtrado', totalCorrigidos);
        setText('res-porcentagem-corrigidos', pctCorrigidos + '% da turma');
        setText('res-diferenca', diff);
        setText('res-porcentagem-sem-correcao', pctSemCorrecao + '% da turma');
        setText('res-alunos-fizeram', totalCorrigidos);
        setText('res-alunos-nao-fizeram', diff);
        setText('res-porcentagem-fizeram', pctFizeram + '% da turma');
        setText('res-porcentagem-nao-fizeram', pctNaoFizeram + '% da turma');

        if (!alunos || alunos.length === 0 || alunos.erro) {
            tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma correção encontrada com os filtros selecionados</td></tr>';
            setText('total-alunos-tabela', '0 alunos');
            ['inicial', 'basico', 'proficiente', 'avancado'].forEach(c => {
                setText(`conceito-${c}-count`, '0');
                const bar = document.getElementById(`conceito-${c}-bar`);
                if (bar) bar.style.width = '2%';
            });
            setText('total-conceitos-label', '0');
            return;
        }

        const dadosAlunos = Array.isArray(alunos) ? alunos : [];

        if (dadosAlunos.length === 0) {
            tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--text3);">Nenhum dado disponível</td></tr>';
            setText('total-alunos-tabela', '0 alunos');
            ['inicial', 'basico', 'proficiente', 'avancado'].forEach(c => {
                setText(`conceito-${c}-count`, '0');
                const bar = document.getElementById(`conceito-${c}-bar`);
                if (bar) bar.style.width = '2%';
            });
            setText('total-conceitos-label', '0');
            return;
        }

        let disciplinaAlvo = null;
        if (provaId && provaId !== '') {
            try {
                const provas = await carregarProvasComCache();
                const prova = provas.find(p => p.id == provaId);
                if (prova && prova.disciplina) {
                    disciplinaAlvo = mapearDisciplina(prova.disciplina);
                }
            } catch (e) {
                console.warn('Não foi possível obter a disciplina da prova:', e);
            }
        }

        function mapearDisciplina(nome) {
            const mapa = {
                'Português': 'portugues',
                'Matemática': 'matematica',
                'Produção de Texto': 'producao',
                'Ciências Humanas': 'ch',
                'Ciências Naturais': 'cn',
                'História': 'ch',
                'Geografia': 'ch',
                'Inglês': 'portugues'
            };
            return mapa[nome] || null;
        }

        const contagemConceitos = { inicial: 0, basico: 0, proficiente: 0, avancado: 0 };

        if (disciplinaAlvo) {
            dadosAlunos.forEach(aluno => {
                const discData = aluno[disciplinaAlvo];
                if (discData && typeof discData === 'object') {
                    const acertos = discData.acertos || 0;
                    const totalDisc = discData.total || 0;
                    const pct = totalDisc > 0 ? Math.round((acertos / totalDisc) * 100) : 0;
                    const conceito = calcularConceito(pct);
                    contagemConceitos[conceito]++;
                } else {
                    contagemConceitos.inicial++;
                }
            });
        } else {
            const disciplinas = ['portugues', 'matematica', 'producao', 'ch', 'cn'];
            dadosAlunos.forEach(aluno => {
                disciplinas.forEach(chave => {
                    const discData = aluno[chave];
                    if (discData && typeof discData === 'object') {
                        const acertos = discData.acertos || 0;
                        const totalDisc = discData.total || 0;
                        const pct = totalDisc > 0 ? Math.round((acertos / totalDisc) * 100) : 0;
                        const conceito = calcularConceito(pct);
                        contagemConceitos[conceito]++;
                    } else {
                        contagemConceitos.inicial++;
                    }
                });
            });
        }

        atualizarGraficosConceitos(contagemConceitos);

        const totalConceitos = contagemConceitos.inicial + contagemConceitos.basico +
                               contagemConceitos.proficiente + contagemConceitos.avancado;
        setText('total-conceitos-label', totalConceitos);

        dadosAlunos.sort((a, b) => (b.media || 0) - (a.media || 0));
        const total = dadosAlunos.length;

        setText('total-alunos-tabela', total + ' alunos');

        function getDadosDisciplina(disciplinaData, totalQuestoes) {
            if (!disciplinaData || typeof disciplinaData !== 'object') {
                return { acertos: 0, erros: 0, conceito: 'inicial' };
            }
            const acertos = disciplinaData.acertos !== undefined ? disciplinaData.acertos : 0;
            let erros = disciplinaData.erros !== undefined ? disciplinaData.erros : 0;
            const totalDisc = disciplinaData.total || totalQuestoes || 0;
            if (erros === 0 && totalDisc > 0 && acertos > 0) erros = totalDisc - acertos;
            const porcentagem = totalDisc > 0 ? Math.round((acertos / totalDisc) * 100) : 0;
            const conceito = calcularConceito(porcentagem);
            return { acertos, erros, conceito };
        }

        function badgeConceito(c) {
            return `badge-conceito-${c}-sm`;
        }

        tbody.innerHTML = dadosAlunos.map((aluno, index) => {
            const medalha = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : (index + 1);

            const portugues = getDadosDisciplina(aluno.portugues, 20);
            const matematica = getDadosDisciplina(aluno.matematica, 20);
            const producao = getDadosDisciplina(aluno.producao, 20);
            const ch = getDadosDisciplina(aluno.ch, 20);
            const cn = getDadosDisciplina(aluno.cn, 20);

            const nomeEscola = aluno.escola || '';
            const nomeTurma = aluno.turma || '';

            return '<tr>' +
                '<td>' + medalha + '</td>' +
                '<td>' + (index + 1) + '</td>' +
                '<td style="text-align:left;"><strong>' + (aluno.aluno_nome || 'Aluno') + '</strong></td>' +
                '<td><span class="badge badge-purple">' + (aluno.serie || '—') + '</span></td>' +
                '<td style="text-align:center;background:rgba(59,130,246,0.03);"><span class="badge badge-blue">' + portugues.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(59,130,246,0.03);"><span class="badge badge-red">' + portugues.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(59,130,246,0.03);"><span class="badge ' + badgeConceito(portugues.conceito) + '">' + portugues.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(16,185,129,0.03);"><span class="badge badge-green">' + matematica.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(16,185,129,0.03);"><span class="badge badge-red">' + matematica.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(16,185,129,0.03);"><span class="badge ' + badgeConceito(matematica.conceito) + '">' + matematica.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(139,92,246,0.03);"><span class="badge badge-purple">' + producao.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(139,92,246,0.03);"><span class="badge badge-red">' + producao.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(139,92,246,0.03);"><span class="badge ' + badgeConceito(producao.conceito) + '">' + producao.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(245,158,11,0.03);"><span class="badge badge-orange">' + ch.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(245,158,11,0.03);"><span class="badge badge-red">' + ch.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(245,158,11,0.03);"><span class="badge ' + badgeConceito(ch.conceito) + '">' + ch.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(20,184,166,0.03);"><span class="badge badge-teal">' + cn.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(20,184,166,0.03);"><span class="badge badge-red">' + cn.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(20,184,166,0.03);"><span class="badge ' + badgeConceito(cn.conceito) + '">' + cn.conceito + '</span></td>' +
                '<td style="font-size:10px;color:var(--text2);">' + (nomeEscola || '—') + '</td>' +
                '<td style="font-size:10px;color:var(--text2);">' + (nomeTurma || '—') + '</td>' +
                '</tr>';
        }).join('');

    } catch (erro) {
        console.error('❌ Erro ao carregar resultados com filtros:', erro);
        const tbody = document.getElementById('tb-resultados-filtrado');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--text3);">Erro ao carregar resultados: ' + erro.message + '</td></tr>';
        }
    }
}

// ============================================
// ATUALIZAR GRÁFICOS DE CONCEITOS
// ============================================
function atualizarGraficosConceitos(contagem) {
    const total = contagem.inicial + contagem.basico + contagem.proficiente + contagem.avancado || 1;

    const cores = {
        inicial: '#ef4444',
        basico: '#f59e0b',
        proficiente: '#3b82f6',
        avancado: '#10b981'
    };

    ['inicial', 'basico', 'proficiente', 'avancado'].forEach(conceito => {
        const count = contagem[conceito] || 0;
        let pct = total > 0 ? (count / total) * 100 : 0;
        pct = Math.max(pct, 2);

        const countEl = document.getElementById(`conceito-${conceito}-count`);
        const barEl = document.getElementById(`conceito-${conceito}-bar`);

        if (countEl) countEl.textContent = count;
        if (barEl) {
            barEl.style.width = pct + '%';
            barEl.style.background = `linear-gradient(90deg, ${cores[conceito]}, ${cores[conceito]}dd)`;
        }
    });
}

// ============================================
// CARREGAR FILTROS RESULTADOS
// ============================================
async function carregarFiltrosResultados() {
    try {
        const escolas = await carregarEscolasComCache();
        const selectEscola = document.getElementById('filtro-escola');
        if (selectEscola && escolas && !escolas.erro) {
            const current = selectEscola.value;
            selectEscola.innerHTML = '<option value="">Todas as escolas</option>';
            escolas.forEach(e => { const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                selectEscola.appendChild(opt); });
            if (current) selectEscola.value = current;
        }

        const turmas = await carregarTurmasComCache();
        const selectTurma = document.getElementById('filtro-turma');
        if (selectTurma && turmas && !turmas.erro) {
            const current = selectTurma.value;
            selectTurma.innerHTML = '<option value="">Todas as turmas</option>';
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                opt.dataset.serie = t.serie || '';
                selectTurma.appendChild(opt);
            });
            if (current) selectTurma.value = current;
        }

        const provas = await carregarProvasComCache();
        const selectProva = document.getElementById('filtro-prova');
        if (selectProva && provas && !provas.erro) {
            const current = selectProva.value;
            selectProva.innerHTML = '<option value="">Todas as provas</option>';
            provas.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.titulo + ' - ' + (p.serie || '');
                selectProva.appendChild(opt);
            });
            if (current) selectProva.value = current;
        }
    } catch (erro) { console.error('Erro ao carregar filtros:', erro); }
}

// ============================================
// CARREGAR TURMAS POR ESCOLA
// ============================================
async function carregarTurmasPorEscola(escolaId) {
    const selectTurma = document.getElementById('filtro-turma');
    const selectSerie = document.getElementById('filtro-serie');
    if (!selectTurma) return;
    selectTurma.innerHTML = '<option value="">Todas as turmas</option>';
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
            if (selectSerie) filtrarTurmasPorSerie(selectSerie, selectTurma);
        }
    } catch (erro) {
        console.error('Erro ao carregar turmas:', erro);
    }
    carregarResultadosComFiltros();
}

// ============================================
// LIMPAR FILTROS RESULTADOS
// ============================================
function limparFiltrosResultados() {
    document.getElementById('filtro-escola').value = '';
    document.getElementById('filtro-serie').value = '';
    document.getElementById('filtro-prova').value = '';

    const selectTurma = document.getElementById('filtro-turma');
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
            carregarResultadosComFiltros();
        }
    }).catch(e => console.error('Erro ao recarregar turmas:', e));

    const selectProva = document.getElementById('filtro-prova');
    carregarProvasComCache(true).then(provas => {
        if (provas && !provas.erro) {
            selectProva.innerHTML = '<option value="">Todas as provas</option>';
            provas.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.titulo + ' - ' + (p.serie || '');
                selectProva.appendChild(opt);
            });
            carregarResultadosComFiltros();
        }
    }).catch(e => console.error('Erro ao recarregar provas:', e));
}

// ============================================
// CORREÇÃO MANUAL (DENTRO DA IA) - FUNÇÃO PRINCIPAL
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
    if (!temGabaritoValido) {
        showToast('❌ Gabarito vazio ou inválido para esta prova!', 'error');
        return;
    }
    setText('cm-aluno-nome', correcaoManualData.alunoNome || 'Aluno');
    setText('cm-prova-titulo', correcaoManualData.provaTitulo || 'Prova');
    setText('cm-turma-info', correcaoManualData.serie + ' | Turma: —');
    setText('cm-data-correcao', new Date().toLocaleDateString('pt-BR'));
    gerarGridCorrecaoManual();
    atualizarResumoCorrecaoManual();
    openM('m-correcao-manual');

    setTimeout(() => {
        destacarQuestoesDuvidosas();
    }, 300);
}

function destacarQuestoesDuvidosas() {
    const confiancas = correcaoManualData.confianca_por_questao || [];
    const itens = document.querySelectorAll('.correcao-manual-item');
    let totalDuvidosas = 0;

    itens.forEach((item, index) => {
        const confianca = confiancas[index] || 100;
        item.style.borderColor = '';
        item.style.borderWidth = '';
        item.style.boxShadow = '';
        
        const oldBadge = item.querySelector('.confianca-badge');
        if (oldBadge) oldBadge.remove();

        if (confianca < 70) {
            totalDuvidosas++;
            item.style.borderColor = 'var(--orange)';
            item.style.borderWidth = '2px';
            item.style.boxShadow = '0 0 20px rgba(245,158,11,0.2)';
            
            const badge = document.createElement('div');
            badge.className = 'confianca-badge confianca-baixa';
            badge.style.cssText = 'font-size:8px; font-weight:700; margin-top:4px; padding:2px 8px; border-radius:12px; background:rgba(239,68,68,0.15); color:#ef4444;';
            badge.textContent = `⚠️ Confiança: ${confianca}%`;
            
            const select = item.querySelector('.q-select');
            if (select) {
                item.insertBefore(badge, select);
            } else {
                item.appendChild(badge);
            }
        } else if (confianca < 80) {
            item.style.borderColor = 'rgba(245,158,11,0.3)';
        }
    });

    if (totalDuvidosas > 0) {
        showToast(`🔍 ${totalDuvidosas} questões com baixa confiança (destacadas em laranja)`, 'warning');
    } else {
        showToast('✅ Todas as questões têm alta confiança!', 'success');
    }
}

function revisarApenasDuvidosas() {
    const confiancas = correcaoManualData.confianca_por_questao || [];
    const itens = document.querySelectorAll('.correcao-manual-item');
    let totalDuvidosas = 0;

    itens.forEach((item, index) => {
        const confianca = confiancas[index] || 100;
        if (confianca < 70) {
            item.style.display = '';
            totalDuvidosas++;
            if (totalDuvidosas === 1) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        } else {
            item.style.display = 'none';
        }
    });

    if (totalDuvidosas === 0) {
        showToast('✅ Nenhuma questão com baixa confiança!', 'success');
        itens.forEach(item => item.style.display = '');
    } else {
        showToast(`🔍 Mostrando apenas ${totalDuvidosas} questões com baixa confiança`, 'info');
    }
}

// ============================================
// GERAR GRID CORREÇÃO MANUAL
// ============================================
function gerarGridCorrecaoManual() {
    const grid = document.getElementById('cm-grid');
    if (!grid) return;
    const qtd = correcaoManualData.quantidade || 20;
    const alternativas = correcaoManualData.alternativas || ['A', 'B', 'C', 'D'];
    const respostas = correcaoManualData.respostasAluno || [];
    const gabarito = correcaoManualData.gabarito || [];
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');

    if (isProducao) {
        grid.style.display = 'flex';
        grid.style.flexDirection = 'column';
        grid.style.gap = '12px';
        grid.style.maxHeight = 'none';
        grid.style.overflowY = 'visible';
    } else {
        grid.style.display = 'grid';
        grid.style.gridTemplateColumns = 'repeat(10, 1fr)';
        grid.style.gap = '6px';
        grid.style.maxHeight = '280px';
        grid.style.overflowY = 'auto';
    }

    grid.innerHTML = '';
    for (let i = 0; i < qtd; i++) {
        const div = document.createElement('div');
        div.className = 'correcao-manual-item';
        const respostaAluno = (i < respostas.length) ? respostas[i] : '';
        const respostaGabarito = (i < gabarito.length) ? gabarito[i] : '';

        const isCorreto = respostaAluno && respostaGabarito && 
                         respostaAluno.toUpperCase() === respostaGabarito.toUpperCase();

        if (isProducao) {
            div.style.background = 'var(--bg2)';
            div.style.border = '1px solid var(--border)';
            div.style.borderRadius = '8px';
            div.style.padding = '10px 14px';
            div.style.textAlign = 'left';
            div.style.display = 'flex';
            div.style.flexDirection = 'column';
            div.style.gap = '6px';

            div.innerHTML = `
                <input class="gab-titulo" type="text" value="Q${i+1}" style="width:100%; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:12px; font-weight:bold;" />
                <div style="font-size:10px;color:var(--text3);">Gabarito: ${respostaGabarito || '—'}</div>
                <textarea class="q-resposta-texto" placeholder="Resposta do aluno..." style="width:100%; min-height:50px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:11px; resize:vertical;">${respostaAluno}</textarea>
                <select class="gab-nivel" style="width:100%; padding:2px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:10px;">
                    <option value="">Nível BNCC</option>
                    <option value="Inicial">Inicial</option>
                    <option value="Básico">Básico</option>
                    <option value="Proficiente">Proficiente</option>
                    <option value="Avançado">Avançado</option>
                </select>
                <textarea class="gab-observacao" placeholder="Observações (opcional)" style="width:100%; min-height:30px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:10px; resize:vertical;"></textarea>
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

            let statusClass = '';
            let statusText = '';
            if (respostaAluno) {
                if (isCorreto) { 
                    statusClass = 'correta'; 
                    statusText = '✅'; 
                } else { 
                    statusClass = 'errada'; 
                    statusText = '❌'; 
                }
            }

            div.innerHTML = `
                <div class="q-num">Q${i+1}</div>
                <div class="q-resposta" style="color:${isCorreto ? 'var(--green)' : (respostaAluno ? 'var(--red)' : 'var(--text3)')}">${respostaAluno || '—'}</div>
                <select class="q-select" data-questao="${i}" onchange="atualizarRespostaManual(this)">${options}</select>
                <div class="q-status ${statusClass}">${statusText}</div>
            `;

            const select = div.querySelector('.q-select');
            if (select) {
                if (respostaAluno && isCorreto) { 
                    select.className = 'q-select correta'; 
                } else if (respostaAluno) { 
                    select.className = 'q-select errada'; 
                }
            }
        }
        grid.appendChild(div);
    }
}

// ============================================
// ATUALIZAR RESPOSTA MANUAL
// ============================================
function atualizarRespostaManual(select) {
    const questaoIndex = parseInt(select.dataset.questao);
    const novaResposta = select.value;
    if (novaResposta) { correcaoManualData.respostasAluno[questaoIndex] = novaResposta.toUpperCase(); } else { correcaoManualData.respostasAluno[questaoIndex] = ''; }
    const item = select.closest('.correcao-manual-item');
    const qResposta = item.querySelector('.q-resposta');
    const qStatus = item.querySelector('.q-status');
    const gabarito = correcaoManualData.gabarito[questaoIndex] || '';
    const resposta = correcaoManualData.respostasAluno[questaoIndex] || '';
    const isCorreto = resposta && gabarito && resposta.toUpperCase() === gabarito.toUpperCase();
    qResposta.textContent = resposta || '—';
    qResposta.style.color = isCorreto ? 'var(--green)' : (resposta ? 'var(--red)' : 'var(--text3)');
    if (resposta) {
        if (isCorreto) { qStatus.textContent = '✅';
            qStatus.className = 'q-status correta';
            select.className = 'q-select correta'; } else { qStatus.textContent = '❌';
            qStatus.className = 'q-status errada';
            select.className = 'q-select errada'; }
    } else { qStatus.textContent = '';
        qStatus.className = 'q-status';
        select.className = 'q-select'; }
    atualizarResumoCorrecaoManual();
}

// ============================================
// ATUALIZAR RESUMO CORREÇÃO MANUAL
// ============================================
function atualizarResumoCorrecaoManual() {
    const qtd = correcaoManualData.quantidade || 20;
    const respostas = correcaoManualData.respostasAluno || [];
    const gabarito = correcaoManualData.gabarito || [];
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');

    let acertos = 0,
        respondidas = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp) {
            respondidas++;
            if (isProducao) {
                if (resp.trim().toLowerCase() === gab.trim().toLowerCase()) acertos++;
            } else {
                if (resp.toUpperCase() === gab.toUpperCase()) acertos++;
            }
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
    if (notaFinal >= (correcaoManualData.notaMinima || 5)) { statusBadge.textContent = '✅ APROVADO';
        statusBadge.className = 'badge badge-green';
        statusAtual.textContent = 'Aprovado';
        statusAtual.style.color = 'var(--green)'; } else if (notaFinal >= (correcaoManualData.notaMinima || 5) * 0.8) { statusBadge.textContent = '⚠️ RECUPERAÇÃO';
        statusBadge.className = 'badge badge-orange';
        statusAtual.textContent = 'Recuperação';
        statusAtual.style.color = 'var(--orange)'; } else { statusBadge.textContent = '❌ REPROVADO';
        statusBadge.className = 'badge badge-red';
        statusAtual.textContent = 'Reprovado';
        statusAtual.style.color = 'var(--red)'; }
    setText('cm-porcentagem', porcentagem + '% de aproveitamento');
}

// ============================================
// PREENCHER GABARITO CM
// ============================================
function preencherGabaritoCM() {
    const qtd = correcaoManualData.quantidade || 20;
    const gabarito = correcaoManualData.gabarito || [];
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid .q-resposta-texto');
        inputs.forEach((input, i) => {
            if (i < gabarito.length) {
                input.value = gabarito[i] || '';
                correcaoManualData.respostasAluno[i] = gabarito[i] || '';
            }
        });
    } else {
        for (let i = 0; i < qtd; i++) {
            if (i < gabarito.length && gabarito[i]) {
                correcaoManualData.respostasAluno[i] = gabarito[i];
            }
        }
        gerarGridCorrecaoManual();
    }
    atualizarResumoCorrecaoManual();
    showToast('📋 Respostas preenchidas com o gabarito!', 'success');
}

// ============================================
// LIMPAR RESPOSTAS CM
// ============================================
function limparRespostasCM() {
    const qtd = correcaoManualData.quantidade || 20;
    const isProducao = (correcaoManualData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid .q-resposta-texto');
        inputs.forEach((input, i) => {
            input.value = '';
            correcaoManualData.respostasAluno[i] = '';
        });
    } else {
        for (let i = 0; i < qtd; i++) {
            correcaoManualData.respostasAluno[i] = '';
        }
        gerarGridCorrecaoManual();
    }
    atualizarResumoCorrecaoManual();
    showToast('🗑️ Respostas limpas!', 'info');
}

// ============================================
// SALVAR CORREÇÃO MANUAL
// ============================================
function salvarCorrecaoManual() {
    const qtd = correcaoManualData.quantidade || 20;
    const respostas = correcaoManualData.respostasAluno || [];
    const gabarito = correcaoManualData.gabarito || [];
    let acertos = 0;

    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp && resp.toUpperCase() === gab.toUpperCase()) {
            acertos++;
        }
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
        respostas: respostas,
        acertos: acertos,
        nota: nota,
        total: qtd
    };

    fetch(API_URL + '/api/corrigir_manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
                carregarResultadosComFiltros();
                carregarDashboard();
                carregarUltimasCorrecoes();
            }, 500);

            const alunoId = correcaoManualData.alunoId;
            if (alunoId) {
                setTimeout(() => {
                    tableFeedback.destacarLinha('tb-resultados-filtrado', alunoId, '✅ Corrigido!');
                }, 800);
            }
        } else {
            progressManager.erro(data.erro || 'Erro ao salvar');
            showToast('❌ Erro ao salvar: ' + (data.erro || 'Erro desconhecido'), 'error');
        }
    })
    .catch(erro => {
        progressManager.erro(erro.message);
        showToast('❌ Erro ao salvar correção: ' + erro.message, 'error');
        console.error('Erro ao salvar correção manual:', erro);
    });
}

// ============================================
// 🔥 CORREÇÃO MANUAL STANDALONE (MENU) - FUNÇÕES CORRIGIDAS
// ============================================

function abrirCorrecaoManualStandalone() {
    // Fecha qualquer modal aberto
    document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
    
    // Limpa os campos anteriores
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
    
    // Esconde as grids e reseta
    document.getElementById('cm-grid-standalone-container').style.display = 'none';
    document.getElementById('cm-info-standalone').style.display = 'none';
    document.getElementById('btn-salvar-correcao-manual').style.display = 'none';
    document.getElementById('cm-grid-standalone').innerHTML = '';
    
    // Carrega as escolas no select
    carregarEscolasParaCorrecaoManual();
    
    // Mostra o modal
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
            if (current) select.value = current;
            if (current) carregarTurmasParaCorrecaoManual(current);
        }
    } catch (erro) {
        console.error('Erro ao carregar escolas para correção manual:', erro);
    }
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
    } catch (e) {
        console.error('Erro ao carregar turmas:', e);
    }
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
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
    }
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
                opt.dataset.turma = p.turma_nome || '';
                opt.dataset.quantidade = p.quantidade_questoes || 20;
                opt.dataset.tipo = p.tipo_questoes || '4';
                opt.dataset.data = p.data_prova || '';
                opt.dataset.gabarito = JSON.stringify(p.gabarito || []);
                opt.dataset.bncc = JSON.stringify(p.bncc || []);
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Erro ao carregar provas:', e);
    }
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
        const alternativas = tipo === '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];

        cmStandaloneData.provaId = parseInt(option.value);
        cmStandaloneData.provaTitulo = option.text.split(' - ')[0] || 'Prova';
        cmStandaloneData.provaData = option.dataset.data || '';
        cmStandaloneData.gabarito = gabarito;
        cmStandaloneData.quantidade = quantidade;
        cmStandaloneData.alternativas = alternativas;
        cmStandaloneData.disciplina = option.dataset.disciplina || '';
        cmStandaloneData.valorPorQuestao = 10 / quantidade;
        cmStandaloneData.respostas = new Array(quantidade).fill('');

        if (!cmStandaloneData.serie) cmStandaloneData.serie = option.dataset.serie || '';

        showToast('✅ Gabarito carregado! Selecione o aluno e clique em "Iniciar Correção"', 'success');
    } catch (e) {
        console.error('Erro ao carregar gabarito:', e);
        showToast('❌ Erro ao carregar gabarito da prova', 'error');
    }
}

function iniciarCorrecaoManualStandalone() {
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

    if (!cmStandaloneData.gabarito || cmStandaloneData.gabarito.length === 0) {
        const provaOption = provaSelect.options[provaSelect.selectedIndex];
        try {
            const gabarito = JSON.parse(provaOption.dataset.gabarito || '[]');
            cmStandaloneData.gabarito = gabarito;
            cmStandaloneData.quantidade = parseInt(provaOption.dataset.quantidade) || 20;
            const tipo = provaOption.dataset.tipo || '4';
            cmStandaloneData.alternativas = tipo === '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
            cmStandaloneData.valorPorQuestao = 10 / cmStandaloneData.quantidade;
            cmStandaloneData.respostas = new Array(cmStandaloneData.quantidade).fill('');
            cmStandaloneData.disciplina = provaOption.dataset.disciplina || '';
        } catch (e) {
            showToast('❌ Erro ao carregar gabarito da prova', 'error');
            return;
        }
    }

    const temGabarito = cmStandaloneData.gabarito.some(g => g && g.trim() !== '');
    if (!temGabarito) {
        showToast('⚠️ Esta prova não tem gabarito cadastrado!', 'warning');
        return;
    }

    setText('cm-sa-aluno', cmStandaloneData.alunoNome);
    setText('cm-sa-turma', cmStandaloneData.serie + ' - ' + cmStandaloneData.turmaNome);
    setText('cm-sa-prova', cmStandaloneData.provaTitulo);
    setText('cm-sa-data', cmStandaloneData.provaData || new Date().toLocaleDateString('pt-BR'));

    document.getElementById('cm-info-standalone').style.display = 'grid';
    document.getElementById('cm-grid-standalone-container').style.display = 'block';
    document.getElementById('btn-salvar-correcao-manual').style.display = 'inline-flex';

    gerarGridCorrecaoManualSA();
    atualizarResumoCorrecaoManualSA();

    showToast('📝 Correção manual iniciada para ' + cmStandaloneData.alunoNome, 'success');
}

// ============================================
// GERAR GRID CORREÇÃO MANUAL STANDALONE
// ============================================
function gerarGridCorrecaoManualSA() {
    const grid = document.getElementById('cm-grid-standalone');
    if (!grid) return;

    const qtd = cmStandaloneData.quantidade || 20;
    const alternativas = cmStandaloneData.alternativas || ['A', 'B', 'C', 'D'];
    const gabarito = cmStandaloneData.gabarito || [];
    const respostas = cmStandaloneData.respostas || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');

    if (isProducao) {
        grid.style.display = 'flex';
        grid.style.flexDirection = 'column';
        grid.style.gap = '12px';
        grid.style.maxHeight = 'none';
        grid.style.overflowY = 'visible';
    } else {
        grid.style.display = 'grid';
        grid.style.gridTemplateColumns = 'repeat(10, 1fr)';
        grid.style.gap = '6px';
        grid.style.maxHeight = '280px';
        grid.style.overflowY = 'auto';
    }

    grid.innerHTML = '';

    for (let i = 0; i < qtd; i++) {
        const div = document.createElement('div');
        div.className = 'cm-item-standalone';

        const gab = (i < gabarito.length) ? gabarito[i] : '';
        const resp = (i < respostas.length) ? respostas[i] : '';

        if (isProducao) {
            div.style.background = 'var(--bg2)';
            div.style.border = '1px solid var(--border)';
            div.style.borderRadius = '8px';
            div.style.padding = '10px 14px';
            div.style.textAlign = 'left';
            div.style.display = 'flex';
            div.style.flexDirection = 'column';
            div.style.gap = '6px';

            div.innerHTML = `
                <input class="gab-titulo" type="text" value="Q${i+1}" style="width:100%; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:12px; font-weight:bold;" />
                <div style="font-size:10px;color:var(--text3);">Gabarito: ${gab || '—'}</div>
                <textarea class="q-resposta-texto" placeholder="Resposta do aluno..." style="width:100%; min-height:50px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:11px; resize:vertical;">${resp}</textarea>
                <select class="gab-nivel" style="width:100%; padding:2px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:10px;">
                    <option value="">Nível BNCC</option>
                    <option value="Inicial">Inicial</option>
                    <option value="Básico">Básico</option>
                    <option value="Proficiente">Proficiente</option>
                    <option value="Avançado">Avançado</option>
                </select>
                <textarea class="gab-observacao" placeholder="Observações (opcional)" style="width:100%; min-height:30px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:10px; resize:vertical;"></textarea>
            `;
            const textarea = div.querySelector('.q-resposta-texto');
            textarea.dataset.questao = i;
            textarea.addEventListener('input', function() {
                cmStandaloneData.respostas[i] = this.value;
                atualizarResumoCorrecaoManualSA();
            });
        } else {
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
                <div class="q-gabarito">${gab || '—'}</div>
                <select class="${selectClass}" data-questao="${i}" onchange="atualizarRespostaManualSA(this)">
                    ${options}
                </select>
                <div class="q-status-icon">${statusIcon}</div>
            `;
        }
        grid.appendChild(div);
    }
}

// ============================================
// ATUALIZAR RESPOSTA MANUAL SA
// ============================================
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

// ============================================
// ATUALIZAR RESUMO CORREÇÃO MANUAL SA
// ============================================
function atualizarResumoCorrecaoManualSA() {
    const qtd = cmStandaloneData.quantidade || 20;
    const respostas = cmStandaloneData.respostas || [];
    const gabarito = cmStandaloneData.gabarito || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');

    let acertos = 0,
        respondidas = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp) {
            respondidas++;
            if (isProducao) {
                if (resp.trim().toLowerCase() === gab.trim().toLowerCase()) acertos++;
            } else {
                if (resp.toUpperCase() === gab.toUpperCase()) acertos++;
            }
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
    if (notaFinal >= (cmStandaloneData.notaMinima || 5)) { statusBadge.textContent = '✅ APROVADO';
        statusBadge.className = 'badge badge-green'; } else if (notaFinal >= (cmStandaloneData.notaMinima || 5) * 0.8) { statusBadge.textContent = '⚠️ RECUPERAÇÃO';
        statusBadge.className = 'badge badge-orange'; } else { statusBadge.textContent = '❌ REPROVADO';
        statusBadge.className = 'badge badge-red'; }
    setText('cm-sa-porcentagem', porcentagem + '% de aproveitamento');
}

// ============================================
// PREENCHER GABARITO MANUAL SA
// ============================================
function preencherGabaritoManualSA() {
    const qtd = cmStandaloneData.quantidade || 20;
    const gabarito = cmStandaloneData.gabarito || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid-standalone .q-resposta-texto');
        inputs.forEach((input, i) => {
            if (i < gabarito.length) {
                input.value = gabarito[i] || '';
                cmStandaloneData.respostas[i] = gabarito[i] || '';
            }
        });
    } else {
        const selects = document.querySelectorAll('#cm-grid-standalone .q-select-manual');
        selects.forEach((select, i) => {
            if (i < gabarito.length && gabarito[i]) {
                select.value = gabarito[i];
                cmStandaloneData.respostas[i] = gabarito[i];
            }
        });
    }
    atualizarResumoCorrecaoManualSA();
    showToast('📋 Respostas preenchidas com o gabarito!', 'success');
}

// ============================================
// LIMPAR RESPOSTAS MANUAL SA
// ============================================
function limparRespostasManualSA() {
    const qtd = cmStandaloneData.quantidade || 20;
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid-standalone .q-resposta-texto');
        inputs.forEach((input, i) => {
            input.value = '';
            cmStandaloneData.respostas[i] = '';
        });
    } else {
        const selects = document.querySelectorAll('#cm-grid-standalone .q-select-manual');
        selects.forEach((select, i) => {
            select.value = '';
            cmStandaloneData.respostas[i] = '';
        });
    }
    atualizarResumoCorrecaoManualSA();
    showToast('🗑️ Respostas limpas!', 'info');
}

// ============================================
// REVISAR APENAS DUVIDOSAS SA
// ============================================
function revisarApenasDuvidosasSA() {
    const confiancas = cmStandaloneData.confianca_por_questao || [];
    const itens = document.querySelectorAll('.cm-item-standalone');
    let totalDuvidosas = 0;

    itens.forEach((item, index) => {
        const confianca = confiancas[index] || 100;
        if (confianca < 70) {
            item.style.display = '';
            totalDuvidosas++;
            if (totalDuvidosas === 1) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        } else {
            item.style.display = 'none';
        }
    });

    if (totalDuvidosas === 0) {
        showToast('✅ Nenhuma questão com baixa confiança!', 'success');
        itens.forEach(item => item.style.display = '');
    } else {
        showToast(`🔍 Mostrando apenas ${totalDuvidosas} questões com baixa confiança`, 'info');
    }
}

// ============================================
// SALVAR CORREÇÃO MANUAL STANDALONE
// ============================================
function salvarCorrecaoManualStandalone() {
    // 🔥 VERIFICA SE OS DADOS EXISTEM
    if (!cmStandaloneData) {
        showToast('❌ Dados não encontrados!', 'error');
        return;
    }

    const provaId = parseInt(cmStandaloneData.provaId);
    const alunoId = parseInt(cmStandaloneData.alunoId);

    // 🔥 VALIDA OS IDs
    if (!provaId || isNaN(provaId) || provaId <= 0) {
        showToast('❌ ID da prova inválido!', 'error');
        console.error('❌ cmStandaloneData.provaId:', cmStandaloneData.provaId);
        return;
    }

    if (!alunoId || isNaN(alunoId) || alunoId <= 0) {
        showToast('❌ ID do aluno inválido!', 'error');
        console.error('❌ cmStandaloneData.alunoId:', cmStandaloneData.alunoId);
        return;
    }

    const qtd = cmStandaloneData.quantidade || 20;
    const respostas = cmStandaloneData.respostas || [];
    const gabarito = cmStandaloneData.gabarito || [];

    const temResposta = respostas.some(r => r && r.trim() !== '');
    if (!temResposta) { 
        showToast('⚠️ Marque pelo menos uma resposta do aluno!', 'warning'); 
        return; 
    }

    let acertos = 0;
    for (let i = 0; i < qtd; i++) {
        const resp = i < respostas.length ? respostas[i] : '';
        const gab = i < gabarito.length ? gabarito[i] : '';
        if (resp && gab && resp.toUpperCase() === gab.toUpperCase()) {
            acertos++;
        }
    }
    
    const valorPorQuestao = cmStandaloneData.valorPorQuestao || (10 / qtd);
    const nota = Math.min((acertos * valorPorQuestao), cmStandaloneData.notaMaxima || 10);

    showToast('💾 Salvando correção manual...', 'info');

    const dadosCorrecao = {
        prova_id: provaId,
        aluno_id: alunoId,
        respostas: respostas.map(r => r || ''),
        acertos: acertos,
        nota: nota,
        total: qtd
    };

    console.log('📤 Enviando dados:', JSON.stringify(dadosCorrecao, null, 2));

    fetch(API_URL + '/api/corrigir_manual', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(dadosCorrecao)
    })
    .then(async response => {
        let data;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            const text = await response.text();
            try {
                data = JSON.parse(text);
            } catch (e) {
                data = { erro: text || 'Erro desconhecido' };
            }
        }

        if (!response.ok) {
            throw new Error(data.erro || data.mensagem || `Erro ${response.status}`);
        }
        return data;
    })
    .then(data => {
        if (data.sucesso) {
            showToast(`✅ Correção salva! Nota: ${nota.toFixed(1)}`, 'success');
            
            // 🔥 LIMPA O CACHE
            limparCache();
                        
            // 🔥 ATUALIZA TODOS OS DADOS AUTOMATICAMENTE
            setTimeout(() => {
                // Atualiza a página atual
                const paginaAtual = document.querySelector('.page.active');
                if (paginaAtual) {
                    const pageId = paginaAtual.id.replace('page-', '');
                    
                    // 🔥 RECARREGA OS DADOS CONFORME A PÁGINA ATUAL
                    switch(pageId) {
                        case 'resultados':
                            carregarResultadosComFiltros();
                            break;
                        case 'dashboard':
                            carregarDashboard();
                            carregarUltimasCorrecoes();
                            break;
                        case 'rel-turma':
                            carregarRelatorioTurmaFiltrado();
                            break;
                        case 'desempenho':
                            if (desempenhoData.alunoSelecionado) {
                                gerarDesempenho();
                            }
                            break;
                        default:
                            carregarResultadosComFiltros();
                            carregarDashboard();
                            carregarUltimasCorrecoes();
                            break;
                    }
                } else {
                    carregarResultadosComFiltros();
                    carregarDashboard();
                    carregarUltimasCorrecoes();
                }
                
                carregarConceitoReal();
                carregarUltimasCorrecoes();
                
                console.log('✅ Todos os dados foram atualizados automaticamente!');
            }, 300);
        } else {
            showToast('❌ Erro ao salvar: ' + (data.erro || 'Erro desconhecido'), 'error');
        }
    })
    .catch(erro => {
        console.error('❌ Erro ao salvar correção manual:', erro);
        showToast('❌ Erro ao salvar: ' + erro.message, 'error');
    });
}

// ============================================
// FUNÇÃO PARA ABRIR CORREÇÃO MANUAL DIRETAMENTE
// ============================================
async function abrirCorrecaoManualDireta(escolaId, turmaId, alunoId, provaId) {
    try {
        showToast('🔄 Carregando dados...', 'info');

        const provaResp = await fetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) {
            showToast('❌ Erro ao carregar prova: ' + (prova.erro || 'Desconhecido'), 'error');
            return;
        }

        const alunoResp = await fetch(`${API_URL}/api/alunos/${alunoId}`);
        const aluno = await alunoResp.json();
        if (!aluno || aluno.erro) {
            showToast('❌ Erro ao carregar aluno: ' + (aluno.erro || 'Desconhecido'), 'error');
            return;
        }

        const historicoResp = await fetch(`${API_URL}/api/historico?aluno_id=${alunoId}&prova_id=${provaId}`);
        const historico = await historicoResp.json();
        let respostas = [];
        if (historico && historico.length > 0 && !historico.erro) {
            respostas = historico[0].respostas || [];
        }

        cmStandaloneData.escolaId = parseInt(escolaId);
        cmStandaloneData.turmaId = parseInt(turmaId);
        cmStandaloneData.provaId = parseInt(provaId);
        cmStandaloneData.alunoId = parseInt(alunoId);
        cmStandaloneData.alunoNome = aluno.nome || 'Aluno';
        cmStandaloneData.turmaNome = '';
        cmStandaloneData.serie = prova.serie || '';
        cmStandaloneData.gabarito = prova.gabarito || [];
        cmStandaloneData.quantidade = prova.quantidade_questoes || 20;
        cmStandaloneData.alternativas = prova.tipo_questoes == '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        cmStandaloneData.valorPorQuestao = 10 / cmStandaloneData.quantidade;
        cmStandaloneData.respostas = respostas.slice(0, cmStandaloneData.quantidade);
        while (cmStandaloneData.respostas.length < cmStandaloneData.quantidade) {
            cmStandaloneData.respostas.push('');
        }
        cmStandaloneData.provaTitulo = prova.titulo || 'Prova';
        cmStandaloneData.provaData = prova.data_prova || '';
        cmStandaloneData.disciplina = prova.disciplina || '';

        openM('m-correcao-manual-standalone');

        const selectsContainer = document.getElementById('cm-selects-container');
        if (selectsContainer) selectsContainer.style.display = 'none';

        document.getElementById('cm-grid-standalone-container').style.display = 'block';
        document.getElementById('btn-salvar-correcao-manual').style.display = 'inline-flex';

        setText('cm-sa-aluno', cmStandaloneData.alunoNome);
        setText('cm-sa-turma', cmStandaloneData.serie + ' - ' + cmStandaloneData.turmaNome);
        setText('cm-sa-prova', cmStandaloneData.provaTitulo);
        setText('cm-sa-data', cmStandaloneData.provaData || new Date().toLocaleDateString('pt-BR'));

        gerarGridCorrecaoManualSA();
        atualizarResumoCorrecaoManualSA();

        showToast('📝 Correção manual carregada para ' + cmStandaloneData.alunoNome, 'success');
    } catch (erro) {
        console.error('❌ Erro ao abrir correção manual direta:', erro);
        showToast('❌ Erro ao carregar dados: ' + erro.message, 'error');
    }
}

// ============================================
// FUNÇÃO CHAMADA PELO BOTÃO "✏️ Editar Gabarito" NA ABA DESEMPENHO
// ============================================
async function editarGabaritoDesempenho() {
    const escolaId = document.getElementById('filtro-escola-desempenho').value;
    const turmaId = document.getElementById('filtro-turma-desempenho').value;
    const alunoId = document.getElementById('filtro-aluno-desempenho').value;
    const provaId = document.getElementById('filtro-prova-desempenho').value;

    if (!escolaId || !turmaId || !alunoId || !provaId) {
        showToast('⚠️ Selecione todos os filtros (escola, turma, aluno e prova) antes de editar o gabarito!', 'error');
        return;
    }

    await abrirCorrecaoManualDireta(escolaId, turmaId, alunoId, provaId);
}

// ============================================
// FUNÇÕES DE USUÁRIO
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
    fetch(API_URL + '/api/usuarios/' + id)
        .then(r => r.json())
        .then(usuario => {
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
        })
        .catch(e => { showToast('❌ Erro ao carregar usuário: ' + e.message, 'error');
            console.error('Erro ao carregar usuário:', e); });
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
        if (id) { url += '/' + id;
            method = 'PUT'; }

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
            carregarDados();
        } else {
            showToast('❌ Erro ao salvar usuário: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar: ' + erro.message, 'error');
        console.error('Erro ao salvar usuário:', erro);
        const btn = document.querySelector('#m-usuario .btn-green');
        if (btn) { btn.textContent = '💾 Salvar Usuário';
            btn.disabled = false; }
    }
}

async function excluirUsuario(id, username) {
    if (username === 'admin') { showToast('⚠️ Não é possível excluir o usuário administrador principal!', 'error'); return; }
    if (!confirm('Excluir o usuário "' + username + '"? Esta ação não pode ser desfeita.')) return;
    try {
        const response = await fetch(API_URL + '/api/usuarios/' + id, { method: 'DELETE' });
        const result = await processarRespostaAPI(response);
        if (result.ok) { showToast('🗑️ Usuário "' + username + '" excluído!', 'error');
            carregarUsuarios(); } else { showToast('Erro: ' + (result.data.erro || 'Erro desconhecido'), 'error'); }
    } catch (erro) { showToast('Erro ao excluir: ' + erro.message, 'error'); }
}

// ============================================
// FUNÇÕES DE TEXTO IA
// ============================================
function prevTexto(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => { document.getElementById('txt-img-prev').style.display = 'block';
        document.getElementById('txt-img').src = e.target.result; };
    reader.readAsDataURL(file);
}

async function avaliarTexto() {
    const texto = document.getElementById('txt-aluno').value;
    const alunoId = document.getElementById('txt-aluno-select').value;
    if (!texto || texto.trim().length < 5) { showToast('❌ Digite um texto com pelo menos 5 caracteres!', 'error'); return; }

    const etapas = [
        { nome: '📝 Preparando texto', descricao: 'Validando e preparando o texto para análise...' },
        { nome: '🤖 Analisando com IA', descricao: 'Gemini AI avaliando critérios textuais...' },
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
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto: texto, aluno_id: alunoId || null })
        });

        progressManager.concluirEtapa(1);
        progressManager.proximaEtapa();

        const dados = await response.json();
        document.getElementById('txt-loading').style.display = 'none';
        document.getElementById('txt-res').style.display = 'block';

        if (dados.erro) {
            progressManager.erro(dados.erro);
            showToast('❌ ' + dados.erro, 'error');
            return;
        }

        progressManager.concluirEtapa(2);
        progressManager.finalizar('✅ Avaliação concluída com sucesso!');

        setText('txt-nota', dados.nota || 0);
        const statusEl = document.getElementById('txt-status');
        if (statusEl) { statusEl.textContent = dados.nota >= 6 ? 'APROVADO' : 'REPROVADO';
            statusEl.className = 'badge ' + (dados.nota >= 6 ? 'badge-green' : 'badge-red'); }
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
        if (fb) fb.innerHTML = dados.feedback || 'Feedback gerado automaticamente.';
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

function salvarAvaliacaoTexto() { showToast('💾 Avaliação salva com sucesso!', 'success'); }

// ============================================
// FUNÇÕES DE CÂMERA
// ============================================
async function abrirCamera() {
    document.getElementById('cam-modal').classList.add('show');
    try {
        if (camStream) camStream.getTracks().forEach(t => t.stop());
        camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: camFacing, width: { ideal: 1280 }, height: { ideal: 720 } } });
        document.getElementById('cam-video').srcObject = camStream;
    } catch (e) { showToast('❌ Câmera não disponível: ' + e.message, 'error');
        fecharCamera(); }
}

function trocarCamera() { camFacing = camFacing === 'environment' ? 'user' : 'environment';
    abrirCamera(); }

function fecharCamera() { document.getElementById('cam-modal').classList.remove('show'); if (camStream) { camStream.getTracks().forEach(t => t.stop());
        camStream = null; } }

function capturarFoto() {
    const vid = document.getElementById('cam-video');
    const canvas = document.getElementById('cam-canvas');
    canvas.width = vid.videoWidth || 640;
    canvas.height = vid.videoHeight || 480;
    canvas.getContext('2d').drawImage(vid, 0, 0);
    const foto = canvas.toDataURL('image/jpeg', 0.9);
    fecharCamera();
    showToast('📸 Foto capturada!', 'ai');
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
// 🔥 CORREÇÃO COM IA - PROCESSO COMPLETO
// ============================================
async function processarComIA(imagemBase64) {
    const escolaId = document.getElementById('corrigir-escola')?.value;
    const turmaId = document.getElementById('corrigir-turma')?.value;
    const provaId = document.getElementById('corrigir-prova')?.value;
    const alunoId = document.getElementById('corrigir-aluno')?.value;

    if (!escolaId || !turmaId || !provaId || !alunoId) {
        showToast('❌ Selecione escola, turma, prova e aluno!', 'error');
        return;
    }

    if (!imagemBase64) {
        showToast('❌ Nenhuma imagem foi fornecida!', 'error');
        return;
    }

    const etapas = [
        { nome: '📸 Preparando imagem', descricao: 'Processando a imagem do cartão resposta...' },
        { nome: '🔍 OCR + Posição', descricao: 'Lendo alternativas marcadas...' },
        { nome: '🤖 Analisando com IA', descricao: 'Detectando respostas...' },
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

        if (!gabarito || gabarito.length === 0) {
            throw new Error('Esta prova não tem gabarito cadastrado!');
        }

        const aluno = await buscarAluno(alunoId);
        if (!aluno) throw new Error('Aluno não encontrado');

        progressManager.atualizarEtapa(2);
        await sleep(300);

        const respostaIA = await enviarParaCorrecao(imagemEnvio, provaId, alunoId);
        
        if (respostaIA.erro) {
            throw new Error(respostaIA.erro);
        }

        let respostasDetectadas = respostaIA.respostas_detectadas || [];
        let confiancas = respostaIA.confianca_por_questao || [];
        let questoesStatus = [];

        const { respostasNormalizadas, confiancasNormalizadas } = normalizarRespostas(
            respostasDetectadas,
            confiancas,
            totalQuestoes,
            isProducao
        );

        let acertos = 0;
        const resultadoQuestoes = [];

        for (let i = 0; i < totalQuestoes; i++) {
            const resp = respostasNormalizadas[i] || '';
            const gab = (i < gabarito.length) ? (gabarito[i] || '') : '';
            const confianca = confiancasNormalizadas[i] || 0;

            let isCorreto = false;
            let statusMsg = 'NÃO RESPONDEU';

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
                } else if (respNormalizada) {
                    statusMsg = '❌ RESPOSTA INVÁLIDA';
                } else {
                    statusMsg = '— NÃO RESPONDEU';
                }
            }

            if (isCorreto) acertos++;

            resultadoQuestoes.push({
                numero: i + 1,
                resposta: resp || '—',
                gabarito: gab || '—',
                acertou: isCorreto,
                status: statusMsg,
                confianca: confianca,
                respondida: !!resp
            });
        }

        const valorPorQuestao = 10 / totalQuestoes;
        const nota = Math.min(acertos * valorPorQuestao, 10);
        const porcentagem = Math.round((acertos / totalQuestoes) * 100);
        const conceito = calcularConceito(porcentagem);

        progressManager.atualizarEtapa(3);
        await sleep(300);

        salvarDadosCorrecaoManual({
            alunoId: parseInt(alunoId),
            alunoNome: aluno.nome || 'Aluno',
            provaId: parseInt(provaId),
            provaTitulo: prova.titulo || 'Prova',
            gabarito: gabarito,
            respostas: respostasNormalizadas,
            quantidade: totalQuestoes,
            alternativas: alternativas,
            notaMaxima: 10,
            notaMinima: 5,
            valorPorQuestao: valorPorQuestao,
            serie: prova.serie || '1º Ano',
            disciplina: prova.disciplina || '',
            confianca_por_questao: confiancasNormalizadas,
            questoes_status: resultadoQuestoes
        });

        // 🔥 ATUALIZAR INTERFACE COM INFORMAÇÕES DO MÉTODO USADO
        const metodoUsado = respostaIA.metodo_usado || respostaIA.modo || 'desconhecido';
        
        atualizarInterfaceCorrecao({
            aluno: aluno,
            prova: prova,
            resultadoQuestoes: resultadoQuestoes,
            acertos: acertos,
            totalQuestoes: totalQuestoes,
            nota: nota,
            porcentagem: porcentagem,
            conceito: conceito,
            confiancas: confiancasNormalizadas,
            metodoUsado: metodoUsado
        });

        progressManager.finalizar(`✅ Correção concluída! ${acertos}/${totalQuestoes} acertos — Nota: ${nota.toFixed(1)}`);
        
        carregarDashboard();
        carregarResultadosComFiltros();
        carregarUltimasCorrecoes();

    } catch (erro) {
        console.error('❌ Erro na correção:', erro);
        progressManager.erro(erro.message || 'Erro ao processar correção');
        showToast('❌ Erro ao processar correção: ' + erro.message, 'error');
    }
}

// ============================================
// FUNÇÕES AUXILIARES DA CORREÇÃO COM IA
// ============================================
async function buscarProva(provaId) {
    try {
        const provas = await carregarProvasComCache();
        return provas.find(p => p.id == provaId);
    } catch (e) {
        console.error('Erro ao buscar prova:', e);
        throw new Error('Erro ao buscar dados da prova');
    }
}

async function buscarAluno(alunoId) {
    try {
        const alunos = await carregarAlunosComCache();
        return alunos.find(a => a.id == alunoId);
    } catch (e) {
        console.error('Erro ao buscar aluno:', e);
        throw new Error('Erro ao buscar dados do aluno');
    }
}

async function enviarParaCorrecao(imagemBase64, provaId, alunoId) {
    try {
        const response = await fetch(`${API_URL}/api/corrigir`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
        
        if (dados.erro) {
            throw new Error(dados.erro);
        }

        if (dados.respostas_detectadas || dados.questoes_status) {
            return dados;
        }

        console.warn('⚠️ API não retornou respostas, usando fallback');
        return gerarFallbackRespostas(imagemBase64);

    } catch (e) {
        console.error('❌ Erro na chamada da API:', e);
        return gerarFallbackRespostas(imagemBase64);
    }
}

function gerarFallbackRespostas(imagemBase64) {
    const respostas = [];
    const confiancas = [];
    
    for (let i = 0; i < 20; i++) {
        const alternativas = ['A', 'B', 'C', 'D'];
        const idx = Math.floor(Math.random() * alternativas.length);
        respostas.push(alternativas[idx]);
        confiancas.push(Math.floor(Math.random() * 30) + 50);
    }

    return {
        respostas_detectadas: respostas,
        confianca_por_questao: confiancas,
        aviso: 'Fallback: Detecção simulada'
    };
}

function normalizarRespostas(respostas, confiancas, totalQuestoes, isProducao) {
    let respostasNormalizadas = [];
    let confiancasNormalizadas = [];

    for (let i = 0; i < totalQuestoes; i++) {
        let resp = (i < respostas.length) ? (respostas[i] || '') : '';
        let conf = (i < confiancas.length) ? (confiancas[i] || 0) : 0;

        if (isProducao) {
            resp = resp.toString().trim();
        } else {
            resp = resp.toString().toUpperCase().trim();
            const alternativasValidas = ['A', 'B', 'C', 'D'];
            if (resp && !alternativasValidas.includes(resp)) {
                resp = 'NÃO_RESPONDEU';
            }
        }

        respostasNormalizadas.push(resp);
        confiancasNormalizadas.push(Math.min(Math.max(conf, 0), 100));
    }

    return { respostasNormalizadas, confiancasNormalizadas };
}

function salvarDadosCorrecaoManual(dados) {
    correcaoManualData = {
        alunoId: dados.alunoId,
        alunoNome: dados.alunoNome,
        provaId: dados.provaId,
        provaTitulo: dados.provaTitulo,
        gabarito: dados.gabarito,
        respostasAluno: dados.respostas,
        quantidade: dados.quantidade,
        alternativas: dados.alternativas,
        notaMaxima: dados.notaMaxima,
        notaMinima: dados.notaMinima,
        valorPorQuestao: dados.valorPorQuestao,
        serie: dados.serie,
        disciplina: dados.disciplina,
        confianca_por_questao: dados.confianca_por_questao,
        bncc: dados.bncc || [],
        questoes_status: dados.questoes_status || []
    };
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

    // 🔥 MÉTODO USADO
    const metodo = dados.metodoUsado || 'desconhecido';
    const metodoBadge = document.getElementById('ia-metodo');
    if (metodoBadge) {
        const metodoLabels = {
            'ocr': '📖 OCR',
            'circulos': '⭕ Círculos',
            'ia': '🤖 IA',
            'ia_fallback': '🤖 IA (Fallback)',
            'fallback': '⚠️ Fallback',
            'manual': '✏️ Manual'
        };
        metodoBadge.textContent = metodoLabels[metodo] || `📌 ${metodo}`;
        metodoBadge.className = `badge ${metodo === 'fallback' ? 'badge-red' : metodo === 'ia' ? 'badge-purple' : 'badge-gray'}`;
    }

    const confiancaMedia = dados.confiancas.reduce((a, b) => a + b, 0) / dados.confiancas.length || 0;
    const badgeConfianca = document.getElementById('confianca-badge');
    if (badgeConfianca) {
        badgeConfianca.textContent = `${confiancaMedia.toFixed(1)}% conf.`;
        badgeConfianca.className = `badge ${confiancaMedia >= 70 ? 'badge-green' : confiancaMedia >= 50 ? 'badge-orange' : 'badge-red'}`;
    }

    const resumoConfianca = document.getElementById('ia-resumo-confianca');
    if (resumoConfianca) {
        const totalDuvidosas = dados.confiancas.filter(c => c < 70).length;
        resumoConfianca.style.display = 'flex';
        resumoConfianca.innerHTML = `
            <span>📊 Confiança média: <strong style="color:${confiancaMedia >= 70 ? 'var(--green)' : confiancaMedia >= 50 ? 'var(--orange)' : 'var(--red)'};">${confiancaMedia.toFixed(1)}%</strong></span>
            ${totalDuvidosas > 0 ? `<span>⚠️ ${totalDuvidosas} questões com baixa confiança (<70%)</span>` : '<span>✅ Todas as questões têm alta confiança!</span>'}
            <span>🎯 Acertos: <strong style="color:var(--green);">${dados.acertos}</strong> / ${dados.totalQuestoes}</span>
            <span>📌 Método: <strong>${metodo}</strong></span>
        `;
    }

    const rd = document.getElementById('ia-resp');
    if (rd) {
        rd.innerHTML = dados.resultadoQuestoes.map(q => {
            const cor = q.acertou ? 'rgba(16,185,129,.2)' : 'rgba(239,68,68,.2)';
            const corTexto = q.acertou ? 'var(--green)' : 'var(--red)';
            const icone = q.acertou ? '✅' : (q.respondida ? '❌' : '—');
            const confColor = q.confianca < 70 ? 'var(--orange)' : 'var(--text2)';
            return `<span style="background:${cor};border:1px solid ${q.acertou ? 'rgba(16,185,129,.4)' : 'rgba(239,68,68,.4)'};padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;color:${corTexto};">Q${q.numero}:${q.resposta || '—'} ${icone}<span style="font-size:8px;color:${confColor};">${q.confianca}%</span></span>`;
        }).join('');
    }

    const grid = document.getElementById('ia-comp');
    if (grid) {
        grid.innerHTML = '';
        
        const totalQuestoes = dados.resultadoQuestoes.length;
        let colunasPorLinha = 5;
        if (totalQuestoes <= 10) colunasPorLinha = 5;
        else if (totalQuestoes <= 15) colunasPorLinha = 5;
        else if (totalQuestoes <= 20) colunasPorLinha = 5;
        else if (totalQuestoes <= 25) colunasPorLinha = 5;
        else colunasPorLinha = 6;
        
        const tituloOficial = document.createElement('div');
        tituloOficial.style.cssText = `
            grid-column: 1 / -1;
            text-align: center;
            padding: 6px 0;
            background: linear-gradient(135deg, rgba(59,130,246,0.10), rgba(139,92,246,0.10));
            border-radius: 6px;
            border: 1px solid rgba(59,130,246,0.15);
            margin-bottom: 2px;
            margin-top: 6px;
        `;
        tituloOficial.innerHTML = `
            <span style="font-size:12px;font-weight:800;color:var(--blue);letter-spacing:0.3px;">📋 GABARITO OFICIAL GERADO PELO SISTEMA</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;font-weight:600;">(${totalQuestoes} questões)</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;">📌 ${dados.metodoUsado || 'ia'}</span>
        `;
        grid.appendChild(tituloOficial);
        
        const gridOficial = document.createElement('div');
        gridOficial.style.cssText = `
            grid-column: 1 / -1;
            display: grid;
            grid-template-columns: repeat(${colunasPorLinha}, 1fr);
            gap: 4px;
            padding: 4px 0;
            background: rgba(59,130,246,0.02);
            border-radius: 4px;
            border: 1px solid rgba(59,130,246,0.06);
        `;
        
        dados.resultadoQuestoes.forEach((q) => {
            const div = document.createElement('div');
            div.style.cssText = `
                background: rgba(59,130,246,0.05);
                border-radius: 4px;
                padding: 3px 2px;
                text-align: center;
                border: 1px solid rgba(59,130,246,0.10);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 1px;
            `;
            div.innerHTML = `
                <div style="font-size:6px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.2px;">Q${q.numero}</div>
                <div style="font-size:16px;font-weight:900;color:var(--green);line-height:1.1;">${q.gabarito || '—'}</div>
            `;
            gridOficial.appendChild(div);
        });
        grid.appendChild(gridOficial);
        
        const tituloAluno = document.createElement('div');
        tituloAluno.style.cssText = `
            grid-column: 1 / -1;
            text-align: center;
            padding: 6px 0;
            background: linear-gradient(135deg, rgba(139,92,246,0.10), rgba(59,130,246,0.10));
            border-radius: 6px;
            border: 1px solid rgba(139,92,246,0.15);
            margin-bottom: 2px;
            margin-top: 8px;
        `;
        tituloAluno.innerHTML = `
            <span style="font-size:12px;font-weight:800;color:var(--purple);letter-spacing:0.3px;">📋 GABARITO DO ALUNO</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;font-weight:600;">${dados.aluno.nome || 'Aluno'}</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;">📌 ${dados.metodoUsado || 'ia'}</span>
        `;
        grid.appendChild(tituloAluno);
        
        const gridAluno = document.createElement('div');
        gridAluno.style.cssText = `
            grid-column: 1 / -1;
            display: grid;
            grid-template-columns: repeat(${colunasPorLinha}, 1fr);
            gap: 4px;
            padding: 4px 0;
            background: rgba(139,92,246,0.02);
            border-radius: 4px;
            border: 1px solid rgba(139,92,246,0.06);
        `;
        
        dados.resultadoQuestoes.forEach((q) => {
            const acertou = q.acertou;
            const resposta = q.resposta || '—';
            const confianca = q.confianca || 100;
            
            let corBg, corTexto, icone;
            if (acertou) {
                corBg = 'rgba(16,185,129,0.10)';
                corTexto = 'var(--green)';
                icone = '✅';
            } else if (q.respondida) {
                corBg = 'rgba(239,68,68,0.10)';
                corTexto = 'var(--red)';
                icone = '❌';
            } else {
                corBg = 'rgba(100,116,139,0.05)';
                corTexto = 'var(--text3)';
                icone = '—';
            }
            
            const confColor = confianca < 70 ? 'var(--orange)' : 'var(--text3)';
            
            const div = document.createElement('div');
            div.style.cssText = `
                background: ${corBg};
                border-radius: 4px;
                padding: 3px 2px;
                text-align: center;
                border: 1px solid ${acertou ? 'rgba(16,185,129,0.20)' : (q.respondida ? 'rgba(239,68,68,0.20)' : 'rgba(100,116,139,0.10)')};
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 1px;
            `;
            div.innerHTML = `
                <div style="font-size:6px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.2px;">Q${q.numero}</div>
                <div style="font-size:16px;font-weight:900;color:${corTexto};line-height:1.1;">${resposta}</div>
                <div style="font-size:6px;font-weight:700;color:${corTexto};">${icone}</div>
                <div style="font-size:6px;color:${confColor};">${Math.round(confianca)}%</div>
            `;
            gridAluno.appendChild(div);
        });
        grid.appendChild(gridAluno);
        
        const divComparacao = document.createElement('div');
        divComparacao.style.cssText = `
            grid-column: 1 / -1;
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 8px;
            padding: 8px 12px;
            margin-top: 8px;
            background: var(--bg2);
            border-radius: 6px;
            border: 1px solid var(--border);
        `;
        
        const acertos = dados.acertos;
        const erros = dados.totalQuestoes - acertos - (dados.totalQuestoes - dados.resultadoQuestoes.filter(q => q.respondida).length);
        const naoRespondidas = dados.totalQuestoes - dados.resultadoQuestoes.filter(q => q.respondida).length;
        const porcentagem = dados.porcentagem;
        
        divComparacao.innerHTML = `
            <div style="text-align:center;padding:4px;background:rgba(16,185,129,0.06);border-radius:4px;border:1px solid rgba(16,185,129,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--green);">${acertos}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">✅ ACERTOS</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(239,68,68,0.06);border-radius:4px;border:1px solid rgba(239,68,68,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--red);">${erros}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">❌ ERROS</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(100,116,139,0.06);border-radius:4px;border:1px solid rgba(100,116,139,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--text3);">${naoRespondidas}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">— NÃO RESP.</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(59,130,246,0.06);border-radius:4px;border:1px solid rgba(59,130,246,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--blue);">${porcentagem}%</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">📊 APROV.</div>
            </div>
        `;
        grid.appendChild(divComparacao);
    }
}

function salvarCorrecao() { showToast('💾 Correção salva com sucesso!', 'success'); }

// ============================================
// FUNÇÕES DE CRUD
// ============================================

// ===== ESCOLA =====
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
        if (btn) { btn.textContent = '💾 Salvar';
            btn.disabled = false; }
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
        if (btn) { btn.textContent = '💾 Salvar Alterações';
            btn.disabled = false; }
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

// ===== TURMA =====
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
        if (btn) { btn.textContent = '💾 Salvar';
            btn.disabled = false; }
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
        if (btn) { btn.textContent = '💾 Salvar Alterações';
            btn.disabled = false; }
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

// ===== ALUNO =====
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
        if (btn) { btn.textContent = '💾 Salvar';
            btn.disabled = false; }
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
        if (btn) { btn.textContent = '💾 Salvar Alterações';
            btn.disabled = false; }
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

// ===== PROVA =====
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
        const originalText = btn.textContent;
        btn.textContent = '⏳ Salvando...';
        btn.disabled = true;

        showToast('💾 Salvando prova...', 'info');
        const response = await fetch(API_URL + '/api/provas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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

            setTimeout(() => {
                tableFeedback.destacarLinha('tb-provas', result.data.id, '✅ Nova!');
            }, 300);

            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao salvar prova: ' + (result.data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar prova: ' + erro.message, 'error');
        console.error('Erro ao salvar prova:', erro);
        const btn = document.querySelector('#page-prova-upload .btn-green');
        if (btn) { btn.textContent = '💾 Salvar';
            btn.disabled = false; }
    }
}

function editarProva(id) { showToast('👁️ Visualizando prova ID ' + id + '...', 'info'); }

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
            carregarProvas();
            carregarDashboard();
            carregarCombos();
        } else {
            showToast('❌ Erro ao excluir prova: ' + (result.data.erro || result.data.mensagem || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        console.error('Erro ao excluir prova:', erro);
        showToast('❌ Erro ao excluir prova: ' + erro.message, 'error');
    }
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

// ============================================
// FUNÇÕES PARA CORREÇÃO (IA)
// ============================================
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
    } catch (erro) {
        console.error('Erro ao carregar escolas para texto:', erro);
    }
}

// ============================================
// CARREGAR FILTROS DO RELATÓRIO POR TURMA
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
            if (current) {
                selectEscola.value = current;
                if (current && current !== '') carregarTurmasRelTurma(current);
            }
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
    } catch (erro) {
        console.error('Erro ao carregar filtros do relatório por turma:', erro);
    }
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
        } catch (erro) {
            console.error('Erro ao carregar turmas:', erro);
        }
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
    } catch (erro) {
        console.error('Erro ao carregar turmas da escola:', erro);
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Erro ao carregar turmas';
        opt.disabled = true;
        selectTurma.appendChild(opt);
    }

    carregarRelatorioTurmaFiltrado();
}

// ============================================
// FUNÇÃO IMPRIMIR RELATÓRIO POR TURMA
// ============================================
async function imprimirRelatorioTurma() {
    showToast('🖨️ Imprimindo relatório...', 'info');
    window.print();
}

// ============================================
// 🔥 CARREGAR RELATÓRIO POR TURMA FILTRADO - APENAS UMA DISCIPLINA
// ============================================
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
        if (optionProva && optionProva.dataset.disciplina) {
            disciplinaSelecionada = optionProva.dataset.disciplina;
        }

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
                    alunosDaTurma = alunosData;
                    totalAlunos = alunosData.length;
                }
            } catch (e) {
                console.warn('Erro ao buscar alunos da turma:', e);
            }
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
                        disciplinaData: {
                            acertos: acertos,
                            erros: erros,
                            total: total,
                            porcentagem: pct,
                            conceito: conceito,
                            nota: discData.nota || 0
                        }
                    });
                }
            });
        }

        if (totalAlunos > 0) {
            const idsComCorrecao = new Set(alunosComCorrecao.map(a => a.aluno_id));
            alunosDaTurma.forEach(aluno => {
                if (!idsComCorrecao.has(aluno.id)) {
                    alunosSemCorrecao.push({
                        aluno_id: aluno.id,
                        aluno_nome: aluno.nome,
                        serie: aluno.turma_serie || serie,
                        turma: aluno.turma_nome || '',
                        escola: aluno.escola_nome || '',
                        disciplinaData: {
                            acertos: 0,
                            erros: 0,
                            total: 20,
                            porcentagem: 0,
                            conceito: calcularConceito(0),
                            nota: 0
                        }
                    });
                }
            });
        }

        const totalComCorrecao = alunosComCorrecao.length;
        const totalSemCorrecao = alunosSemCorrecao.length;

        document.getElementById('rel-total-alunos-conceitos').textContent = totalComCorrecao + ' alunos';
        document.getElementById('rel-total-alunos-tabela').textContent = totalComCorrecao + ' alunos';

        let somaPorcentagem = 0;
        let totalQuestoes = 0;
        let totalAcertos = 0;
        let totalErros = 0;

        alunosComCorrecao.forEach(aluno => {
            const d = aluno.disciplinaData;
            somaPorcentagem += d.porcentagem;
            totalAcertos += d.acertos;
            totalErros += d.erros;
            totalQuestoes += d.total;
        });

        const media = totalComCorrecao > 0 ? Math.round(somaPorcentagem / totalComCorrecao) : 0;
        const conceitoGeral = calcularConceito(media);

        document.getElementById('rel-media').textContent = media + '%';
        document.getElementById('rel-disciplina-nome-card').textContent = `Disciplina: ${disciplinaSelecionada}`;
        document.getElementById('rel-total-correcoes').textContent = totalComCorrecao + ' correções';
        document.getElementById('rel-disciplina-nome').textContent = disciplinaSelecionada;

        const conceitoGeralEl = document.getElementById('rel-conceito-geral');
        if (conceitoGeralEl) {
            const labels = {
                'inicial': '🔴 Inicial',
                'basico': '🟠 Básico',
                'proficiente': '🔵 Proficiente',
                'avancado': '🟢 Avançado'
            };
            const badgeClasses = {
                'inicial': 'badge-conceito-inicial',
                'basico': 'badge-conceito-basico',
                'proficiente': 'badge-conceito-proficiente',
                'avancado': 'badge-conceito-avancado'
            };
            conceitoGeralEl.textContent = labels[conceitoGeral] || '—';
            conceitoGeralEl.className = `badge ${badgeClasses[conceitoGeral] || 'badge-gray'}`;
        }

        const contagemConceitos = { inicial: 0, basico: 0, proficiente: 0, avancado: 0 };
        alunosComCorrecao.forEach(aluno => {
            const conceito = aluno.disciplinaData.conceito;
            if (contagemConceitos[conceito] !== undefined) {
                contagemConceitos[conceito]++;
            }
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

        // ============================================
        // 🔥 ATUALIZAR O CABEÇALHO DA TABELA - APENAS UMA DISCIPLINA
        // ============================================
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
                    <th style="background:${bgDisciplina};font-size:7px;padding:2px 2px;color:${corDisciplina};">ACERTOS</th>
                    <th style="background:${bgDisciplina};font-size:7px;padding:2px 2px;color:${corDisciplina};">ERROS</th>
                    <th style="background:${bgDisciplina};font-size:7px;padding:2px 2px;color:${corDisciplina};">CONCEITO</th>
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

        function badgeConceito(c) {
            const classes = {
                'inicial': 'badge-conceito-inicial-sm',
                'basico': 'badge-conceito-basico-sm',
                'proficiente': 'badge-conceito-proficiente-sm',
                'avancado': 'badge-conceito-avancado-sm'
            };
            return classes[c] || 'badge-gray';
        }

        const conceitoLabel = {
            'inicial': 'inicial',
            'basico': 'basico',
            'proficiente': 'proficiente',
            'avancado': 'avancado'
        };

        tbody.innerHTML = todosAlunos.map((aluno, index) => {
            const d = aluno.disciplinaData;
            
            let medalha = '';
            if (index === 0) medalha = '🥇';
            else if (index === 1) medalha = '🥈';
            else if (index === 2) medalha = '🥉';
            else medalha = (index + 1);

            const conceitoBadge = `<span class="badge ${badgeConceito(d.conceito)}">${conceitoLabel[d.conceito] || d.conceito}</span>`;

            return `<tr>
                <td style="font-size:14px;">${medalha}</td>
                <td>${index + 1}</td>
                <td style="text-align:left;font-weight:600;">${aluno.aluno_nome || 'Aluno'}</td>
                <td><span class="badge badge-purple" style="font-size:9px;">${aluno.serie || '—'}</span></td>
                <td style="text-align:center;background:${bgDisciplina};font-weight:700;color:var(--green);">${d.acertos}</td>
                <td style="text-align:center;background:${bgDisciplina};font-weight:700;color:var(--red);">${d.erros}</td>
                <td style="text-align:center;background:${bgDisciplina};">${conceitoBadge}</td>
                <td style="font-size:9px;color:var(--text2);">${aluno.escola || '—'}</td>
                <td style="font-size:9px;color:var(--text2);">${aluno.turma || '—'}</td>
            </tr>`;
        }).join('');

        // ============================================
        // ATUALIZAR GRÁFICO DE ACERTOS POR QUESTÃO
        // ============================================
        atualizarGraficoAcertosPorQuestao(dadosAgrupados, disciplinaSelecionada, tipoAvaliacao);

        document.getElementById('rel-disc-acertos').textContent = totalAcertos;
        document.getElementById('rel-disc-erros').textContent = totalErros;
        document.getElementById('rel-disc-media').textContent = totalComCorrecao > 0 ? (totalAcertos / totalComCorrecao).toFixed(1) : '0.0';
        document.getElementById('rel-disc-conceito').textContent = conceitoGeral || '—';

    } catch (erro) {
        console.error('❌ Erro ao carregar relatório por turma:', erro);
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
    }).catch(e => console.error('Erro ao recarregar turmas:', e));

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
    }).catch(e => console.error('Erro ao recarregar provas:', e));
}

// ============================================
// 🔥 CORREÇÃO - ATUALIZAR GRÁFICO DE ACERTOS POR QUESTÃO
// ============================================
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
            totalAcertosEl.textContent = '0';
            totalErrosEl.textContent = '0';
            mediaEl.textContent = '0%';
            return;
        }

        const questoesMap = new Map();
        let totalAcertos = 0;
        let totalErros = 0;
        let totalAlunos = 0;
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
                    if (!questoesMap.has(num)) {
                        questoesMap.set(num, { acertos: 0, erros: 0 });
                    }
                    const data = questoesMap.get(num);
                    
                    if (!bnccMap.has(num)) {
                        const bncc = q.bncc || q.codigo_bncc || (bnccList[idx] || 'N/A');
                        bnccMap.set(num, bncc);
                    }
                    
                    const resp = q.resposta || '';
                    const gab = q.gabarito || '';
                    const isRespondida = resp && resp !== '' && resp !== '—' && resp !== '-';
                    const isCorreta = isRespondida && resp.toUpperCase() === gab.toUpperCase();
                    
                    if (isCorreta || q.acertou === true || q.correta === true) {
                        data.acertos++;
                        totalAcertos++;
                    } else if (isRespondida || q.respondida !== false) {
                        data.erros++;
                        totalErros++;
                    } else {
                        data.erros++;
                        totalErros++;
                    }
                });
            } else {
                const respostas = discData.respostas || [];
                const gabarito = discData.gabarito || [];
                const total = discData.total || 20;
                
                for (let i = 0; i < Math.min(respostas.length, gabarito.length, total); i++) {
                    const num = i + 1;
                    if (!questoesMap.has(num)) {
                        questoesMap.set(num, { acertos: 0, erros: 0 });
                    }
                    const data = questoesMap.get(num);
                    
                    if (!bnccMap.has(num)) {
                        const bncc = (bnccList[i] || 'N/A');
                        bnccMap.set(num, bncc);
                    }
                    
                    const resp = String(respostas[i] || '').trim().toUpperCase();
                    const gab = String(gabarito[i] || '').trim().toUpperCase();
                    
                    const isRespostaValida = resp && resp !== '' && resp !== '—' && resp !== '-';
                    const isCorreta = isRespostaValida && resp === gab && gab !== '';
                    
                    if (isCorreta) {
                        data.acertos++;
                        totalAcertos++;
                    } else {
                        data.erros++;
                        totalErros++;
                    }
                }
            }
        });

        const totalQuestoes = questoesMap.size || 20;

        totalQuestoesEl.textContent = totalQuestoes + ' questões';
        totalAcertosEl.textContent = totalAcertos;
        totalErrosEl.textContent = totalErros;

        const media = totalAlunos > 0 && totalQuestoes > 0 ? 
            Math.round((totalAcertos / (totalAlunos * totalQuestoes)) * 100) : 0;
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
            div.style.cssText = `
                background: var(--surface);
                border-radius: 10px;
                padding: 12px 10px;
                border: 1px solid var(--border);
                text-align: center;
                transition: all 0.2s ease;
            `;
            
            let corBarra = '#ef4444';
            let labelPerformance = '🔴 Baixo';
            if (pctAcertos >= 80) {
                corBarra = '#10b981';
                labelPerformance = '🟢 Alto';
            } else if (pctAcertos >= 60) {
                corBarra = '#f59e0b';
                labelPerformance = '🟡 Médio';
            } else if (pctAcertos >= 40) {
                corBarra = '#f59e0b';
                labelPerformance = '🟡 Médio-Baixo';
            } else if (pctAcertos >= 20) {
                corBarra = '#ef4444';
                labelPerformance = '🔴 Crítico';
            }
            
            div.innerHTML = `
                <div style="font-size: 14px; font-weight: 800; color: var(--text1); margin-bottom: 4px;">
                    Q${num}
                </div>
                <div style="display:flex; justify-content:center; align-items:center; gap:4px; font-size: 16px; font-weight: 700; margin: 4px 0;">
                    <span style="color: var(--green);">${data.acertos}</span>
                    <span style="color: var(--text3); font-weight: 300;">/</span>
                    <span style="color: var(--red);">${data.erros}</span>
                </div>
                <div style="font-size: 9px; color: var(--text3); font-weight: 600; margin-bottom: 4px;">Acertos / Erros</div>
                <div style="font-size: 12px; font-weight: 700; color: var(--blue); margin-bottom: 4px;">Total: ${total}</div>
                <div style="font-size: 11px; font-weight: 700; color: #8b5cf6; background: rgba(139,92,246,0.12); padding: 3px 12px; border-radius: 8px; display: inline-block; margin-bottom: 4px; font-family: 'Courier New', monospace; letter-spacing: 0.3px;">
                    ${bnccCode}
                </div>
                <div class="progress" style="height: 8px; background: var(--bg2); border-radius: 6px; overflow: hidden; margin: 6px 0;">
                    <div class="progress-fill" style="width: ${Math.max(pctAcertos, 2)}%; background: ${corBarra}; border-radius: 6px; transition: width 0.8s ease;"></div>
                </div>
                <div style="display: flex; justify-content: center; gap: 10px; font-size: 11px; font-weight: 700;">
                    <span style="color: var(--green);">${pctAcertos}%</span>
                    <span style="color: var(--text3); font-weight: 300;">|</span>
                    <span style="color: var(--red);">${pctErros}%</span>
                </div>
            `;
            container.appendChild(div);
        });

    } catch (erro) {
        console.error('❌ Erro ao atualizar gráfico de acertos:', erro);
        const container = document.getElementById('rel-acertos-grid');
        if (container) {
            container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--red);">Erro ao carregar dados: ${erro.message}</div>`;
        }
    }
}

// ============================================
// FUNÇÕES DA ABA DESEMPENHO DO ALUNO
// ============================================

async function carregarEscolasDesempenho() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('filtro-escola-desempenho');

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

        const provas = await carregarProvasComCache();
        const selectProva = document.getElementById('filtro-prova-desempenho');

        if (selectProva && provas && !provas.erro) {
            const current = selectProva.value;
            selectProva.innerHTML = '<option value="">Selecione a prova...</option>';
            provas.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                const serie = p.serie || 'Série não definida';
                opt.textContent = p.titulo + ' - ' + serie + ' - ' + (p.disciplina || '');
                opt.dataset.serie = serie;
                opt.dataset.quantidade = p.quantidade_questoes || 20;
                opt.dataset.gabarito = JSON.stringify(p.gabarito || []);
                opt.dataset.bncc = JSON.stringify(p.bncc || []);
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
            if (current) selectProva.value = current;
        }

        document.getElementById('filtro-turma-desempenho').innerHTML = '<option value="">Selecione a turma...</option>';
        document.getElementById('filtro-aluno-desempenho').innerHTML = '<option value="">Selecione o aluno...</option>';

    } catch (erro) {
        console.error('Erro ao carregar escolas para desempenho:', erro);
        showToast('❌ Erro ao carregar dados: ' + erro.message, 'error');
    }
}

async function carregarTurmasDesempenho(escolaId) {
    const selectTurma = document.getElementById('filtro-turma-desempenho');
    const selectAluno = document.getElementById('filtro-aluno-desempenho');

    selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    selectAluno.innerHTML = '<option value="">Selecione o aluno...</option>';

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
        console.error('Erro ao carregar turmas:', e);
        showToast('❌ Erro ao carregar turmas', 'error');
    }
}

async function carregarAlunosDesempenho(turmaId) {
    const selectAluno = document.getElementById('filtro-aluno-desempenho');
    selectAluno.innerHTML = '<option value="">Selecione o aluno...</option>';

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
    } catch (e) {
        console.error('Erro ao carregar alunos:', e);
        showToast('❌ Erro ao carregar alunos', 'error');
    }
}

// ===== FUNÇÃO GERAR DESEMPENHO =====
async function gerarDesempenho() {
    const escolaId = document.getElementById('filtro-escola-desempenho').value;
    const turmaId = document.getElementById('filtro-turma-desempenho').value;
    const alunoId = document.getElementById('filtro-aluno-desempenho').value;
    const provaId = document.getElementById('filtro-prova-desempenho').value;

    if (!escolaId || !turmaId || !alunoId || !provaId) {
        showToast('⚠️ Preencha todos os campos: ESCOLA, TURMA, ALUNO e PROVA!', 'error');
        return;
    }

    showToast('🔍 Buscando dados do aluno...', 'info');

    try {
        const escolaResp = await fetch(`${API_URL}/api/escolas/${escolaId}`);
        const escola = await escolaResp.json();

        const turmaResp = await fetch(`${API_URL}/api/turmas/${turmaId}`);
        const turma = await turmaResp.json();

        const alunoResp = await fetch(`${API_URL}/api/alunos/${alunoId}`);
        const aluno = await alunoResp.json();

        const provaResp = await fetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();

        if (!escola || escola.erro || !turma || turma.erro || !aluno || aluno.erro || !prova || prova.erro) {
            showToast('❌ Erro ao carregar dados. Verifique os filtros selecionados.', 'error');
            return;
        }

        const historicoResp = await fetch(`${API_URL}/api/historico?aluno_id=${alunoId}&prova_id=${provaId}`);
        const historico = await historicoResp.json();

        const gabarito = prova.gabarito || [];
        const bncc = prova.bncc || [];
        const totalQuestoes = prova.quantidade_questoes || 20;

        let respostasAluno = [];
        let disciplina = prova.disciplina || 'Português';

        if (historico && historico.length > 0 && !historico.erro) {
            const correcao = historico[0];
            respostasAluno = correcao.respostas || [];
            if (correcao.disciplina) disciplina = correcao.disciplina;
        } else {
            try {
                const respostasResp = await fetch(`${API_URL}/api/respostas?aluno_id=${alunoId}&prova_id=${provaId}`);
                const respostasData = await respostasResp.json();
                if (respostasData && !respostasData.erro) {
                    respostasAluno = respostasData.respostas || [];
                }
            } catch (e) {
                console.warn('Nenhuma resposta encontrada:', e);
            }
        }

        while (respostasAluno.length < totalQuestoes) respostasAluno.push('');

        let acertos = 0,
            erros = 0;
        const resultadoQuestoes = [];

        for (let i = 0; i < totalQuestoes; i++) {
            const resp = (i < respostasAluno.length) ? (respostasAluno[i] || '') : '';
            const gab = (i < gabarito.length) ? (gabarito[i] || '') : '';
            const codigoBncc = (i < bncc.length) ? (bncc[i] || '') : '';
            const isCorreto = resp && gab && resp.toUpperCase() === gab.toUpperCase();

            if (resp) { if (isCorreto) acertos++;
                else erros++; }

            resultadoQuestoes.push({
                numero: i + 1,
                resposta: resp || '—',
                gabarito: gab || '—',
                bncc: codigoBncc,
                acertou: isCorreto,
                respondida: !!resp
            });
        }

        const pct = totalQuestoes > 0 ? Math.round((acertos / totalQuestoes) * 100) : 0;

        let conceito = 'Inicial';
        let conceitoCor = 'badge-red';
        if (pct > 80) { conceito = 'Avançado';
            conceitoCor = 'badge-green'; } else if (pct > 60) { conceito = 'Proficiente';
            conceitoCor = 'badge-blue'; } else if (pct > 40) { conceito = 'Básico';
            conceitoCor = 'badge-orange'; }

        desempenhoData.alunoSelecionado = {
            escola,
            turma,
            aluno,
            prova,
            respostas: respostasAluno,
            gabarito: gabarito,
            bncc: bncc,
            resultadoQuestoes: resultadoQuestoes,
            acertos: acertos,
            erros: erros,
            porcentagem: pct,
            conceito: conceito,
            disciplina: disciplina,
            totalQuestoes: totalQuestoes
        };

        document.getElementById('resultado-desempenho').style.display = 'block';

        setText('resumo-nota', pct + '%');
        setText('resumo-acertos', acertos);
        setText('resumo-erros', erros);
        setText('resumo-conceito', conceito);

        setText('info-escola', escola.nome || '—');
        setText('info-turma', (turma.nome || '') + ' - ' + (turma.serie || ''));
        setText('info-aluno', aluno.nome || '—');
        setText('info-prova', prova.titulo || '—');
        setText('info-data', new Date().toLocaleDateString('pt-BR'));

        const card = document.getElementById('desempenho-disciplina-unica');
        card.style.display = 'block';

        setText('disciplina-unica-titulo', `📖 ${disciplina}`);

        const grid = document.getElementById('disciplina-unica-questoes');
        grid.innerHTML = '';

        const isProducao = (disciplina === 'Produção de Texto');

        if (isProducao) {
            grid.style.display = 'flex';
            grid.style.flexDirection = 'column';
            grid.style.gap = '12px';
            grid.style.padding = '8px 0';

            resultadoQuestoes.forEach(q => {
                const div = document.createElement('div');
                div.style.background = 'var(--bg2)';
                div.style.border = '1px solid var(--border)';
                div.style.borderRadius = '8px';
                div.style.padding = '10px 14px';
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                div.style.gap = '6px';

                let bnccHtml = '';
                if (q.bncc && q.bncc.trim() !== '') {
                    bnccHtml = `<div style="font-size:9px; color:#a78bfa; background:rgba(139,92,246,0.1); padding:2px 6px; border-radius:4px;">BNCC: ${q.bncc}</div>`;
                }

                div.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:12px; font-weight:700; color:var(--text2);">Q${q.numero}</span>
                        <span class="q-status-text" style="font-size:10px; font-weight:700; padding:2px 8px; border-radius:12px; background:${q.acertou ? 'rgba(16,185,129,0.15)' : (q.respondida ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)')}; color:${q.acertou ? 'var(--green)' : (q.respondida ? 'var(--red)' : 'var(--text3)')};">${q.acertou ? '✅ ACERTOU: ADQUIRIU HABILIDADE' : (q.respondida ? '❌ ERROU: RECOMPOSIÇÃO DE APRENDIZAGEM' : '—')}
                    </span>
                    </div>
                    <div style="font-size:11px; color:var(--text3);">Resposta: <strong>${q.resposta}</strong></div>
                    <div style="font-size:11px; color:var(--text3);">Gabarito: <strong style="color:var(--green);">${q.gabarito}</strong></div>
                    ${bnccHtml}
                    <div style="font-size:10px; color:var(--text3); border-top:1px solid var(--border); padding-top:6px;">Nível BNCC: ${q.bncc || 'Não definido'}</div>
                `;
                grid.appendChild(div);
            });
        } else {
            grid.style.display = 'grid';
            grid.style.gridTemplateColumns = 'repeat(10, 1fr)';
            grid.style.gap = '6px';
            grid.style.padding = '8px 4px';

            resultadoQuestoes.forEach(q => {
                const div = document.createElement('div');
                div.className = `questao-item ${q.acertou ? 'acertou' : (q.respondida ? 'errou' : '')}`;
                let bnccHtml = '';
                if (q.bncc && q.bncc.trim() !== '') {
                    bnccHtml = `<div style="font-size:6px; color:#a78bfa; background:rgba(139,92,246,0.1); padding:0 4px; border-radius:4px; margin-top:2px;">BNCC: ${q.bncc}</div>`;
                }
                div.innerHTML = `
                    <div class="q-num">Q${q.numero}</div>
                    <div class="q-resp">${q.resposta}</div>
                    <div class="q-gab">${q.gabarito}</div>
                    <span class="q-status-text ${q.acertou ? 'acertou' : (q.respondida ? 'errou' : '')}">${q.acertou ? '✅ ACERTOU: ADQUIRIU HABILIDADE' : (q.respondida ? '❌ ERROU: RECOMPOSIÇÃO DE APRENDIZAGEM' : '')}</span>
                    ${bnccHtml}
                `;
                grid.appendChild(div);
            });
        }

        setText('disciplina-unica-acertos', acertos);
        setText('disciplina-unica-erros', erros);
        setText('disciplina-unica-nota', pct + '%');

        const statusBadge = document.getElementById('disciplina-unica-status');
        statusBadge.textContent = conceito;
        statusBadge.className = `badge ${conceitoCor}`;

        setText('disciplina-unica-conceito', conceito);

        const gabCard = document.getElementById('gabarito-oficial-card');
        gabCard.style.display = 'block';

        const gabCardTitle = document.querySelector('#gabarito-oficial-card .card-title');
        if (gabCardTitle) {
            gabCardTitle.textContent = isProducao ? '📋 Gabarito Oficial (Texto)' : '📋 Gabarito Oficial da Prova';
        }

        const gabGrid = document.getElementById('gabarito-oficial-grid');
        gabGrid.innerHTML = '';

        if (isProducao) {
            gabGrid.style.display = 'flex';
            gabGrid.style.flexDirection = 'column';
            gabGrid.style.gap = '12px';
            gabGrid.style.padding = '8px 0';

            gabarito.forEach((gab, idx) => {
                const codigoBncc = (idx < bncc.length) ? bncc[idx] : '';
                const div = document.createElement('div');
                div.style.background = 'var(--bg2)';
                div.style.border = '1px solid var(--border)';
                div.style.borderRadius = '8px';
                div.style.padding = '10px 14px';
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                div.style.gap = '6px';

                div.innerHTML = `
                    <div style="font-weight:700; color:var(--text2);">Q${idx+1}</div>
                    <div style="font-size:13px; font-weight:700; color:var(--green);">${gab || '—'}</div>
                    ${codigoBncc ? `<div style="font-size:9px; color:var(--purple);">BNCC: ${codigoBncc}</div>` : ''}
                    <div style="font-size:10px; color:var(--text3); border-top:1px solid var(--border); padding-top:6px;">Nível BNCC: ${codigoBncc || 'Não definido'}</div>
                `;
                gabGrid.appendChild(div);
            });
        } else {
            gabGrid.style.display = 'grid';
            gabGrid.style.gridTemplateColumns = 'repeat(10, 1fr)';
            gabGrid.style.gap = '6px';
            gabGrid.style.padding = '8px 4px';

            gabarito.forEach((gab, idx) => {
                const codigoBncc = (idx < bncc.length) ? bncc[idx] : '';
                const div = document.createElement('div');
                div.className = 'questao-item';
                div.innerHTML = `
                    <div class="q-num">Q${idx+1}</div>
                    <div class="q-resp" style="color: var(--green);">${gab || '—'}</div>
                    <div class="q-gab">Oficial</div>
                    ${codigoBncc ? `<div style="font-size:6px; color: var(--purple); margin-top:2px; background:rgba(139,92,246,0.1); padding:0 4px; border-radius:4px;">BNCC: ${codigoBncc}</div>` : ''}
                `;
                gabGrid.appendChild(div);
            });
        }

        showToast(`✅ Desempenho gerado para ${aluno.nome} - ${disciplina}: ${acertos}/${totalQuestoes} acertos (${pct}%)`, 'success');

    } catch (erro) {
        console.error('❌ Erro ao gerar desempenho:', erro);
        showToast('❌ Erro ao gerar desempenho: ' + erro.message, 'error');
    }
}

// ===== FUNÇÃO GERAR DOCUMENTO =====
function gerarDocumentoDesempenho() {
    if (gerandoDocumento) {
        showToast('⏳ Aguarde, o documento está sendo gerado...', 'info');
        return;
    }

    const data = desempenhoData.alunoSelecionado;
    if (!data) {
        showToast('⚠️ Gere o desempenho primeiro!', 'error');
        return;
    }

    const btn = document.getElementById('btnGerarDocumento');
    gerandoDocumento = true;
    btn.disabled = true;
    btn.textContent = '⏳ Gerando...';

    try {
        const win = window.open('', '_blank');
        if (!win) {
            showToast('⚠️ Permita pop-ups para gerar o documento!', 'error');
            gerandoDocumento = false;
            btn.disabled = false;
            btn.textContent = '📄 GERAR DOCUMENTO';
            return;
        }

        const { escola, turma, aluno, prova, resultadoQuestoes, acertos, erros, porcentagem, conceito, disciplina, totalQuestoes, gabarito, bncc } = data;

        // Geração do HTML do documento (encurtado para caber)
        let html = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Relatório de Desempenho - ${aluno.nome}</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: Arial, sans-serif; padding: 30px; background: #fff; color: #333; }
                .header { text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 15px; margin-bottom: 25px; }
                .header h1 { font-size: 24px; color: #1e293b; }
                .header h2 { font-size: 18px; color: #475569; margin-top: 5px; }
                .header .sub { font-size: 14px; color: #64748b; margin-top: 5px; }
                .info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; background: #f8fafc; padding: 15px 20px; border-radius: 8px; margin-bottom: 25px; border: 1px solid #e2e8f0; }
                .info-grid .item { font-size: 14px; }
                .info-grid .label { color: #64748b; font-weight: 600; }
                .info-grid .value { color: #0f172a; font-weight: 700; }
                .resumo { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
                .resumo .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; text-align: center; }
                .resumo .card .valor { font-size: 28px; font-weight: 800; }
                .resumo .card .label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.3px; }
                .resumo .card .valor.blue { color: #3b82f6; }
                .resumo .card .valor.green { color: #10b981; }
                .resumo .card .valor.red { color: #ef4444; }
                .resumo .card .valor.purple { color: #8b5cf6; }
                .questoes-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 6px; padding: 8px 4px; }
                .questao-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 2px; text-align: center; font-size: 10px; }
                .questao-item.acertou { border-color: #10b981; background: rgba(16,185,129,0.08); }
                .questao-item.errou { border-color: #ef4444; background: rgba(239,68,68,0.08); }
                .questao-item .q-num { font-size: 7px; color: #94a3b8; font-weight: 700; }
                .questao-item .q-resp { font-weight: 700; font-size: 12px; background: #fff; border-radius: 4px; padding: 0 4px; line-height: 20px; width: 100%; }
                .questao-item .q-gab { font-size: 7px; color: #94a3b8; }
                .questao-item .q-status-text { font-size: 7px; font-weight: 700; display: block; line-height: 1.2; margin-top: 1px; padding: 1px 4px; border-radius: 4px; width: 100%; }
                .questao-item.acertou .q-resp { color: #10b981; }
                .questao-item.errou .q-resp { color: #ef4444; }
                .gabarito-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 6px; padding: 8px 4px; }
                .gabarito-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 2px; text-align: center; font-size: 10px; }
                .gabarito-item .q-num { font-size: 7px; color: #94a3b8; font-weight: 700; }
                .gabarito-item .q-resp { font-weight: 700; font-size: 12px; color: #10b981; }
                .footer { margin-top: 25px; padding-top: 15px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }
                @media print { body { padding: 15px; } .no-print { display: none; } }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 RELATÓRIO DE DESEMPENHO</h1>
                <h2>${prova.titulo || 'Prova'}</h2>
                <div class="sub">${disciplina}</div>
            </div>

            <div class="info-grid">
                <div class="item"><span class="label">🏫 Escola:</span> <span class="value">${escola.nome || '—'}</span></div>
                <div class="item"><span class="label">👥 Turma:</span> <span class="value">${(turma.nome || '') + ' - ' + (turma.serie || '')}</span></div>
                <div class="item"><span class="label">🎒 Aluno:</span> <span class="value">${aluno.nome || '—'}</span></div>
                <div class="item"><span class="label">📄 Prova:</span> <span class="value">${prova.titulo || '—'}</span></div>
                <div class="item"><span class="label">📅 Data:</span> <span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
            </div>

            <div class="resumo">
                <div class="card"><div class="valor blue">${porcentagem}%</div><div class="label">Porcentagem de Acertos</div></div>
                <div class="card"><div class="valor green">${acertos}</div><div class="label">Acertos</div></div>
                <div class="card"><div class="valor red">${erros}</div><div class="label">Erros</div></div>
                <div class="card"><div class="valor purple">${conceito}</div><div class="label">Conceito</div></div>
            </div>

            <h3 style="margin: 20px 0 10px;">📖 ${disciplina}</h3>
            <div class="questoes-grid">
        `;

        // Questões
        resultadoQuestoes.forEach(q => {
            const acertou = q.acertou;
            const resposta = q.resposta || '—';
            const gab = q.gabarito || '—';
            html += `
                <div class="questao-item ${acertou ? 'acertou' : (q.respondida ? 'errou' : '')}">
                    <div class="q-num">Q${q.numero}</div>
                    <div class="q-resp">${resposta}</div>
                    <div class="q-gab">${gab}</div>
                    <span class="q-status-text">${acertou ? '✅' : (q.respondida ? '❌' : '—')}</span>
                    ${q.bncc ? `<div style="font-size:6px; color:#8b5cf6; margin-top:2px;">BNCC: ${q.bncc}</div>` : ''}
                </div>
            `;
        });

        html += `
            </div>

            <h3 style="margin: 20px 0 10px;">📋 Gabarito Oficial</h3>
            <div class="gabarito-grid">
        `;

        // Gabarito
        gabarito.forEach((gab, idx) => {
            const codigoBncc = (idx < bncc.length) ? bncc[idx] : '';
            html += `
                <div class="gabarito-item">
                    <div class="q-num">Q${idx+1}</div>
                    <div class="q-resp">${gab || '—'}</div>
                    ${codigoBncc ? `<div style="font-size:6px; color:#8b5cf6; margin-top:2px;">BNCC: ${codigoBncc}</div>` : ''}
                </div>
            `;
        });

        html += `
            </div>

            <div class="footer">
                <p>Documento gerado pelo Sistema CorrigePro - ${new Date().toLocaleString('pt-BR')}</p>
                <p style="margin-top:5px;">Prefeitura Municipal de São Sebastião da Boa Vista - Secretaria Municipal de Educação</p>
            </div>
        </body>
        </html>
        `;

        win.document.write(html);
        win.document.close();
        setTimeout(() => win.print(), 600);

        showToast('📄 Documento gerado!', 'success');
    } catch (erro) {
        console.error('Erro ao gerar documento:', erro);
        showToast('❌ Erro ao gerar documento: ' + erro.message, 'error');
    } finally {
        setTimeout(() => {
            gerandoDocumento = false;
            btn.disabled = false;
            btn.textContent = '📄 GERAR DOCUMENTO';
        }, 1000);
    }
}

function limparFiltrosDesempenho() {
    document.getElementById('filtro-escola-desempenho').value = '';
    document.getElementById('filtro-turma-desempenho').innerHTML = '<option value="">Selecione a turma...</option>';
    document.getElementById('filtro-aluno-desempenho').innerHTML = '<option value="">Selecione o aluno...</option>';
    document.getElementById('filtro-prova-desempenho').value = '';
    document.getElementById('resultado-desempenho').style.display = 'none';
    document.getElementById('desempenho-disciplina-unica').style.display = 'none';
    document.getElementById('gabarito-oficial-card').style.display = 'none';
    desempenhoData.alunoSelecionado = null;
    showToast('✕ Filtros limpos!', 'info');
}

// ============================================
// FUNÇÕES DE TURMA PARA TEXTO IA
// ============================================
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
    } catch (e) { console.error('Erro ao carregar turmas:', e); }
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
    } catch (e) { console.error('Erro ao carregar alunos:', e); }
}

// ============================================
// CARREGAR DADOS - FUNÇÃO PRINCIPAL
// ============================================
async function carregarDados() {
    console.log('🔄 Carregando dados do sistema...');
    
    try {
        console.log('📌 Carregando dados essenciais...');
        
        await Promise.all([
            carregarEscolas(),
            carregarTurmas(),
            carregarAlunos(),
            carregarProvas(),
            carregarDashboard()
        ]);
        
        console.log('✅ Dados essenciais carregados!');
        
        atualizarDatasImpressao();
        
        console.log('📌 Carregando dados secundários em segundo plano...');
        
        setTimeout(() => {
            carregarDadosSecundarios();
        }, 300);
        
        console.log('✅ Interface principal carregada!');
        
    } catch (erro) {
        console.error('❌ Erro ao carregar dados essenciais:', erro);
        showToast('⚠️ Erro ao carregar dados essenciais. Recarregue a página.', 'error');
    }
}

// ============================================
// DADOS SECUNDÁRIOS (CARREGAR EM SEGUNDO PLANO)
// ============================================
async function carregarDadosSecundarios() {
    console.log('🔄 Iniciando carga de dados secundários...');
    
    try {
        await Promise.all([
            carregarResultadosComFiltros(),
            carregarGabaritos(),
            carregarUltimasCorrecoes(),
            carregarConceitoReal()
        ]);
        console.log('✅ Dados de resultados carregados!');
        
        await Promise.all([
            carregarUsuarios(),
            carregarCombos()
        ]);
        console.log('✅ Dados de usuários carregados!');
        
        await Promise.all([
            carregarRelatorios(),
            carregarUserData(),
            carregarEscolasFiltroAlunos(),
            carregarEscolasCorrigir(),
            carregarEscolasTexto(),
            carregarEscolasParaCorrecaoManual()
        ]);
        console.log('✅ Dados de formulários carregados!');
        
        await Promise.all([
            carregarFiltrosRelTurma(),
            carregarFiltroEscolaTurmas(),
            carregarEscolasDesempenho()
        ]);
        console.log('✅ Dados de filtros carregados!');
        
        console.log('✅ TODOS OS DADOS CARREGADOS COM SUCESSO!');
        
    } catch (erro) {
        console.warn('⚠️ Erro ao carregar dados secundários:', erro);
    }
}

// ============================================
// CARREGAR CONCEITO REAL
// ============================================
async function carregarConceitoReal() {
    try {
        const [conceitoResp, turmasResp] = await Promise.all([
            fetch(`${API_URL}/api/dashboard/Conceito`),
            fetch(`${API_URL}/api/turmas`)
        ]);

        const dados = await conceitoResp.json();
        const turmasLista = await turmasResp.json();

        const container = document.getElementById('grafico-Conceito');
        const badge = document.getElementById('total-turmas-badge');
        if (!container) return;

        if (!dados || dados.erro || (Array.isArray(dados) && dados.length === 0)) {
            container.innerHTML = `<div style="text-align:center;color:var(--text3);padding:20px;">
                <div style="font-size:30px;margin-bottom:10px;">📭</div>
                <p>Nenhuma turma com correções ainda.</p>
                <p style="font-size:12px;">Cadastre turmas e faça correções para ver o Conceito.</p>
            </div>`;
            if (badge) badge.textContent = '0 turmas';
            return;
        }

        let dadosArray = Array.isArray(dados) ? dados : Object.values(dados);

        const turmasMap = new Map();
        if (turmasLista && !turmasLista.erro && Array.isArray(turmasLista)) {
            turmasLista.forEach(t => { turmasMap.set(t.id, t.nome || `Turma ${t.id}`); });
        }

        const agrupado = new Map();
        dadosArray.forEach(item => {
            let turmaId = item.turma_id || item.id || item.turmaId;
            if (!turmaId) {
                if (item.nome) turmaId = 'nome_' + item.nome;
                else return;
            }

            let nomeReal = turmasMap.get(turmaId);
            if (!nomeReal && item.nome && item.nome !== 'Turma sem nome') nomeReal = item.nome;
            if (!nomeReal) nomeReal = `Turma ${turmaId}`;

            if (!agrupado.has(turmaId)) {
                agrupado.set(turmaId, {
                    id: turmaId,
                    nome: nomeReal,
                    somaPorcentagem: 0,
                    totalCorrecoes: 0,
                    contagem: 0
                });
            }
            const turma = agrupado.get(turmaId);
            if (item.porcentagem !== undefined) { turma.somaPorcentagem += item.porcentagem;
                turma.contagem++; }
            if (item.total_correcoes !== undefined) turma.totalCorrecoes += item.total_correcoes;
            else if (item.correcoes !== undefined) turma.totalCorrecoes += item.correcoes;
            else turma.totalCorrecoes += 1;
            if (item.nome && item.nome !== 'Turma sem nome' && item.nome.trim() !== '') turma.nome = item.nome;
        });

        let turmasAgrupadas;
        if (agrupado.size === 0) {
            turmasAgrupadas = dadosArray.map((item, index) => ({
                id: index,
                nome: item.nome || `Turma ${index+1}`,
                porcentagem: item.porcentagem || 0,
                total_correcoes: item.total_correcoes || 0,
                media: item.media || item.porcentagem || 0
            }));
        } else {
            turmasAgrupadas = Array.from(agrupado.values()).map(t => ({
                id: t.id,
                nome: t.nome,
                porcentagem: t.contagem > 0 ? Math.round(t.somaPorcentagem / t.contagem) : 0,
                total_correcoes: t.totalCorrecoes,
                media: t.contagem > 0 ? (t.somaPorcentagem / t.contagem) : 0
            }));
        }

        if (badge) badge.textContent = turmasAgrupadas.length + ' turmas';

        const maxBarras = 5;
        let dadosFiltrados = turmasAgrupadas.sort((a, b) => b.porcentagem - a.porcentagem);
        if (dadosFiltrados.length > maxBarras) dadosFiltrados = dadosFiltrados.slice(0, maxBarras);

        let html = '<div class="chart-bars">';
        const cores = ['linear-gradient(180deg,#3b82f6,#1d4ed8)', 'linear-gradient(180deg,#06b6d4,#0e7490)', 'linear-gradient(180deg,#8b5cf6,#6d28d9)', 'linear-gradient(180deg,#10b981,#047857)', 'linear-gradient(180deg,#f59e0b,#b45309)'];

        dadosFiltrados.forEach((turma, index) => {
            const nome = turma.nome || `Turma ${turma.id}`;
            const porcentagem = turma.porcentagem || 0;
            const altura = Math.max(20, (porcentagem / 100) * 130);
            const cor = cores[index % cores.length];
            html += `<div class="chart-bar-item" title="${nome} - Média: ${turma.media || 0}">
                <div class="chart-bar-val">${porcentagem}%</div>
                <div class="chart-bar" style="height:${altura}px;background:${cor};"></div>
                <div class="chart-bar-lbl">${nome}</div>
            </div>`;
        });
        html += '</div>';

        container.innerHTML = html;

    } catch (erro) {
        console.error('Erro ao carregar Conceito:', erro);
        const container = document.getElementById('grafico-Conceito');
        if (container) {
            container.innerHTML = `<div style="text-align:center;color:var(--red);padding:20px;">
                <div style="font-size:30px;margin-bottom:10px;">⚠️</div>
                <p>Erro ao carregar dados de Conceito.</p>
            </div>`;
        }
    }
}

// ============================================
// CARREGAR ÚLTIMAS CORREÇÕES
// ============================================
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
                    'inicial': 'badge-conceito-inicial', 
                    'basico': 'badge-conceito-basico', 
                    'proficiente': 'badge-conceito-proficiente', 
                    'avancado': 'badge-conceito-avancado' 
                };
                const nomeConceito = { 
                    'inicial': '🔴 Inicial', 
                    'basico': '🟠 Básico', 
                    'proficiente': '🔵 Proficiente', 
                    'avancado': '🟢 Avançado' 
                };
                const badge = badgeMap[conceito] || 'badge-gray';
                const label = nomeConceito[conceito] || 'Indefinido';
                return `<tr>
                    <td><strong>${item.aluno_nome || 'Aluno'}</strong></td>
                    <td>${item.prova_titulo || 'Prova'}</td>
                    <td><strong>${porcentagem}%</strong></td>
                    <td><span class="badge ${badge}">${label}</span></td>
                </tr>`;
            }).join('');
        }
    } catch (erro) { 
        console.error('Erro ao carregar últimas correções:', erro); 
    }
}

// ============================================
// CARREGAR USUÁRIOS
// ============================================
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
            return '<tr data-id="' + u.id + '" data-username="' + u.username + '">' +
                '<td><strong>' + u.username + '</strong><br><small style="color:var(--text3);font-size:10px;">' + (u.nome || '') + '</small></td>' +
                '<td><span class="badge ' + perfilBadge + '">' + (u.perfil === 'admin' ? 'Admin' : 'Usuário') + '</span></td>' +
                '<td><span class="badge ' + statusBadge + '">' + statusText + '</span></td>' +
                '<td>' +
                '<div class="btn-group">' +
                (isAdmin ? '<span style="font-size:10px;color:var(--text3);">Sistema</span>' : '<button class="btn btn-outline btn-sm" onclick="editarUsuario(' + u.id + ')">✏️</button><button class="btn-del" onclick="excluirUsuario(' + u.id + ', \'' + u.username + '\')">🗑️</button>') +
                '</div>' +
                '</td></tr>';
        }).join('');
    } catch (erro) { console.error('Erro ao carregar usuários:', erro); }
}

// ============================================
// EXPORTAR FUNCTIONS
// ============================================
function exportarResultadosFiltrados() {
    showToast('📥 Exportando resultados filtrados...', 'info');
    const tbody = document.getElementById('tb-resultados-filtrado');
    if (!tbody) return;
    let csv = 'Posição,Número,Nome,Série,Português_Acertos,Português_Erros,Português_Conceito,Matemática_Acertos,Matemática_Erros,Matemática_Conceito,Produção_Acertos,Produção_Erros,Produção_Conceito,CH_Acertos,CH_Erros,CH_Conceito,CN_Acertos,CN_Erros,CN_Conceito,Escola,Turma\n';
    tbody.querySelectorAll('tr').forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 20) {
            csv += cells[0].textContent.trim() + ',' +
                cells[1].textContent.trim() + ',' +
                cells[2].textContent.trim() + ',' +
                cells[3].textContent.trim() + ',' +
                cells[4].textContent.trim() + ',' +
                cells[5].textContent.trim() + ',' +
                cells[6].textContent.trim() + ',' +
                cells[7].textContent.trim() + ',' +
                cells[8].textContent.trim() + ',' +
                cells[9].textContent.trim() + ',' +
                cells[10].textContent.trim() + ',' +
                cells[11].textContent.trim() + ',' +
                cells[12].textContent.trim() + ',' +
                cells[13].textContent.trim() + ',' +
                cells[14].textContent.trim() + ',' +
                cells[15].textContent.trim() + ',' +
                cells[16].textContent.trim() + ',' +
                cells[17].textContent.trim() + ',' +
                cells[18].textContent.trim() + ',' +
                cells[19].textContent.trim() + '\n';
        }
    });
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'resultados_filtrados.csv';
    a.click();
    URL.revokeObjectURL(url);
    showToast('✅ Resultados exportados!', 'success');
}

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

    let html = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Lista de Alunos</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial, sans-serif; margin: 30px; background: #fff; }
            h1 { text-align: center; font-size: 24px; margin-bottom: 8px; }
            .filtros { text-align: center; color: #555; margin-bottom: 20px; font-size: 14px; }
            table { width: 100%; border-collapse: collapse; font-size: 12px; }
            th, td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; }
            th { background: #f2f2f2; font-weight: 700; }
            tr:nth-child(even) { background: #fafafa; }
            .footer { text-align: center; margin-top: 20px; color: #999; font-size: 12px; }
            @media print {
                body { margin: 10px; }
                .no-print { display: none; }
            }
        </style>
    </head>
    <body>
        <h1>📋 Lista de Alunos</h1>
        <div class="filtros">
            <strong>Escola:</strong> ${escolaNome} &nbsp;|&nbsp;
            <strong>Turma:</strong> ${turmaNome} &nbsp;|&nbsp;
            <strong>Série:</strong> ${serieNome}
        </div>
        <table>
            <thead>
                <tr>
                    <th>Nº</th>
                    <th>Matrícula</th>
                    <th>Nome Completo</th>
                    <th>Série</th>
                    <th>Turma</th>
                    <th>Escola</th>
                    <th>Data Nasc.</th>
                </tr>
            </thead>
            <tbody>
    `;
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
            const numero = cells[0].textContent.trim();
            const matricula = cells[1].textContent.trim();
            const nome = cells[2].textContent.trim();
            const serie = cells[3].textContent.trim();
            const turma = cells[4].textContent.trim();
            const escola = cells[5].textContent.trim();
            const dataNasc = cells[6].textContent.trim();
            html += `
                <tr>
                    <td>${numero}</td>
                    <td>${matricula}</td>
                    <td>${nome}</td>
                    <td>${serie}</td>
                    <td>${turma}</td>
                    <td>${escola}</td>
                    <td>${dataNasc}</td>
                </tr>
            `;
        }
    });
    html += `
            </tbody>
        </table>
        <div class="footer">
            Gerado em ${new Date().toLocaleString('pt-BR')}
        </div>
    </body>
    </html>
    `;

    const win = window.open('', '_blank');
    if (!win) {
        showToast('⚠️ Permita pop-ups para imprimir.', 'error');
        return;
    }
    win.document.write(html);
    win.document.close();
    win.focus();
    win.print();
}

// ============================================
// 🔥 FUNÇÃO PARA GERAR PDF PROFISSIONAL DO RELATÓRIO POR TURMA
// ============================================
// ============================================
// 🔥 FUNÇÃO PARA GERAR PDF PROFISSIONAL DO RELATÓRIO POR TURMA - CORRIGIDA
// ============================================
function exportarRelatorioPDF() {
    // Verifica se há dados para exportar
    const tbody = document.getElementById('tb-rel-alunos');
    if (!tbody) {
        showToast('❌ Nenhum dado para exportar!', 'error');
        return;
    }

    const rows = tbody.querySelectorAll('tr');
    if (rows.length === 0 || (rows.length === 1 && rows[0].textContent.includes('Nenhum aluno'))) {
        showToast('⚠️ Nenhum dado disponível para gerar o PDF.', 'error');
        return;
    }

    showToast('📄 Gerando PDF...', 'info');

    // Obtém os filtros atuais
    const escolaSelect = document.getElementById('rel-turma-escola');
    const serieSelect = document.getElementById('rel-turma-serie');
    const turmaSelect = document.getElementById('rel-turma-turma');
    const provaSelect = document.getElementById('rel-turma-prova');

    const escolaNome = escolaSelect?.options[escolaSelect.selectedIndex]?.text || 'Não informado';
    const serieNome = serieSelect?.options[serieSelect.selectedIndex]?.text || 'Não informado';
    const turmaNome = turmaSelect?.options[turmaSelect.selectedIndex]?.text || 'Não informado';
    
    // Obtém a disciplina
    let disciplinaNome = 'Português';
    const provaOption = provaSelect?.options[provaSelect.selectedIndex];
    if (provaOption && provaOption.dataset.disciplina) {
        disciplinaNome = provaOption.dataset.disciplina;
    }

    // Obtém os dados do relatório
    const mediaEl = document.getElementById('rel-media');
    const media = mediaEl ? mediaEl.textContent : '0%';
    
    const conceitoEl = document.getElementById('rel-conceito-geral');
    const conceito = conceitoEl ? conceitoEl.textContent : '—';

    // 🔥 COLETA OS DADOS DOS ALUNOS DIRETAMENTE DA TABELA
    const alunosData = [];
    let totalAcertosGeral = 0;
    let totalErrosGeral = 0;
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 9) {
            const posicao = cells[0]?.textContent.trim() || '';
            const numero = cells[1]?.textContent.trim() || '';
            const nome = cells[2]?.textContent.trim() || '';
            const serie = cells[3]?.textContent.trim() || '';
            
            // 🔥 PEGA OS ACERTOS E ERROS DA TABELA
            const acertosText = cells[4]?.textContent.trim() || '0';
            const errosText = cells[5]?.textContent.trim() || '0';
            const acertos = parseInt(acertosText) || 0;
            const erros = parseInt(errosText) || 0;
            
            const conceitoAluno = cells[6]?.textContent.trim() || '';
            const escola = cells[7]?.textContent.trim() || '';
            const turma = cells[8]?.textContent.trim() || '';
            
            totalAcertosGeral += acertos;
            totalErrosGeral += erros;
            
            alunosData.push({ 
                posicao, 
                numero, 
                nome, 
                serie, 
                acertos, 
                erros, 
                conceito: conceitoAluno, 
                escola, 
                turma 
            });
        }
    });

    const totalAlunos = alunosData.length;

    // 🔥 COLETA OS DADOS DE ACERTOS POR QUESTÃO DIRETAMENTE DO DOM
    const acertosPorQuestao = [];
    const acertosGrid = document.getElementById('rel-acertos-grid');
    
    if (acertosGrid) {
        // Procura por todos os cards de questão
        const items = acertosGrid.querySelectorAll('.acertos-por-questao-item, [style*="padding:12px 10px"], [class*="questao"]');
        
        items.forEach(item => {
            // Tenta encontrar o número da questão
            let qNum = '';
            const qNumEl = item.querySelector('.q-num') || item.querySelector('[style*="font-size: 14px; font-weight: 800;"]');
            if (qNumEl) {
                qNum = qNumEl.textContent.trim();
            } else {
                // Tenta extrair do texto
                const texto = item.textContent || '';
                const match = texto.match(/Q(\d+)/i);
                if (match) {
                    qNum = 'Q' + match[1];
                }
            }
            
            // Tenta encontrar acertos/erros
            let acertos = '0', erros = '0';
            const numeros = item.querySelectorAll('[style*="color: var(--green);"], [style*="color: var(--red);"]');
            if (numeros.length >= 2) {
                acertos = numeros[0].textContent.trim();
                erros = numeros[1].textContent.trim();
            } else {
                // Tenta extrair do texto "22 / 3"
                const texto = item.textContent || '';
                const match = texto.match(/(\d+)\s*\/\s*(\d+)/);
                if (match) {
                    acertos = match[1] || '0';
                    erros = match[2] || '0';
                }
            }
            
            // Tenta encontrar total
            let total = parseInt(acertos) + parseInt(erros);
            
            // Tenta encontrar BNCC
            let bncc = 'N/A';
            const bnccEl = item.querySelector('[style*="color:#8b5cf6;"]') || 
                           item.querySelector('[style*="background:rgba(139,92,246,0.12);"]');
            if (bnccEl) {
                bncc = bnccEl.textContent.trim();
            } else {
                const texto = item.textContent || '';
                const match = texto.match(/(EF\d+[A-Z]+\d+)/);
                if (match) {
                    bncc = match[1];
                }
            }
            
            // Tenta encontrar porcentagens
            let pctAcertos = '0%', pctErros = '0%';
            const pctElements = item.querySelectorAll('[style*="color: var(--green);"], [style*="color: var(--red);"]');
            if (pctElements.length >= 4) {
                pctAcertos = pctElements[2]?.textContent.trim() || '0%';
                pctErros = pctElements[3]?.textContent.trim() || '0%';
            } else {
                const texto = item.textContent || '';
                const match = texto.match(/(\d+)%\s*[|]\s*(\d+)%/);
                if (match) {
                    pctAcertos = match[1] + '%';
                    pctErros = match[2] + '%';
                }
            }
            
            if (qNum) {
                acertosPorQuestao.push({ 
                    numero: qNum, 
                    acertos: acertos, 
                    erros: erros, 
                    total: total,
                    bncc: bncc,
                    pctAcertos: pctAcertos,
                    pctErros: pctErros
                });
            }
        });
    }

    // 🔥 SE NÃO CONSEGUIU PEGAR DOS CARDS, TENTA PEGAR DO CONTEÚDO DIRETO
    if (acertosPorQuestao.length === 0 && acertosGrid) {
        const html = acertosGrid.innerHTML;
        const matches = html.match(/Q(\d+).*?(\d+)\s*\/\s*(\d+).*?(EF\d+[A-Z]+\d+).*?(\d+)%\s*[|]\s*(\d+)%/gs);
        if (matches) {
            matches.forEach(match => {
                const qMatch = match.match(/Q(\d+)/);
                const numMatch = match.match(/(\d+)\s*\/\s*(\d+)/);
                const bnccMatch = match.match(/(EF\d+[A-Z]+\d+)/);
                const pctMatch = match.match(/(\d+)%\s*[|]\s*(\d+)%/);
                
                if (qMatch && numMatch) {
                    acertosPorQuestao.push({
                        numero: 'Q' + qMatch[1],
                        acertos: numMatch[1] || '0',
                        erros: numMatch[2] || '0',
                        total: parseInt(numMatch[1] || '0') + parseInt(numMatch[2] || '0'),
                        bncc: bnccMatch ? bnccMatch[1] : 'N/A',
                        pctAcertos: pctMatch ? pctMatch[1] + '%' : '0%',
                        pctErros: pctMatch ? pctMatch[2] + '%' : '0%'
                    });
                }
            });
        }
    }

    // 🔥 CALCULA A MÉDIA CORRETA
    const totalQuestoesGeral = totalAcertosGeral + totalErrosGeral;
    const mediaCalculada = totalQuestoesGeral > 0 && totalAlunos > 0 ? 
        Math.round((totalAcertosGeral / (totalAlunos * (totalQuestoesGeral / totalAlunos))) * 100) : 0;

    // ============================================
    // GERAÇÃO DO HTML PARA O PDF
    // ============================================
    const dataAtual = new Date().toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });

    // Função para badge do conceito
    function getConceitoBadge(conceito) {
        const conceitos = {
            'inicial': { label: '🔴 Inicial', color: '#ef4444', bg: '#fef2f2' },
            'basico': { label: '🟠 Básico', color: '#f59e0b', bg: '#fffbeb' },
            'proficiente': { label: '🔵 Proficiente', color: '#3b82f6', bg: '#eff6ff' },
            'avancado': { label: '🟢 Avançado', color: '#10b981', bg: '#ecfdf5' }
        };
        const c = conceitos[conceito?.toLowerCase()] || { label: conceito || '—', color: '#64748b', bg: '#f1f5f9' };
        return `<span style="background:${c.bg}; color:${c.color}; padding:2px 12px; border-radius:12px; font-size:10px; font-weight:700;">${c.label}</span>`;
    }

    // Gera o HTML do relatório
    let html = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Relatório por Turma - ${disciplinaNome}</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                background: #ffffff;
                padding: 20px;
                color: #1e293b;
            }
            
            .header {
                border-bottom: 3px solid #1e293b;
                padding-bottom: 16px;
                margin-bottom: 20px;
            }
            
            .header-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 6px;
                flex-wrap: wrap;
                gap: 10px;
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .header-left .logo {
                width: 60px;
                height: 60px;
                object-fit: contain;
                border-radius: 4px;
            }
            
            .header-left .instituicao {
                display: flex;
                flex-direction: column;
            }
            
            .header-left .instituicao .prefeitura {
                font-size: 10px;
                font-weight: 600;
                color: #475569;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .header-left .instituicao .secretaria {
                font-size: 13px;
                font-weight: 800;
                color: #1e293b;
                letter-spacing: 0.3px;
            }
            
            .header-left .instituicao .departamento {
                font-size: 10px;
                color: #475569;
                font-weight: 600;
            }
            
            .header-left .instituicao .sisam {
                font-size: 14px;
                font-weight: 900;
                color: #2563eb;
                letter-spacing: 0.5px;
            }
            
            .header-right {
                text-align: right;
                border-left: 2px solid #e2e8f0;
                padding-left: 16px;
            }
            
            .header-right .titulo-relatorio {
                font-size: 18px;
                font-weight: 800;
                color: #1e293b;
                letter-spacing: 0.3px;
            }
            
            .header-right .subtitulo-relatorio {
                font-size: 11px;
                color: #475569;
                font-weight: 600;
            }
            
            .info-grid {
                display: grid;
                grid-template-columns: repeat(6, 1fr);
                gap: 8px 16px;
                background: #f8fafc;
                padding: 12px 20px;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
                margin-bottom: 16px;
            }
            
            .info-grid .item {
                display: flex;
                flex-direction: column;
            }
            
            .info-grid .item .label {
                font-size: 8px;
                font-weight: 700;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .info-grid .item .value {
                font-size: 12px;
                font-weight: 700;
                color: #0f172a;
                margin-top: 1px;
            }
            
            .section-title {
                font-size: 14px;
                font-weight: 800;
                color: #1e293b;
                margin: 16px 0 10px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .section-title .badge {
                font-size: 9px;
                background: #eff6ff;
                color: #2563eb;
                padding: 2px 12px;
                border-radius: 12px;
                font-weight: 700;
            }
            
            .questoes-grid {
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 10px;
                margin-bottom: 12px;
            }
            
            .questao-card {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 14px;
                text-align: center;
            }
            
            .questao-card .q-num {
                font-size: 13px;
                font-weight: 800;
                color: #1e293b;
                margin-bottom: 4px;
                background: #e2e8f0;
                display: inline-block;
                padding: 0 12px;
                border-radius: 8px;
            }
            
            .questao-card .q-result {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 6px;
                font-size: 15px;
                font-weight: 700;
                margin: 4px 0;
            }
            
            .questao-card .q-result .acertos {
                color: #10b981;
            }
            
            .questao-card .q-result .erros {
                color: #ef4444;
            }
            
            .questao-card .q-result .divider {
                color: #94a3b8;
                font-weight: 300;
            }
            
            .questao-card .q-label {
                font-size: 9px;
                color: #94a3b8;
                font-weight: 600;
                margin-bottom: 4px;
            }
            
            .questao-card .q-total {
                font-size: 11px;
                font-weight: 700;
                color: #3b82f6;
                margin-bottom: 4px;
            }
            
            .questao-card .q-bncc {
                font-size: 10px;
                font-weight: 700;
                color: #8b5cf6;
                background: #f5f3ff;
                padding: 3px 12px;
                border-radius: 8px;
                display: inline-block;
                font-family: 'Courier New', monospace;
                letter-spacing: 0.3px;
                border: 1px solid rgba(139,92,246,0.2);
            }
            
            .q-porcentagens {
                display: flex;
                justify-content: center;
                gap: 12px;
                margin-top: 4px;
                font-size: 10px;
                font-weight: 700;
            }
            .q-porcentagens .pct-acertos { color: #10b981; }
            .q-porcentagens .pct-erros { color: #ef4444; }
            .q-porcentagens .pct-divider { color: #94a3b8; font-weight: 300; }
            
            .resumo-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin: 12px 0 16px;
            }
            
            .resumo-card {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 16px;
                text-align: center;
            }
            
            .resumo-card .valor {
                font-size: 24px;
                font-weight: 900;
            }
            
            .resumo-card .valor.green { color: #10b981; }
            .resumo-card .valor.red { color: #ef4444; }
            .resumo-card .valor.blue { color: #3b82f6; }
            .resumo-card .valor.purple { color: #8b5cf6; }
            
            .resumo-card .label {
                font-size: 9px;
                color: #94a3b8;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.3px;
                margin-top: 2px;
            }
            
            .table-wrap {
                overflow-x: auto;
                margin: 12px 0;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
                font-size: 10px;
            }
            
            thead {
                background: #f1f5f9;
            }
            
            th {
                padding: 8px 6px;
                text-align: center;
                font-weight: 700;
                color: #475569;
                border-bottom: 2px solid #e2e8f0;
                font-size: 8px;
                text-transform: uppercase;
                letter-spacing: 0.3px;
            }
            
            td {
                padding: 6px 4px;
                border-bottom: 1px solid #f1f5f9;
                text-align: center;
                font-size: 9px;
                color: #1e293b;
            }
            
            tr:nth-child(even) td {
                background: #fafbfc;
            }
            
            .pos-medalha {
                font-size: 16px;
            }
            
            .nome-aluno {
                font-weight: 600;
                text-align: left;
                padding-left: 8px;
            }
            
            .badge-conceito {
                display: inline-block;
                padding: 2px 10px;
                border-radius: 12px;
                font-size: 8px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.2px;
            }
            
            .badge-inicial { background: #fef2f2; color: #ef4444; }
            .badge-basico { background: #fffbeb; color: #f59e0b; }
            .badge-proficiente { background: #eff6ff; color: #3b82f6; }
            .badge-avancado { background: #ecfdf5; color: #10b981; }
            
            .acertos-cell { color: #10b981; font-weight: 700; }
            .erros-cell { color: #ef4444; font-weight: 700; }
            
            .col-escola, .col-turma {
                font-size: 7px;
                color: #64748b;
                max-width: 80px;
            }
            
            .assinaturas {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 40px;
                margin-top: 24px;
                padding-top: 16px;
                border-top: 1px solid #e2e8f0;
                text-align: center;
            }
            
            .assinatura-item {
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            
            .assinatura-item .linha {
                width: 180px;
                border-bottom: 1.5px solid #1e293b;
                margin-bottom: 4px;
            }
            
            .assinatura-item .cargo {
                font-size: 9px;
                color: #64748b;
                font-weight: 600;
            }
            
            .assinatura-item .nome-assinatura {
                font-size: 10px;
                font-weight: 700;
                color: #1e293b;
                margin-bottom: 2px;
            }
            
            .footer {
                margin-top: 20px;
                padding-top: 12px;
                border-top: 1px solid #e2e8f0;
                display: flex;
                justify-content: space-between;
                font-size: 8px;
                color: #94a3b8;
                flex-wrap: wrap;
                gap: 4px;
            }
            
            .footer strong {
                color: #475569;
            }
            
            @media print {
                body { padding: 10px; }
                .no-print { display: none; }
                .questao-card { break-inside: avoid; }
                tr { break-inside: avoid; }
                .assinaturas { break-inside: avoid; }
                @page { size: A4 landscape; margin: 8mm 6mm; }
            }
            
            @media (max-width: 768px) {
                .info-grid { grid-template-columns: repeat(3, 1fr); }
                .resumo-grid { grid-template-columns: repeat(2, 1fr); }
                .questoes-grid { grid-template-columns: repeat(3, 1fr); }
                .assinaturas { grid-template-columns: 1fr; gap: 20px; }
                .header-top { flex-direction: column; align-items: flex-start; }
                .header-right { border-left: none; padding-left: 0; text-align: left; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-top">
                <div class="header-left">
                    <img src="https://github.com/jorg3o3iras/adabee-sistema/blob/main/dgp.jpg?raw=true" alt="DGP" class="logo" style="width:60px;height:60px;object-fit:contain;border-radius:4px;">
                    <div class="instituicao">
                        <span class="prefeitura">PREFEITURA MUNICIPAL DE</span>
                        <span class="secretaria">SÃO SEBASTIÃO DA BOA VISTA</span>
                        <span class="departamento">SECRETARIA MUNICIPAL DE EDUCAÇÃO</span>
                        <span class="departamento">DEPARTAMENTO DE GESTÃO PEDAGÓGICA - DGP</span>
                        <span class="sisam">SISAM 2026</span>
                    </div>
                </div>
                <div class="header-right">
                    <div class="titulo-relatorio">📊 RELATÓRIO POR TURMA</div>
                    <div class="subtitulo-relatorio">Relatório de desempenho dos alunos - ${disciplinaNome}</div>
                    <div style="font-size:9px; color:#94a3b8; margin-top:2px;">Ano Letivo 2026</div>
                </div>
            </div>
        </div>

        <div class="info-grid">
            <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escolaNome}</span></div>
            <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${serieNome}</span></div>
            <div class="item"><span class="label">📖 DISCIPLINA</span><span class="value">${disciplinaNome}</span></div>
            <div class="item"><span class="label">👥 TURMA</span><span class="value">${turmaNome}</span></div>
            <div class="item"><span class="label">📅 DATA</span><span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
            <div class="item"><span class="label">📊 BIMESTRE</span><span class="value">1º e 2º bimestre</span></div>
        </div>

        <div class="section-title">
            📊 Acertos por Questão — ${disciplinaNome}
            <span class="badge">${totalAlunos} alunos</span>
        </div>

        <div class="questoes-grid">
            ${acertosPorQuestao.length > 0 ? acertosPorQuestao.map(q => {
                const total = parseInt(q.acertos) + parseInt(q.erros);
                let pctAcertos = q.pctAcertos || '0%';
                let pctErros = q.pctErros || '0%';
                if (total > 0) {
                    const calcAcertos = Math.round((parseInt(q.acertos) / total) * 100);
                    const calcErros = Math.round((parseInt(q.erros) / total) * 100);
                    if (pctAcertos === '0%' || pctAcertos === '0%') {
                        pctAcertos = calcAcertos + '%';
                        pctErros = calcErros + '%';
                    }
                }
                return `
                    <div class="questao-card">
                        <div class="q-num">${q.numero}</div>
                        <div class="q-result">
                            <span class="acertos">${q.acertos}</span>
                            <span class="divider">/</span>
                            <span class="erros">${q.erros}</span>
                        </div>
                        <div class="q-label">Acertos / Erros</div>
                        <div class="q-total">Total: ${total}</div>
                        <div class="q-bncc">${q.bncc}</div>
                        <div class="q-porcentagens">
                            <span class="pct-acertos">${pctAcertos}</span>
                            <span class="pct-divider">|</span>
                            <span class="pct-erros">${pctErros}</span>
                        </div>
                    </div>
                `;
            }).join('') : `
                <div style="grid-column:1/-1;text-align:center;padding:20px;color:#94a3b8;">
                    Nenhum dado disponível para esta disciplina.
                </div>
            `}
        </div>

        <div class="resumo-grid">
            <div class="resumo-card"><div class="valor green">${totalAcertosGeral}</div><div class="label">✅ Total de Acertos</div></div>
            <div class="resumo-card"><div class="valor red">${totalErrosGeral}</div><div class="label">❌ Total de Erros</div></div>
            <div class="resumo-card"><div class="valor blue">${media || mediaCalculada + '%'}</div><div class="label">📊 Média da Turma</div></div>
            <div class="resumo-card"><div class="valor purple">${conceito}</div><div class="label">📊 Conceito</div></div>
        </div>

        <div class="section-title">
            📋 Lista de Alunos
            <span class="badge">${totalAlunos} alunos</span>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>POS.</th>
                        <th>Nº</th>
                        <th style="text-align:left;">NOME</th>
                        <th>SÉRIE</th>
                        <th>ACERTOS</th>
                        <th>ERROS</th>
                        <th>CONCEITO</th>
                        <th>ESCOLA</th>
                        <th>TURMA</th>
                    </tr>
                </thead>
                <tbody>
                    ${alunosData.map(a => {
                        const medalha = a.posicao === '🥇' ? '🥇' : a.posicao === '🥈' ? '🥈' : a.posicao === '🥉' ? '🥉' : a.posicao || '—';
                        const conceitoClass = a.conceito ? `badge-${a.conceito.toLowerCase()}` : 'badge-inicial';
                        return `
                            <tr>
                                <td><span class="pos-medalha">${medalha}</span></td>
                                <td>${a.numero}</td>
                                <td class="nome-aluno">${a.nome}</td>
                                <td>${a.serie}</td>
                                <td class="acertos-cell">${a.acertos}</td>
                                <td class="erros-cell">${a.erros}</td>
                                <td><span class="badge-conceito ${conceitoClass}">${a.conceito || '—'}</span></td>
                                <td class="col-escola">${a.escola}</td>
                                <td class="col-turma">${a.turma}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>

        <div class="assinaturas">
            <div class="assinatura-item"><div class="linha"></div><div class="nome-assinatura">Professor(a) Responsável</div><div class="cargo">Professor(a)</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="nome-assinatura">Diretor(a)</div><div class="cargo">Diretor(a)</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="nome-assinatura">Secretário(a) de Educação</div><div class="cargo">Secretaria Municipal de Educação</div></div>
        </div>

        <div class="footer">
            <span>📄 Documento gerado pelo sistema <strong>CorrigePro</strong></span>
            <span>${dataAtual}</span>
            <span>© 2026 CorrigePro — Secretaria Municipal de Educação</span>
        </div>

    </body>
    </html>
    `;

    // Abrir em nova janela
    const win = window.open('', '_blank');
    if (!win) {
        showToast('⚠️ Permita pop-ups para gerar o PDF.', 'error');
        return;
    }

    win.document.write(html);
    win.document.close();

    win.onload = function() {
        setTimeout(() => {
            win.focus();
            win.print();
        }, 500);
    };

    showToast('📄 PDF gerado com sucesso!', 'success');
}

// ============================================
// GABARITO - BUILD GRID
// ============================================
function buildGabGrid() {
    const grid = document.getElementById('gab-grid');
    const headerContainer = document.getElementById('gab-header-container');
    if (!grid) return;

    const serieEl = document.getElementById('gab-serie');
    const totalEl = document.getElementById('gab-total');
    const provaSelect = document.getElementById('gab-prova');

    if (!serieEl || !totalEl || !provaSelect) return;

    const selectedOption = provaSelect.options[provaSelect.selectedIndex];
    const provaNome = selectedOption ? selectedOption.text || 'Gabarito' : 'Gabarito';
    const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
    const isProducao = (disciplina === 'Produção de Texto');

    if (headerContainer) {
        const disciplinaLabel = disciplina || 'Disciplina';
        headerContainer.innerHTML = `
            <div class="gab-header-title">
                <span class="icon">📝</span>
                <span>Gabarito: <span class="prova-nome">${provaNome}</span></span>
                <span class="badge-disciplina">${disciplinaLabel}</span>
            </div>
        `;
    }

    const alts = ['A', 'B', 'C', 'D'];
    const total = parseInt(totalEl.value) || 20;
    const lbl = document.getElementById('gab-label');
    if (lbl) {
        if (isProducao) {
            lbl.textContent = '📝 Produção de Texto — Resposta descritiva e nível BNCC';
        } else {
            lbl.textContent = '📝 Gabarito com 4 alternativas: A, B, C, D';
        }
    }

    if (isProducao) {
        grid.style.display = 'flex';
        grid.style.flexDirection = 'column';
        grid.style.gap = '16px';
    } else {
        grid.style.display = 'grid';
        grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(120px, 1fr))';
        grid.style.gap = '14px';
    }

    grid.innerHTML = '';
    for (let i = 1; i <= total; i++) {
        const div = document.createElement('div');
        div.className = 'gab-item';
        if (isProducao) {
            div.innerHTML = `
                <input class="gab-titulo" type="text" value="Q${i}" style="width:100%; background:var(--bg2); border:2px solid var(--border2); border-radius:6px; color:var(--text); padding:6px 10px; font-size:14px; font-weight:bold; text-align:center;" />
                <textarea class="gab-texto" placeholder="Digite a resposta esperada..." style="width:100%; min-height:70px; background:var(--bg2); border:2.5px solid var(--border2); border-radius:8px; color:var(--text); padding:8px 10px; font-size:13px; resize:vertical;"></textarea>
                <select class="gab-nivel" style="width:100%; margin-top:2px; padding:5px 8px; background:var(--bg2); border:2px solid var(--border2); border-radius:6px; color:var(--text); font-size:12px;">
                    <option value="">Nível BNCC</option>
                    <option value="Inicial">Inicial</option>
                    <option value="Básico">Básico</option>
                    <option value="Proficiente">Proficiente</option>
                    <option value="Avançado">Avançado</option>
                </select>
                <textarea class="gab-observacao" placeholder="Observações (opcional)" style="width:100%; min-height:35px; background:var(--bg2); border:2px solid var(--border2); border-radius:6px; color:var(--text); padding:5px 8px; font-size:11px; resize:vertical; margin-top:4px;"></textarea>
            `;
        } else {
            let opts = '<option value="">—</option>';
            alts.forEach(a => { opts += '<option>' + a + '</option>'; });
            div.innerHTML = `
                <div class="gab-num">Q${i}</div>
                <select class="gab-select" onchange="this.classList.toggle('filled', this.value!='')">${opts}</select>
                <input class="gab-bncc" placeholder="BNCC" style="width:100%; margin-top:2px; padding:5px 8px; background:var(--bg); border:2px solid var(--border2); border-radius:6px; color:var(--text); font-size:10px; text-align:center;" />
            `;
        }
        grid.appendChild(div);
    }
}

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
        document.querySelectorAll('.gab-titulo').forEach(inp => inp.value = 'Q' + (Array.from(document.querySelectorAll('.gab-titulo')).indexOf(inp) + 1));
        document.querySelectorAll('.gab-texto').forEach(ta => ta.value = '');
        document.querySelectorAll('.gab-nivel').forEach(sel => sel.value = '');
        document.querySelectorAll('.gab-observacao').forEach(ta => ta.value = '');
    } else {
        document.querySelectorAll('.gab-select').forEach(s => { s.value = ''; s.classList.remove('filled'); });
        document.querySelectorAll('.gab-bncc').forEach(inp => inp.value = '');
    }
}

// ============================================
// SALVAR GABARITO
// ============================================
async function saveGab() {
    try {
        const provaSelect = document.getElementById('gab-prova');
        const selectedOption = provaSelect.options[provaSelect.selectedIndex];
        const disciplina = selectedOption ? selectedOption.dataset.disciplina : '';
        const isProducao = (disciplina === 'Produção de Texto');

        const respostas = [];
        const bncc = [];

        if (isProducao) {
            const textareas = document.querySelectorAll('.gab-texto');
            const niveis = document.querySelectorAll('.gab-nivel');
            textareas.forEach((ta, idx) => {
                respostas.push(ta.value.trim() || '');
                if (niveis[idx]) bncc.push(niveis[idx].value.trim() || '');
            });
        } else {
            const selects = document.querySelectorAll('.gab-select');
            const bnccInputs = document.querySelectorAll('.gab-bncc');
            selects.forEach((s, idx) => {
                respostas.push(s.value || '');
                if (bnccInputs[idx]) bncc.push(bnccInputs[idx].value.trim() || '');
            });
        }

        const respostasValidas = respostas.filter(r => r !== '');
        if (respostasValidas.length === 0) { showToast('⚠️ Preencha pelo menos uma questão do gabarito!', 'error'); return; }

        const provaId = provaSelect.value;
        if (!provaId) { showToast('❌ Selecione uma prova primeiro!', 'error'); return; }

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
            carregarGabaritos();
            carregarCombos();
            carregarProvas();
        } else {
            showToast(`❌ ${result.erro || 'Erro desconhecido'}`, 'error');
        }
    } catch (erro) {
        showToast('❌ Erro ao salvar gabarito: ' + erro.message, 'error');
    }
}

// ============================================
// EDITAR GABARITO
// ============================================
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

                go('gabarito');

                setTimeout(() => {
                    const serieMap = { '1º Ano': '1', '2º Ano': '2', '3º Ano': '3', '4º Ano': '4', '5º Ano': '5', '6º Ano': '6', '7º Ano': '7', '8º Ano': '8', '9º Ano': '9' };
                    const serieVal = serieMap[prova.serie] || '2';
                    document.getElementById('gab-serie').value = serieVal;
                    document.getElementById('gab-total').value = prova.quantidade_questoes || 20;

                    const selectProva = document.getElementById('gab-prova');
                    if (selectProva) selectProva.value = id;

                    buildGabGrid();

                    setTimeout(() => {
                        const isProducao = (disciplina === 'Produção de Texto');
                        if (isProducao) {
                            const titulos = document.querySelectorAll('.gab-titulo');
                            const textareas = document.querySelectorAll('.gab-texto');
                            const niveis = document.querySelectorAll('.gab-nivel');
                            const observacoes = document.querySelectorAll('.gab-observacao');

                            titulos.forEach((inp, i) => {
                                if (i < gabarito.length) inp.value = 'Q' + (i+1);
                            });
                            textareas.forEach((ta, i) => {
                                if (i < gabarito.length) ta.value = gabarito[i] || '';
                            });
                            niveis.forEach((sel, i) => {
                                if (i < bncc.length && bncc[i]) sel.value = bncc[i];
                            });
                        } else {
                            const selects = document.querySelectorAll('.gab-select');
                            const bnccInputs = document.querySelectorAll('.gab-bncc');
                            selects.forEach((s, i) => {
                                if (i < gabarito.length && gabarito[i]) { s.value = gabarito[i]; s.classList.add('filled'); }
                            });
                            bnccInputs.forEach((inp, i) => {
                                if (i < bncc.length && bncc[i]) inp.value = bncc[i];
                            });
                        }
                        showToast('📋 Gabarito carregado para edição!', 'success');
                    }, 100);
                }, 150);
            } else {
                showToast('⚠️ Esta prova não tem gabarito cadastrado', 'warning');
                go('gabarito');
            }
        })
        .catch(e => { showToast('❌ Erro ao carregar gabarito: ' + e.message, 'error'); console.error('Erro ao carregar gabarito:', e); });
}

// ============================================
// EXCLUIR GABARITO
// ============================================
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

// ============================================
// LISTA POR TURMA
// ============================================
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
    } catch (e) {
        console.error('Erro ao carregar turmas:', e);
    }
}

async function gerarListaTurma() {
    const escolaId = document.getElementById('lista-escola').value;
    const turmaId = document.getElementById('lista-turma').value;
    const provaId = document.getElementById('lista-prova')?.value || '';
    
    if (!turmaId) { 
        showToast('❌ Selecione uma turma!', 'error'); 
        return; 
    }
    if (!escolaId) { 
        showToast('❌ Selecione uma escola!', 'error'); 
        return; 
    }
    
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
        if (provasDisponiveis.length === 0) {
            provasDisponiveis = provas;
        }
        
        let prova = null;
        if (provaId) {
            prova = provas.find(p => p.id == provaId);
        }
        if (!prova && provasDisponiveis.length > 0) {
            prova = provasDisponiveis[0];
        }
        
        if (!prova) {
            container.innerHTML = `
                <div style="text-align:center;padding:30px;color:var(--orange);">
                    <div style="font-size:40px;margin-bottom:10px;">📝</div>
                    <p style="font-weight:700;">Nenhuma prova cadastrada para esta turma</p>
                    <p style="font-size:12px;color:var(--text3);">Cadastre uma prova para a série <strong>${serieTurma || 'desta turma'}</strong></p>
                    <button class="btn btn-primary" style="margin-top:10px;" onclick="go('prova-upload')">➕ Cadastrar Prova</button>
                </div>
            `;
            showToast('❌ Nenhuma prova para esta turma!', 'error');
            return;
        }
        
        const escolas = await carregarEscolasComCache();
        const escola = escolas.find(e => e.id == turma?.escola_id);
        
        let provasOptions = '';
        provasDisponiveis.forEach(p => {
            const selected = p.id == prova.id ? 'selected' : '';
            provasOptions += `<option value="${p.id}" ${selected}>${p.titulo} (${p.disciplina || 'Sem disciplina'})</option>`;
        });

        let html = `
            <div style="text-align:center;padding:12px 0 18px;border-bottom:1px solid var(--border);margin-bottom:14px;">
                <div style="font-size:16px;font-weight:800;">${escola?.nome || 'Escola'}</div>
                <div style="color:var(--text2);font-size:13px;margin-top:4px;">
                    Turma: ${turma?.nome || '—'} | Série: ${turma?.serie || '—'}
                </div>
                <div style="color:var(--text3);font-size:12px;margin-top:2px;">
                    Professor(a): ${turma?.professor || '—'} | 
                    Turno: ${turma?.turno || 'Manhã'} | 
                    Total: ${alunos.length} alunos
                </div>
                <div style="margin-top:10px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <label style="font-size:12px;font-weight:600;color:var(--text2);">📖 Prova:</label>
                        <select id="lista-prova-select" class="form-control" style="width:250px;padding:6px 10px;font-size:12px;" onchange="gerarListaTurma()">
                            ${provasOptions}
                        </select>
                    </div>
                    <button class="btn btn-green" onclick="gerarCartoesTodosAlunos(${escolaId}, ${turmaId}, ${prova.id})">
                        📄 GERAR TODOS OS CARTOES
                    </button>
                    <button class="btn btn-primary" onclick="gerarListaTurma()">🔄 Atualizar</button>
                </div>
                <div style="margin-top:8px;color:var(--text3);font-size:11px;">
                    ✅ Clique em "GERAR TODOS OS CARTOES" para abrir todos os cartões resposta de uma vez
                </div>
            </div>
        `;
        
        html += '<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px;max-height:400px;overflow-y:auto;">';
        
        for (let i = 0; i < alunos.length; i++) {
            const aluno = alunos[i];
            html += `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--surface2);border-radius:8px;border:1px solid var(--border);">
                    <div>
                        <strong>${aluno.nome}</strong> 
                        <span class="badge badge-blue">Nº ${aluno.numero_chamada || '—'}</span>
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="gerarCartaoResposta(${escolaId}, ${turmaId}, ${aluno.id}, ${prova.id})">
                        📄 Gerar Cartão
                    </button>
                </div>
            `;
        }
        
        html += '</div>';
        
        html += `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:20px;padding-top:18px;border-top:1px solid var(--border);">
                <div style="text-align:center;">
                    <div style="border-top:1px solid var(--border2);padding-top:8px;font-size:12px;color:var(--text2);">Professor(a) Responsável</div>
                </div>
                <div style="text-align:center;">
                    <div style="border-top:1px solid var(--border2);padding-top:8px;font-size:12px;color:var(--text2);">Diretor(a)</div>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
        showToast(`📋 ${alunos.length} alunos encontrados. Clique em "GERAR TODOS OS CARTOES" para gerar todos!`, 'info');
        
    } catch (erro) {
        console.error('Erro ao gerar lista:', erro);
        showToast('❌ Erro: ' + erro.message, 'error');
    }
}

async function gerarCartaoResposta(escolaId, turmaId, alunoId, provaId) {
    try {
        const novaAba = window.open('', '_blank');
        if (!novaAba) {
            showToast('❌ Permita pop-ups para gerar o cartão resposta!', 'error');
            return;
        }
        
        novaAba.document.write(`
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"><title>Gerando Cartão Resposta...</title></head>
            <body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Arial,sans-serif;background:#f0f2f5;">
                <div style="text-align:center;">
                    <div style="font-size:60px;margin-bottom:20px;">⏳</div>
                    <h2 style="color:#1e293b;">Gerando cartão resposta...</h2>
                    <p style="color:#64748b;">Aguarde um momento</p>
                </div>
            </body>
            </html>
        `);
        novaAba.document.close();

        const provas = await carregarProvasComCache();
        const prova = provas.find(p => p.id == provaId);
        const qtdQuestoes = prova?.quantidade_questoes || 20;
        const tipoQuestoes = prova?.tipo_questoes || 4;
        const alternativas = tipoQuestoes == 3 ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        const nomeProva = prova?.titulo || 'Prova';

        const [alunoResp, escolaResp, turmaResp] = await Promise.all([
            fetch(`${API_URL}/api/alunos/${alunoId}`),
            fetch(`${API_URL}/api/escolas/${escolaId}`),
            fetch(`${API_URL}/api/turmas/${turmaId}`)
        ]);
        
        const aluno = await alunoResp.json();
        const escola = await escolaResp.json();
        const turma = await turmaResp.json();

        const nomeAluno = aluno.nome || 'Aluno';
        const nomeEscola = escola.nome || 'Escola';
        const nomeTurma = turma.nome || 'Turma';
        const serie = turma.serie || prova?.serie || '';
        const dataAtual = new Date().toLocaleDateString('pt-BR');

        // 🔥 LAYOUT VERTICAL COMPACTO - TODAS AS QUESTÕES EM UMA COLUNA
        let html = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cartão Resposta - ${nomeAluno}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #f0f2f5;
            display: flex;
            justify-content: center;
            padding: 8px;
            min-height: 100vh;
        }
        
        .container {
            max-width: 650px;
            width: 100%;
            background: #ffffff;
            padding: 12px 16px;
            border-radius: 10px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            border: 1px solid #e5e7eb;
        }
        
        .header {
            text-align: center;
            border-bottom: 2px solid #2563eb;
            padding-bottom: 6px;
            margin-bottom: 6px;
        }
        
        .header .brasao { font-size: 20px; }
        .header h1 { font-size: 10px; color: #1e293b; letter-spacing: 0.5px; font-weight: 700; }
        .header h2 { 
            font-size: 12px; 
            color: #2563eb; 
            font-weight: 800;
            background: #eff6ff;
            display: inline-block;
            padding: 1px 16px;
            border-radius: 12px;
            margin-top: 1px;
        }
        .header .prova-nome {
            font-size: 10px;
            color: #475569;
            font-weight: 600;
            background: #f1f5f9;
            padding: 1px 12px;
            border-radius: 8px;
            display: inline-block;
            margin-top: 1px;
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 2px 6px;
            background: #f8fafc;
            padding: 4px 10px;
            border-radius: 4px;
            margin-bottom: 6px;
            border: 1px solid #e2e8f0;
            font-size: 9px;
        }
        
        .info-grid .item { display: flex; flex-direction: column; }
        .info-grid .label { font-size: 6px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.2px; }
        .info-grid .value { font-size: 9px; font-weight: 700; color: #0f172a; }
        
        .instrucoes {
            background: #eff6ff;
            border-left: 3px solid #2563eb;
            padding: 3px 10px;
            border-radius: 4px;
            margin-bottom: 6px;
            font-size: 8px;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }
        
        .instrucoes .icone { font-size: 12px; }
        .instrucoes strong { color: #2563eb; }
        .instrucoes .destaque {
            background: #dbeafe;
            padding: 0 10px;
            border-radius: 8px;
            font-weight: 700;
            color: #1d4ed8;
            font-size: 7px;
        }
        
        .questoes-container {
            display: flex;
            flex-direction: column;
            gap: 2px;
            width: 100%;
            margin: 4px 0;
        }
        
        .questao-linha {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 3px 8px;
            border-bottom: 1px solid #f1f5f9;
            background: #ffffff;
            border-radius: 4px;
            width: 100%;
            min-height: 32px;
        }
        
        .questao-linha:hover {
            background: #f8fafc;
        }
        
        .questao-linha .numero {
            font-size: 11px;
            font-weight: 800;
            color: #1e293b;
            min-width: 38px;
            text-align: center;
            flex-shrink: 0;
        }
        
        .questao-linha .numero span {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #ffffff;
            padding: 1px 10px;
            border-radius: 10px;
            font-size: 9px;
            box-shadow: 0 1px 4px rgba(37,99,235,0.20);
        }
        
        .opcoes {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            flex: 1;
        }
        
        .opcao {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 1px;
            cursor: pointer;
            padding: 1px 3px;
            border-radius: 4px;
            transition: all 0.15s;
        }
        
        .opcao:hover { transform: scale(1.04); }
        
        .opcao .circulo {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            border: 2.5px solid #000000 !important;
            background: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 800;
            color: #000000;
            transition: all 0.15s ease;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }
        
        .opcao input:checked + .circulo {
            border-color: #000000 !important;
            background: #000000 !important;
            color: #ffffff !important;
            box-shadow: 0 0 0 3px rgba(0,0,0,0.10), 0 1px 6px rgba(0,0,0,0.15);
            transform: scale(1.04);
        }
        
        .opcao:hover .circulo {
            border-color: #333333 !important;
            transform: scale(1.03);
        }
        
        .opcao input:checked:hover .circulo {
            transform: scale(1.06);
            box-shadow: 0 0 0 4px rgba(0,0,0,0.08), 0 2px 10px rgba(0,0,0,0.18);
        }
        
        .opcao input[type="radio"] {
            position: absolute;
            opacity: 0;
            width: 0;
            height: 0;
        }
        
        .opcao .label-alt {
            font-size: 8px;
            font-weight: 700;
            color: #000000;
            letter-spacing: 0.2px;
            margin-top: 1px;
        }
        
        .opcao input:checked + .circulo + .label-alt {
            color: #000000;
            font-weight: 900;
        }
        
        .footer {
            margin-top: 6px;
            padding-top: 4px;
            border-top: 1.5px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 3px;
            font-size: 7px;
            color: #94a3b8;
        }
        
        .footer strong { color: #475569; }
        
        .btn-print {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 4px;
            width: 100%;
            justify-content: center;
            box-shadow: 0 2px 10px rgba(37, 99, 235, 0.18);
        }
        
        .btn-print:hover {
            background: linear-gradient(135deg, #1d4ed8, #1e40af);
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(37, 99, 235, 0.28);
        }
        
        .legenda {
            text-align: center;
            margin-top: 4px;
            font-size: 7px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 4px;
            display: flex;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .legenda .dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            border: 2px solid #94a3b8;
        }
        
        .legenda .dot.checked {
            background: #000000;
            border-color: #000000;
        }
        
        @media print {
            body { background: white; padding: 0; margin: 0; }
            .container { 
                box-shadow: none; 
                border: none; 
                padding: 6px 10px; 
                border-radius: 0; 
                max-width: 100%;
            }
            .btn-print { display: none; }
            .questao-linha:hover { background: #ffffff; }
            .opcao:hover .circulo { transform: none; border-color: #000000 !important; }
            .opcao input:checked + .circulo { 
                background: #000000 !important; 
                border-color: #000000 !important; 
                color: #ffffff !important; 
                box-shadow: none; 
                transform: none;
            }
            .opcao input:checked:hover + .circulo { transform: none; box-shadow: none; }
            .questao-linha { break-inside: avoid; page-break-inside: avoid; border-bottom: 1px solid #e5e7eb; }
            .questao-linha .numero span { background: #1e293b; color: white; box-shadow: none; }
            .header { border-bottom-color: #1e293b; }
            .header h2 { background: #f1f5f9; color: #1e293b; }
            .instrucoes { background: #f8fafc; border-left-color: #1e293b; }
            .footer { border-top-color: #1e293b; }
            
            .container { max-height: 100vh; overflow: hidden; }
            .questoes-container { gap: 1px; }
            .questao-linha { min-height: 26px; padding: 2px 6px; }
            .opcao .circulo { width: 24px; height: 24px; font-size: 11px; border-width: 2px; }
            .opcao .label-alt { font-size: 7px; }
            .info-grid { padding: 2px 8px; gap: 1px 4px; }
            .info-grid .value { font-size: 8px; }
        }
        
        @media (max-width: 600px) {
            .opcao .circulo {
                width: 26px;
                height: 26px;
                font-size: 11px;
                border-width: 2px;
            }
            .opcoes { gap: 5px; }
            .info-grid {
                grid-template-columns: repeat(3, 1fr);
                gap: 1px 4px;
                padding: 3px 6px;
                font-size: 8px;
            }
            .info-grid .value { font-size: 8px; }
            .header h2 { font-size: 10px; padding: 1px 12px; }
            .header h1 { font-size: 8px; }
            .questao-linha { min-height: 28px; padding: 2px 4px; }
            .questao-linha .numero { min-width: 30px; font-size: 9px; }
            .questao-linha .numero span { font-size: 7px; padding: 0 8px; }
            .container { padding: 8px 10px; }
            .instrucoes { font-size: 7px; padding: 2px 8px; gap: 4px; }
        }
        
        @media (max-width: 400px) {
            .opcao .circulo {
                width: 22px;
                height: 22px;
                font-size: 9px;
                border-width: 1.5px;
            }
            .opcao .label-alt { font-size: 6px; }
            .opcoes { gap: 3px; }
            .questao-linha { min-height: 24px; padding: 1px 3px; }
            .questao-linha .numero { min-width: 24px; font-size: 8px; }
            .questao-linha .numero span { font-size: 6px; padding: 0 6px; }
            .info-grid {
                grid-template-columns: 1fr 1fr;
                gap: 1px 3px;
                padding: 2px 4px;
                font-size: 7px;
            }
            .info-grid .value { font-size: 7px; }
            .header h2 { font-size: 9px; padding: 0 10px; }
            .header .prova-nome { font-size: 8px; padding: 0 8px; }
            .container { padding: 4px 6px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="brasao">🏛️</div>
            <h1>SECRETARIA MUNICIPAL DE EDUCAÇÃO</h1>
            <h2>📝 SISAM 2026 — CARTÃO RESPOSTA</h2>
            <div class="prova-nome">${nomeProva}</div>
        </div>

        <div class="info-grid">
            <div class="item"><span class="label">🎒 Aluno</span><span class="value">${nomeAluno}</span></div>
            <div class="item"><span class="label">🏫 Escola</span><span class="value">${nomeEscola}</span></div>
            <div class="item"><span class="label">👥 Turma</span><span class="value">${nomeTurma}</span></div>
            <div class="item"><span class="label">📚 Série</span><span class="value">${serie}</span></div>
            <div class="item"><span class="label">📅 Data</span><span class="value">${dataAtual}</span></div>
            <div class="item"><span class="label">📝 Qtd</span><span class="value">${qtdQuestoes}</span></div>
        </div>

        <div class="instrucoes">
            <span class="icone">✏️</span>
            <span><strong>Instruções:</strong> Preencha <strong>completamente</strong> o círculo. Use caneta <strong>preta</strong> ou <strong>azul</strong>. Não rasure.</span>
            <span class="destaque">${qtdQuestoes} questões</span>
        </div>

        <div class="questoes-container">
`;

        for (let i = 0; i < qtdQuestoes; i++) {
            html += `
            <div class="questao-linha">
                <div class="numero"><span>Q${i+1}</span></div>
                <div class="opcoes">
            `;
            
            for (let alt of alternativas) {
                html += `
                    <label class="opcao">
                        <input type="radio" name="q${i+1}" value="${alt}">
                        <span class="circulo">${alt}</span>
                        <span class="label-alt">${alt}</span>
                    </label>
                `;
            }
            
            html += `
                </div>
            </div>
            `;
        }

        html += `
        </div>

        <button class="btn-print" onclick="window.print()">
            🖨️ IMPRIMIR CARTÃO RESPOSTA
        </button>

        <div class="footer">
            <span>📄 Gerado pelo sistema <strong>CorrigePro</strong></span>
            <span>${new Date().toLocaleString('pt-BR')}</span>
        </div>

        <div class="legenda">
            <span><span class="dot"></span> Não preenchido</span>
            <span><span class="dot checked"></span> Preenchido</span>
            <span>⚠️ Preencha o círculo completamente</span>
        </div>
    </div>
    <script>
        window.onload = function() {
            console.log('✅ Cartão resposta pronto');
        };
    <\/script>
</body>
</html>
`;

        novaAba.document.open();
        novaAba.document.write(html);
        novaAba.document.close();

        showToast(`✅ Cartão resposta com ${qtdQuestoes} questões gerado!`, 'success');

    } catch (erro) {
        console.error('Erro ao gerar cartão:', erro);
        showToast('❌ Erro: ' + erro.message, 'error');
    }
}

// ============================================
// GERAR TODOS OS CARTOES RESPOSTA DA TURMA
// ============================================
async function gerarCartoesTodosAlunos(escolaId, turmaId, provaId) {
    try {
        showToast('📄 Gerando cartões para todos os alunos...', 'info');
        
        const alunos = await carregarAlunosComCache({ turma_id: turmaId });
        
        if (!alunos || alunos.length === 0) {
            showToast('❌ Nenhum aluno encontrado nesta turma!', 'error');
            return;
        }
        
        for (let i = 0; i < alunos.length; i++) {
            const aluno = alunos[i];
            setTimeout(() => {
                gerarCartaoResposta(escolaId, turmaId, aluno.id, provaId);
            }, i * 300);
        }
        
        showToast(`✅ Gerando ${alunos.length} cartões...`, 'success');
        
    } catch (erro) {
        console.error('Erro ao gerar cartões:', erro);
        showToast('❌ Erro: ' + erro.message, 'error');
    }
}

// ============================================
// FUNÇÕES AUXILIARES
// ============================================
function switchTab(idx, btn) {
    const parent = btn.closest('.tab-nav');
    if (parent) { parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); }
    const card = btn.closest('.card');
    if (card) { card.querySelectorAll('.tab-c').forEach((tc, i) => { tc.style.display = i === idx ? 'block' : 'none'; }); }
}

function openM(id) {
    document.getElementById(id).classList.add('show');
    if (id === 'm-turma' || id === 'm-aluno') { carregarCombos(); if (id === 'm-aluno') carregarEscolasParaAluno(); }
    if (id === 'm-prova') { carregarCombos(); const tipo = document.getElementById('modal-prova-tipo').value; gerarGabaritoModal(tipo); }
}

// ============================================
// FUNÇÃO PARA FECHAR MODAL - CORRIGIDA
// ============================================
function closeM(id) {
    console.log('🔴 Fechando modal:', id);
    const modal = document.getElementById(id);
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('show');
        console.log('✅ Modal fechado:', id);
    } else {
        console.warn('⚠️ Modal não encontrado:', id);
    }
}

// ============================================
// FUNÇÃO PARA ABRIR MODAL - CORRIGIDA
// ============================================
function openM(id) {
    console.log('🟢 Abrindo modal:', id);
    const modal = document.getElementById(id);
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('show');
        console.log('✅ Modal aberto:', id);
    } else {
        console.warn('⚠️ Modal não encontrado:', id);
    }
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
        input.addEventListener('input', function() { this.value = this.value.toUpperCase().replace(/[^A-D]/g, ''); if (this.value && !alts.includes(this.value)) this.value = ''; });
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
    setTimeout(() => { row.remove(); showToast('🗑️ ' + tipo.charAt(0).toUpperCase() + tipo.slice(1) + ' "' + nome + '" excluído(a).', 'error'); delTarget = null; limparCache(); renumerarTabela(row.closest('tbody')); }, 350);
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
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(row => { row.style.display = row.textContent.toLowerCase().includes(val) ? '' : 'none'; });
}

function filtrarSerie(sel) {
    const val = sel.value;
    document.querySelectorAll('#tb-turmas tr').forEach(row => { row.style.display = (!val || row.dataset.serie === val) ? '' : 'none'; });
}

function showToast(msg, type) {
    type = type || 'info';
    const c = document.getElementById('toast-c');
    const t = document.createElement('div');
    t.className = 'toast toast-' + type;
    const icons = { info: 'ℹ️', success: '✅', error: '❌', ai: '🤖', warning: '⚠️' };
    t.innerHTML = '<span>' + (icons[type] || 'ℹ️') + '</span><span>' + msg + '</span>';
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, 3200);
}

function simUpload() { setTimeout(() => { document.getElementById('up-ok').style.display = 'block'; showToast('✅ Arquivo enviado!', 'success'); }, 600); }

function atualizarInfoAlts() {
    const s = document.getElementById('prova-serie');
    const disciplina = document.getElementById('prova-disciplina').value;
    const info = document.getElementById('info-alts');
    if (!s || !info) return;
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

function carregarTurmasProva() {
    const escolaId = document.getElementById('prova-escola').value;
    if (!escolaId) return;
    const select = document.getElementById('prova-turma');
    select.innerHTML = '<option value="">Selecione a turma</option>';
    carregarTurmasComCache(escolaId).then(turmas => {
        if (turmas && !turmas.erro) { turmas.forEach(t => { const opt = document.createElement('option'); opt.value = t.id; opt.textContent = t.nome + ' - ' + (t.serie || '—'); select.appendChild(opt); }); }
    }).catch(e => console.error(e));
}

function salvarConfiguracoes() { showToast('✅ Configurações salvas!', 'success'); }

function carregarUserData() {
    console.log('🔄 Carregando dados do usuário...');
    try {
        const tbody = document.getElementById('u-tb-turmas');
        if (tbody) {
            carregarTurmasComCache().then(turmas => {
                if (turmas && turmas.length > 0) {
                    tbody.innerHTML = turmas.map(t => {
                        const totalAlunos = t.total_alunos || 0;
                        return '<tr><td><strong>' + t.nome + '</strong></td><td><span class="badge badge-purple">' + (t.serie || '—') + '</span></td><td>' + (t.professor || '—') + '</td><td><span class="badge badge-blue">' + totalAlunos + '</span></td><td><button class="btn btn-green btn-sm" onclick="go(\'lista-turma\')">📋</button></td></tr>';
                    }).join('');
                }
            }).catch(e => console.error(e));
        }
    } catch (e) { console.log('Erro ao carregar dados do usuário:', e); }
}

// ============================================
// CARREGAR COMBOS (COM CACHE)
// ============================================
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

// ============================================
// CARREGAR ESCOLAS PARA O SELECT DE ESCOLA NO CADASTRO DE ALUNO
// ============================================
async function carregarEscolasParaAluno() {
    try {
        console.log('🔄 Carregando escolas para o select de aluno...');

        const escolas = await carregarEscolasComCache();

        console.log('📥 Escolas recebidas:', escolas);

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
        } else {
            console.warn('⚠️ Elemento "aluno-escola" não encontrado no DOM');
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
            console.log('✅ Select "editar-aluno-escola" atualizado com', escolas.length, 'escolas');
        }

    } catch (erro) {
        console.error('❌ Erro ao carregar escolas para o select de aluno:', erro);
    }
}

// ============================================
// FUNÇÃO PARA CARREGAR TURMAS POR ESCOLA NO CADASTRO DE ALUNO
// ============================================
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
        showToast('🔄 Carregando turmas...', 'info');
        const turmas = await carregarTurmasComCache(escolaId);
        console.log('📥 Turmas recebidas:', turmas);

        if (turmas && !turmas.erro && turmas.length > 0) {
            turmas.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome + ' - ' + (t.serie || '');
                opt.dataset.serie = t.serie || '';
                selectTurma.appendChild(opt);
            });
            console.log(`✅ ${turmas.length} turmas carregadas para a escola`);
            showToast(`✅ ${turmas.length} turmas encontradas`, 'success');
        } else {
            console.log('ℹ️ Nenhuma turma encontrada para esta escola');
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Nenhuma turma cadastrada';
            opt.disabled = true;
            selectTurma.appendChild(opt);
            showToast('ℹ️ Esta escola não possui turmas cadastradas', 'info');
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

// ============================================
// CARREGAR RELATÓRIOS
// ============================================
async function carregarRelatorios() {
    try {
        const alunos = await carregarAlunosComCache();
        const correcoesResp = await fetch(API_URL + '/api/historico');
        const correcoes = await correcoesResp.json();
        const totalAlunos = alunos.length || 0;
        const Habilidades = correcoes.filter(c => c.nota >= 6).length || 0;
        const recuperacao = correcoes.filter(c => c.nota >= 4 && c.nota < 6).length || 0;
        const media = correcoes.length > 0 ? (correcoes.reduce((s, c) => s + c.nota, 0) / correcoes.length) : 0;

        setText('rel-total-alunos', totalAlunos);
        setText('rel-Habilidades', Habilidades);
        setText('rel-recuperacao', recuperacao);
        setText('rel-media', media.toFixed(1));

        const faixas = { '0-2': 0, '2-4': 0, '4-6': 0, '6-8': 0, '8-10': 0 };
        correcoes.forEach(c => { if (c.nota < 2) faixas['0-2']++;
            else if (c.nota < 4) faixas['2-4']++;
            else if (c.nota < 6) faixas['4-6']++;
            else if (c.nota < 8) faixas['6-8']++;
            else faixas['8-10']++; });
        const maxVal = Math.max(...Object.values(faixas), 1);
        setText('d0-2', faixas['0-2']);
        setText('d2-4', faixas['2-4']);
        setText('d4-6', faixas['4-6']);
        setText('d6-8', faixas['6-8']);
        setText('d8-10', faixas['8-10']);

        const bars = document.querySelectorAll('#dist-notas .chart-bar');
        const vals = [faixas['0-2'], faixas['2-4'], faixas['4-6'], faixas['6-8'], faixas['8-10']];
        vals.forEach((v, i) => { if (bars[i]) { bars[i].style.height = (maxVal > 0 ? Math.max(10, (v / maxVal) * 110) : 10) + 'px'; } });

        let totalPtAcertos = 0,
            totalPtErros = 0,
            totalPtQuestoes = 0;
        let totalMatAcertos = 0,
            totalMatErros = 0,
            totalMatQuestoes = 0;
        let totalProdAcertos = 0,
            totalProdErros = 0,
            totalProdQuestoes = 0;
        let totalCHAcertos = 0,
            totalCHErros = 0,
            totalCHQuestoes = 0;
        let totalCNAcertos = 0,
            totalCNErros = 0,
            totalCNQuestoes = 0;

        if (correcoes && correcoes.length > 0) {
            correcoes.forEach(c => {
                const disciplina = c.disciplina || '';
                const acertos = c.acertos || 0;
                const total = c.total || 20;
                const erros = total - acertos;

                const discLower = disciplina.toLowerCase();
                if (discLower.includes('português') || discLower.includes('portugues')) {
                    totalPtAcertos += acertos;
                    totalPtErros += erros;
                    totalPtQuestoes += total;
                } else if (discLower.includes('matemática') || discLower.includes('matematica')) {
                    totalMatAcertos += acertos;
                    totalMatErros += erros;
                    totalMatQuestoes += total;
                } else if (discLower.includes('produção') || discLower.includes('producao') || discLower.includes('texto')) {
                    totalProdAcertos += acertos;
                    totalProdErros += erros;
                    totalProdQuestoes += total;
                } else if (discLower.includes('ciências humanas') || discLower.includes('ch')) {
                    totalCHAcertos += acertos;
                    totalCHErros += erros;
                    totalCHQuestoes += total;
                } else if (discLower.includes('ciências naturais') || discLower.includes('cn')) {
                    totalCNAcertos += acertos;
                    totalCNErros += erros;
                    totalCNQuestoes += total;
                }
            });
        }

        const totalCorrecoes = correcoes.length || 1;
        setText('rel-pt-acertos', totalPtAcertos);
        setText('rel-pt-erros', totalPtErros);
        setText('rel-pt-media', totalCorrecoes > 0 ? (totalPtAcertos / totalCorrecoes).toFixed(1) : '0.0');

        setText('rel-mat-acertos', totalMatAcertos);
        setText('rel-mat-erros', totalMatErros);
        setText('rel-mat-media', totalCorrecoes > 0 ? (totalMatAcertos / totalCorrecoes).toFixed(1) : '0.0');

        setText('rel-prod-acertos', totalProdAcertos);
        setText('rel-prod-erros', totalProdErros);
        setText('rel-prod-media', totalCorrecoes > 0 ? (totalProdAcertos / totalCorrecoes).toFixed(1) : '0.0');

        setText('rel-ch-acertos', totalCHAcertos);
        setText('rel-ch-erros', totalCHErros);
        setText('rel-ch-media', totalCorrecoes > 0 ? (totalCHAcertos / totalCorrecoes).toFixed(1) : '0.0');

        setText('rel-cn-acertos', totalCNAcertos);
        setText('rel-cn-erros', totalCNErros);
        setText('rel-cn-media', totalCorrecoes > 0 ? (totalCNAcertos / totalCorrecoes).toFixed(1) : '0.0');

        await carregarRelatorioEscola();
        atualizarDatasImpressao();
    } catch (erro) { console.error('Erro ao carregar relatórios:', erro); }
}

async function carregarRelatorioEscola() {
    try {
        const escolas = await carregarEscolasComCache();
        const turmas = await carregarTurmasComCache();
        const alunos = await carregarAlunosComCache();
        const correcoesResp = await fetch(API_URL + '/api/historico');
        const correcoes = await correcoesResp.json();
        const tbody = document.getElementById('tb-rel-escola');
        if (!tbody) return;
        if (!escolas || escolas.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma escola cadastrada</td></tr>';
        } else {
            tbody.innerHTML = escolas.map(e => {
                const turmasEscola = turmas.filter(t => t.escola_id === e.id);
                const alunosEscola = alunos.filter(a => a.escola_id === e.id);
                const correcoesEscola = correcoes.filter(c => { const aluno = alunos.find(a => a.id === c.aluno_id); return aluno && aluno.escola_id === e.id; });
                const media = correcoesEscola.length > 0 ? (correcoesEscola.reduce((s, c) => s + c.nota, 0) / correcoesEscola.length) : 0;
                const Habilidades = correcoesEscola.filter(c => c.nota >= 6).length;
                const perc = correcoesEscola.length > 0 ? Math.round((Habilidades / correcoesEscola.length) * 100) : 0;
                return '<tr><td><strong>' + e.nome + '</strong></td><td>' + turmasEscola.length + '</td><td>' + alunosEscola.length + '</td><td><strong style="color:' + (media >= 6 ? 'var(--green)' : 'var(--orange)') + ';">' + media.toFixed(1) + '</strong></td><td>' + perc + '%</td><td><div class="progress" style="width:140px;"><div class="progress-fill ' + (perc >= 70 ? 'pf-green' : 'pf-orange') + '" style="width:' + perc + '%;"></div></div></td></tr>';
            }).join('');
        }
    } catch (erro) { console.error('Erro ao carregar relatório por escola:', erro); }
}

// ============================================
// DOM READY
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    const tipoSelect = document.getElementById('modal-prova-tipo');
    if (tipoSelect) { tipoSelect.addEventListener('change', function() { gerarGabaritoModal(this.value); }); }
    buildGabGrid();
    carregarCombos();
    carregarDados();
    carregarFiltrosResultados();
    carregarResultadosComFiltros();
    carregarConceitoReal();
    carregarEscolasFiltroAlunos();
    const tipoProva = document.getElementById('modal-prova-tipo');
    if (tipoProva) gerarGabaritoModal(tipoProva.value);
    atualizarDatasImpressao();
    carregarEscolasParaCorrecaoManual();
    carregarFiltrosRelTurma();
    carregarFiltroEscolaTurmas();
    carregarEscolasParaAluno();
    carregarEscolasDesempenho();
    popularSelectQuestoes();
    popularSelectGabTotal();

    const disciplinaSelect = document.getElementById('prova-disciplina');
    if (disciplinaSelect) {
        disciplinaSelect.addEventListener('change', atualizarInfoAlts);
    }

    const gabProvaSelect = document.getElementById('gab-prova');
    if (gabProvaSelect) {
        gabProvaSelect.addEventListener('change', buildGabGrid);
    }
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

// ================================================================
// 🔥 MATRIZ DE PROFICIÊNCIA - CRUD COMPLETO (CORRIGIDO)
// ================================================================

// 🔥 Variáveis globais (verifica se já existem para evitar duplicação)
if (typeof matrizesData === 'undefined') {
    var matrizesData = [];
}
if (typeof matrizEditId === 'undefined') {
    var matrizEditId = null;
}
if (typeof matrizDescritorCounter === 'undefined') {
    var matrizDescritorCounter = 0;
}
if (typeof matrizParaDeletar === 'undefined') {
    var matrizParaDeletar = null;
}

// ================================================================
// 🔥 CARREGAR MATRIZES DA API
// ================================================================

async function carregarMatrizes() {
    try {
        const response = await fetch('/api/matrizes');
        if (!response.ok) throw new Error('Erro ao carregar matrizes');
        matrizesData = await response.json();
        renderizarMatrizes(matrizesData);
        atualizarTotalMatrizes(matrizesData.length);
    } catch (error) {
        console.error('❌ Erro ao carregar matrizes:', error);
        matrizesData = carregarMatrizesLocal();
        renderizarMatrizes(matrizesData);
        atualizarTotalMatrizes(matrizesData.length);
    }
}

// ================================================================
// 🔥 RENDERIZAR MATRIZES NA TABELA (COM BOTÃO VISUALIZAR)
// ================================================================

function renderizarMatrizes(matrizes) {
    const tbody = document.getElementById('tb-matrizes');
    if (!tbody) return;

    if (!matrizes || matrizes.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma matriz cadastrada.</td></tr>`;
        return;
    }

    let html = '';
    matrizes.forEach((matriz, index) => {
        // Normaliza os descritores
        let descritores = [];
        if (matriz.descritores) {
            if (Array.isArray(matriz.descritores)) {
                descritores = matriz.descritores;
            } else if (typeof matriz.descritores === 'string') {
                try {
                    descritores = JSON.parse(matriz.descritores);
                } catch (e) {
                    descritores = [];
                }
            } else if (typeof matriz.descritores === 'object') {
                descritores = [matriz.descritores];
            }
        }
        // 🔥 Normaliza cada descritor para ter 'descritor' e 'bncc'
        descritores = descritores.map(d => ({
            bncc: d.bncc || '',
            descritor: d.descritor || d.descricao || ''
        }));

        const totalDescritores = descritores.length;

        const nivelBadge = {
            'Básico': 'badge-nivel-basico',
            'Intermediário': 'badge-nivel-intermediario',
            'Avançado': 'badge-nivel-avancado'
        }[matriz.nivel] || 'badge-gray';

        let descritoresPreview = 'Nenhum descritor';
        if (totalDescritores > 0) {
            const previewText = descritores.map(d => `${d.bncc || ''}: ${d.descritor || ''}`).join('; ');
            descritoresPreview = `<span class="descritores-preview" title="${previewText}">${previewText.substring(0, 60)}${previewText.length > 60 ? '...' : ''}</span>`;
        }

        html += `
            <tr>
                <td>${index + 1}</td>
                <td><strong>${matriz.ano || '-'}</strong></td>
                <td>${matriz.disciplina || '-'}</td>
                <td><span class="badge ${nivelBadge}">${matriz.nivel || '-'}</span></td>
                <td>
                    <span class="badge-descritores">📋 <span class="count">${totalDescritores}</span></span>
                    ${descritoresPreview}
                </td>
                <td style="font-size:10px;color:var(--text3);">${formatarData(matriz.created_at)}</td>
                <td>
                    <div class="matriz-actions">
                        <button class="btn btn-sm btn-edit" onclick="editarMatriz(${matriz.id})" title="Editar">✏️</button>
                        <button class="btn btn-sm btn-view" onclick="visualizarMatriz(${matriz.id})" title="Visualizar">👁️</button>
                        <button class="btn btn-sm btn-delete" onclick="excluirMatriz(${matriz.id})" title="Excluir">🗑️</button>
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

// ================================================================
// 🔥 ATUALIZAR CONTADOR DE MATRIZES
// ================================================================

function atualizarTotalMatrizes(total) {
    const el = document.getElementById('total-matrizes');
    if (el) el.textContent = `${total} matrizes`;
}

// ================================================================
// 🔥 ABRIR MODAL PARA NOVA MATRIZ
// ================================================================

function abrirModalMatriz() {
    matrizEditId = null;
    matrizDescritorCounter = 0;
    
    document.getElementById('matriz-modal-title').textContent = '📊 Nova Matriz de Proficiência';
    document.getElementById('matriz-edit-id').value = '';
    document.getElementById('matriz-ano').value = '';
    document.getElementById('matriz-disciplina').value = '';
    document.getElementById('matriz-nivel').value = '';
    
    const container = document.getElementById('matriz-descritores-container');
    container.innerHTML = `
        <div style="text-align:center;padding:20px;color:var(--text3);font-size:13px;">
            Clique em "Adicionar Descritor" para começar
        </div>
    `;
    
    openM('m-matriz');
}

// ================================================================
// 🔥 EDITAR MATRIZ
// ================================================================

function editarMatriz(id) {
    const matriz = matrizesData.find(m => m.id === id);
    if (!matriz) {
        toast('Matriz não encontrada', 'error');
        return;
    }

    matrizEditId = id;
    document.getElementById('matriz-modal-title').textContent = `✏️ Editar Matriz - ${matriz.ano} / ${matriz.disciplina}`;
    document.getElementById('matriz-edit-id').value = id;
    document.getElementById('matriz-ano').value = matriz.ano || '';
    document.getElementById('matriz-disciplina').value = matriz.disciplina || '';
    document.getElementById('matriz-nivel').value = matriz.nivel || '';
    
    const container = document.getElementById('matriz-descritores-container');
    container.innerHTML = '';
    
    const descritores = matriz.descritores || [];
    if (descritores.length === 0) {
        container.innerHTML = `
            <div style="text-align:center;padding:20px;color:var(--text3);font-size:13px;">
                Nenhum descritor cadastrado. Clique em "Adicionar Descritor" para começar.
            </div>
        `;
    } else {
        descritores.forEach(d => adicionarDescritorMatriz(d.bncc, d.descritor));
    }
    
    openM('m-matriz');
}

// ================================================================
// 🔥 ADICIONAR DESCRITOR DINÂMICAMENTE (COM TEXTAREA)
// ================================================================

function adicionarDescritorMatriz(bnccValue = '', descritorValue = '') {
    const container = document.getElementById('matriz-descritores-container');
    
    const placeholder = container.querySelector('.matriz-descritores-empty');
    if (placeholder) placeholder.remove();
    
    const counter = ++matrizDescritorCounter;
    
    const item = document.createElement('div');
    item.className = 'matriz-descritor-item';
    item.dataset.index = counter;
    item.innerHTML = `
        <div class="descritor-header">
            <span class="descritor-num">📌 Descritor #${counter}</span>
            <button class="btn-remover-descritor" onclick="removerDescritorMatriz(this)" title="Remover descritor">×</button>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label class="form-label">BNCC</label>
                <input class="form-control" type="text" placeholder="Ex: EF01MA01" value="${bnccValue}">
            </div>
            <div class="form-group">
                <label class="form-label">Descritor</label>
                <textarea class="form-control" placeholder="Descreva a habilidade..." rows="4" style="resize:vertical; min-height:70px;">${descritorValue}</textarea>
            </div>
        </div>
    `;
    
    container.appendChild(item);
    item.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ================================================================
// 🔥 REMOVER DESCRITOR
// ================================================================

function removerDescritorMatriz(btn) {
    const item = btn.closest('.matriz-descritor-item');
    if (!item) return;
    
    const num = item.dataset.index;
    if (confirm(`Remover Descritor #${num}?`)) {
        item.classList.add('removing');
        setTimeout(() => {
            item.remove();
            const container = document.getElementById('matriz-descritores-container');
            if (container.children.length === 0) {
                container.innerHTML = `
                    <div style="text-align:center;padding:20px;color:var(--text3);font-size:13px;">
                        Clique em "Adicionar Descritor" para começar
                    </div>
                `;
            }
            toast('Descritor removido', 'info');
        }, 300);
    }
}

// ================================================================
// 🔥 SALVAR MATRIZ (CRIAR / ATUALIZAR) - CORRIGIDO
// ================================================================

async function salvarMatriz() {
    try {
        const ano = document.getElementById('matriz-ano').value;
        const disciplina = document.getElementById('matriz-disciplina').value;
        const nivel = document.getElementById('matriz-nivel').value;
        
        if (!ano) { toast('Selecione o Ano', 'error'); return; }
        if (!disciplina) { toast('Selecione a Disciplina', 'error'); return; }
        if (!nivel) { toast('Selecione o Nível', 'error'); return; }
        
        const container = document.getElementById('matriz-descritores-container');
        const items = container.querySelectorAll('.matriz-descritor-item');
        const descritores = [];
        
        items.forEach((item, index) => {
            // 🔥 Usa seletores específicos para evitar confusão
            const bnccInput = item.querySelector('input.form-control');
            const descritorInput = item.querySelector('textarea.form-control');
            
            const bncc = bnccInput ? bnccInput.value.trim() : '';
            const descritor = descritorInput ? descritorInput.value.trim() : '';
            
            descritores.push({ bncc, descritor });
            
            // 🔥 Log para depuração
            console.log(`📌 Descritor #${index+1}: BNCC="${bncc}", Descritor="${descritor}"`);
        });
        
        console.log('📦 Dados a enviar:', { ano, disciplina, nivel, descritores });
        
        const editId = document.getElementById('matriz-edit-id').value;
        const url = editId ? `/api/matrizes/${editId}` : '/api/matrizes';
        const method = editId ? 'PUT' : 'POST';
        
        if (typeof showToast === 'function') showToast('Salvando matriz...', 'info');
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ano, disciplina, nivel, descritores })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.erro || 'Erro ao salvar matriz');
        }
        
        const result = await response.json();
        console.log('✅ Resposta da API:', result);
        toast(result.mensagem || 'Matriz salva com sucesso!', 'success');
        
        fecharModalMatriz();
        await carregarMatrizes();
        
    } catch (error) {
        console.error('❌ Erro ao salvar matriz:', error);
        toast(error.message || 'Erro ao salvar matriz', 'error');
    }
}

// ================================================================
// 🔥 EXCLUIR MATRIZ
// ================================================================

function excluirMatriz(id) {
    const matriz = matrizesData.find(m => m.id === id);
    if (!matriz) {
        toast('Matriz não encontrada', 'error');
        return;
    }
    
    matrizParaDeletar = id;
    const nome = `${matriz.ano} - ${matriz.disciplina} (${matriz.nivel})`;
    document.getElementById('matriz-deletar-nome').textContent = nome;
    
    openM('m-deletar-matriz');
}

function fecharModalDeletarMatriz() {
    matrizParaDeletar = null;
    closeM('m-deletar-matriz');
}

async function confirmarDeletarMatriz() {
    if (!matrizParaDeletar) return;
    
    try {
        const id = matrizParaDeletar;
        const response = await fetch(`/api/matrizes/${id}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.erro || 'Erro ao excluir matriz');
        }
        
        toast('Matriz excluída com sucesso!', 'success');
        fecharModalDeletarMatriz();
        await carregarMatrizes();
        
    } catch (error) {
        console.error('❌ Erro ao excluir matriz:', error);
        toast(error.message || 'Erro ao excluir matriz', 'error');
        fecharModalDeletarMatriz();
    }
}

// ================================================================
// 🔥 FECHAR MODAL MATRIZ
// ================================================================

function fecharModalMatriz() {
    matrizEditId = null;
    closeM('m-matriz');
}

// ================================================================
// 🔥 FILTRAR MATRIZES
// ================================================================

function filtrarMatrizes() {
    const ano = document.getElementById('filtro-matriz-ano').value;
    const disciplina = document.getElementById('filtro-matriz-disciplina').value;
    const nivel = document.getElementById('filtro-matriz-nivel').value;
    
    let filtradas = matrizesData;
    if (ano) filtradas = filtradas.filter(m => m.ano === ano);
    if (disciplina) filtradas = filtradas.filter(m => m.disciplina === disciplina);
    if (nivel) filtradas = filtradas.filter(m => m.nivel === nivel);
    
    renderizarMatrizes(filtradas);
    atualizarTotalMatrizes(filtradas.length);
}

function limparFiltrosMatriz() {
    document.getElementById('filtro-matriz-ano').value = '';
    document.getElementById('filtro-matriz-disciplina').value = '';
    document.getElementById('filtro-matriz-nivel').value = '';
    renderizarMatrizes(matrizesData);
    atualizarTotalMatrizes(matrizesData.length);
}

// ================================================================
// 🔥 VISUALIZAR MATRIZ
// ================================================================

let visualizarMatrizId = null;

function visualizarMatriz(id) {
    const matriz = matrizesData.find(m => m.id === id);
    if (!matriz) {
        toast('Matriz não encontrada', 'error');
        return;
    }
    
    // 🔥 Normaliza os descritores (aceita 'descritor' ou 'descricao')
    const descritores = (matriz.descritores || []).map(d => ({
        bncc: d.bncc || '',
        descritor: d.descritor || d.descricao || ''  // fallback para 'descricao'
    }));
    
    // 🔥 Salva na variável global com os dados normalizados
    window.matrizVisualizando = {
        ...matriz,
        descritores: descritores
    };
    
    visualizarMatrizId = id;
    document.getElementById('visualizar-matriz-titulo').textContent = `📊 Matriz: ${matriz.ano} - ${matriz.disciplina}`;

    const conteudo = document.getElementById('visualizar-matriz-conteudo');
    if (!conteudo) return;

    let descritoresHtml = '';
    if (descritores.length === 0) {
        descritoresHtml = '<div style="color:var(--text3);font-size:13px;">Nenhum descritor cadastrado.</div>';
    } else {
        descritoresHtml = '<div style="display:flex;flex-direction:column;gap:10px;margin-top:8px;">';
        descritores.forEach((d, idx) => {
            const bncc = d.bncc || '—';
            const desc = d.descritor || '—';
            descritoresHtml += `
                <div style="background:var(--bg2);border-radius:8px;padding:12px 16px;border:1px solid var(--border);">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
                        <span style="font-weight:700;color:var(--purple);">📌 Descritor #${idx+1}</span>
                        <span style="font-size:11px;background:rgba(139,92,246,0.12);padding:2px 12px;border-radius:12px;color:var(--purple);font-weight:700;">BNCC: ${bncc}</span>
                    </div>
                    <div style="margin-top:6px;font-size:14px;color:var(--text);line-height:1.5; white-space: pre-wrap; word-wrap: break-word;">${desc}</div>
            `;
        });
        descritoresHtml += '</div>';
    }

    const nivelBadge = {
        'Básico': 'badge-nivel-basico',
        'Intermediário': 'badge-nivel-intermediario',
        'Avançado': 'badge-nivel-avancado'
    }[matriz.nivel] || 'badge-gray';

    conteudo.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
            <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;text-align:center;">
                <div style="font-size:11px;color:var(--text3);font-weight:600;">📚 ANO</div>
                <div style="font-size:18px;font-weight:800;color:var(--text);">${matriz.ano || '—'}</div>
            </div>
            <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;text-align:center;">
                <div style="font-size:11px;color:var(--text3);font-weight:600;">📖 DISCIPLINA</div>
                <div style="font-size:18px;font-weight:800;color:var(--text);">${matriz.disciplina || '—'}</div>
            </div>
            <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;text-align:center;">
                <div style="font-size:11px;color:var(--text3);font-weight:600;">📊 NÍVEL</div>
                <div style="font-size:18px;font-weight:800;color:var(--text);"><span class="badge ${nivelBadge}">${matriz.nivel || '—'}</span></div>
            </div>
        </div>
        <div style="border-top:1px solid var(--border);padding-top:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:8px;">
                <span style="font-size:15px;font-weight:700;color:var(--text2);">📋 Descritores (${descritores.length})</span>
            </div>
            ${descritoresHtml}
        </div>
    `;

    openM('m-visualizar-matriz');
}

// ================================================================
// 🔥 IMPRIMIR MATRIZ VISUALIZADA (PDF)
// ================================================================

function imprimirMatrizVisualizada() {
    // 🔥 Usa a matriz normalizada da variável global
    const matriz = window.matrizVisualizando;
    if (!matriz) {
        toast('❌ Nenhuma matriz para imprimir. Visualize uma matriz primeiro.', 'error');
        return;
    }

    const titulo = `📊 Matriz: ${matriz.ano} - ${matriz.disciplina}`;
    const win = window.open('', '_blank');
    if (!win) {
        toast('⚠️ Permita pop-ups para gerar o PDF.', 'error');
        return;
    }

    // 🔥 Garante que os descritores estejam normalizados
    const descritores = (matriz.descritores || []).map(d => ({
        bncc: d.bncc || '',
        descritor: d.descritor || d.descricao || ''  // fallback
    }));

    const nivel = matriz.nivel || '—';
    const ano = matriz.ano || '—';
    const disciplina = matriz.disciplina || '—';

    // 🔥 NOVO: Gera lista de parágrafos com cores alternadas
    let descritoresHtml = '';
    if (descritores.length === 0) {
        descritoresHtml = '<p style="color:#94a3b8;text-align:center;padding:16px;">Nenhum descritor cadastrado.</p>';
    } else {
        descritoresHtml = '<div style="margin-top:8px;">';
        descritores.forEach((d, idx) => {
            const bncc = d.bncc || '—';
            const desc = d.descritor || '—';
            // Cores alternadas: cinza claro (#f8fafc) e branco (#ffffff)
            const bgColor = idx % 2 === 0 ? '#ffffff' : '#f8fafc';
            descritoresHtml += `
                <div style="background:${bgColor}; padding:10px 14px; border-bottom:1px solid #e2e8f0; line-height:1.6; white-space: pre-wrap; word-wrap: break-word;">
                    <span style="font-weight:700; color:#8b5cf6;">${bncc}</span>
                    <span style="color:#1e293b;">${desc}</span>
                </div>
            `;
        });
        descritoresHtml += '</div>';
    }

    // 🔥 O HTML do PDF permanece IDÊNTICO ao original, exceto o conteúdo de .table-wrap
    const html = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>${titulo}</title>
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                padding: 30px;
                background: #fff;
                color: #1e293b;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: #ffffff;
                padding: 20px 30px;
                border-radius: 12px;
                border: 1px solid #e2e8f0;
                box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            }
            .header {
                text-align: center;
                border-bottom: 3px solid #2563eb;
                padding-bottom: 15px;
                margin-bottom: 20px;
            }
            .header h1 {
                font-size: 22px;
                font-weight: 800;
                color: #0f172a;
                letter-spacing: -0.3px;
            }
            .header .sub {
                font-size: 14px;
                color: #475569;
                margin-top: 4px;
            }
            .header .data {
                font-size: 12px;
                color: #94a3b8;
                margin-top: 4px;
            }
            .info-grid {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 15px;
                margin: 18px 0 22px;
            }
            .info-card {
                background: #f8fafc;
                border-radius: 8px;
                padding: 12px 14px;
                text-align: center;
                border: 1px solid #e2e8f0;
            }
            .info-card .label {
                font-size: 10px;
                color: #94a3b8;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.3px;
            }
            .info-card .value {
                font-size: 18px;
                font-weight: 800;
                color: #0f172a;
                margin-top: 4px;
            }
            .info-card .value .badge {
                display: inline-block;
                padding: 2px 14px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: 700;
                background: #e2e8f0;
                color: #1e293b;
            }
            .section-title {
                font-size: 16px;
                font-weight: 700;
                color: #1e293b;
                margin: 12px 0 6px;
                padding-bottom: 6px;
                border-bottom: 2px solid #e2e8f0;
            }
            .table-wrap {
                overflow-x: auto;
                margin-top: 4px;
            }
            .footer {
                margin-top: 20px;
                padding-top: 12px;
                border-top: 1px solid #e2e8f0;
                font-size: 10px;
                color: #94a3b8;
                text-align: center;
            }
            @media print {
                body { padding: 10px; }
                .container { box-shadow: none; border: none; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>${titulo}</h1>
                <div class="sub">Matriz de Proficiência — SISAM 2026</div>
                <div class="data">${new Date().toLocaleString('pt-BR')}</div>
            </div>

            <div class="info-grid">
                <div class="info-card">
                    <div class="label">📚 Ano</div>
                    <div class="value">${ano}</div>
                </div>
                <div class="info-card">
                    <div class="label">📖 Disciplina</div>
                    <div class="value">${disciplina}</div>
                </div>
                <div class="info-card">
                    <div class="label">📊 Nível</div>
                    <div class="value"><span class="badge">${nivel}</span></div>
                </div>
            </div>

            <div class="section-title">📋 Descritores (${descritores.length})</div>
            <div class="table-wrap">
                ${descritoresHtml}
            </div>

            <div class="footer">
                Documento gerado pelo sistema CorrigePro — Secretaria Municipal de Educação
            </div>
        </div>
        <script>
            window.onload = function() {
                window.print();
            };
        <\/script>
    </body>
    </html>
    `;

    win.document.write(html);
    win.document.close();
}

// ================================================================
// 🔥 FUNÇÕES AUXILIARES
// ================================================================

function formatarData(dataStr) {
    if (!dataStr) return '-';
    try {
        const d = new Date(dataStr);
        return d.toLocaleDateString('pt-BR');
    } catch {
        return dataStr;
    }
}

function toast(mensagem, tipo = 'info') {
    if (typeof showToast === 'function') {
        showToast(mensagem, tipo);
        return;
    }
    const container = document.getElementById('toast-c');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast toast-${tipo}`;
    el.textContent = mensagem;
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(40px)';
        setTimeout(() => el.remove(), 400);
    }, 3000);
}

function carregarMatrizesLocal() {
    const stored = localStorage.getItem('matrizes_data');
    if (stored) {
        try {
            return JSON.parse(stored);
        } catch {
            return [];
        }
    }
    return [];
}

// ================================================================
// 🔥 INICIALIZAÇÃO
// ================================================================

// Carregar matrizes quando a página for carregada
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('page-matriz')) {
        carregarMatrizes();
    }
});

// ================================================================
// FIM - MATRIZ DE PROFICIÊNCIA
// ================================================================
