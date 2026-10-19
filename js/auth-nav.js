// ============================================================
// JS/AUTH-NAV.JS — Login, logout, navegação, menu
// Extraído de script.js — Corte 2
// ============================================================

// ═══ MENU TOGGLE ═══
function toggleMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('menuOverlay');
    const toggle = document.getElementById('menuToggle');
    if (!sidebar || !overlay || !toggle) return;
    sidebar.classList.toggle('open');
    overlay.classList.toggle('show');
    toggle.classList.toggle('active');
    toggle.innerHTML = sidebar.classList.contains('open') ? '✕' : '☰';
}

// ═══ LOGIN ═══
function setLTab(t) {
    loginType = t;
    document.querySelectorAll('.login-tab').forEach((el, i) => {
        el.classList.toggle('active', (i === 0 && t === 'admin') || (i === 1 && t === 'user'));
    });
}

async function doLogin() {
    const u = document.getElementById('lu').value.trim();
    const p = document.getElementById('lp').value.trim();

    if (!u || !p) {
        showToast('❌ Preencha usuário e senha!', 'error');
        shakeCard();
        return;
    }

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
        // Fallback: se API cair, aceita usuários fixos
        console.warn('Login via API falhou, tentando fallback:', erro);
        if ((u === 'admin' && p === 'admin') ||
            ((u === 'usuario' || u === 'professor1') && p === '123')) {
            const perfil = u === 'admin' ? 'admin' : 'usuario';
            startApp(perfil, u);
        } else {
            showToast('❌ Usuário ou senha incorretos!', 'error');
            shakeCard();
        }
    }
}

function shakeCard() {
    const c = document.querySelector('.login-card');
    if (!c) return;
    c.style.animation = 'none';
    setTimeout(() => c.style.animation = 'shake .4s ease', 10);
}

// ═══ START APP (após login) ═══
function startApp(role, uname) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    document.getElementById('sb-avatar').textContent = uname[0].toUpperCase();
    document.getElementById('sb-uname').textContent = uname;
    document.getElementById('sb-urole').textContent = role === 'admin' ? 'Administrador do Sistema' : 'Usuário do Sistema';

    const isAdmin = role === 'admin';

    const admSb = document.getElementById('adm-sb');
    const usrSb = document.getElementById('usr-sb');
    if (admSb) admSb.style.display = 'block';
    if (usrSb) usrSb.style.display = 'none';

    const menuConfig = document.getElementById('menu-config');
    if (menuConfig) {
        menuConfig.style.display = isAdmin ? 'block' : 'none';
    }

    go('dashboard');

    // ═══ CHAMADAS PROTEGIDAS POR typeof ═══
    // Isso evita ReferenceError se algum script ainda não carregou.
    if (typeof buildGabGrid === 'function') buildGabGrid();
    if (typeof carregarDados === 'function') carregarDados();
    if (typeof atualizarDatasImpressao === 'function') atualizarDatasImpressao();
    if (typeof carregarEscolasParaCorrecaoManual === 'function') carregarEscolasParaCorrecaoManual();
    if (typeof carregarFiltrosRelTurma === 'function') carregarFiltrosRelTurma();
    if (typeof carregarEscolasDesempenho === 'function') carregarEscolasDesempenho();
    if (typeof popularSelectQuestoes === 'function') popularSelectQuestoes();
    if (typeof popularSelectGabTotal === 'function') popularSelectGabTotal();
    if (typeof carregarEscolasCorrigir === 'function') carregarEscolasCorrigir();
}

function doLogout() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    document.getElementById('lu').value = '';
    document.getElementById('lp').value = '';
    if (typeof fecharCamera === 'function') fecharCamera();
}

// ═══ NAVEGAÇÃO ═══
function go(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const el = document.getElementById('page-' + page);
    if (el) el.classList.add('active');

    document.querySelectorAll('.sb-item').forEach(s => s.classList.toggle('active', s.dataset.p === page));

    switch(page) {
        case 'escola':
            if (typeof carregarEscolas === 'function') carregarEscolas();
            break;
        case 'turmas':
            if (typeof carregarFiltroEscolaTurmas === 'function') carregarFiltroEscolaTurmas();
            if (typeof carregarTurmas === 'function') carregarTurmas();
            break;
        case 'alunos': {
            const escolaId = document.getElementById('filtro-escola-alunos')?.value || '';
            if (typeof carregarAlunos === 'function') carregarAlunos(escolaId);
            break;
        }
        case 'provas':
            if (typeof carregarProvas === 'function') carregarProvas();
            break;
        case 'resultados':
            if (typeof carregarFiltrosResultados === 'function') carregarFiltrosResultados();
            if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
            break;
        // 🔧 FIX: case próprio para o EDITOR de gabarito (tela singular /page-gabarito)
        // Popula o select #gab-prova, que antes nunca era preenchido ao entrar na tela.
        case 'gabarito':
            if (typeof carregarProvasParaGabarito === 'function') carregarProvasParaGabarito();
            if (typeof popularSelectGabTotal === 'function') popularSelectGabTotal();
            break;
        // Lista/tabela de gabaritos (tela plural /page-gabaritos)
        case 'gabaritos':
            if (typeof carregarGabaritos === 'function') carregarGabaritos();
            break;
        // 🔧 FIX: popula #txt-prova ao entrar na tela "Texto com IA"
        // Sem este case, o select de Prova ficava vazio até salvar prova em outra tela.
        case 'correcao-texto':
            if (typeof carregarProvasParaTexto === 'function') carregarProvasParaTexto();
            break;
        case 'rel-turma':
            if (typeof carregarFiltrosRelTurma === 'function') carregarFiltrosRelTurma();
            if (typeof carregarRelatorioTurmaFiltrado === 'function') carregarRelatorioTurmaFiltrado();
            break;
        case 'desempenho':
            if (typeof carregarEscolasDesempenho === 'function') carregarEscolasDesempenho();
            break;
        case 'dashboard':
            if (typeof carregarDashboard === 'function') carregarDashboard();
            if (typeof carregarUltimasCorrecoes === 'function') carregarUltimasCorrecoes();
            break;
        case 'corrigir-ia':
            if (typeof carregarEscolasCorrigir === 'function') carregarEscolasCorrigir();
            break;
        case 'matriz':
            if (typeof carregarMatrizes === 'function') carregarMatrizes();
            break;
    }

    if (typeof atualizarDatasImpressao === 'function') atualizarDatasImpressao();
    paginaAtual = page;

    if (window.innerWidth <= 900) {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('menuOverlay');
        const toggle = document.getElementById('menuToggle');
        if (sidebar && overlay && toggle && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            toggle.classList.remove('active');
            toggle.innerHTML = '☰';
        }
    }
}

// ═══ ENTER NO CAMPO DE SENHA = LOGIN ═══
document.getElementById('lp')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
});

console.log('✅ js/auth-nav.js carregado');
