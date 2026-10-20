// ============================================================
// JS/AUTH-NAV.JS — Login, logout, navegação, menu
// ============================================================

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

function setLTab(t) {
    loginType = t;
    document.querySelectorAll('.login-tab').forEach((el, i) => {
        el.classList.toggle('active', (i === 0 && t === 'admin') || (i === 1 && t === 'user'));
    });
}

// ═══ LOGIN ═══
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
            // ✅ Salva sessão com contexto de escola
            salvarSessao({
                id: data.id,
                username: data.username || data.usuario,
                nome: data.nome,
                perfil: data.perfil,
                escola_id: (data.escola_id != null) ? data.escola_id : null,
                escola_nome: data.escola_nome || null
            });
            startApp(data.perfil, data.nome, data.username || data.usuario, data.escola_nome);
        } else {
            showToast('❌ ' + (data.erro || 'Usuário ou senha incorretos!'), 'error');
            shakeCard();
        }
    } catch (erro) {
        console.warn('Login via API falhou, tentando fallback:', erro);
        // Fallback (dev/teste) — sem escola
        const credenciais = {
            'admin': { senha: 'admin', perfil: 'admin' },
            'usuario': { senha: '123', perfil: 'usuario' },
            'professor1': { senha: '123', perfil: 'usuario' }
        };
        const cred = credenciais[u];
        if (cred && cred.senha === p) {
            salvarSessao({
                id: 0, username: u,
                nome: u.charAt(0).toUpperCase() + u.slice(1),
                perfil: cred.perfil,
                escola_id: null, escola_nome: null
            });
            startApp(cred.perfil, u, u, null);
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

// ═══ START APP ═══
function startApp(role, nome, username, escolaNome) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';

    const inicial = (nome || username || 'U').charAt(0).toUpperCase();
    document.getElementById('sb-avatar').textContent = inicial;
    document.getElementById('sb-uname').textContent = nome || username || '—';

    // Mostra nome da escola ou "Administração"
    const roleText = role === 'admin'
        ? '🛠️ Administrador (todas as escolas)'
        : (escolaNome ? '🏫 ' + escolaNome : '🏫 Sem escola vinculada');
    document.getElementById('sb-urole').textContent = roleText;

    const isAdmin = role === 'admin';

    const admSb = document.getElementById('adm-sb');
    const usrSb = document.getElementById('usr-sb');
    if (admSb) admSb.style.display = 'block';
    if (usrSb) usrSb.style.display = 'none';

    const menuConfig = document.getElementById('menu-config');
    if (menuConfig) menuConfig.style.display = isAdmin ? 'block' : 'none';

    go('dashboard');

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
    // ✅ Limpa sessão
    limparSessao();
    if (typeof limparCache === 'function') limparCache();

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
        case 'gabarito':
            if (typeof carregarProvasParaGabarito === 'function') carregarProvasParaGabarito();
            if (typeof popularSelectGabTotal === 'function') popularSelectGabTotal();
            break;
        case 'gabaritos':
            if (typeof carregarGabaritos === 'function') carregarGabaritos();
            break;
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

document.getElementById('lp')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
});

console.log('✅ js/auth-nav.js carregado');
