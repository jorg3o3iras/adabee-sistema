// ═══════════════════════════════════════════════════════════════
// 🧪 TEST RUNNER — CorrigePro
// Cole este script no Console (F12) e pressione Enter
// ═══════════════════════════════════════════════════════════════

(async function runTests() {
    const results = [];
    const startTime = Date.now();

    function test(nome, ok, detalhe = '') {
        results.push({ nome, ok, detalhe });
        const icone = ok ? '✅' : '❌';
        const cor = ok ? 'color:#10b981;font-weight:bold' : 'color:#ef4444;font-weight:bold';
        console.log(`%c${icone} ${nome}${detalhe ? ' — ' + detalhe : ''}`, cor);
    }

    function checkFn(name, expected = 'function') {
        try {
            const tipo = typeof window[name];
            test(`Função ${name}()`, tipo === expected, `tipo=${tipo}`);
        } catch (e) {
            test(`Função ${name}()`, false, e.message);
        }
    }

    function checkEl(id, deveExistir = true) {
        const el = document.getElementById(id);
        const existe = !!el;
        test(`Elemento #${id}`, existe === deveExistir, existe ? 'existe' : 'NÃO existe');
    }

    async function testRota(nome, url, expectedStatus = 200) {
        try {
            const r = await fetch(url, { method: 'GET' });
            const ok = r.status === expectedStatus;
            test(`Rota ${nome}`, ok, `HTTP ${r.status}`);
        } catch (e) {
            test(`Rota ${nome}`, false, e.message);
        }
    }

    console.log('%c════════════════════════════════════════════', 'color:#3b82f6;font-weight:bold');
    console.log('%c🧪 TEST RUNNER — CorrigePro', 'color:#3b82f6;font-size:16px;font-weight:bold');
    console.log('%c════════════════════════════════════════════', 'color:#3b82f6;font-weight:bold');

    // ═══ BLOCO 1 — Variáveis globais ═══
    console.log('\n%c📦 BLOCO 1 — Variáveis globais', 'color:#8b5cf6;font-weight:bold');
    test('API_URL definida', typeof API_URL === 'string' && API_URL.startsWith('http'), API_URL);
    test('progressManager existe', typeof progressManager !== 'undefined', typeof progressManager);
    test('tableFeedback existe', typeof tableFeedback !== 'undefined', typeof tableFeedback);
    test('paginaAtual definida', typeof paginaAtual === 'string', paginaAtual);

    // ═══ BLOCO 2 — Funções core.js ═══
    console.log('\n%c📦 BLOCO 2 — Funções core.js', 'color:#8b5cf6;font-weight:bold');
    [
        'escapeHtml', 'escapeAttr', 'showToast', 'toast',
        'openM', 'closeM', 'setText', 'setHTML',
        'processarRespostaAPI', 'calcularConceito', 'mapearDisciplina',
        'carregarEscolasComCache', 'carregarTurmasComCache',
        'carregarAlunosComCache', 'carregarProvasComCache', 'limparCache',
        'atualizarDatasImpressao', 'popularSelectQuestoes', 'popularSelectGabTotal',
        'filtrarTabela', 'filtrarSerie', 'filtrarTurmasPorSerie',
        'renumerarTabela', 'excluir', 'cancelarDel', 'confirmarDel',
        'switchTab', 'simUpload', 'salvarConfiguracoes'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 3 — Funções auth-nav.js ═══
    console.log('\n%c📦 BLOCO 3 — Funções auth-nav.js', 'color:#8b5cf6;font-weight:bold');
    ['toggleMenu', 'setLTab', 'doLogin', 'shakeCard', 'startApp', 'doLogout', 'go'].forEach(fn => checkFn(fn));

    // ═══ BLOCO 4 — Funções cadastros.js ═══
    console.log('\n%c📦 BLOCO 4 — Funções cadastros.js', 'color:#8b5cf6;font-weight:bold');
    [
        'carregarEscolas', 'salvarEscola', 'editarEscola', 'salvarEdicaoEscola', 'excluirEscola',
        'carregarTurmas', 'salvarTurma', 'editarTurma', 'salvarEdicaoTurma', 'excluirTurma',
        'carregarAlunos', 'salvarAluno', 'editarAluno', 'salvarEdicaoAluno', 'excluirAluno',
        'carregarEscolasFiltroAlunos', 'carregarFiltroEscolaTurmas',
        'carregarTurmasPorEscolaParaAluno', 'carregarTurmasFiltroAlunos',
        'filtrarAlunosPorEscola', 'filtrarAlunosPorSerie',
        'aplicarFiltrosTurmas', 'limparFiltrosTurmas',
        'carregarTurmasLista', 'carregarEscolasTexto',
        'carregarCombos', 'carregarEscolasParaAluno', 'carregarEscolasParaCorrecaoManual',
        'processarListaAlunos', 'fecharAbaMulti', 'verAlunosDaTurma'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 5 — Funções provas.js ═══
    console.log('\n%c📦 BLOCO 5 — Funções provas.js', 'color:#8b5cf6;font-weight:bold');
    [
        'carregarProvas', 'salvarProva', 'editarProva', 'excluirProva', 'salvarProvaModal',
        'visualizarProva', 'editarProvaDireto', 'carregarGabaritos',
        'buildGabGrid', 'fillGabRand', 'clearGab', 'saveGab',
        'editarGabarito', 'excluirGabarito',
        'renderizarAlternativasProducao', 'atualizarTituloProducao',
        'atualizarCabecalhoProducao', 'atualizarAlternativaProducao',
        'adicionarAlternativaProducao', 'removerAlternativaProducao',
        'gerarGabaritoModal', 'atualizarInfoAlts', 'carregarTurmasProva',
        'carregarProvasParaGabarito', 'carregarProvasParaTexto',
        'carregarProvasParaFiltro', 'carregarProvasParaDesempenho'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 6 — Funções correcao.js (IA) ═══
    console.log('\n%c📦 BLOCO 6 — Funções correcao.js (IA) — CRÍTICO', 'color:#ef4444;font-weight:bold');
    [
        'carregarEscolasCorrigir',
        'carregarTurmasPorEscolaCorrigir',
        'carregarAlunosPorTurmaCorrigir',
        'carregarProvasPorTurmaCorrigir',
        'carregarAlunosPorProvaFiltrados',
        'abrirCamera', 'trocarCamera', 'fecharCamera', 'capturarFoto',
        'abrirArquivo', 'processarArq',
        'processarComIA', 'buscarProva', 'buscarAluno',
        'enviarParaCorrecao', 'normalizarRespostas',
        'salvarDadosCorrecaoManual', 'atualizarInterfaceCorrecao',
        'salvarCorrecao',
        'abrirCorrecaoManual', 'destacarQuestoesDuvidosas', 'revisarApenasDuvidosas',
        'gerarGridCorrecaoManual', 'atualizarRespostaManual',
        'atualizarResumoCorrecaoManual', 'preencherGabaritoCM', 'limparRespostasCM',
        'salvarCorrecaoManual', 'ajustarUIporDisciplina',
        'abrirCorrecaoManualStandalone', 'carregarTurmasParaCorrecaoManual',
        'carregarAlunosParaCorrecaoManual', 'carregarProvasParaCorrecaoManualPorTurma',
        'carregarGabaritoParaCorrecaoManual', 'iniciarCorrecaoManualStandalone',
        'gerarGridCorrecaoManualSA', 'atualizarSituacaoCM', 'atualizarRespostaManualSA',
        'atualizarResumoCorrecaoManualSA', 'preencherGabaritoManualSA',
        'limparRespostasManualSA', 'revisarApenasDuvidosasSA',
        'salvarCorrecaoManualStandalone', 'salvarNotaProducaoCM',
        'abrirCorrecaoManualDireta', 'editarGabaritoDesempenho',
        'abrirCameraAutomatico', 'processarArqAutomatico',
        'corrigirAutomatico', 'mostrarErroAutomatico', 'mostrarResultadoAutomatico',
        'limparResultadoAutomatico', 'abrirCorrecaoManualAuto', 'salvarCorrecaoAuto'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 7 — Funções resultados.js ═══
    console.log('\n%c📦 BLOCO 7 — Funções resultados.js', 'color:#8b5cf6;font-weight:bold');
    [
        'carregarDashboard', 'carregarResultadosComFiltros', 'atualizarGraficosConceitos',
        'carregarFiltrosResultados', 'carregarTurmasPorEscola', 'limparFiltrosResultados',
        'carregarConceitoReal', 'carregarUltimasCorrecoes',
        'carregarRelatorios', 'carregarRelatorioEscola',
        'carregarFiltrosRelTurma', 'carregarTurmasRelTurma', 'imprimirRelatorioTurma',
        'carregarRelatorioTurmaFiltrado', 'limparFiltrosRelTurma',
        'atualizarGraficoAcertosPorQuestao',
        'carregarEscolasDesempenho', 'carregarTurmasDesempenho', 'carregarAlunosDesempenho',
        'gerarDesempenho', 'limparFiltrosDesempenho',
        'carregarDados', 'carregarDadosSecundarios',
        'exportarResultadosFiltrados', 'carregarUsuarios', 'carregarUserData'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 8 — Funções impressao.js ═══
    console.log('\n%c📦 BLOCO 8 — Funções impressao.js', 'color:#8b5cf6;font-weight:bold');
    [
        'buildCabecalhoInstitucional', 'buildCSSBase', 'buildFooterPadrao',
        'buildDocumentoHTML', 'abrirEImprimir',
        'imprimirAlunos', 'exportarRelatorioPDF', 'imprimirResultadosMelhorados',
        'gerarCartaoResposta', 'gerarCartoesTodosAlunos',
        'gerarDocumentoDesempenho', 'gerarDocumentoNormal', 'gerarDocumentoProducao',
        'imprimirMatrizVisualizada'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 9 — Funções transferencia.js ═══
    console.log('\n%c📦 BLOCO 9 — Funções transferencia.js', 'color:#8b5cf6;font-weight:bold');
    [
        'carregarEscolasTransferencia', 'carregarTurmasTransfOrigem', 'carregarAlunosTransf',
        'renderizarListaAlunosTransf', 'toggleAlunoTransf', 'selecionarTodosTransf',
        'atualizarBotaoTransf', 'carregarTurmasTransfDestino', 'confirmarTransferencia'
    ].forEach(fn => checkFn(fn));

    // ═══ BLOCO 10 — Elementos HTML ═══
    console.log('\n%c📦 BLOCO 10 — Elementos HTML', 'color:#8b5cf6;font-weight:bold');
    [
        'login-screen', 'app', 'lu', 'lp', 'sb-uname',
        'tb-escola', 'tb-turmas', 'tb-alunos', 'tb-provas', 'tb-gabaritos',
        'tb-matrizes', 'tb-resultados-filtrado', 'tb-rel-alunos', 'tb-usuarios',
        'corrigir-escola', 'corrigir-turma', 'corrigir-prova', 'corrigir-aluno',
        'cm-escola-select', 'cm-turma-select', 'cm-prova-select', 'cm-aluno-select',
        'transf-escola-origem', 'transf-turma-origem', 'transf-escola-destino', 'transf-turma-destino',
        'lista-escola', 'lista-turma', 'gab-prova', 'prova-serie',
        'cam-modal', 'cam-video', 'cam-canvas',
        'progress-modal', 'progress-barra', 'toast-c'
    ].forEach(id => checkEl(id));

    // ═══ BLOCO 11 — Rotas de API ═══
    console.log('\n%c📦 BLOCO 11 — Rotas de API', 'color:#f59e0b;font-weight:bold');
    await testRota('/api/escolas', API_URL + '/api/escolas');
    await testRota('/api/turmas', API_URL + '/api/turmas');
    await testRota('/api/alunos', API_URL + '/api/alunos');
    await testRota('/api/provas', API_URL + '/api/provas');
    await testRota('/api/dashboard', API_URL + '/api/dashboard');
    await testRota('/api/usuarios', API_URL + '/api/usuarios');
    await testRota('/api/historico?limit=1', API_URL + '/api/historico?limit=1');
    await testRota('/api/matrizes', API_URL + '/api/matrizes');
    await testRota('/api/dashboard/Conceito', API_URL + '/api/dashboard/Conceito');

    // ═══ BLOCO 12 — Dados reais ═══
    console.log('\n%c📦 BLOCO 12 — Dados reais', 'color:#10b981;font-weight:bold');
    try {
        const escolas = await carregarEscolasComCache();
        test('Escolas carregadas', Array.isArray(escolas) && escolas.length > 0, `${escolas.length} escolas`);
        const turmas = await carregarTurmasComCache();
        test('Turmas carregadas', Array.isArray(turmas) && turmas.length > 0, `${turmas.length} turmas`);
        const alunos = await carregarAlunosComCache();
        test('Alunos carregados', Array.isArray(alunos) && alunos.length > 0, `${alunos.length} alunos`);
        const provas = await carregarProvasComCache();
        test('Provas carregadas', Array.isArray(provas) && provas.length > 0, `${provas.length} provas`);
    } catch (e) {
        test('Dados reais', false, e.message);
    }

    // ═══ BLOCO 13 — Estado do login ═══
    console.log('\n%c📦 BLOCO 13 — Estado do login', 'color:#10b981;font-weight:bold');
    const loginScreen = document.getElementById('login-screen');
    const appEl = document.getElementById('app');
    test('App visível (logado)', appEl && appEl.style.display === 'flex');
    test('Login escondido', loginScreen && loginScreen.style.display === 'none');

    // ═══ RELATÓRIO FINAL ═══
    const total = results.length;
    const passed = results.filter(r => r.ok).length;
    const failed = results.filter(r => !r.ok).length;
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    const porcentagem = Math.round((passed / total) * 100);

    console.log('\n%c════════════════════════════════════════════', 'color:#3b82f6;font-weight:bold');
    console.log('%c📊 RELATÓRIO FINAL', 'color:#3b82f6;font-size:18px;font-weight:bold');
    console.log('%c════════════════════════════════════════════', 'color:#3b82f6;font-weight:bold');
    console.log(`%c✅ PASSOU: ${passed}`, 'color:#10b981;font-weight:bold;font-size:14px');
    console.log(`%c❌ FALHOU: ${failed}`, failed > 0 ? 'color:#ef4444;font-weight:bold;font-size:14px' : 'color:#64748b;font-size:14px');
    console.log(`%c📈 TOTAL:  ${total}`, 'color:#3b82f6;font-weight:bold;font-size:14px');
    console.log(`%c⏱️  Tempo:  ${duration}s`, 'color:#64748b;font-size:12px');
    console.log(`%c🎯 ${porcentagem}% dos testes passaram`, porcentagem === 100 ? 'color:#10b981;font-weight:bold;font-size:16px' : 'color:#f59e0b;font-weight:bold;font-size:16px');

    if (failed > 0) {
        console.log('\n%c❌ TESTES QUE FALHARAM:', 'color:#ef4444;font-weight:bold;font-size:14px');
        results.filter(r => !r.ok).forEach(r => {
            console.log(`%c  ❌ ${r.nome} — ${r.detalhe}`, 'color:#ef4444');
        });

        const relatorio = results.map(r => `${r.ok ? '✅' : '❌'} ${r.nome}${r.detalhe ? ' — ' + r.detalhe : ''}`).join('\n');
        console.log('\n%c📋 COPIE O RELATÓRIO ABAIXO E ME ENVIE:', 'color:#8b5cf6;font-weight:bold;font-size:14px');
        console.log('%c' + relatorio, 'color:#64748b;font-size:11px;font-family:monospace');

        window._testReport = relatorio;
        console.log('\n💡 Dica: execute `copy(_testReport)` no console para copiar o relatório automaticamente.');
    } else {
        console.log('\n%c🎉 TODOS OS TESTES PASSARAM! SISTEMA 100% OPERACIONAL! 🎉', 'color:#10b981;font-weight:bold;font-size:18px');
    }

    console.log('%c════════════════════════════════════════════\n', 'color:#3b82f6;font-weight:bold');
})();