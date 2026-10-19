// ============================================================
// JS/CORE.JS — Config, segurança, cache, progress, feedback, DOM
// Extraído de script.js — Corte 1
// Ordem: PRIMEIRO (antes de todos os outros)
// ============================================================

// ═══ CONFIGURAÇÃO DA API ═══
const API_URL = 'https://adabee-sistema-wg2a.onrender.com';

// ═══ ESTADO GLOBAL COMPARTILHADO ═══
let loginType = 'admin';
let camStream = null;
let camFacing = 'environment';
let delTarget = null;
let ultimaImagem = null;
let gerandoDocumento = false;
let paginaAtual = 'dashboard';

// ═══ SEGURANÇA — ESCAPE HTML (anti-XSS) ═══
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

// ═══ SISTEMA DE PROGRESSO VISUAL ═══
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

// ═══ SISTEMA DE FEEDBACK VISUAL PARA TABELAS ═══
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

// ═══ FUNÇÃO AUXILIAR SLEEP ═══
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ═══ SISTEMA DE CACHE ═══
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

// ═══ FUNÇÕES AUXILIARES DE DOM ═══
function setText(id, valor) {
    const el = document.getElementById(id);
    if (el) el.textContent = valor;
}

function setHTML(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

// ═══ PROCESSAR RESPOSTAS DA API ═══
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

// ═══ CÁLCULO DE CONCEITO ═══
function calcularConceito(porcentagem) {
    if (porcentagem <= 40) return 'inicial';
    if (porcentagem <= 60) return 'basico';
    if (porcentagem <= 80) return 'proficiente';
    return 'avancado';
}

// ═══ MAPEAMENTO GLOBAL DE DISCIPLINA ═══
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

// ═══ TOAST E MODAIS ═══
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

    if (id === 'm-turma' || id === 'm-aluno') {
        if (typeof carregarCombos === 'function') carregarCombos();
        if (id === 'm-aluno' && typeof carregarEscolasParaAluno === 'function') carregarEscolasParaAluno();
    }
    if (id === 'm-prova') {
        if (typeof carregarCombos === 'function') carregarCombos();
        const tipoEl = document.getElementById('modal-prova-tipo');
        if (tipoEl && typeof gerarGabaritoModal === 'function') gerarGabaritoModal(tipoEl.value);
    }
}

// ═══════════════════════════════════════════════════════════════
// ═══ ADICIONADO DO MONOLÍTICO — funções que faltavam aqui ═══
// ═══════════════════════════════════════════════════════════════

// Preenche datas de impressão em todos os relatórios
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

// Filtra tabelas por texto (search box)
function filtrarTabela(input, tbodyId) {
    const val = input.value.toLowerCase();
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(val) ? '' : 'none';
    });
}

// Filtra tabela de turmas por série
function filtrarSerie(sel) {
    const val = sel.value;
    document.querySelectorAll('#tb-turmas tr').forEach(row => {
        row.style.display = (!val || row.dataset.serie === val) ? '' : 'none';
    });
}

// Filtra as opções do select de turma conforme a série escolhida
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

// Renumera as linhas de uma tabela após exclusão
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

// Modal genérico de confirmação de exclusão
function excluir(btn, tipo, nome) {
    const row = btn.closest('tr');
    delTarget = { row, tipo, nome };
    document.getElementById('del-nome-txt').textContent = '"' + nome + '"';
    document.getElementById('del-modal').classList.add('show');
}

function cancelarDel() {
    document.getElementById('del-modal').classList.remove('show');
    delTarget = null;
}

function confirmarDel() {
    document.getElementById('del-modal').classList.remove('show');
    if (!delTarget) return;
    const { row, tipo, nome } = delTarget;
    row.classList.add('deleting');
    setTimeout(() => {
        row.remove();
        showToast('🗑️ ' + tipo.charAt(0).toUpperCase() + tipo.slice(1) + ' "' + nome + '" excluído(a).', 'error');
        delTarget = null;
        if (typeof limparCache === 'function') limparCache();
        renumerarTabela(row.closest('tbody'));
    }, 350);
}

// Switch de abas em modais
function switchTab(idx, btn) {
    const parent = btn.closest('.tab-nav');
    if (parent) {
        parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }
    const card = btn.closest('.card');
    if (card) {
        card.querySelectorAll('.tab-c').forEach((tc, i) => {
            tc.style.display = i === idx ? 'block' : 'none';
        });
    }
}

// Simula upload (feedback visual)
function simUpload() {
    setTimeout(() => {
        const el = document.getElementById('up-ok');
        if (el) el.style.display = 'block';
        showToast('✅ Arquivo enviado!', 'success');
    }, 600);
}

// Salva configurações (feedback visual)
function salvarConfiguracoes() {
    showToast('✅ Configurações salvas!', 'success');
}

// ═══ FIM DOS ADICIONADOS DO MONOLÍTICO ═══

console.log('✅ js/core.js carregado');
