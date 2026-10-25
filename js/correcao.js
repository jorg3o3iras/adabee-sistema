// ============================================================
// JS/CORRECAO.JS — Câmera, IA, correção manual, correção auto QR
// Com apiFetch (header X-Usuario-Username)
// ⚠️ CORRIGIDO: preserva sentinel 'MULTIPLA' (dupla marcação = errada)
// ✨ NOVO: painel detalhado (#ia-detalhes) + modal "Ver cartão original"
// ============================================================

let correcaoManualData = {
    alunoId: null, alunoNome: '', provaId: null, provaTitulo: '',
    gabarito: [], respostasAluno: [], quantidade: 20,
    alternativas: ['A', 'B', 'C', 'D'], notaMaxima: 10, notaMinima: 5,
    valorPorQuestao: 0.5, serie: '1º Ano', disciplina: '',
    confianca_por_questao: [], questoes_suspeitas: []
};

let cmStandaloneData = {
    escolaId: null, turmaId: null, provaId: null, alunoId: null,
    alunoNome: '', turmaNome: '', serie: '', escolaNome: '',
    gabarito: [], respostas: [], quantidade: 20,
    alternativas: ['A', 'B', 'C', 'D'], notaMaxima: 10, notaMinima: 5,
    valorPorQuestao: 0.5, provaTitulo: '', provaData: '', disciplina: '',
    confianca_por_questao: [], questoes_suspeitas: []
};

let autoModoAtivo = false;

// ═══════════════════════════════════════════════════════════════════
// Combos da tela "Corrigir com IA"
// ═══════════════════════════════════════════════════════════════════
async function carregarEscolasCorrigir() {
    try {
        const escolas = await carregarEscolasComCache();
        const select = document.getElementById('corrigir-escola');
        if (select && escolas && !escolas.erro) {
            const current = select.value;
            select.innerHTML = '<option value="">Selecione a escola...</option>';
            escolas.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id; opt.textContent = e.nome;
                select.appendChild(opt);
            });
            if (current) {
                select.value = current;
                carregarTurmasPorEscolaCorrigir(current);
            }
        }
    } catch (erro) { console.error('Erro ao carregar escolas para correção:', erro); }
}

async function carregarTurmasPorEscolaCorrigir(escolaId) {
    const selectTurma = document.getElementById('corrigir-turma');
    const selectProva = document.getElementById('corrigir-prova');
    const selectAluno = document.getElementById('corrigir-aluno');
    if (!selectTurma) return;
    selectTurma.innerHTML = '<option value="">Selecione a turma...</option>';
    if (selectProva) selectProva.innerHTML = '<option value="">Selecione...</option>';
    if (selectAluno) selectAluno.innerHTML = '<option value="">Selecione...</option>';
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

async function carregarAlunosPorTurmaCorrigir(turmaId) {
    const selectAluno = document.getElementById('corrigir-aluno');
    if (!selectAluno) return;
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

async function carregarProvasPorTurmaCorrigir(turmaId) {
    const selectProva = document.getElementById('corrigir-prova');
    if (!selectProva) return;
    selectProva.innerHTML = '<option value="">Selecione...</option>';
    if (!turmaId) return;
    try {
        const provas = await carregarProvasComCache();
        const turmas = await carregarTurmasComCache();
        const turmaData = turmas.find(t => t.id == turmaId);
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
    } catch (e) { console.error('Erro ao carregar provas:', e); }
}

async function carregarAlunosPorProvaFiltrados(provaId) {
    const selectAluno = document.getElementById('corrigir-aluno');
    if (!selectAluno) return;
    selectAluno.innerHTML = '<option value="">Selecione...</option>';
    if (!provaId) return;
    try {
        const provaResp = await apiFetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) {
            showToast('❌ Erro ao carregar dados da prova', 'error');
            return;
        }
        const turmaId = document.getElementById('corrigir-turma')?.value;
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
    } catch (e) { console.error('Erro ao carregar alunos:', e); }
}

// ═══════════════════════════════════════════════════════════════════
// CÂMERA
// ═══════════════════════════════════════════════════════════════════
async function abrirCamera() {
    document.getElementById('cam-modal').classList.add('show');
    try {
        if (camStream) camStream.getTracks().forEach(t => t.stop());
        camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: camFacing, width: { ideal: 1280 }, height: { ideal: 720 } } });
        document.getElementById('cam-video').srcObject = camStream;
    } catch (e) {
        showToast('❌ Câmera não disponível: ' + e.message, 'error');
        fecharCamera();
    }
}

function trocarCamera() {
    camFacing = camFacing === 'environment' ? 'user' : 'environment';
    abrirCamera();
}

function fecharCamera() {
    const camModal = document.getElementById('cam-modal');
    if (camModal) camModal.classList.remove('show');
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

function abrirArquivo() {
    const inp = document.getElementById('inp-arq');
    if (inp) inp.click();
}

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

// ═══════════════════════════════════════════════════════════════════
// CORREÇÃO COM IA
// ═══════════════════════════════════════════════════════════════════
async function processarComIA(imagemBase64) {
    // ✨ NOVO: guarda a imagem para o botão "Ver cartão original"
    window._ultimaImagemCorrigida = imagemBase64;

    const escolaId = document.getElementById('corrigir-escola')?.value;
    const turmaId = document.getElementById('corrigir-turma')?.value;
    const provaId = document.getElementById('corrigir-prova')?.value;
    const alunoId = document.getElementById('corrigir-aluno')?.value;
    if (!escolaId || !turmaId || !provaId || !alunoId) {
        showToast('❌ Selecione escola, turma, prova e aluno!', 'error'); return;
    }
    if (!imagemBase64) {
        showToast('❌ Nenhuma imagem foi fornecida!', 'error'); return;
    }

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
        progressManager.atualizarEtapa(0); await sleep(500);
        let imagemEnvio = imagemBase64;
        if (imagemBase64.startsWith('data:image')) {
            const partes = imagemBase64.split(',');
            if (partes.length > 1) imagemEnvio = partes[1];
        }
        progressManager.atualizarEtapa(1); await sleep(300);
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
        progressManager.atualizarEtapa(2); await sleep(300);
        const respostaIA = await enviarParaCorrecao(imagemEnvio, provaId, alunoId);
        if (respostaIA.erro) throw new Error(respostaIA.erro);
        progressManager.atualizarEtapa(3); await sleep(200);
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
            let isCorreto = false;
            let statusMsg = 'NÃO RESPONDEU';
            let isMultipla = false;

            if (isProducao) {
                if (resp && gab) {
                    const respLimpa = resp.trim().toLowerCase();
                    const gabLimpo = gab.trim().toLowerCase();
                    isCorreto = respLimpa === gabLimpo || respLimpa.includes(gabLimpo) || gabLimpo.includes(respLimpa);
                    statusMsg = isCorreto ? '✅ ACERTOU' : '❌ ERROU';
                }
            } else if (resp === 'MULTIPLA') {
                // ⚠️ Dupla marcação NUNCA é acerto
                isMultipla = true;
                isCorreto = false;
                statusMsg = '⚠️ MÚLTIPLA MARCAÇÃO';
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
                numero: i + 1, resposta: resp || '—', gabarito: gab || '—',
                acertou: isCorreto, status: statusMsg, confianca: confianca,
                respondida: !!resp, multipla: isMultipla
            });
        }
        const valorPorQuestao = 10 / totalQuestoes;
        const nota = Math.min(acertos * valorPorQuestao, 10);
        const porcentagem = Math.round((acertos / totalQuestoes) * 100);
        const conceito = calcularConceito(porcentagem);
        progressManager.atualizarEtapa(4); await sleep(300);
        salvarDadosCorrecaoManual({
            alunoId: parseInt(alunoId), alunoNome: aluno.nome || 'Aluno',
            provaId: parseInt(provaId), provaTitulo: prova.titulo || 'Prova',
            gabarito: gabarito, respostas: respostasNormalizadas,
            quantidade: totalQuestoes, alternativas: alternativas,
            notaMaxima: 10, notaMinima: 5, valorPorQuestao: valorPorQuestao,
            serie: prova.serie || '1º Ano', disciplina: prova.disciplina || '',
            confianca_por_questao: confiancasNormalizadas,
            questoes_suspeitas: respostaIA.questoes_suspeitas || [],
            questoes_status: resultadoQuestoes
        });
        const metodoUsado = respostaIA.metodo_usado || respostaIA.modo || 'desconhecido';
        atualizarInterfaceCorrecao({
            aluno: aluno, prova: prova, resultadoQuestoes: resultadoQuestoes,
            acertos: acertos, totalQuestoes: totalQuestoes, nota: nota,
            porcentagem: porcentagem, conceito: conceito, confiancas: confiancasNormalizadas,
            metodoUsado: metodoUsado, requerRevisao: respostaIA.requer_revisao_manual || false,
            questoesSuspeitas: respostaIA.questoes_suspeitas || []
        });
        progressManager.atualizarEtapa(5); await sleep(200);
        progressManager.finalizar(`✅ Correção concluída! ${acertos}/${totalQuestoes} acertos — Nota: ${nota.toFixed(1)}`);
        if (typeof carregarDashboard === 'function') carregarDashboard();
        if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
        if (typeof carregarUltimasCorrecoes === 'function') carregarUltimasCorrecoes();
    } catch (erro) {
        console.error('❌ Erro na correção:', erro);
        progressManager.erro(erro.message || 'Erro ao processar correção');
        showToast('❌ Erro ao processar correção: ' + erro.message, 'error');
    }
}

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
        const response = await apiFetch(`${API_URL}/api/corrigir`, {
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
        if (dados.erro) throw new Error(dados.erro);
        if (!dados.respostas_detectadas && !dados.questoes_status) {
            throw new Error('A IA não conseguiu detectar as respostas. Tire uma foto mais nítida com boa iluminação.');
        }
        return dados;
    } catch (e) {
        console.error('❌ Erro na chamada da API:', e);
        throw e;
    }
}

function normalizarRespostas(respostas, confiancas, totalQuestoes, isProducao, tipoQuestoes = 4) {
    let respostasNormalizadas = [];
    let confiancasNormalizadas = [];
    const alternativasValidas = tipoQuestoes == 3 ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
    for (let i = 0; i < totalQuestoes; i++) {
        let resp = (i < respostas.length) ? (respostas[i] || '') : '';
        let conf = (i < confiancas.length) ? (confiancas[i] || 0) : 0;
        if (isProducao) {
            resp = resp.toString().trim();
        } else {
            let s = resp.toString().trim().toUpperCase();

            // ⚠️ Sentinel de dupla marcação: PRESERVAR antes de qualquer strip
            if (s === 'MULTIPLA' || s === 'MÚLTIPLA' || s === 'MULTIPLE' || s === 'MULTI' || s === 'ANULADA') {
                respostasNormalizadas.push('MULTIPLA');
                confiancasNormalizadas.push(Math.min(Math.max(conf, 0), 100));
                continue;
            }

            s = s.replace(/^[\(\[]*/, '').replace(/[\)\]\.\,\;\:\-]*$/, '');
            let encontrou = '';
            if (alternativasValidas.includes(s)) encontrou = s;
            else {
                for (const alt of alternativasValidas) {
                    if (s.includes(alt)) { encontrou = alt; break; }
                }
            }
            resp = encontrou;
        }
        respostasNormalizadas.push(resp);
        confiancasNormalizadas.push(Math.min(Math.max(conf, 0), 100));
    }
    return { respostasNormalizadas, confiancasNormalizadas };
}

function salvarDadosCorrecaoManual(dados) {
    correcaoManualData = {
        alunoId: dados.alunoId, alunoNome: dados.alunoNome,
        provaId: dados.provaId, provaTitulo: dados.provaTitulo,
        gabarito: dados.gabarito, respostasAluno: dados.respostas,
        quantidade: dados.quantidade, alternativas: dados.alternativas,
        notaMaxima: dados.notaMaxima, notaMinima: dados.notaMinima,
        valorPorQuestao: dados.valorPorQuestao, serie: dados.serie,
        disciplina: dados.disciplina,
        confianca_por_questao: dados.confianca_por_questao,
        questoes_suspeitas: dados.questoes_suspeitas || [],
        bncc: dados.bncc || [], questoes_status: dados.questoes_status || []
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

    const metodo = dados.metodoUsado || 'desconhecido';
    const metodoBadge = document.getElementById('ia-metodo');
    if (metodoBadge) {
        const metodoLabels = {
            'template': '🎯 Template', 'template+cv': '🎯 Template+CV',
            'ia': '🤖 IA', 'ia+circulos': '🤖 IA + Círculos',
            'ia_parcial': '🤖 IA (Parcial)', 'circulos': '⭕ Círculos',
            'circulos_parcial': '⭕ Círculos (Parcial)', 'manual': '✏️ Manual',
            'template_evalbee_v4': '🎯 Template v4', 'evalbee_v4': '🎯 EvalBee v4',
            'ia_fallback': '🤖 IA (Fallback)'
        };
        metodoBadge.textContent = metodoLabels[metodo] || `📌 ${metodo}`;
        const classe = metodo === 'template' || metodo === 'template+cv' || metodo.includes('evalbee') ? 'badge-green' :
                       metodo === 'ia' || metodo === 'ia_fallback' ? 'badge-purple' :
                       metodo.includes('circulos') ? 'badge-orange' : 'badge-gray';
        metodoBadge.className = `badge ${classe}`;
    }

    // ⚠️ Confiança média APENAS das questões RESPONDIDAS
    // (em branco é 100% de certeza que está em branco — não distorce a média)
    const paresRespondidos = dados.resultadoQuestoes
        .map((q, i) => ({ q, i }))
        .filter(({ q }) => q.respondida);
    const confiancasRespondidas = paresRespondidos.map(({ i }) => dados.confiancas[i] || 0);
    const confiancaMedia = confiancasRespondidas.length > 0
        ? confiancasRespondidas.reduce((a, b) => a + b, 0) / confiancasRespondidas.length
        : 100;

    const badgeConfianca = document.getElementById('confianca-badge');
    if (badgeConfianca) {
        badgeConfianca.textContent = `${confiancaMedia.toFixed(1)}% conf.`;
        badgeConfianca.className = `badge ${confiancaMedia >= 70 ? 'badge-green' : confiancaMedia >= 50 ? 'badge-orange' : 'badge-red'}`;
    }

    const resumoConfianca = document.getElementById('ia-resumo-confianca');
    if (resumoConfianca) {
        // ⚠️ Só conta como "duvidosa" se for RESPONDIDA, não-múltipla e conf < 70
        const respondidasBaixaConf = dados.resultadoQuestoes.filter((q, i) => {
            return q.respondida && !q.multipla && (dados.confiancas[i] || 0) < 70;
        }).length;

        const totalMultiplas = dados.resultadoQuestoes.filter(q => q.multipla || q.resposta === 'MULTIPLA').length;
        const totalEmBranco = dados.resultadoQuestoes.filter(q => !q.respondida).length;
        const totalRespondidas = dados.totalQuestoes - totalEmBranco;

        resumoConfianca.style.display = 'flex';
        let alertaRevisao = '';
        if (dados.requerRevisao) {
            alertaRevisao = `<span style="color:var(--orange);font-weight:700;">⚠️ REVISÃO MANUAL RECOMENDADA</span>`;
        }
        let alertaMultipla = '';
        if (totalMultiplas > 0) {
            alertaMultipla = `<span style="color:var(--orange);font-weight:700;">⚠️ ${totalMultiplas} MÚLTIPLA MARCAÇÃO</span>`;
        }
        let alertaBranco = '';
        if (totalEmBranco > 0) {
            alertaBranco = `<span style="color:var(--text2);font-weight:700;">— ${totalEmBranco} EM BRANCO (contam como erradas)</span>`;
        }

        // Só exibe "todas alta confiança" se NÃO houver múltiplas nem em branco
        let statusConfianca = '';
        if (respondidasBaixaConf > 0) {
            statusConfianca = `<span>⚠️ ${respondidasBaixaConf} questões com baixa confiança (<70%)</span>`;
        } else if (totalMultiplas === 0 && totalEmBranco === 0) {
            statusConfianca = `<span>✅ Todas as questões têm alta confiança!</span>`;
        } else {
            statusConfianca = `<span>✅ Nenhuma questão respondida com baixa confiança</span>`;
        }

        resumoConfianca.innerHTML = `
            <span>📊 Confiança média: <strong style="color:${confiancaMedia >= 70 ? 'var(--green)' : confiancaMedia >= 50 ? 'var(--orange)' : 'var(--red)'};">${confiancaMedia.toFixed(1)}%</strong></span>
            ${statusConfianca}
            <span>🎯 Acertos: <strong style="color:var(--green);">${dados.acertos}</strong> / ${dados.totalQuestoes}</span>
            <span>📌 Método: <strong>${metodo}</strong></span>
            ${alertaMultipla}
            ${alertaBranco}
            ${alertaRevisao}
        `;
    }

    // ✨ NOVO: painel detalhado dos 4 estados (só aparece na tela IA)
    const containerDetalhes = document.getElementById('ia-detalhes');
    if (containerDetalhes) {
        const questoesList = dados.resultadoQuestoes || [];

        function isBrancoIA(q) {
            const isMultipla = q.multipla || q.resposta === 'MULTIPLA';
            if (isMultipla) return false;
            if (q.respondida === false) return true;
            const r = (q.resposta || '').toString().trim();
            return !r || r === '—' || r === '-';
        }

        const totalMultiplas = questoesList.filter(q => q.multipla || q.resposta === 'MULTIPLA').length;
        const totalBrancos = questoesList.filter(isBrancoIA).length;
        const totalErros = Math.max(0, dados.totalQuestoes - dados.acertos - totalMultiplas - totalBrancos);

        const linhas = [];
        linhas.push(`<div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(16,185,129,0.08); border-radius:8px; border-left:3px solid var(--green);"><span style="font-size:18px; flex-shrink:0;">✅</span><span style="font-size:13px; color:var(--text);"><strong style="color:var(--green);">${dados.acertos} ${dados.acertos === 1 ? 'questão marcada' : 'questões marcadas'} CORRETAMENTE</strong><span style="color:var(--text3); font-size:11px;"> — contam como acerto</span></span></div>`);
        if (totalErros > 0) {
            linhas.push(`<div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(239,68,68,0.06); border-radius:8px; border-left:3px solid var(--red);"><span style="font-size:18px; flex-shrink:0;">❌</span><span style="font-size:13px; color:var(--text);"><strong style="color:var(--red);">${totalErros} ${totalErros === 1 ? 'questão marcada' : 'questões marcadas'} INCORRETAMENTE</strong><span style="color:var(--text3); font-size:11px;"> — contam como erro</span></span></div>`);
        }
        if (totalMultiplas > 0) {
            linhas.push(`<div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(245,158,11,0.08); border-radius:8px; border-left:3px solid var(--orange);"><span style="font-size:18px; flex-shrink:0;">⚠️</span><span style="font-size:13px; color:var(--text);"><strong style="color:var(--orange);">${totalMultiplas} ${totalMultiplas === 1 ? 'questão com MÚLTIPLA MARCAÇÃO' : 'questões com MÚLTIPLA MARCAÇÃO'}</strong><span style="color:var(--text3); font-size:11px;"> — mais de uma bolha preenchida, contam como erro</span></span></div>`);
        }
        if (totalBrancos > 0) {
            linhas.push(`<div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(100,116,139,0.08); border-radius:8px; border-left:3px solid var(--text3);"><span style="font-size:18px; flex-shrink:0;">—</span><span style="font-size:13px; color:var(--text);"><strong style="color:var(--text2);">${totalBrancos} ${totalBrancos === 1 ? 'questão EM BRANCO' : 'questões EM BRANCO'}</strong><span style="color:var(--text3); font-size:11px;"> — não respondidas, contam como erro</span></span></div>`);
        }

        containerDetalhes.innerHTML = `<div style="margin-top:14px; padding:12px; background:var(--surface2); border-radius:10px; border:1px solid var(--border);"><div style="font-size:11px; font-weight:800; color:var(--text); margin-bottom:10px; text-transform:uppercase; letter-spacing:0.6px;">📋 Detalhes da correção</div><div style="display:flex; flex-direction:column; gap:6px;">${linhas.join('')}</div></div>`;
    }

    const rd = document.getElementById('ia-resp');
    if (rd) {
        rd.innerHTML = dados.resultadoQuestoes.map(q => {
            const isMultipla = q.multipla || q.resposta === 'MULTIPLA';
            const isBranco = !q.respondida;
            const cor = q.acertou ? 'rgba(16,185,129,.2)'
                      : isMultipla ? 'rgba(245,158,11,.2)'
                      : isBranco ? 'rgba(100,116,139,.15)'
                      : 'rgba(239,68,68,.2)';
            const corTexto = q.acertou ? 'var(--green)'
                            : isMultipla ? 'var(--orange)'
                            : isBranco ? 'var(--text3)'
                            : 'var(--red)';
            const icone = q.acertou ? '✅' : isMultipla ? '⚠️' : (isBranco ? '—' : '❌');
            const respostaExibida = isMultipla ? 'MÚLT' : (isBranco ? 'BRANCO' : (q.resposta || '—'));
            const confColor = q.confianca < 70 ? 'var(--orange)' : 'var(--text2)';
            const borderColor = q.acertou ? 'rgba(16,185,129,.4)'
                              : isMultipla ? 'rgba(245,158,11,.4)'
                              : isBranco ? 'rgba(100,116,139,.3)'
                              : 'rgba(239,68,68,.4)';
            return `<span style="background:${cor};border:1px solid ${borderColor};padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;color:${corTexto};">Q${q.numero}:${escapeHtml(respostaExibida)} ${icone}<span style="font-size:8px;color:${confColor};">${q.confianca}%</span></span>`;
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
        tituloOficial.innerHTML = `
            <span style="font-size:12px;font-weight:800;color:var(--blue);letter-spacing:0.3px;">📋 GABARITO OFICIAL GERADO PELO SISTEMA</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;font-weight:600;">(${totalQuestoes} questões)</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;">📌 ${escapeHtml(dados.metodoUsado || 'ia')}</span>
        `;
        grid.appendChild(tituloOficial);

        const gridOficial = document.createElement('div');
        gridOficial.style.cssText = `grid-column: 1 / -1; display: grid; grid-template-columns: repeat(${colunasPorLinha}, 1fr); gap: 4px; padding: 4px 0; background: rgba(59,130,246,0.02); border-radius: 4px; border: 1px solid rgba(59,130,246,0.06);`;
        dados.resultadoQuestoes.forEach((q) => {
            const div = document.createElement('div');
            div.style.cssText = `background: rgba(59,130,246,0.05); border-radius: 4px; padding: 3px 2px; text-align: center; border: 1px solid rgba(59,130,246,0.10); display: flex; flex-direction: column; align-items: center; gap: 1px;`;
            div.innerHTML = `
                <div style="font-size:6px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.2px;">Q${q.numero}</div>
                <div style="font-size:16px;font-weight:900;color:var(--green);line-height:1.1;">${escapeHtml(q.gabarito || '—')}</div>
            `;
            gridOficial.appendChild(div);
        });
        grid.appendChild(gridOficial);

        const tituloAluno = document.createElement('div');
        tituloAluno.style.cssText = `grid-column: 1 / -1; text-align: center; padding: 6px 0; background: linear-gradient(135deg, rgba(139,92,246,0.10), rgba(59,130,246,0.10)); border-radius: 6px; border: 1px solid rgba(139,92,246,0.15); margin-bottom: 2px; margin-top: 8px;`;
        tituloAluno.innerHTML = `
            <span style="font-size:12px;font-weight:800;color:var(--purple);letter-spacing:0.3px;">📋 GABARITO DO ALUNO</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;font-weight:600;">${escapeHtml(dados.aluno.nome || 'Aluno')}</span>
            <span style="font-size:9px;color:var(--text3);margin-left:8px;">📌 ${escapeHtml(dados.metodoUsado || 'ia')}</span>
        `;
        grid.appendChild(tituloAluno);

        const gridAluno = document.createElement('div');
        gridAluno.style.cssText = `grid-column: 1 / -1; display: grid; grid-template-columns: repeat(${colunasPorLinha}, 1fr); gap: 4px; padding: 4px 0; background: rgba(139,92,246,0.02); border-radius: 4px; border: 1px solid rgba(139,92,246,0.06);`;

        dados.resultadoQuestoes.forEach((q) => {
            const acertou = q.acertou;
            const isMultipla = q.multipla || q.resposta === 'MULTIPLA';
            const isBranco = !q.respondida;
            const resposta = isMultipla ? '⚠️' : (isBranco ? '—' : (q.resposta || '—'));
            const confianca = q.confianca || 100;
            let corBg, corTexto, icone, borderC;
            if (acertou) { corBg = 'rgba(16,185,129,0.10)'; corTexto = 'var(--green)'; icone = '✅'; borderC = 'rgba(16,185,129,0.20)'; }
            else if (isMultipla) { corBg = 'rgba(245,158,11,0.12)'; corTexto = 'var(--orange)'; icone = '⚠️'; borderC = 'rgba(245,158,11,0.3)'; }
            else if (isBranco) { corBg = 'rgba(100,116,139,0.06)'; corTexto = 'var(--text3)'; icone = '—'; borderC = 'rgba(100,116,139,0.15)'; }
            else { corBg = 'rgba(239,68,68,0.10)'; corTexto = 'var(--red)'; icone = '❌'; borderC = 'rgba(239,68,68,0.20)'; }
            const confColor = confianca < 70 ? 'var(--orange)' : 'var(--text3)';
            const div = document.createElement('div');
            div.style.cssText = `background: ${corBg}; border-radius: 4px; padding: 3px 2px; text-align: center; border: 1px solid ${borderC}; display: flex; flex-direction: column; align-items: center; gap: 1px;`;
            div.innerHTML = `
                <div style="font-size:6px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.2px;">Q${q.numero}</div>
                <div style="font-size:16px;font-weight:900;color:${corTexto};line-height:1.1;">${escapeHtml(resposta)}</div>
                <div style="font-size:6px;font-weight:700;color:${corTexto};">${icone}</div>
                <div style="font-size:6px;color:${confColor};">${Math.round(confianca)}%</div>
            `;
            gridAluno.appendChild(div);
        });
        grid.appendChild(gridAluno);

        const divComparacao = document.createElement('div');
        divComparacao.style.cssText = `grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr 1fr; gap: 8px; padding: 8px 12px; margin-top: 8px; background: var(--bg2); border-radius: 6px; border: 1px solid var(--border);`;
        const acertos = dados.acertos;
        const multiplas = dados.resultadoQuestoes.filter(q => q.multipla || q.resposta === 'MULTIPLA').length;
        const brancos = dados.resultadoQuestoes.filter(q => !q.respondida).length;
        const errosMarcados = dados.totalQuestoes - acertos - brancos - multiplas;
        const porcentagem = dados.porcentagem;
        divComparacao.innerHTML = `
            <div style="text-align:center;padding:4px;background:rgba(16,185,129,0.06);border-radius:4px;border:1px solid rgba(16,185,129,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--green);">${acertos}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">✅ ACERTOS</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(239,68,68,0.06);border-radius:4px;border:1px solid rgba(239,68,68,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--red);">${errosMarcados}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">❌ ERROS</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(245,158,11,0.08);border-radius:4px;border:1px solid rgba(245,158,11,0.15);">
                <div style="font-size:18px;font-weight:900;color:var(--orange);">${multiplas}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">⚠️ MÚLTIPLAS</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(100,116,139,0.08);border-radius:4px;border:1px solid rgba(100,116,139,0.15);">
                <div style="font-size:18px;font-weight:900;color:var(--text3);">${brancos}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">— EM BRANCO</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(59,130,246,0.06);border-radius:4px;border:1px solid rgba(59,130,246,0.10);">
                <div style="font-size:18px;font-weight:900;color:var(--blue);">${porcentagem}%</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">📊 APROV.</div>
            </div>
            <div style="text-align:center;padding:4px;background:rgba(139,92,246,0.06);border-radius:4px;border:1px solid rgba(139,92,246,0.10);">
                <div style="font-size:14px;font-weight:900;color:var(--purple);line-height:1.3;">${dados.nota.toFixed(1)}</div>
                <div style="font-size:8px;color:var(--text2);font-weight:600;">⭐ NOTA</div>
            </div>
        `;
        grid.appendChild(divComparacao);
    }
}

// ═══ SALVAR CORREÇÃO ═══
// ═══ SALVAR CORREÇÃO (COM FLUXO CONTÍNUO) ═══
async function salvarCorrecao() {
    if (!correcaoManualData || !correcaoManualData.respostasAluno) {
        showToast('❌ Nenhuma correção para salvar!', 'error'); return;
    }
    const provaId = correcaoManualData.provaId;
    const alunoId = correcaoManualData.alunoId;
    const respostas = correcaoManualData.respostasAluno;
    const gabarito = correcaoManualData.gabarito;
    const total = correcaoManualData.quantidade;
    if (!provaId || !alunoId) {
        showToast('❌ Dados da correção incompletos!', 'error'); return;
    }
    let acertos = 0;
    for (let i = 0; i < total; i++) {
        const resp = (i < respostas.length) ? (respostas[i] || '') : '';
        const gab = (i < gabarito.length) ? (gabarito[i] || '') : '';
        // ⚠️ MULTIPLA nunca é acerto, e vazio também não
        if (resp && resp !== 'MULTIPLA' && gab && resp.toUpperCase() === gab.toUpperCase()) acertos++;
    }
    const nota = Math.min(acertos * (correcaoManualData.valorPorQuestao || (10/total)), 10);
    
    try {
        showToast('💾 Salvando correção...', 'info');
        const response = await apiFetch(`${API_URL}/api/corrigir_manual`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prova_id: provaId, aluno_id: alunoId, respostas: respostas,
                acertos: acertos, nota: nota, total: total
            })
        });
        const data = await response.json();
        
        if (data.sucesso) {
            showToast(`✅ Correção salva! Nota: ${nota.toFixed(1)}`, 'success');
            limparCache();
            
            // Atualiza os painéis de fundo
            if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
            if (typeof carregarDashboard === 'function') carregarDashboard();
            if (typeof carregarUltimasCorrecoes === 'function') carregarUltimasCorrecoes();

            // 🚀 NOVO: FLUXO CONTÍNUO
            // Aguarda 1.2 segundos para o professor ler o "Sucesso" e limpa a tela
            setTimeout(() => {
                // 1. Se estiver no fluxo de QR Code (Automático)
                const autoResult = document.getElementById('auto-resultado');
                if (autoResult && autoResult.style.display === 'block') {
                    limparResultadoAutomatico(); // Limpa foto, preview e resultados
                    
                    // Abre o seletor de arquivo automaticamente para o próximo cartão
                    setTimeout(() => {
                        const inputArq = document.getElementById('inp-arq-auto');
                        if (inputArq) {
                            inputArq.value = ''; // Limpa o cache do input
                            inputArq.click();    // Abre a janela de arquivos
                        }
                    }, 300);
                }

                // 2. Se estiver no fluxo de IA Normal (Selecionando aluno)
                const iaResult = document.getElementById('ia-result');
                if (iaResult && iaResult.style.display === 'block') {
                    iaResult.style.display = 'none';
                    
                    // Limpa o aluno selecionado para o professor escolher o próximo
                    const selectAluno = document.getElementById('corrigir-aluno');
                    if (selectAluno) selectAluno.value = '';
                    
                    // Opcional: Scroll para o topo para ver o botão de câmera
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
            }, 1200);

        } else {
            showToast('❌ Erro ao salvar: ' + (data.erro || 'Erro desconhecido'), 'error');
        }
    } catch (erro) {
        console.error('Erro ao salvar correção:', erro);
        showToast('❌ Erro ao salvar: ' + erro.message, 'error');
    }
}

// ═══ CORREÇÃO MANUAL INLINE ═══
function abrirCorrecaoManual() {
    if (!correcaoManualData.respostasAluno || correcaoManualData.respostasAluno.length === 0) {
        showToast('❌ Nenhuma correção para editar. Faça uma correção com IA primeiro!', 'error'); return;
    }
    if (!correcaoManualData.gabarito || !Array.isArray(correcaoManualData.gabarito) || correcaoManualData.gabarito.length === 0) {
        showToast('❌ Gabarito não disponível para esta prova!', 'error'); return;
    }
    const temGabaritoValido = correcaoManualData.gabarito.some(g => g && g.trim() !== '');
    if (!temGabaritoValido) {
        showToast('❌ Gabarito vazio ou inválido para esta prova!', 'error'); return;
    }
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
    if (totalDuvidosas > 0) {
        showToast(`🔍 ${totalDuvidosas} questões com baixa confiança (destacadas em laranja)`, 'warning');
    } else {
        showToast('✅ Todas as questões têm alta confiança!', 'success');
    }
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
        const isMultipla = (respostaAluno === 'MULTIPLA');
        const isCorreto = !isMultipla && respostaAluno && respostaGabarito && respostaAluno.toUpperCase() === respostaGabarito.toUpperCase();

        if (isProducao) {
            div.style.background = 'var(--bg2)'; div.style.border = '1px solid var(--border)';
            div.style.borderRadius = '8px'; div.style.padding = '10px 14px';
            div.style.textAlign = 'left'; div.style.display = 'flex';
            div.style.flexDirection = 'column'; div.style.gap = '6px';
            div.innerHTML = `
                <input class="gab-titulo" type="text" value="Q${i+1}" style="width:100%; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:12px; font-weight:bold;" />
                <div style="font-size:10px;color:var(--text3);">Gabarito: ${escapeHtml(respostaGabarito || '—')}</div>
                <textarea class="q-resposta-texto" placeholder="Resposta do aluno..." style="width:100%; min-height:50px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:4px; font-size:11px; resize:vertical;">${escapeHtml(respostaAluno)}</textarea>
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
            // Adiciona opção MÚLTIPLA
            if (isMultipla) {
                options += `<option value="MULTIPLA" selected>⚠️ MÚLTIPLA</option>`;
            } else {
                options += `<option value="MULTIPLA">⚠️ MÚLTIPLA</option>`;
            }
            let statusClass = ''; let statusText = '';
            if (respostaAluno) {
                if (isMultipla) { statusClass = 'multipla'; statusText = '⚠️'; }
                else if (isCorreto) { statusClass = 'correta'; statusText = '✅'; }
                else { statusClass = 'errada'; statusText = '❌'; }
            }
            const respTexto = isMultipla ? '⚠️ MÚLT' : (respostaAluno || '—');
            const respColor = isMultipla ? 'var(--orange)' : (isCorreto ? 'var(--green)' : (respostaAluno ? 'var(--red)' : 'var(--text3)'));
            div.innerHTML = `
                <div class="q-num">Q${i+1}</div>
                <div class="q-resposta" style="color:${respColor}">${escapeHtml(respTexto)}</div>
                <select class="q-select" data-questao="${i}" onchange="atualizarRespostaManual(this)">${options}</select>
                <div class="q-status ${statusClass}">${statusText}</div>
            `;
            const select = div.querySelector('.q-select');
            if (select) {
                if (isMultipla) select.className = 'q-select multipla';
                else if (respostaAluno && isCorreto) select.className = 'q-select correta';
                else if (respostaAluno) select.className = 'q-select errada';
            }
        }
        grid.appendChild(div);
    }
}

function atualizarRespostaManual(select) {
    const questaoIndex = parseInt(select.dataset.questao);
    const novaResposta = select.value;
    correcaoManualData.respostasAluno[questaoIndex] = novaResposta ? novaResposta.toUpperCase() : '';

    const item = select.closest('.correcao-manual-item');
    const qResposta = item.querySelector('.q-resposta');
    const qStatus = item.querySelector('.q-status');
    const gabarito = correcaoManualData.gabarito[questaoIndex] || '';
    const resposta = correcaoManualData.respostasAluno[questaoIndex] || '';
    const isMultipla = (resposta === 'MULTIPLA');
    const isCorreto = !isMultipla && resposta && gabarito && resposta.toUpperCase() === gabarito.toUpperCase();

    qResposta.textContent = isMultipla ? '⚠️ MÚLT' : (resposta || '—');
    qResposta.style.color = isMultipla ? 'var(--orange)' : (isCorreto ? 'var(--green)' : (resposta ? 'var(--red)' : 'var(--text3)'));
    if (isMultipla) {
        qStatus.textContent = '⚠️'; qStatus.className = 'q-status multipla'; select.className = 'q-select multipla';
    } else if (resposta) {
        if (isCorreto) { qStatus.textContent = '✅'; qStatus.className = 'q-status correta'; select.className = 'q-select correta'; }
        else { qStatus.textContent = '❌'; qStatus.className = 'q-status errada'; select.className = 'q-select errada'; }
    } else {
        qStatus.textContent = ''; qStatus.className = 'q-status'; select.className = 'q-select';
    }
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
            if (isProducao) {
                if (resp.trim().toLowerCase() === gab.trim().toLowerCase()) acertos++;
            } else {
                if (resp !== 'MULTIPLA' && resp.toUpperCase() === gab.toUpperCase()) acertos++;
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
    if (statusBadge && statusAtual) {
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
            if (i < gabarito.length) {
                input.value = gabarito[i] || '';
                correcaoManualData.respostasAluno[i] = gabarito[i] || '';
            }
        });
    } else {
        for (let i = 0; i < qtd; i++) {
            if (i < gabarito.length && gabarito[i]) correcaoManualData.respostasAluno[i] = gabarito[i];
        }
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
        if (resp && resp !== 'MULTIPLA' && resp.toUpperCase() === gab.toUpperCase()) acertos++;
    }
    const nota = Math.min((acertos * correcaoManualData.valorPorQuestao), correcaoManualData.notaMaxima || 10);

    const etapas = [
        { nome: '📝 Processando respostas', descricao: 'Validando respostas do aluno...' },
        { nome: '📊 Calculando nota', descricao: 'Calculando aproveitamento...' },
        { nome: '💾 Salvando no sistema', descricao: 'Persistindo correção...' }
    ];
    progressManager.iniciar('💾 Salvando Correção Manual', etapas, '✏️');

    const dadosCorrecao = {
        prova_id: correcaoManualData.provaId, aluno_id: correcaoManualData.alunoId,
        respostas: respostas, acertos: acertos, nota: nota, total: qtd
    };

    apiFetch(API_URL + '/api/corrigir_manual', {
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
                if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
                if (typeof carregarDashboard === 'function') carregarDashboard();
                if (typeof carregarUltimasCorrecoes === 'function') carregarUltimasCorrecoes();
            }, 500);
            const alunoId = correcaoManualData.alunoId;
            if (alunoId && typeof tableFeedback !== 'undefined') {
                setTimeout(() => tableFeedback.destacarLinha('tb-resultados-filtrado', alunoId, '✅ Corrigido!'), 800);
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

// ═══ CORREÇÃO MANUAL STANDALONE ═══
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
    } catch (e) { console.error('Erro ao carregar turmas:', e); }
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
    } catch (e) { console.error('Erro ao carregar alunos:', e); }
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
                opt.textContent = p.titulo + ' - ' + (p.serie || '') + ' - ' + (p.disciplina || '');
                opt.dataset.serie = p.serie || '';
                opt.dataset.quantidade = p.quantidade_questoes || 20;
                opt.dataset.tipo = p.tipo_questoes || '4';
                opt.dataset.data = p.data_prova || '';
                opt.dataset.gabarito = JSON.stringify(p.gabarito || []);
                opt.dataset.bncc = JSON.stringify(p.bncc || []);
                opt.dataset.disciplina = p.disciplina || '';
                selectProva.appendChild(opt);
            });
        }
    } catch (e) { console.error('Erro ao carregar provas:', e); }
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
        const provaResp = await apiFetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) {
            showToast('❌ Erro ao carregar prova: ' + (prova.erro || 'Desconhecido'), 'error');
            return;
        }
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
            for (let i = 0; i < cmStandaloneData.quantidade; i++) {
                cmStandaloneData.situacoes[i] = prova.niveis[i] || '';
            }
        }
    } catch (e) {
        console.error('Erro ao carregar prova:', e);
        showToast('❌ Erro ao carregar dados da prova: ' + e.message, 'error');
        return;
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
        grid.style.display = 'flex'; grid.style.flexDirection = 'column';
        grid.style.gap = '14px'; grid.style.maxHeight = 'none'; grid.style.overflowY = 'visible';
    } else {
        grid.style.display = 'grid'; grid.style.gridTemplateColumns = 'repeat(10, 1fr)';
        grid.style.gap = '6px'; grid.style.maxHeight = '280px'; grid.style.overflowY = 'auto';
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
            const cabecalhoHTML = `<div class="cm-q-cabecalho-inline">${escapeHtml(headerTexto)}</div>`;
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
            } else {
                gabFormatadoHTML = '<div style="color:var(--text3);font-style:italic;">Sem gabarito cadastrado</div>';
            }
            const situacaoAtual = (i < situacoes.length) ? (situacoes[i] || '') : '';
            const opcoesSit = ['', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'];
            let optsSitHTML = '';
            opcoesSit.forEach(op => {
                const sel = (situacaoAtual === op) ? 'selected' : '';
                optsSitHTML += `<option value="${op}" ${sel}>${op === '' ? '—' : op}</option>`;
            });
            div.innerHTML = `
                ${cabecalhoHTML}
                <div>
                    <div class="cm-q-resposta-label">📋 Situação de Correção:</div>
                    <div class="cm-gabarito-formatado">${gabFormatadoHTML}</div>
                </div>
                <div>
                    <div class="cm-q-resposta-label">✍️ Observação do Professor:</div>
                    <textarea class="cm-q-resposta-texto" placeholder="Escreva sua avaliação/observação sobre a resposta do aluno..." data-questao="${i}">${escapeHtml(resp || '')}</textarea>
                </div>
                <div class="cm-q-situacao-wrapper">
                    <label class="cm-q-situacao-label">📊 Situação de Correção Alternativa:</label>
                    <select class="cm-q-situacao-select" data-questao="${i}" onchange="atualizarSituacaoCM(this)">
                        ${optsSitHTML}
                    </select>
                </div>
            `;
            const textarea = div.querySelector('.cm-q-resposta-texto');
            textarea.addEventListener('input', function() {
                cmStandaloneData.respostas[i] = this.value;
            });
        } else {
            div.className = 'cm-item-standalone';
            const isMultipla = (resp === 'MULTIPLA');
            let options = '<option value="">—</option>';
            alternativas.forEach(alt => {
                const selected = resp && resp.toUpperCase() === alt ? 'selected' : '';
                options += `<option value="${alt}" ${selected}>${alt}</option>`;
            });
            if (isMultipla) {
                options += `<option value="MULTIPLA" selected>⚠️ MÚLTIPLA</option>`;
            } else {
                options += `<option value="MULTIPLA">⚠️ MÚLTIPLA</option>`;
            }
            const isCorreto = !isMultipla && resp && gab && resp.toUpperCase() === gab.toUpperCase();
            let statusIcon = '';
            if (resp) statusIcon = isMultipla ? '⚠️' : (isCorreto ? '✅' : '❌');
            let selectClass = 'q-select-manual';
            if (resp) selectClass += isMultipla ? ' multipla' : (isCorreto ? ' correta' : ' errada');
            div.innerHTML = `
                <div class="q-num">Q${i+1}</div>
                <div class="q-gabarito">${escapeHtml(gab || '—')}</div>
                <select class="${selectClass}" data-questao="${i}" onchange="atualizarRespostaManualSA(this)">
                    ${options}
                </select>
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
    cmStandaloneData.respostas[questaoIndex] = novaResposta ? novaResposta.toUpperCase() : '';
    const item = select.closest('.cm-item-standalone');
    const statusIcon = item.querySelector('.q-status-icon');
    const gabarito = cmStandaloneData.gabarito[questaoIndex] || '';
    const resposta = cmStandaloneData.respostas[questaoIndex] || '';
    const isMultipla = (resposta === 'MULTIPLA');
    const isCorreto = !isMultipla && resposta && gabarito && resposta.toUpperCase() === gabarito.toUpperCase();
    select.className = 'q-select-manual';
    if (resposta) {
        if (isMultipla) select.className += ' multipla';
        else select.className += isCorreto ? ' correta' : ' errada';
    }
    if (isMultipla) statusIcon.textContent = '⚠️';
    else if (resposta) statusIcon.textContent = isCorreto ? '✅' : '❌';
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
            if (isProducao) {
                if (resp.trim().toLowerCase() === gab.trim().toLowerCase()) acertos++;
            } else {
                if (resp !== 'MULTIPLA' && resp.toUpperCase() === gab.toUpperCase()) acertos++;
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
    if (statusBadge) {
        if (notaFinal >= (cmStandaloneData.notaMinima || 5)) { statusBadge.textContent = '✅ APROVADO'; statusBadge.className = 'badge badge-green'; }
        else if (notaFinal >= (cmStandaloneData.notaMinima || 5) * 0.8) { statusBadge.textContent = '⚠️ RECUPERAÇÃO'; statusBadge.className = 'badge badge-orange'; }
        else { statusBadge.textContent = '❌ REPROVADO'; statusBadge.className = 'badge badge-red'; }
    }
    setText('cm-sa-porcentagem', porcentagem + '% de aproveitamento');
}

function preencherGabaritoManualSA() {
    const gabarito = cmStandaloneData.gabarito || [];
    const isProducao = (cmStandaloneData.disciplina === 'Produção de Texto');
    if (isProducao) {
        const inputs = document.querySelectorAll('#cm-grid-standalone .cm-q-resposta-texto');
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
        if (isSuspeita) {
            item.style.display = '';
            totalDuvidosas++;
            if (totalDuvidosas === 1) item.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
        if (resp && resp !== 'MULTIPLA' && gab && resp.toUpperCase() === gab.toUpperCase()) acertos++;
    }
    const valorPorQuestao = cmStandaloneData.valorPorQuestao || (10 / qtd);
    const nota = Math.min((acertos * valorPorQuestao), cmStandaloneData.notaMaxima || 10);
    showToast('💾 Salvando correção manual...', 'info');
    const dadosCorrecao = {
        prova_id: provaId, aluno_id: alunoId,
        respostas: respostas.map(r => r || ''),
        acertos: acertos, nota: nota, total: qtd
    };
    apiFetch(API_URL + '/api/corrigir_manual', {
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
                const paginaAtualEl = document.querySelector('.page.active');
                if (paginaAtualEl) {
                    const pageId = paginaAtualEl.id.replace('page-', '');
                    switch(pageId) {
                        case 'resultados':
                            if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
                            break;
                        case 'dashboard':
                            if (typeof carregarDashboard === 'function') carregarDashboard();
                            if (typeof carregarUltimasCorrecoes === 'function') carregarUltimasCorrecoes();
                            break;
                        case 'rel-turma':
                            if (typeof carregarRelatorioTurmaFiltrado === 'function') carregarRelatorioTurmaFiltrado();
                            break;
                        case 'desempenho':
                            if (typeof desempenhoData !== 'undefined' && desempenhoData.alunoSelecionado && typeof gerarDesempenho === 'function') gerarDesempenho();
                            break;
                        default:
                            if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
                            if (typeof carregarDashboard === 'function') carregarDashboard();
                            break;
                    }
                }
                if (typeof carregarConceitoReal === 'function') carregarConceitoReal();
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

async function salvarNotaProducaoCM() {
    const notaInput = document.getElementById('cm-nota-valor');
    const obsInput = document.getElementById('cm-nota-observacao');
    const statusDiv = document.getElementById('cm-nota-status');
    const btn = document.getElementById('btn-salvar-nota-cm');
    const nota = notaInput ? notaInput.value : '';
    const alunoId = cmStandaloneData.alunoId;
    const provaId = cmStandaloneData.provaId;
    if (!alunoId || !provaId) { showToast('❌ Dados incompletos: aluno ou prova ausentes!', 'error'); return; }
    if (!nota || nota === '') {
        showToast('❌ Digite a nota!', 'error');
        if (notaInput) notaInput.focus();
        return;
    }
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
                resposta: resp || '—', gabarito: gab || '—',
                situacao: sit || '', acertou: false, respondida: !!resp,
                bncc: '', status: `Situação: ${sit || '—'}`,
                status_texto: `📝 Situação ${sit || '—'}`
            });
        }
        const response = await apiFetch(`${API_URL}/api/salvar_nota_producao`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                aluno_id: parseInt(alunoId), prova_id: parseInt(provaId),
                nota: notaNum, observacao: '', questoes_status: questoesStatus
            })
        });
        const dados = await response.json();
        if (dados.sucesso) {
            showToast(`✅ Nota ${notaNum.toFixed(1)} salva para ${dados.aluno}!`, 'success');
            if (statusDiv) {
                statusDiv.className = 'sucesso';
                statusDiv.textContent = `✅ Nota ${notaNum.toFixed(1)} salva! Já aparece em Resultados, Rel. Turma e Desempenho.`;
                statusDiv.style.background = 'rgba(16,185,129,0.12)';
                statusDiv.style.color = 'var(--green)';
                statusDiv.style.border = '1.5px solid rgba(16,185,129,0.3)';
            }
            if (notaInput) notaInput.value = '';
            if (obsInput) obsInput.value = '';
            limparCache();
            setTimeout(() => {
                if (typeof carregarResultadosComFiltros === 'function') carregarResultadosComFiltros();
                if (typeof carregarDashboard === 'function') carregarDashboard();
                if (typeof carregarUltimasCorrecoes === 'function') carregarUltimasCorrecoes();
            }, 500);
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
        console.error('Erro ao salvar nota produção:', erro);
        showToast('❌ Erro ao salvar nota: ' + erro.message, 'error');
        if (statusDiv) {
            statusDiv.className = 'erro';
            statusDiv.textContent = '❌ Erro ao salvar: ' + erro.message;
            statusDiv.style.background = 'rgba(239,68,68,0.12)';
            statusDiv.style.color = 'var(--red)';
            statusDiv.style.border = '1.5px solid rgba(239,68,68,0.3)';
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function abrirCorrecaoManualDireta(escolaId, turmaId, alunoId, provaId) {
    try {
        showToast('🔄 Carregando dados...', 'info');
        const provaResp = await apiFetch(`${API_URL}/api/provas/${provaId}`);
        const prova = await provaResp.json();
        if (!prova || prova.erro) { showToast('❌ Erro ao carregar prova', 'error'); return; }
        const alunoResp = await apiFetch(`${API_URL}/api/alunos/${alunoId}`);
        const aluno = await alunoResp.json();
        if (!aluno || aluno.erro) { showToast('❌ Erro ao carregar aluno', 'error'); return; }
        const historicoResp = await apiFetch(`${API_URL}/api/historico?aluno_id=${alunoId}&prova_id=${provaId}`);
        const historico = await historicoResp.json();
        let respostas = [];
        if (historico && historico.length > 0 && !historico.erro) respostas = historico[0].respostas || [];

        cmStandaloneData.escolaId = parseInt(escolaId);
        cmStandaloneData.turmaId = parseInt(turmaId);
        cmStandaloneData.provaId = parseInt(provaId);
        cmStandaloneData.alunoId = parseInt(alunoId);
        cmStandaloneData.alunoNome = aluno.nome || 'Aluno';
        cmStandaloneData.serie = prova.serie || '';
        cmStandaloneData.gabarito = prova.gabarito || [];
        cmStandaloneData.quantidade = prova.quantidade_questoes || 20;
        cmStandaloneData.alternativas = prova.tipo_questoes == '3' ? ['A', 'B', 'C'] : ['A', 'B', 'C', 'D'];
        cmStandaloneData.valorPorQuestao = 10 / cmStandaloneData.quantidade;
        cmStandaloneData.respostas = respostas.slice(0, cmStandaloneData.quantidade);
        while (cmStandaloneData.respostas.length < cmStandaloneData.quantidade) cmStandaloneData.respostas.push('');
        cmStandaloneData.provaTitulo = prova.titulo || 'Prova';
        cmStandaloneData.provaData = prova.data_prova || '';
        cmStandaloneData.disciplina = prova.disciplina || '';

        openM('m-correcao-manual-standalone');
        const selectsContainer = document.getElementById('cm-selects-container');
        if (selectsContainer) selectsContainer.style.display = 'none';
        document.getElementById('cm-grid-standalone-container').style.display = 'block';
        setText('cm-sa-aluno', cmStandaloneData.alunoNome);
        setText('cm-sa-turma', cmStandaloneData.serie);
        setText('cm-sa-prova', cmStandaloneData.provaTitulo);
        setText('cm-sa-data', cmStandaloneData.provaData || new Date().toLocaleDateString('pt-BR'));
        ajustarUIporDisciplina();
        gerarGridCorrecaoManualSA();
        atualizarResumoCorrecaoManualSA();
        showToast('📝 Correção manual carregada para ' + cmStandaloneData.alunoNome, 'success');
    } catch (erro) {
        console.error('❌ Erro ao abrir correção manual direta:', erro);
        showToast('❌ Erro ao carregar dados: ' + erro.message, 'error');
    }
}

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

// ═══ CORREÇÃO AUTOMÁTICA POR QR CODE ═══
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

    // ✨ NOVO: guarda a imagem para o botão "Ver cartão original" (QR auto)
    window._ultimaImagemCorrigida = imagem;

    const resultadoDiv = document.getElementById('auto-resultado');
    const conteudoDiv = document.getElementById('auto-resultado-conteudo');
    if (resultadoDiv) resultadoDiv.style.display = 'block';
    if (conteudoDiv) {
        conteudoDiv.innerHTML = `
            <div style="text-align:center; padding:20px;">
                <div class="spinner" style="margin:0 auto 14px;"></div>
                <p style="font-size:15px; font-weight:700;">🔍 Lendo o QR Code do cartão...</p>
                <p style="font-size:13px; color:var(--text2); margin-top:6px;">Identificando aluno, prova, escola e turma automaticamente</p>
            </div>
        `;
    }
    try {
        const response = await apiFetch(`${API_URL}/api/corrigir-automatico`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ imagem: imagem, salvar_auto: false })
        });
        const dados = await response.json();
        if (!response.ok || !dados.sucesso) {
            mostrarErroAutomatico(dados.erro || 'Erro na correção automática', dados.dicas);
            return;
        }
        mostrarResultadoAutomatico(dados);
        window._autoImagem = null;
        const preview = document.getElementById('auto-preview');
        if (preview) preview.style.display = 'none';
    } catch (erro) {
        console.error('Erro na correção automática:', erro);
        mostrarErroAutomatico('Erro de conexão: ' + erro.message);
    }
}

function mostrarErroAutomatico(mensagem, dicas) {
    const conteudoDiv = document.getElementById('auto-resultado-conteudo');
    if (!conteudoDiv) return;
    let dicasHtml = '';
    if (dicas && Array.isArray(dicas)) {
        dicasHtml = '<div style="margin-top:14px; padding:12px; background:rgba(245,158,11,0.1); border-radius:8px; border-left:3px solid var(--orange);"><strong style="color:var(--orange);">Dicas:</strong><ul style="margin-top:6px; padding-left:20px; font-size:13px; color:var(--text2); line-height:1.7;">';
        dicas.forEach(d => { dicasHtml += `<li>${escapeHtml(d)}</li>`; });
        dicasHtml += '</ul></div>';
    }
    conteudoDiv.innerHTML = `
        <div style="padding:16px; background:rgba(239,68,68,0.08); border-radius:10px; border-left:4px solid var(--red);">
            <div style="font-size:15px; font-weight:700; color:var(--red); margin-bottom:8px;">❌ ${escapeHtml(mensagem)}</div>
            ${dicasHtml}
            <div style="margin-top:14px; padding-top:14px; border-top:1px solid var(--border); font-size:13px; color:var(--text2);">
                <strong>Alternativa:</strong> use os campos abaixo (Escola / Turma / Prova / Aluno) para corrigir manualmente.
            </div>
        </div>
    `;
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

    const conceitoCores = { 'inicial': '#ef4444', 'basico': '#f59e0b', 'proficiente': '#3b82f6', 'avancado': '#10b981' };
    const cor = conceitoCores[conceito] || '#94a3b8';
    const conceitoLabel = { 'inicial': '🔴 Inicial', 'basico': '🟠 Básico', 'proficiente': '🔵 Proficiente', 'avancado': '🟢 Avançado' }[conceito] || conceito;

    // ═══════════════════════════════════════════════════════════════
    // Contadores por estado: multiplas, brancos, erros marcados
    // ═══════════════════════════════════════════════════════════════
    const questoesStatus = Array.isArray(dados.questoes_status) ? dados.questoes_status : [];

    function isQuestaoBranco(q) {
        const isMultipla = q.multipla || q.resposta === 'MULTIPLA';
        if (isMultipla) return false;
        if (q.respondida === false) return true;
        const resp = (q.resposta || '').toString().trim();
        return !resp || resp === '—' || resp === '-';
    }

    const totalMultiplas = questoesStatus.filter(q => q.multipla || q.resposta === 'MULTIPLA').length;
    const totalBrancos = questoesStatus.filter(isQuestaoBranco).length;
    const totalErrosMarcados = Math.max(0, total - acertos - totalMultiplas - totalBrancos);

    let questoesHtml = '';
    if (questoesStatus.length > 0) {
        questoesHtml = '<div style="display:grid; grid-template-columns:repeat(10,1fr); gap:4px; margin-top:12px;">';
        questoesStatus.forEach(q => {
            const isMultipla = q.multipla || q.resposta === 'MULTIPLA';
            const isBranco = isQuestaoBranco(q);
            const acertou = q.acertou;
            const resp = isMultipla ? '⚠️' : (isBranco ? '—' : (q.resposta || '—'));
            let corQ, corTexto, icone;
            if (acertou) { corQ = 'rgba(16,185,129,0.15)'; corTexto = 'var(--green)'; icone = '✅'; }
            else if (isMultipla) { corQ = 'rgba(245,158,11,0.15)'; corTexto = 'var(--orange)'; icone = '⚠️'; }
            else if (isBranco) { corQ = 'rgba(100,116,139,0.1)'; corTexto = 'var(--text3)'; icone = '—'; }
            else { corQ = 'rgba(239,68,68,0.15)'; corTexto = 'var(--red)'; icone = '❌'; }
            questoesHtml += `<div style="background:${corQ}; border-radius:6px; padding:5px 2px; text-align:center;"><div style="font-size:8px; font-weight:700; color:var(--text3);">Q${q.numero}</div><div style="font-size:13px; font-weight:800; color:${corTexto};">${escapeHtml(resp)}</div><div style="font-size:8px;">${icone}</div></div>`;
        });
        questoesHtml += '</div>';
    }

    // ═══════════════════════════════════════════════════════════════
    // PAINEL DETALHADO — os 4 estados com explicação
    // ═══════════════════════════════════════════════════════════════
    const linhasResumo = [];

    linhasResumo.push(`
        <div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(16,185,129,0.08); border-radius:8px; border-left:3px solid var(--green);">
            <span style="font-size:18px; flex-shrink:0;">✅</span>
            <span style="font-size:13px; color:var(--text);">
                <strong style="color:var(--green);">${acertos} ${acertos === 1 ? 'questão marcada' : 'questões marcadas'} CORRETAMENTE</strong>
                <span style="color:var(--text3); font-size:11px;"> — contam como acerto</span>
            </span>
        </div>
    `);

    if (totalErrosMarcados > 0) {
        linhasResumo.push(`
            <div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(239,68,68,0.06); border-radius:8px; border-left:3px solid var(--red);">
                <span style="font-size:18px; flex-shrink:0;">❌</span>
                <span style="font-size:13px; color:var(--text);">
                    <strong style="color:var(--red);">${totalErrosMarcados} ${totalErrosMarcados === 1 ? 'questão marcada' : 'questões marcadas'} INCORRETAMENTE</strong>
                    <span style="color:var(--text3); font-size:11px;"> — contam como erro</span>
                </span>
            </div>
        `);
    }

    if (totalMultiplas > 0) {
        linhasResumo.push(`
            <div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(245,158,11,0.08); border-radius:8px; border-left:3px solid var(--orange);">
                <span style="font-size:18px; flex-shrink:0;">⚠️</span>
                <span style="font-size:13px; color:var(--text);">
                    <strong style="color:var(--orange);">${totalMultiplas} ${totalMultiplas === 1 ? 'questão com MÚLTIPLA MARCAÇÃO' : 'questões com MÚLTIPLA MARCAÇÃO'}</strong>
                    <span style="color:var(--text3); font-size:11px;"> — mais de uma bolha preenchida, contam como erro</span>
                </span>
            </div>
        `);
    }

    if (totalBrancos > 0) {
        linhasResumo.push(`
            <div style="display:flex; align-items:center; gap:10px; padding:8px 12px; background:rgba(100,116,139,0.08); border-radius:8px; border-left:3px solid var(--text3);">
                <span style="font-size:18px; flex-shrink:0;">—</span>
                <span style="font-size:13px; color:var(--text);">
                    <strong style="color:var(--text2);">${totalBrancos} ${totalBrancos === 1 ? 'questão EM BRANCO' : 'questões EM BRANCO'}</strong>
                    <span style="color:var(--text3); font-size:11px;"> — não respondidas, contam como erro</span>
                </span>
            </div>
        `);
    }

    let painelResumo = `
        <div style="margin-top:14px; padding:12px; background:var(--surface2); border-radius:10px; border:1px solid var(--border);">
            <div style="font-size:11px; font-weight:800; color:var(--text); margin-bottom:10px; text-transform:uppercase; letter-spacing:0.6px;">📋 Detalhes da correção</div>
            <div style="display:flex; flex-direction:column; gap:6px;">
                ${linhasResumo.join('')}
            </div>
        </div>
    `;

    let alertaHtml = painelResumo;

    if (dados.requer_revisao_manual) {
        alertaHtml += '<div style="margin-top:12px; padding:10px; background:rgba(245,158,11,0.12); border-radius:8px; border-left:3px solid var(--orange); font-size:12px; color:var(--orange);">⚠️ <strong>Revisão manual recomendada</strong> — algumas questões respondidas tiveram baixa confiança de leitura.</div>';
    }

    conteudoDiv.innerHTML = `
        <div style="background:linear-gradient(135deg, rgba(139,92,246,0.08), rgba(6,182,212,0.08)); border-radius:12px; padding:16px; border:2px solid rgba(139,92,246,0.3);">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
                <div style="font-size:16px; font-weight:800; color:#a78bfa;">✅ Correção Automática Concluída!</div>
                <span class="badge badge-purple" style="font-size:10px;">VIA QR CODE</span>
            </div>
            <div style="display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-bottom:14px; font-size:13px;">
                <div style="background:var(--surface2); border-radius:8px; padding:10px;"><div style="color:var(--text3); font-size:9px; font-weight:700; margin-bottom:3px;">ALUNO</div><div style="font-weight:700;">${escapeHtml(aluno)}</div></div>
                <div style="background:var(--surface2); border-radius:8px; padding:10px;"><div style="color:var(--text3); font-size:9px; font-weight:700; margin-bottom:3px;">PROVA</div><div style="font-weight:700;">${escapeHtml(prova)}</div></div>
                <div style="background:var(--surface2); border-radius:8px; padding:10px;"><div style="color:var(--text3); font-size:9px; font-weight:700; margin-bottom:3px;">ESCOLA</div><div style="font-weight:700; font-size:12px;">${escapeHtml(escola)}</div></div>
                <div style="background:var(--surface2); border-radius:8px; padding:10px;"><div style="color:var(--text3); font-size:9px; font-weight:700; margin-bottom:3px;">TURMA</div><div style="font-weight:700; font-size:12px;">${escapeHtml(turma)}</div></div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:8px; margin-bottom:14px;">
                <div style="background:var(--surface2); border-radius:8px; padding:10px; text-align:center;"><div style="font-size:26px; font-weight:900; color:var(--green);">${acertos}</div><div style="font-size:10px; color:var(--text3); font-weight:700;">✅ ACERTOS</div></div>
                <div style="background:var(--surface2); border-radius:8px; padding:10px; text-align:center;"><div style="font-size:26px; font-weight:900; color:var(--red);">${total - acertos}</div><div style="font-size:10px; color:var(--text3); font-weight:700;">❌ NÃO ACERTOS</div></div>
                <div style="background:var(--surface2); border-radius:8px; padding:10px; text-align:center;"><div style="font-size:26px; font-weight:900; color:var(--blue);">${porcentagem}%</div><div style="font-size:10px; color:var(--text3); font-weight:700;">📊 APROVEIT.</div></div>
                <div style="background:var(--surface2); border-radius:8px; padding:10px; text-align:center;"><div style="font-size:26px; font-weight:900; color:${cor};">${nota.toFixed(1)}</div><div style="font-size:10px; color:var(--text3); font-weight:700;">⭐ NOTA</div></div>
            </div>
            <div style="text-align:center; margin-bottom:10px;"><span style="background:${cor}20; color:${cor}; padding:6px 18px; border-radius:20px; font-size:13px; font-weight:800;">${conceitoLabel}</span></div>
            ${questoesHtml}
            ${alertaHtml}
            <div style="display:flex; gap:8px; margin-top:16px; flex-wrap:wrap; justify-content:center;">
                <button class="btn btn-outline btn-sm no-print" onclick="verCartaoOriginal()" style="background:rgba(139,92,246,0.1); border-color:rgba(139,92,246,0.4); color:#a78bfa;">🖼️ Ver cartão original</button>
                <button class="btn btn-orange btn-sm no-print" onclick="abrirCorrecaoManualAuto()">✏️ Correção Manual</button>
                <button class="btn btn-green btn-sm no-print" onclick="salvarCorrecaoAuto()">💾 Salvar</button>
                <button class="btn btn-green btn-sm" onclick="go('resultados')">📊 Ver em Resultados</button>
                <button class="btn btn-outline btn-sm" onclick="limparResultadoAutomatico()">🔄 Nova Correção</button>
                <button class="btn btn-primary btn-sm" onclick="go('desempenho')">📈 Desempenho do Aluno</button>
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
    if (!correcaoManualData || !correcaoManualData.respostasAluno || correcaoManualData.respostasAluno.length === 0) {
        showToast('❌ Nenhuma correção para editar!', 'error'); return;
    }
    if (!correcaoManualData.gabarito || correcaoManualData.gabarito.length === 0) {
        showToast('❌ Gabarito não disponível para esta prova!', 'error'); return;
    }
    abrirCorrecaoManual();
}

async function salvarCorrecaoAuto() {
    if (!correcaoManualData || !correcaoManualData.respostasAluno) {
        showToast('❌ Nenhuma correção para salvar!', 'error'); return;
    }
    if (!correcaoManualData.provaId || !correcaoManualData.alunoId) {
        showToast('❌ Dados incompletos: prova ou aluno ausentes!', 'error'); return;
    }
    await salvarCorrecao();
}

// ═══════════════════════════════════════════════════════════════════
// ✨ NOVO: MODAL "VER CARTÃO ORIGINAL"
// Abre a foto do cartão em tela cheia para o professor comparar
// ═══════════════════════════════════════════════════════════════════

function verCartaoOriginal() {
    const imagem = window._ultimaImagemCorrigida;
    if (!imagem) {
        showToast('⚠️ Foto do cartão não disponível. Faça uma nova correção para visualizar.', 'warning');
        return;
    }
    const modal = document.getElementById('m-ver-cartao');
    const img = document.getElementById('ver-cartao-img');
    if (!modal || !img) {
        showToast('❌ Modal não encontrado. Adicione <div id="m-ver-cartao"> ao index.html', 'error');
        console.error('[verCartaoOriginal] Elemento #m-ver-cartao não existe no DOM');
        return;
    }
    img.src = imagem;
    modal.style.display = 'flex';
    document.addEventListener('keydown', _fecharCartaoComEsc);
}

function _fecharCartaoComEsc(e) {
    if (e.key === 'Escape') {
        fecharCartaoOriginal();
    }
}

function fecharCartaoOriginal() {
    const modal = document.getElementById('m-ver-cartao');
    const img = document.getElementById('ver-cartao-img');
    if (modal) modal.style.display = 'none';
    if (img) img.src = '';
    document.removeEventListener('keydown', _fecharCartaoComEsc);
}

function abrirCartaoNovaAba() {
    const imagem = window._ultimaImagemCorrigida;
    if (!imagem) return;
    const w = window.open('', '_blank');
    if (w) {
        w.document.write(`<!DOCTYPE html><html><head><title>Cartão resposta — CorrigePro</title>
        <style>body{margin:0;background:#111;display:flex;align-items:center;justify-content:center;min-height:100vh;flex-direction:column;font-family:system-ui,sans-serif;}
        img{max-width:100%;max-height:95vh;object-fit:contain;box-shadow:0 10px 40px rgba(0,0,0,0.6);}
        .bar{position:fixed;top:12px;right:12px;display:flex;gap:8px;}
        .bar button{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:6px;padding:6px 12px;font-size:12px;font-weight:700;cursor:pointer;}
        .bar button:hover{background:rgba(255,255,255,0.25);}
        </style></head><body>
        <div class="bar"><button onclick="window.print()">🖨️ Imprimir</button></div>
        <img src="${imagem}" alt="Cartão original">
        </body></html>`);
        w.document.close();
    } else {
        showToast('⚠️ Bloqueador de pop-up impediu abrir a nova aba', 'warning');
    }
}

function baixarCartaoOriginal() {
    const imagem = window._ultimaImagemCorrigida;
    if (!imagem) return;
    const a = document.createElement('a');
    a.href = imagem;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    a.download = `cartao_${timestamp}.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('✅ Download iniciado!', 'success');
}

// Fechar ao clicar fora da imagem (no fundo preto)
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('m-ver-cartao');
    if (modal) {
        modal.addEventListener('click', (e) => {
            // Só fecha se clicou no overlay (não na imagem nem nos botões)
            if (e.target.id === 'm-ver-cartao') {
                fecharCartaoOriginal();
            }
        });
    }
});

console.log('✅ js/correcao.js carregado (com MULTIPLA + modal Ver Cartão Original)');
