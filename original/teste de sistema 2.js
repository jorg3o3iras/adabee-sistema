(async () => {
    // ═══════════════════════════════════════════════════════════
    // DIAGNÓSTICO AVANÇADO — CorrigePro (v2)
    // Testa selects, fetch, IDs, tempos e estados de todas as telas
    // ═══════════════════════════════════════════════════════════

    const esperar = (ms) => new Promise(r => setTimeout(r, ms));
    const t0 = performance.now();

    // Intercepta fetch para contar chamadas e status
    const fetchLog = [];
    const fetchOriginal = window.fetch;
    window.fetch = function (...args) {
        const url = typeof args[0] === 'string' ? args[0] : args[0].url;
        const inicio = performance.now();
        const p = fetchOriginal.apply(this, args);
        p.then(res => {
            fetchLog.push({
                url: url.replace(location.origin, ''),
                status: res.status,
                ok: res.ok,
                ms: Math.round(performance.now() - inicio)
            });
        }).catch(err => {
            fetchLog.push({ url, status: 'ERRO', ok: false, ms: Math.round(performance.now() - inicio), erro: err.message });
        });
        return p;
    };

    // ═══════════════════════════════════════════════════════════
    // Configuração dos testes
    // precisa: true  → select DEVE estar populado ao entrar na tela
    // precisa: false → select é opcional ou depende de interação (turma, etc.)
    // ═══════════════════════════════════════════════════════════
    const testes = [
        // ── Selects de PROVA (auto-init ao entrar) ──
        { tela: 'gabarito',       select: '#gab-prova',                 precisa: true,  nome: '✅ Gabarito (editor)' },
        { tela: 'correcao-texto', select: '#txt-prova',                 precisa: true,  nome: '📝 Texto com IA' },
        { tela: 'resultados',     select: '#filtro-prova',              precisa: true,  nome: '🏆 Resultados' },
        { tela: 'rel-turma',      select: '#rel-turma-prova',           precisa: true,  nome: '📊 Rel. por Turma' },
        { tela: 'desempenho',     select: '#filtro-prova-desempenho',   precisa: true,  nome: '📊 Desempenho do Aluno' },

        // ── Selects de ESCOLA (auto-init ao entrar) ──
        { tela: 'corrigir-ia',    select: '#corrigir-escola',           precisa: true,  nome: '🤖 Corrigir — Escola' },
        { tela: 'desempenho',     select: '#filtro-escola-desempenho',  precisa: true,  nome: '📊 Desempenho — Escola' },
        { tela: 'turmas',         select: '#filtro-escola-turmas',      precisa: true,  nome: '👥 Turmas — Escola' },
        { tela: 'alunos',         select: '#filtro-escola-alunos',      precisa: true,  nome: '🎒 Alunos — Escola' },

        // ── Selects OPCIONAIS ou dependentes de interação ──
        { tela: 'resultados',     select: '#filtro-escola',             precisa: false, nome: '🏆 Resultados — Escola (opcional)' },
        { tela: 'rel-turma',      select: '#rel-turma-escola',          precisa: false, nome: '📊 Rel. Turma — Escola (opcional)' },
        // ⚠️ #corrigir-prova só é populado APÓS selecionar uma turma
        // (onchange do #corrigir-turma chama carregarProvasPorTurmaCorrigir).
        // Não é auto-init → precisa: false (evita falso positivo).
        { tela: 'corrigir-ia',    select: '#corrigir-prova',            precisa: false, nome: '🤖 Corrigir — Prova (depende de turma)' },
    ];

    // IDs que DEVEM existir no DOM (páginas principais)
    const idsObrigatorios = [
        'page-dashboard', 'page-escola', 'page-turmas', 'page-alunos',
        'page-provas', 'page-prova-upload', 'page-gabarito', 'page-gabaritos',
        'page-correcao-texto', 'page-corrigir-ia', 'page-resultados',
        'page-rel-turma', 'page-desempenho', 'page-matriz', 'page-config',
        'page-transferir-alunos', 'page-lista-turma',
    ];

    // Funções globais que DEVEM existir
    const funcoesObrigatorias = [
        'go', 'startApp', 'doLogin', 'doLogout',
        'carregarProvasParaGabarito', 'carregarProvasParaTexto',
        'carregarProvasParaFiltro', 'carregarProvasParaDesempenho',
        'buildGabGrid', 'saveGab', 'editarGabarito',
        'showToast', 'escapeHtml', 'escapeAttr',
    ];

    console.log('%c╔═══════════════════════════════════════════════════╗', 'color:#3b82f6;font-weight:bold');
    console.log('%c║   🔬 DIAGNÓSTICO AVANÇADO — CorrigePro (v2)      ║', 'color:#3b82f6;font-weight:bold');
    console.log('%c╚═══════════════════════════════════════════════════╝', 'color:#3b82f6;font-weight:bold');

    // ═══════════════════════════════════════════════════════════
    // BLOCO 1 — IDs obrigatórios no DOM
    // ═══════════════════════════════════════════════════════════
    console.log('\n%c📋 BLOCO 1 — IDs de páginas no DOM', 'font-weight:bold;color:#8b5cf6');
    const idsFaltando = idsObrigatorios.filter(id => !document.getElementById(id));
    if (idsFaltando.length === 0) {
        console.log(`%c✅ Todos os ${idsObrigatorios.length} IDs de página existem`, 'color:#10b981');
    } else {
        console.log(`%c❌ IDs faltando (${idsFaltando.length}):`, 'color:#ef4444;font-weight:bold', idsFaltando);
    }

    // ═══════════════════════════════════════════════════════════
    // BLOCO 2 — Funções globais
    // ═══════════════════════════════════════════════════════════
    console.log('\n%c🔧 BLOCO 2 — Funções globais', 'font-weight:bold;color:#8b5cf6');
    const funcoesFaltando = funcoesObrigatorias.filter(f => typeof window[f] !== 'function');
    if (funcoesFaltando.length === 0) {
        console.log(`%c✅ Todas as ${funcoesObrigatorias.length} funções globais existem`, 'color:#10b981');
    } else {
        console.log(`%c❌ Funções faltando (${funcoesFaltando.length}):`, 'color:#ef4444;font-weight:bold', funcoesFaltando);
    }

    // ═══════════════════════════════════════════════════════════
    // BLOCO 3 — Selects por tela (com fetch e tempo)
    // ═══════════════════════════════════════════════════════════
    console.log('\n%c🔍 BLOCO 3 — Selects por tela (fetch + tempo)', 'font-weight:bold;color:#8b5cf6');

    const resultados = [];
    for (const t of testes) {
        const inicioTela = performance.now();
        try {
            go(t.tela);
            await esperar(1300);
            const sel = document.querySelector(t.select);
            const ms = Math.round(performance.now() - inicioTela);

            if (!sel) {
                resultados.push({
                    Tela: t.nome, Select: t.select, Status: '❌ SELECT NÃO EXISTE',
                    Opções: 0, 'Ms': ms
                });
                continue;
            }

            const total = sel.options.length;
            const provas = total - 1;
            const status = t.precisa
                ? (provas > 0 ? '✅ OK' : '❌ VAZIO')
                : (provas > 0 ? '✅ OK' : '⚠️ vazio (opcional)');

            resultados.push({
                Tela: t.nome, Select: t.select, Status: status,
                Opções: provas, 'Ms': ms
            });
        } catch (e) {
            resultados.push({
                Tela: t.nome, Select: t.select, Status: '💥 ERRO: ' + e.message,
                Opções: 0, 'Ms': 0
            });
        }
    }
    console.table(resultados);

    // ═══════════════════════════════════════════════════════════
    // BLOCO 4 — Chamadas de fetch disparadas
    // ═══════════════════════════════════════════════════════════
    console.log('\n%c🌐 BLOCO 4 — Chamadas de rede disparadas', 'font-weight:bold;color:#8b5cf6');
    if (fetchLog.length === 0) {
        console.log('%c⚠️ Nenhum fetch detectado!', 'color:#f59e0b;font-weight:bold');
    } else {
        console.table(fetchLog.map(f => ({
            URL: f.url, Status: f.status, OK: f.ok, 'Ms': f.ms
        })));
        const erros = fetchLog.filter(f => !f.ok);
        if (erros.length > 0) {
            console.log(`%c❌ ${erros.length} fetch(es) com erro:`, 'color:#ef4444;font-weight:bold', erros);
        } else {
            console.log(`%c✅ Todos os ${fetchLog.length} fetches retornaram OK`, 'color:#10b981');
        }
    }

    // ═══════════════════════════════════════════════════════════
    // BLOCO 5 — Estado de elementos críticos
    // ═══════════════════════════════════════════════════════════
    console.log('\n%c🧩 BLOCO 5 — Estado dos elementos críticos', 'font-weight:bold;color:#8b5cf6');
    const criticos = {
        '#tb-escola':            'tbody de escolas',
        '#tb-turmas':            'tbody de turmas',
        '#tb-alunos':            'tbody de alunos',
        '#tb-provas':            'tbody de provas',
        '#tb-gabaritos':         'tbody de gabaritos',
        '#tb-matrizes':          'tbody de matrizes',
        '#tb-usuarios':          'tbody de usuários',
        '#ultimas-correcoes':    'tbody de últimas correções',
        '#gab-grid':             'grid do gabarito',
        '#gab-serie':            'select de série do gabarito',
        '#gab-total':            'select de nº de questões do gabarito',
    };
    const resumoCriticos = [];
    for (const [sel, desc] of Object.entries(criticos)) {
        const el = document.querySelector(sel);
        resumoCriticos.push({
            Seletor: sel, Descrição: desc,
            Existe: el ? '✅' : '❌',
            Filhos: el ? el.children.length : 0
        });
    }
    console.table(resumoCriticos);

    // ═══════════════════════════════════════════════════════════
    // BLOCO 6 — Tamanho do cache de provas
    // ═══════════════════════════════════════════════════════════
    console.log('\n%c💾 BLOCO 6 — Cache e ambiente', 'font-weight:bold;color:#8b5cf6');
    console.log('Provas em cache (_provasCache):', window._provasCache?.length ?? '(não definido)');
    console.log('API_URL:', typeof API_URL !== 'undefined' ? API_URL : '(não definido)');
    console.log('paginaAtual:', typeof paginaAtual !== 'undefined' ? paginaAtual : '(não definido)');
    console.log('loginType:', typeof loginType !== 'undefined' ? loginType : '(não definido)');
    console.log('Usuário:', document.getElementById('sb-uname')?.textContent);
    console.log('Perfil:', document.getElementById('sb-urole')?.textContent);

    // ═══════════════════════════════════════════════════════════
    // RESUMO FINAL
    // ═══════════════════════════════════════════════════════════
    const totalMs = Math.round(performance.now() - t0);
    const falhas = resultados.filter(r => r.Status.includes('❌') || r.Status.includes('💥'));
    const avisos = resultados.filter(r => r.Status.includes('⚠️'));

    console.log('\n%c╔═══════════════════════════════════════════════════╗', 'color:#3b82f6;font-weight:bold');
    console.log('%c║   📊 RESUMO FINAL                                 ║', 'color:#3b82f6;font-weight:bold');
    console.log('%c╚═══════════════════════════════════════════════════╝', 'color:#3b82f6;font-weight:bold');
    console.log(`⏱️  Tempo total: ${totalMs} ms`);
    console.log(`✅ OK: ${resultados.length - falhas.length - avisos.length} | ⚠️  Avisos: ${avisos.length} | ❌ Falhas: ${falhas.length}`);
    console.log(`🌐 Fetches: ${fetchLog.length} | ❌ Com erro: ${fetchLog.filter(f => !f.ok).length}`);

    if (falhas.length === 0) {
        console.log('%c🎉 SISTEMA OK — nenhum problema crítico detectado', 'font-size:14px;font-weight:bold;color:#10b981');
    } else {
        console.log('%c⚠️ PROBLEMAS ENCONTRADOS:', 'font-size:13px;font-weight:bold;color:#ef4444');
        falhas.forEach(f => console.log(`   • ${f.Tela} → ${f.Select} → ${f.Status}`));
        console.log('%cPara corrigir, verifique o case correspondente no go() do auth-nav.js', 'color:#f59e0b');
    }

    // Restaura fetch original e volta ao dashboard
    window.fetch = fetchOriginal;
    go('dashboard');
    console.log('\n✅ Diagnóstico concluído. fetch original restaurado.');
})();