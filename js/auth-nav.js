// ============================================================
// AUTH-NAV.JS — Login, logout, navegação, menu
// Extraído de script.js — Corte 2
// ============================================================

// ═══ MENU TOGGLE ═══
function toggleMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('menuOverlay');
    const toggle = document.getElementById('menuToggle');
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

document.getElementById('lp')?.addEventListener('keydown', e => {
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

// ═══ NAVEGAÇÃO ═══
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
        case 'matriz':
            carregarMatrizes();
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