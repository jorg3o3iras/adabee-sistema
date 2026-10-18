// ============================================================
// RESULTADOS.JS — Dashboard, Resultados, Relatórios, Desempenho
// Extraído de script.js — Corte 6
// Inclui complemento: resultados-extra.js (datas de impressão)
// ============================================================

// ═══ ATUALIZAR DATAS DE IMPRESSÃO ═══
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

// ═══ ESTADO DE DESEMPENHO ═══
let desempenhoData = {
    alunoSelecionado: null,
    respostas: [],
    gabarito: [],
    questoes: [],
    disciplinas: []
};

// ═══ CARREGAR DASHBOARD ═══
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

// ═══ CARREGAR RESULTADOS COM FILTROS ═══
async function carregarResultadosComFiltros() {
    try {
        const escolaId = document.getElementById('filtro-escola').value;
        const serie = document.getElementById('filtro-serie').value;
        const turmaId = document.getElementById('filtro-turma').value;
        const provaId = document.getElementById('filtro-prova').value;

        console.log('🔍 [Resultados] Filtros aplicados:', {
            escolaId: escolaId || '(vazio)',
            serie: serie || '(vazio)',
            turmaId: turmaId || '(vazio)',
            provaId: provaId || '(vazio)'
        });

        if (!turmaId && !provaId) {
            console.warn('⚠️ [Resultados] SEM filtro de turma nem prova — pode estourar com muitos alunos');
            showToast('⚠️ Selecione TURMA e PROVA para resultados precisos', 'warning');
        }

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

        console.log('📡 [Resultados] URL:', url);

        const response = await fetch(url);

        if (!response.ok) {
            console.error('❌ HTTP', response.status, 'ao buscar /api/historico/agrupado');
            const tbody = document.getElementById('tb-resultados-filtrado');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--red);">' +
                    '❌ Erro do servidor (' + response.status + '). Selecione TURMA e PROVA específicas para reduzir o volume.' +
                    '</td></tr>';
            }
            return;
        }

        const textoResposta = await response.text();

        if (!textoResposta || textoResposta.trim() === '') {
            console.error('❌ Backend retornou resposta VAZIA');
            const tbody = document.getElementById('tb-resultados-filtrado');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--orange);">' +
                    '⚠️ O servidor não retornou dados (resposta vazia). Selecione TURMA e PROVA específicas.' +
                    '</td></tr>';
            }
            return;
        }

        let alunos;
        try {
            alunos = JSON.parse(textoResposta);
        } catch (e) {
            console.error('❌ JSON inválido recebido:', e);
            console.error('📄 Primeiros 500 chars da resposta:', textoResposta.substring(0, 500));
            const tbody = document.getElementById('tb-resultados-filtrado');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--red);">' +
                    '❌ Resposta do servidor corrompida. Selecione TURMA e PROVA específicas.' +
                    '</td></tr>';
            }
            return;
        }

        console.log('✅ [Resultados] Alunos recebidos:', Array.isArray(alunos) ? alunos.length : 'não-array');

        const tbody = document.getElementById('tb-resultados-filtrado');
        if (!tbody) return;

        const totalCorrigidos = (alunos && !alunos.erro && Array.isArray(alunos)) ? alunos.length : 0;
        const diff = Math.max(0, totalAlunosTurma - totalCorrigidos);

        const pctCorrigidos = totalAlunosTurma > 0 ? Math.round((totalCorrigidos / totalAlunosTurma) * 100) : 0;
        const pctSemCorrecao = totalAlunosTurma > 0 ? Math.round((diff / totalAlunosTurma) * 100) : 0;
        const pctFizeram = pctCorrigidos;
        const pctNaoFizeram = pctSemCorrecao;

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

        const contagemConceitos = { inicial: 0, basico: 0, proficiente: 0, avancado: 0 };

        if (disciplinaAlvo) {
            dadosAlunos.forEach(aluno => {
                const discData = aluno[disciplinaAlvo];
                if (discData && typeof discData === 'object') {
                    const acertos = discData.acertos || 0;
                    const totalDisc = discData.total || 0;
                    const nota = discData.nota !== undefined ? Number(discData.nota) : 0;

                    let pct;
                    if (nota > 0 && totalDisc <= 10) {
                        pct = Math.round((nota / 10) * 100);
                    } else {
                        pct = totalDisc > 0 ? Math.round((acertos / totalDisc) * 100) : 0;
                    }

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
                        const nota = discData.nota !== undefined ? Number(discData.nota) : 0;

                        let pct;
                        if (nota > 0 && totalDisc <= 10) {
                            pct = Math.round((nota / 10) * 100);
                        } else {
                            pct = totalDisc > 0 ? Math.round((acertos / totalDisc) * 100) : 0;
                        }

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
                return { acertos: 0, erros: 0, conceito: 'inicial', nota: 0 };
            }
            const acertos = disciplinaData.acertos !== undefined ? disciplinaData.acertos : 0;
            let erros = disciplinaData.erros !== undefined ? disciplinaData.erros : 0;
            const totalDisc = disciplinaData.total || totalQuestoes || 0;
            const nota = disciplinaData.nota !== undefined ? Number(disciplinaData.nota) : 0;

            let porcentagem;
            if (nota > 0 && totalDisc <= 10) {
                porcentagem = Math.round((nota / 10) * 100);
            } else {
                if (erros === 0 && totalDisc > 0 && acertos > 0) erros = totalDisc - acertos;
                porcentagem = totalDisc > 0 ? Math.round((acertos / totalDisc) * 100) : 0;
            }

            const conceito = calcularConceito(porcentagem);
            return { acertos, erros, conceito, nota };
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

            const notaProducaoTexto = (producao && producao.nota !== undefined && producao.nota !== null && Number(producao.nota) > 0)
                ? Number(producao.nota).toFixed(1)
                : '—';

            return '<tr>' +
                '<td>' + medalha + '</td>' +
                '<td>' + (index + 1) + '</td>' +
                '<td style="text-align:left;"><strong>' + escapeHtml(aluno.aluno_nome || 'Aluno') + '</strong></td>' +
                '<td><span class="badge badge-purple">' + escapeHtml(aluno.serie || '—') + '</span></td>' +
                '<td style="text-align:center;background:rgba(59,130,246,0.03);"><span class="badge badge-blue">' + portugues.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(59,130,246,0.03);"><span class="badge badge-red">' + portugues.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(59,130,246,0.03);"><span class="badge ' + badgeConceito(portugues.conceito) + '">' + portugues.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(16,185,129,0.03);"><span class="badge badge-green">' + matematica.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(16,185,129,0.03);"><span class="badge badge-red">' + matematica.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(16,185,129,0.03);"><span class="badge ' + badgeConceito(matematica.conceito) + '">' + matematica.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(139,92,246,0.05);padding:4px;">' +
                    '<div style="font-size:9px;font-weight:700;color:var(--text3);margin-bottom:2px;">NOTA</div>' +
                    '<div style="font-size:16px;font-weight:900;color:var(--purple);">' + notaProducaoTexto + '</div>' +
                '</td>' +
                '<td style="text-align:center;background:rgba(245,158,11,0.03);"><span class="badge badge-orange">' + ch.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(245,158,11,0.03);"><span class="badge badge-red">' + ch.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(245,158,11,0.03);"><span class="badge ' + badgeConceito(ch.conceito) + '">' + ch.conceito + '</span></td>' +
                '<td style="text-align:center;background:rgba(20,184,166,0.03);"><span class="badge badge-teal">' + cn.acertos + '</span></td>' +
                '<td style="text-align:center;background:rgba(20,184,166,0.03);"><span class="badge badge-red">' + cn.erros + '</span></td>' +
                '<td style="text-align:center;background:rgba(20,184,166,0.03);"><span class="badge ' + badgeConceito(cn.conceito) + '">' + cn.conceito + '</span></td>' +
                '<td style="font-size:10px;color:var(--text2);">' + escapeHtml(nomeEscola || '—') + '</td>' +
                '<td style="font-size:10px;color:var(--text2);">' + escapeHtml(nomeTurma || '—') + '</td>' +
                '</tr>';
        }).join('');

    } catch (erro) {
        console.error('❌ Erro ao carregar resultados com filtros:', erro);
        const tbody = document.getElementById('tb-resultados-filtrado');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:30px;color:var(--text3);">Erro ao carregar resultados: ' + escapeHtml(erro.message) + '</td></tr>';
        }
    }
}

// ═══ GRÁFICOS DE CONCEITOS ═══
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

// ═══ FILTROS DE RESULTADOS ═══
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
                opt.textContent = p.titulo + ' - ' + (p.serie || '') + ' - ' + (p.disciplina || '');
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
            if (current) selectProva.value = current;
            console.log('✅ [Filtros Resultados] Provas populadas:', provas.length);
        } else {
            console.warn('⚠️ [Filtros Resultados] Não foi possível popular o select de provas');
        }
    } catch (erro) { console.error('Erro ao carregar filtros:', erro); }
}

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
                opt.textContent = p.titulo + ' - ' + (p.serie || '') + ' - ' + (p.disciplina || '');
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
            carregarResultadosComFiltros();
        }
    }).catch(e => console.error('Erro ao recarregar provas:', e));
}

// ═══ CONCEITO REAL (DASHBOARD) ═══
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
            html += `<div class="chart-bar-item" title="${escapeAttr(nome)} - Média: ${turma.media || 0}">
                <div class="chart-bar-val">${porcentagem}%</div>
                <div class="chart-bar" style="height:${altura}px;background:${cor};"></div>
                <div class="chart-bar-lbl">${escapeHtml(nome)}</div>
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

// ═══ ÚLTIMAS CORREÇÕES ═══
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
                    <td><strong>${escapeHtml(item.aluno_nome || 'Aluno')}</strong></td>
                    <td>${escapeHtml(item.prova_titulo || 'Prova')}</td>
                    <td><strong>${porcentagem}%</strong></td>
                    <td><span class="badge ${badge}">${label}</span></td>
                </tr>`;
            }).join('');
        }
    } catch (erro) {
        console.error('Erro ao carregar últimas correções:', erro);
    }
}

// ═══ RELATÓRIOS ═══
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
                return '<tr><td><strong>' + escapeHtml(e.nome) + '</strong></td><td>' + turmasEscola.length + '</td><td>' + alunosEscola.length + '</td><td><strong style="color:' + (media >= 6 ? 'var(--green)' : 'var(--orange)') + ';">' + media.toFixed(1) + '</strong></td><td>' + perc + '%</td><td><div class="progress" style="width:140px;"><div class="progress-fill ' + (perc >= 70 ? 'pf-green' : 'pf-orange') + '" style="width:' + perc + '%;"></div></div></td></tr>';
            }).join('');
        }
    } catch (erro) { console.error('Erro ao carregar relatório por escola:', erro); }
}

// ═══ FILTROS RELATÓRIO POR TURMA ═══
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

async function imprimirRelatorioTurma() {
    showToast('🖨️ Imprimindo relatório...', 'info');
    window.print();
}

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
            if (pctAcertos >= 80) corBarra = '#10b981';
            else if (pctAcertos >= 60) corBarra = '#f59e0b';
            else if (pctAcertos >= 40) corBarra = '#f59e0b';
            else if (pctAcertos >= 20) corBarra = '#ef4444';

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
                    ${escapeHtml(bnccCode)}
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
            container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--red);">Erro ao carregar dados: ${escapeHtml(erro.message)}</div>`;
        }
    }
}

// ═══ DESEMPENHO DO ALUNO ═══
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
        const textosQuestoes = prova.textos_questoes || [];
        const totalQuestoes = prova.quantidade_questoes || 20;

        let respostasAluno = [];
        let disciplina = prova.disciplina || 'Português';
        let notaRealProducao = 0;

        let questoesStatusHistorico = [];
        if (historico && historico.length > 0 && !historico.erro) {
            const correcao = historico[0];
            respostasAluno = correcao.respostas || [];
            if (correcao.disciplina) disciplina = correcao.disciplina;
            notaRealProducao = parseFloat(correcao.nota) || 0;
            questoesStatusHistorico = correcao.questoes_status || [];
            if (typeof questoesStatusHistorico === 'string') {
                try {
                    questoesStatusHistorico = JSON.parse(questoesStatusHistorico);
                } catch (e) {
                    questoesStatusHistorico = [];
                }
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

        const isProducao = (disciplina === 'Produção de Texto');

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
            totalQuestoes: totalQuestoes,
            notaProducao: notaRealProducao,
            questoesStatusHistorico: questoesStatusHistorico,
            textosQuestoes: textosQuestoes
        };

        document.getElementById('resultado-desempenho').style.display = 'block';

        // ═══════════════════════════════════════════════════════════════
        // ✅ CONTROLE DOS CARDS DO RESUMO
        // Em Produção de Texto:
        //   - Esconde: Porcentagem de Acertos, Acertos, Erros
        //   - MANTÉM: Conceito (ao lado do NOTA)
        //   - Adiciona: NOTA
        // Nas demais provas: mostra todos os cards originais.
        // ═══════════════════════════════════════════════════════════════
        const resumoContainer = document.querySelector('.desempenho-resumo');
        if (resumoContainer) {
            const cardsResumo = resumoContainer.querySelectorAll('.item');
            if (isProducao) {
                // ✅ Esconde apenas os 3 primeiros cards (Porcentagem, Acertos, Erros)
                //    Mantém o 4º (Conceito) visível
                cardsResumo.forEach((card, idx) => {
                    card.style.display = (idx <= 2) ? 'none' : '';
                });

                // Remove qualquer card "NOTA" antigo e recria limpo
                let notaResumoCard = document.getElementById('resumo-nota-card');
                if (notaResumoCard) notaResumoCard.remove();

                notaResumoCard = document.createElement('div');
                notaResumoCard.id = 'resumo-nota-card';
                notaResumoCard.className = 'item';
                notaResumoCard.innerHTML = `
                    <div class="valor" id="resumo-nota-producao" style="color:#8b5cf6;">0.0</div>
                    <div class="label">NOTA</div>
                `;
                resumoContainer.appendChild(notaResumoCard);

                const notaResumoEl = document.getElementById('resumo-nota-producao');
                if (notaResumoEl) notaResumoEl.textContent = notaRealProducao.toFixed(1);

                resumoContainer.classList.add('duplo');

                // ✅ Esconde a barra de stats internos (Acertos/Erros/Aproveitamento/Conceito)
                const statsInternos = document.getElementById('disciplina-unica-stats');
                if (statsInternos) statsInternos.style.display = 'none';

                // ✅ Esconde SOMENTE a legenda de acertos (✅ Acertou / ❌ Errou / — Não respondeu)
                const legendaAcertos = document.getElementById('legenda-desempenho');
                if (legendaAcertos) legendaAcertos.style.display = 'none';

                // ✅ Garante que as badges de conceito continuam visíveis
                const legendaConceitos = document.getElementById('legenda-conceitos');
                if (legendaConceitos) legendaConceitos.style.display = 'flex';

            } else {
                // ✅ Provas normais: mostra tudo
                cardsResumo.forEach(card => { card.style.display = ''; });

                const notaResumoCard = document.getElementById('resumo-nota-card');
                if (notaResumoCard) notaResumoCard.remove();

                resumoContainer.classList.remove('duplo');

                const statsInternos = document.getElementById('disciplina-unica-stats');
                if (statsInternos) statsInternos.style.display = 'flex';

                const legendaAcertos = document.getElementById('legenda-desempenho');
                if (legendaAcertos) legendaAcertos.style.display = 'flex';

                const legendaConceitos = document.getElementById('legenda-conceitos');
                if (legendaConceitos) legendaConceitos.style.display = 'flex';
            }
        }

        // ✅ Sempre preenche o Conceito; só Porcentagem/Acertos/Erros ficam ocultos em Produção
        setText('resumo-conceito', conceito);

        if (!isProducao) {
            setText('resumo-nota', pct + '%');
            setText('resumo-acertos', acertos);
            setText('resumo-erros', erros);
        }

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

        if (isProducao) {
            grid.style.display = 'flex';
            grid.style.flexDirection = 'column';
            grid.style.gap = '14px';
            grid.style.padding = '8px 0';

            resultadoQuestoes.forEach((q, i) => {
                const statusSalvo = questoesStatusHistorico[i] || {};
                const situacao = statusSalvo.situacao || '';
                const observacaoProfessor = statusSalvo.resposta || statusSalvo.observacao || '';
                const div = document.createElement('div');
                div.style.background = 'var(--bg2)';
                div.style.border = '1px solid var(--border)';
                div.style.borderRadius = '8px';
                div.style.padding = '12px 14px';
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                div.style.gap = '8px';

                const tq = textosQuestoes[i] || {};
                const cabecalho = (tq && tq.cabecalho) ? tq.cabecalho : '';
                const tituloQ = (tq && tq.titulo) ? tq.titulo : `Q${q.numero}`;
                const headerTexto = cabecalho ? `${tituloQ} - ${cabecalho}` : tituloQ;

                let gabFormatadoHTML = '';
                const gab = q.gabarito || '';
                if (gab && gab.trim() !== '' && gab !== '—') {
                    const blocos = gab.split(/\n(?=[A-Z]\))/);
                    blocos.forEach(bloco => {
                        const match = bloco.match(/^([A-Z])\)\s*([\s\S]*)$/);
                        if (match) {
                            const letra = match[1];
                            const texto = match[2].trim();
                            gabFormatadoHTML += `<div style="display:flex; gap:6px; align-items:flex-start; margin-bottom:4px;">
                                <span style="font-weight:800; color:#8b5cf6; min-width:14px;">${escapeHtml(letra)}</span>
                                <span style="font-size:12px; color:var(--text2);">${escapeHtml(texto)}</span>
                            </div>`;
                        } else if (bloco.trim()) {
                            gabFormatadoHTML += `<div style="font-size:12px; color:var(--text2);">${escapeHtml(bloco.trim())}</div>`;
                        }
                    });
                } else {
                    gabFormatadoHTML = '<div style="font-size:12px; color:var(--text3); font-style:italic;">Sem gabarito</div>';
                }

                const observacao = observacaoProfessor;

                div.innerHTML = `
                    <div style="font-size:13px; font-weight:800; color:#a78bfa;">${escapeHtml(headerTexto)}</div>
                    <div>
                        <div style="font-size:11px; font-weight:700; color:var(--text3); margin-bottom:4px;">📋 Situação de Correção:</div>
                        <div>${gabFormatadoHTML}</div>
                    </div>
                    <div>
                        <div style="font-size:11px; font-weight:700; color:var(--text3); margin-bottom:4px;">✍️ Observação do Professor:</div>
                        <textarea readonly style="width:100%; min-height:40px; background:var(--surface2); border:1px solid var(--border); border-radius:6px; padding:6px; font-size:11px; color:var(--text2); resize:none;" placeholder="Escreva sua avaliação/observação sobre a resposta do aluno...">${escapeHtml(observacao)}</textarea>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:11px; font-weight:700; color:var(--text3);">📊 Situação de Correção Alternativa:</span>
                        <span style="font-size:13px; font-weight:800; color:${situacao ? '#8b5cf6' : 'var(--text3)'}; background:${situacao ? 'rgba(139,92,246,0.12)' : 'var(--surface2)'}; padding:2px 12px; border-radius:8px; border:1px solid ${situacao ? 'rgba(139,92,246,0.3)' : 'var(--border)'};">${escapeHtml(situacao || '—')}</span>
                    </div>
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
                    bnccHtml = `<div style="font-size:6px; color:#a78bfa; background:rgba(139,92,246,0.1); padding:0 4px; border-radius:4px; margin-top:2px;">BNCC: ${escapeHtml(q.bncc)}</div>`;
                }
                div.innerHTML = `
                    <div class="q-num">Q${q.numero}</div>
                    <div class="q-resp">${escapeHtml(q.resposta)}</div>
                    <div class="q-gab">${escapeHtml(q.gabarito)}</div>
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
        const gabCardTitle = document.querySelector('#gabarito-oficial-card .card-title');
        const gabGrid = document.getElementById('gabarito-oficial-grid');

        if (isProducao) {
            gabCard.style.display = 'none';
            gabGrid.innerHTML = '';
        } else {
            gabCard.style.display = 'block';

            if (gabCardTitle) {
                gabCardTitle.textContent = '📋 Gabarito Oficial da Prova';
            }

            gabGrid.innerHTML = '';
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
                    <div class="q-resp" style="color: var(--green);">${escapeHtml(gab || '—')}</div>
                    <div class="q-gab">Oficial</div>
                    ${codigoBncc ? `<div style="font-size:6px; color: var(--purple); margin-top:2px; background:rgba(139,92,246,0.1); padding:0 4px; border-radius:4px;">BNCC: ${escapeHtml(codigoBncc)}</div>` : ''}
                `;
                gabGrid.appendChild(div);
            });
        }

        const notaCard = document.getElementById('desempenho-nota-producao-card');
        if (notaCard) {
            notaCard.style.display = 'none';
        }

        showToast(`✅ Desempenho gerado para ${aluno.nome} - ${disciplina}: ${acertos}/${totalQuestoes} acertos (${pct}%)`, 'success');

    } catch (erro) {
        console.error('❌ Erro ao gerar desempenho:', erro);
        showToast('❌ Erro ao gerar desempenho: ' + erro.message, 'error');
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

    const resumoContainer = document.querySelector('.desempenho-resumo');
    if (resumoContainer) {
        resumoContainer.classList.remove('duplo');
        resumoContainer.querySelectorAll('.item').forEach(card => {
            card.style.display = '';
        });
        const notaResumoCard = document.getElementById('resumo-nota-card');
        if (notaResumoCard) notaResumoCard.remove();
    }

    // ✅ Restaura visibilidade dos elementos escondidos no modo Produção
    const statsInternosLimpar = document.getElementById('disciplina-unica-stats');
    if (statsInternosLimpar) statsInternosLimpar.style.display = 'flex';

    const legendaAcertosLimpar = document.getElementById('legenda-desempenho');
    if (legendaAcertosLimpar) legendaAcertosLimpar.style.display = 'flex';

    // ✅ NOVO: restaura também as badges de conceito (🔴🟠🔵🟢)
    const legendaConceitosLimpar = document.getElementById('legenda-conceitos');
    if (legendaConceitosLimpar) legendaConceitosLimpar.style.display = 'flex';

    const notaCardLimpar = document.getElementById('desempenho-nota-producao-card');
    if (notaCardLimpar) notaCardLimpar.style.display = 'none';

    desempenhoData.alunoSelecionado = null;
    showToast('✕ Filtros limpos!', 'info');
}

// ═══ CARGA INICIAL ═══
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

// ═══ EXPORTAR RESULTADOS ═══
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
