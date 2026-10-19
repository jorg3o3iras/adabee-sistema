// ============================================================
// SCRIPT.JS (FINAL) — Matriz, usuários, texto IA, cartões, boot
// Depois da divisão: só o que sobrou dos 7 cortes
// Ordem: ÚLTIMO (depois de todos os js/*.js)
// ============================================================

// ═══ VARIÁVEIS DE ESTADO REMANESCENTES ═══
let usuarioEditandoId = null;
let visualizarMatrizId = null;
let matrizesData = [];
let matrizEditId = null;
let matrizDescritorCounter = 0;
let matrizParaDeletar = null;

// ═══ FUNÇÕES AUXILIARES GERAIS ═══
function switchTab(idx, btn) {
    const parent = btn.closest('.tab-nav');
    if (parent) { parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); }
    const card = btn.closest('.card');
    if (card) { card.querySelectorAll('.tab-c').forEach((tc, i) => { tc.style.display = i === idx ? 'block' : 'none'; }); }
}

function simUpload() { setTimeout(() => { document.getElementById('up-ok').style.display = 'block'; showToast('✅ Arquivo enviado!', 'success'); }, 600); }

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
                        return '<tr><td><strong>' + escapeHtml(t.nome) + '</strong></td><td><span class="badge badge-purple">' + escapeHtml(t.serie || '—') + '</span></td><td>' + escapeHtml(t.professor || '—') + '</td><td><span class="badge badge-blue">' + totalAlunos + '</span></td><td><button class="btn btn-green btn-sm" onclick="go(\'lista-turma\')">📋</button></td></tr>';
                    }).join('');
                }
            }).catch(e => console.error(e));
        }
    } catch (e) { console.log('Erro ao carregar dados do usuário:', e); }
}

function filtrarTabela(input, tbodyId) {
    const val = input.value.toLowerCase();
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(row => { row.style.display = row.textContent.toLowerCase().includes(val) ? '' : 'none'; });
}

function filtrarSerie(sel) {
    const val = sel.value;
    document.querySelectorAll('#tb-turmas tr').forEach(row => { row.style.display = (!val || row.dataset.serie === val) ? '' : 'none'; });
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

// ═══ TEXTOS COM IA ═══
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
            } else {
                showToast('❌ ' + (dados.erro || 'Não foi possível ler a imagem'), 'error');
            }
        } catch (err) {
            console.error('Erro no OCR:', err);
            showToast('❌ Erro ao processar imagem: ' + err.message, 'error');
        }
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
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ imagem: imgEl.src })
            });
            const dados = await response.json();
            if (dados.sucesso && dados.texto) {
                texto = dados.texto;
                document.getElementById('txt-aluno').value = texto;
            } else {
                showToast('❌ ' + (dados.erro || 'Não foi possível ler a imagem'), 'error');
                return;
            }
        } catch (err) {
            showToast('❌ Erro ao processar imagem: ' + err.message, 'error');
            return;
        }
    }

    if (!texto || texto.trim().length < 5) {
        showToast('❌ Digite um texto, selecione uma foto ou cole o conteúdo!', 'error');
        return;
    }

    const etapas = [
        { nome: '📝 Preparando texto', descricao: 'Validando e preparando o texto para análise...' },
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

    if (!alunoId) {
        showToast('⚠️ Selecione o aluno antes de salvar!', 'error');
        return;
    }
    if (!texto || texto.trim().length < 5) {
        showToast('⚠️ Nenhum texto para salvar!', 'error');
        return;
    }
    if (!nota || nota === 0) {
        showToast('⚠️ Avalie o texto antes de salvar!', 'error');
        return;
    }

    showToast('💾 Salvando avaliação...', 'info');

    try {
        const response = await fetch(API_URL + '/api/salvar_correcao_texto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                aluno_id: parseInt(alunoId),
                prova_id: provaId ? parseInt(provaId) : null,
                texto: texto,
                nota: nota,
                metricas: metricas,
                feedback: feedback
            })
        });

        const dados = await response.json();

        if (dados.sucesso) {
            showToast(`✅ Avaliação salva! Aluno vinculado. Nota: ${nota.toFixed(1)}`, 'success');
        } else {
            showToast('❌ Erro ao salvar: ' + (dados.erro || 'Erro desconhecido'), 'error');
        }
    } catch (err) {
        console.error('Erro ao salvar avaliação:', err);
        showToast('❌ Erro ao salvar: ' + err.message, 'error');
    }
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
    } catch (erro) {
        console.error('Erro ao carregar escolas para texto:', erro);
    }
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

// ═══ CARTÕES RESPOSTA (LISTA POR TURMA) ═══
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
    const provaId = document.getElementById('lista-prova-select')?.value || '';

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
                    <p style="font-size:12px;color:var(--text3);">Cadastre uma prova para a série <strong>${escapeHtml(serieTurma || 'desta turma')}</strong></p>
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
            provasOptions += `<option value="${p.id}" ${selected}>${escapeHtml(p.titulo)} (${escapeHtml(p.disciplina || 'Sem disciplina')})</option>`;
        });

        let html = `
            <div style="text-align:center;padding:12px 0 18px;border-bottom:1px solid var(--border);margin-bottom:14px;">
                <div style="font-size:16px;font-weight:800;">${escapeHtml(escola?.nome || 'Escola')}</div>
                <div style="color:var(--text2);font-size:13px;margin-top:4px;">
                    Turma: ${escapeHtml(turma?.nome || '—')} | Série: ${escapeHtml(turma?.serie || '—')}
                </div>
                <div style="color:var(--text3);font-size:12px;margin-top:2px;">
                    Professor(a): ${escapeHtml(turma?.professor || '—')} | 
                    Turno: ${escapeHtml(turma?.turno || 'Manhã')} | 
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
                        <strong>${escapeHtml(aluno.nome)}</strong> 
                        <span class="badge badge-blue">Nº ${escapeHtml(aluno.numero_chamada || '—')}</span>
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

// ═══ USUÁRIOS ═══
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
                '<td>' +
                '<div class="btn-group">' +
                (isAdmin ? '<span style="font-size:10px;color:var(--text3);">Sistema</span>' : '<button class="btn btn-outline btn-sm" onclick="editarUsuario(' + u.id + ')">✏️</button><button class="btn-del" onclick="excluirUsuario(' + u.id + ', \'' + escapeAttr(u.username) + '\')">🗑️</button>') +
                '</div>' +
                '</td></tr>';
        }).join('');
    } catch (erro) { console.error('Erro ao carregar usuários:', erro); }
}

// ═══ MATRIZ DE PROFICIÊNCIA ═══
async function carregarMatrizes() {
    try {
        const response = await fetch(API_URL + '/api/matrizes');
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

function renderizarMatrizes(matrizes) {
    const tbody = document.getElementById('tb-matrizes');
    if (!tbody) return;

    if (!matrizes || matrizes.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text3);">Nenhuma matriz cadastrada.</td></tr>`;
        return;
    }

    let html = '';
    matrizes.forEach((matriz, index) => {
        let descritores = [];
        if (matriz.descritores) {
            if (Array.isArray(matriz.descritores)) descritores = matriz.descritores;
            else if (typeof matriz.descritores === 'string') {
                try { descritores = JSON.parse(matriz.descritores); } catch (e) { descritores = []; }
            } else if (typeof matriz.descritores === 'object') descritores = [matriz.descritores];
        }
        descritores = descritores.map(d => ({
            bncc: d.bncc || '',
            descritor: d.descritor || d.descricao || ''
        }));

        const totalDescritores = descritores.length;
        const nivelBadge = {
            'Básico': 'badge-nivel-basico',
            'Inicial': 'badge-nivel-inicial',
            'Intermediário': 'badge-nivel-intermediario',
            'Proficiente': 'badge-nivel-proficiente',
            'Avançado': 'badge-nivel-avancado'
        }[matriz.nivel] || 'badge-gray';

        let descritoresPreview = 'Nenhum descritor';
        if (totalDescritores > 0) {
            const previewText = descritores.map(d => `${d.bncc || ''}: ${d.descritor || ''}`).join('; ');
            descritoresPreview = `<span class="descritores-preview" title="${escapeAttr(previewText)}">${escapeHtml(previewText.substring(0, 60))}${previewText.length > 60 ? '...' : ''}</span>`;
        }

        html += `
            <tr>
                <td>${index + 1}</td>
                <td><strong>${escapeHtml(matriz.ano || '-')}</strong></td>
                <td>${escapeHtml(matriz.disciplina || '-')}</td>
                <td><span class="badge ${nivelBadge}">${escapeHtml(matriz.nivel || '-')}</span></td>
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

function atualizarTotalMatrizes(total) {
    const el = document.getElementById('total-matrizes');
    if (el) el.textContent = `${total} matrizes`;
}

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

function editarMatriz(id) {
    const matriz = matrizesData.find(m => m.id === id);
    if (!matriz) {
        toast('Matriz não encontrada', 'error');
        return;
    }

    matrizEditId = id;
    document.getElementById('matriz-modal-title').textContent = `✏️ Editar Matriz - ${escapeHtml(matriz.ano)} / ${escapeHtml(matriz.disciplina)}`;
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
                <label class="form-label">habilidades bncc</label>
                <input class="form-control" type="text" placeholder="Ex: EF01MA01" value="${escapeAttr(bnccValue)}">
            </div>
            <div class="form-group">
                <label class="form-label">Descritor</label>
                <textarea class="form-control" placeholder="Descreva a habilidade..." rows="4" style="resize:vertical; min-height:70px;">${escapeHtml(descritorValue)}</textarea>
            </div>
        </div>
    `;

    container.appendChild(item);
    item.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

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
            const bnccInput = item.querySelector('input.form-control');
            const descritorInput = item.querySelector('textarea.form-control');

            const bncc = bnccInput ? bnccInput.value.trim() : '';
            const descritor = descritorInput ? descritorInput.value.trim() : '';

            descritores.push({ bncc, descritor });
        });

        const editId = document.getElementById('matriz-edit-id').value;
        const url = editId ? `${API_URL}/api/matrizes/${editId}` : `${API_URL}/api/matrizes`;
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
        toast(result.mensagem || 'Matriz salva com sucesso!', 'success');

        fecharModalMatriz();
        await carregarMatrizes();

    } catch (error) {
        console.error('❌ Erro ao salvar matriz:', error);
        toast(error.message || 'Erro ao salvar matriz', 'error');
    }
}

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
        const response = await fetch(`${API_URL}/api/matrizes/${id}`, { method: 'DELETE' });

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

function fecharModalMatriz() {
    matrizEditId = null;
    closeM('m-matriz');
}

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

function visualizarMatriz(id) {
    const matriz = matrizesData.find(m => m.id === id);
    if (!matriz) {
        toast('Matriz não encontrada', 'error');
        return;
    }

    const descritores = (matriz.descritores || []).map(d => ({
        bncc: d.bncc || '',
        descritor: d.descritor || d.descricao || ''
    }));

    window.matrizVisualizando = { ...matriz, descritores: descritores };

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
                        <span style="font-size:11px;background:rgba(139,92,246,0.12);padding:2px 12px;border-radius:12px;color:var(--purple);font-weight:700;">BNCC: ${escapeHtml(bncc)}</span>
                    </div>
                    <div style="margin-top:6px;font-size:14px;color:var(--text);line-height:1.5; white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(desc)}</div>
                </div>
            `;
        });
        descritoresHtml += '</div>';
    }

    const nivelBadge = {
        'Básico': 'badge-nivel-basico',
        'Inicial': 'badge-nivel-inicial',
        'Intermediário': 'badge-nivel-intermediario',
        'Proficiente': 'badge-nivel-proficiente',
        'Avançado': 'badge-nivel-avancado'
    }[matriz.nivel] || 'badge-gray';

    conteudo.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
            <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;text-align:center;">
                <div style="font-size:11px;color:var(--text3);font-weight:600;">📚 ANO</div>
                <div style="font-size:18px;font-weight:800;color:var(--text);">${escapeHtml(matriz.ano || '—')}</div>
            </div>
            <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;text-align:center;">
                <div style="font-size:11px;color:var(--text3);font-weight:600;">📖 DISCIPLINA</div>
                <div style="font-size:18px;font-weight:800;color:var(--text);">${escapeHtml(matriz.disciplina || '—')}</div>
            </div>
            <div style="background:var(--bg2);border-radius:8px;padding:10px 14px;text-align:center;">
                <div style="font-size:11px;color:var(--text3);font-weight:600;">📊 NÍVEL</div>
                <div style="font-size:18px;font-weight:800;color:var(--text);"><span class="badge ${nivelBadge}">${escapeHtml(matriz.nivel || '—')}</span></div>
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

// ═══ FORMATAÇÃO ═══
function formatarData(dataStr) {
    if (!dataStr) return '-';
    try {
        const d = new Date(dataStr);
        return d.toLocaleDateString('pt-BR');
    } catch {
        return dataStr;
    }
}

function carregarMatrizesLocal() {
    const stored = localStorage.getItem('matrizes_data');
    if (stored) {
        try { return JSON.parse(stored); } catch { return []; }
    }
    return [];
}

// ═══ BOOT — DOMContentLoaded ═══
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

    if (document.getElementById('page-matriz')) {
        carregarMatrizes();
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

// ═══════════════════════════════════════════════════════════════
// 🔒 PROTEÇÃO DA TELA DE CONFIGURAÇÕES — SENHA DO ADMIN LOGADO
// ═══════════════════════════════════════════════════════════════

let tentativasSenhaConfig = 0;
let bloqueioSenhaAte = 0;

function getUsuarioLogado() {
    try {
        const local = localStorage.getItem('usuario') || localStorage.getItem('user') || localStorage.getItem('usuarioLogado');
        if (local) {
            try { return JSON.parse(local); } catch (e) {}
        }
        
        const session = sessionStorage.getItem('usuario') || sessionStorage.getItem('user');
        if (session) {
            try { return JSON.parse(session); } catch (e) {}
        }
        
        if (typeof usuarioLogado !== 'undefined' && usuarioLogado) return usuarioLogado;
        if (typeof currentUser !== 'undefined' && currentUser) return currentUser;
        if (typeof usuarioAtual !== 'undefined' && usuarioAtual) return usuarioAtual;
        
        const unameEl = document.getElementById('sb-uname');
        if (unameEl && unameEl.textContent.trim()) {
            return { username: unameEl.textContent.trim(), nome: unameEl.textContent.trim() };
        }
        
        return null;
    } catch (e) {
        console.warn('Erro ao buscar usuário logado:', e);
        return null;
    }
}

function pedirSenhaConfig() {
    if (Date.now() < bloqueioSenhaAte) {
        const seg = Math.ceil((bloqueioSenhaAte - Date.now()) / 1000);
        showToast(`⏳ Aguarde ${seg}s antes de tentar novamente`, 'error');
        return;
    }

    const input = document.getElementById('senha-config-input');
    const erroEl = document.getElementById('senha-config-erro');
    const loadingEl = document.getElementById('senha-config-loading');
    const btn = document.getElementById('btn-desbloquear-config');
    
    if (input) input.value = '';
    if (erroEl) erroEl.style.display = 'none';
    if (loadingEl) loadingEl.style.display = 'none';
    if (btn) { btn.disabled = false; btn.textContent = '🔓 Desbloquear'; }

    const modal = document.getElementById('m-senha-config');
    if (modal) {
        modal.classList.add('show');
        setTimeout(() => { if (input) input.focus(); }, 100);
    }
}

function cancelarSenhaConfig() {
    const modal = document.getElementById('m-senha-config');
    const input = document.getElementById('senha-config-input');
    const erroEl = document.getElementById('senha-config-erro');
    const loadingEl = document.getElementById('senha-config-loading');
    const btn = document.getElementById('btn-desbloquear-config');
    
    if (modal) modal.classList.remove('show');
    if (input) input.value = '';
    if (erroEl) erroEl.style.display = 'none';
    if (loadingEl) loadingEl.style.display = 'none';
    if (btn) { btn.disabled = false; btn.textContent = '🔓 Desbloquear'; }
}

async function validarSenhaConfig() {
    const input = document.getElementById('senha-config-input');
    const erroEl = document.getElementById('senha-config-erro');
    const loadingEl = document.getElementById('senha-config-loading');
    const btn = document.getElementById('btn-desbloquear-config');
    
    if (!input) return;
    const senhaDigitada = input.value.trim();
    
    if (!senhaDigitada) {
        if (erroEl) { erroEl.textContent = '⚠️ Digite a senha'; erroEl.style.display = 'block'; }
        return;
    }
    
    const usuario = getUsuarioLogado();
    if (!usuario || !usuario.username) {
        if (erroEl) {
            erroEl.textContent = '❌ Não foi possível identificar o usuário logado. Faça login novamente.';
            erroEl.style.display = 'block';
        }
        return;
    }
    
    if (erroEl) erroEl.style.display = 'none';
    if (loadingEl) loadingEl.style.display = 'block';
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Verificando...'; }
    
    try {
        const response = await fetch(`${API_URL}/api/verificar-senha-admin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: usuario.username,
                senha: senhaDigitada
            })
        });
        
        const data = await response.json();
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (btn) { btn.disabled = false; btn.textContent = '🔓 Desbloquear'; }
        
        if (data.ok) {
            tentativasSenhaConfig = 0;
            bloqueioSenhaAte = 0;
            cancelarSenhaConfig();
            go('config');
            
            document.querySelectorAll('.sb-item').forEach(el => el.classList.remove('active'));
            const menuConfig = document.getElementById('menu-config');
            if (menuConfig) menuConfig.classList.add('active');
            
            showToast('🔓 Acesso liberado', 'success');
        } else {
            tentativasSenhaConfig++;
            
            if (erroEl) {
                if (tentativasSenhaConfig >= 3) {
                    bloqueioSenhaAte = Date.now() + 30000;
                    erroEl.textContent = `🚫 Muitas tentativas erradas. Aguarde 30 segundos.`;
                    
                    setTimeout(() => {
                        const e = document.getElementById('senha-config-erro');
                        if (e) e.style.display = 'none';
                        tentativasSenhaConfig = 0;
                        bloqueioSenhaAte = 0;
                    }, 30000);
                } else {
                    erroEl.textContent = `❌ ${data.erro || 'Senha incorreta'} (${tentativasSenhaConfig}/3)`;
                }
                erroEl.style.display = 'block';
            }
            
            if (input) { input.value = ''; input.focus(); }
        }
    } catch (e) {
        console.error('Erro ao verificar senha:', e);
        if (loadingEl) loadingEl.style.display = 'none';
        if (btn) { btn.disabled = false; btn.textContent = '🔓 Desbloquear'; }
        if (erroEl) {
            erroEl.textContent = '❌ Erro de conexão. Tente novamente.';
            erroEl.style.display = 'block';
        }
    }
}
