// ============================================================
// IMPRESSAO.JS — PDFs, cartões resposta, impressões
// Extraído de script.js — Corte 7
// ============================================================

// ═══ IMPRIMIR ALUNOS ═══
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
            <strong>Escola:</strong> ${escapeHtml(escolaNome)} &nbsp;|&nbsp;
            <strong>Turma:</strong> ${escapeHtml(turmaNome)} &nbsp;|&nbsp;
            <strong>Série:</strong> ${escapeHtml(serieNome)}
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
                    <td>${escapeHtml(numero)}</td>
                    <td>${escapeHtml(matricula)}</td>
                    <td>${escapeHtml(nome)}</td>
                    <td>${escapeHtml(serie)}</td>
                    <td>${escapeHtml(turma)}</td>
                    <td>${escapeHtml(escola)}</td>
                    <td>${escapeHtml(dataNasc)}</td>
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

// ═══ EXPORTAR RELATÓRIO PDF ═══
function exportarRelatorioPDF() {
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

    const escolaSelect = document.getElementById('rel-turma-escola');
    const serieSelect = document.getElementById('rel-turma-serie');
    const turmaSelect = document.getElementById('rel-turma-turma');
    const provaSelect = document.getElementById('rel-turma-prova');

    const escolaNome = escolaSelect?.options[escolaSelect.selectedIndex]?.text || 'Não informado';
    const serieNome = serieSelect?.options[serieSelect.selectedIndex]?.text || 'Não informado';
    const turmaNome = turmaSelect?.options[turmaSelect.selectedIndex]?.text || 'Não informado';

    let disciplinaNome = 'Português';
    const provaOption = provaSelect?.options[provaSelect.selectedIndex];
    if (provaOption && provaOption.dataset.disciplina) {
        disciplinaNome = provaOption.dataset.disciplina;
    }

    const mediaEl = document.getElementById('rel-media');
    const media = mediaEl ? mediaEl.textContent : '0%';

    const conceitoEl = document.getElementById('rel-conceito-geral');
    const conceito = conceitoEl ? conceitoEl.textContent : '—';

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
                posicao, numero, nome, serie, acertos, erros,
                conceito: conceitoAluno, escola, turma
            });
        }
    });

    const totalAlunos = alunosData.length;

    const acertosPorQuestao = [];
    const acertosGrid = document.getElementById('rel-acertos-grid');

    if (acertosGrid) {
        const items = acertosGrid.querySelectorAll('.acertos-por-questao-item');

        items.forEach(item => {
            let qNum = '';
            const texto = item.textContent || '';
            const match = texto.match(/Q(\d+)/);
            if (match) qNum = 'Q' + match[1];

            let acertos = '0', erros = '0';
            const matchNum = texto.match(/(\d+)\s*\/\s*(\d+)/);
            if (matchNum) {
                acertos = matchNum[1] || '0';
                erros = matchNum[2] || '0';
            }

            let bncc = 'N/A';
            const matchBncc = texto.match(/(EF\d+[A-Z]+\d+)/);
            if (matchBncc) bncc = matchBncc[1];

            let pctAcertos = '0%', pctErros = '0%';
            const matchPct = texto.match(/(\d+)%\s*[|]\s*(\d+)%/);
            if (matchPct) {
                pctAcertos = matchPct[1] + '%';
                pctErros = matchPct[2] + '%';
            }

            if (qNum) {
                acertosPorQuestao.push({
                    numero: qNum, acertos, erros,
                    total: parseInt(acertos) + parseInt(erros),
                    bncc, pctAcertos, pctErros
                });
            }
        });
    }

    const totalQuestoesGeral = totalAcertosGeral + totalErrosGeral;
    const mediaCalculada = totalQuestoesGeral > 0 && totalAlunos > 0 ?
        Math.round((totalAcertosGeral / (totalAlunos * (totalQuestoesGeral / totalAlunos))) * 100) : 0;

    const dataAtual = new Date().toLocaleString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });

    let html = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Relatório por Turma - ${escapeHtml(disciplinaNome)}</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Arial, sans-serif; background: #ffffff; padding: 20px; color: #1e293b; }
            .header { border-bottom: 3px solid #1e293b; padding-bottom: 16px; margin-bottom: 20px; }
            .header-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; flex-wrap: wrap; gap: 10px; }
            .header-left { display: flex; align-items: center; gap: 12px; }
            .header-left .instituicao { display: flex; flex-direction: column; }
            .header-left .instituicao .prefeitura { font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; }
            .header-left .instituicao .secretaria { font-size: 13px; font-weight: 800; color: #1e293b; letter-spacing: 0.3px; }
            .header-left .instituicao .departamento { font-size: 10px; color: #475569; font-weight: 600; }
            .header-left .instituicao .sisam { font-size: 14px; font-weight: 900; color: #2563eb; letter-spacing: 0.5px; }
            .header-right { text-align: right; border-left: 2px solid #e2e8f0; padding-left: 16px; }
            .header-right .titulo-relatorio { font-size: 18px; font-weight: 800; color: #1e293b; letter-spacing: 0.3px; }
            .header-right .subtitulo-relatorio { font-size: 11px; color: #475569; font-weight: 600; }
            .info-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px 16px; background: #f8fafc; padding: 12px 20px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 16px; }
            .info-grid .item { display: flex; flex-direction: column; }
            .info-grid .item .label { font-size: 8px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
            .info-grid .item .value { font-size: 12px; font-weight: 700; color: #0f172a; margin-top: 1px; }
            .section-title { font-size: 14px; font-weight: 800; color: #1e293b; margin: 16px 0 10px; }
            .questoes-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 12px; }
            .questao-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; text-align: center; }
            .questao-card .q-num { font-size: 13px; font-weight: 800; color: #1e293b; margin-bottom: 4px; background: #e2e8f0; display: inline-block; padding: 0 12px; border-radius: 8px; }
            .questao-card .q-result { display: flex; justify-content: center; align-items: center; gap: 6px; font-size: 15px; font-weight: 700; margin: 4px 0; }
            .questao-card .q-result .acertos { color: #10b981; }
            .questao-card .q-result .erros { color: #ef4444; }
            .questao-card .q-bncc { font-size: 10px; font-weight: 700; color: #8b5cf6; background: #f5f3ff; padding: 3px 12px; border-radius: 8px; display: inline-block; font-family: 'Courier New', monospace; }
            .resumo-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0 16px; }
            .resumo-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; text-align: center; }
            .resumo-card .valor { font-size: 24px; font-weight: 900; }
            .resumo-card .valor.green { color: #10b981; }
            .resumo-card .valor.red { color: #ef4444; }
            .resumo-card .valor.blue { color: #3b82f6; }
            .resumo-card .valor.purple { color: #8b5cf6; }
            .resumo-card .label { font-size: 9px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; margin-top: 2px; }
            .table-wrap { overflow-x: auto; margin: 12px 0; border: 1px solid #e2e8f0; border-radius: 8px; }
            table { width: 100%; border-collapse: collapse; font-size: 10px; }
            thead { background: #f1f5f9; }
            th { padding: 8px 6px; text-align: center; font-weight: 700; color: #475569; border-bottom: 2px solid #e2e8f0; font-size: 8px; text-transform: uppercase; }
            td { padding: 6px 4px; border-bottom: 1px solid #f1f5f9; text-align: center; font-size: 9px; color: #1e293b; }
            tr:nth-child(even) td { background: #fafbfc; }
            .nome-aluno { font-weight: 600; text-align: left; padding-left: 8px; }
            .badge-conceito { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 8px; font-weight: 700; text-transform: uppercase; }
            .badge-inicial { background: #fef2f2; color: #ef4444; }
            .badge-basico { background: #fffbeb; color: #f59e0b; }
            .badge-proficiente { background: #eff6ff; color: #3b82f6; }
            .badge-avancado { background: #ecfdf5; color: #10b981; }
            .acertos-cell { color: #10b981; font-weight: 700; }
            .erros-cell { color: #ef4444; font-weight: 700; }
            .assinaturas { display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center; }
            .assinatura-item { display: flex; flex-direction: column; align-items: center; }
            .assinatura-item .linha { width: 180px; border-bottom: 1.5px solid #1e293b; margin-bottom: 4px; }
            .assinatura-item .cargo { font-size: 9px; color: #64748b; font-weight: 600; }
            .footer { margin-top: 20px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 8px; color: #94a3b8; flex-wrap: wrap; }
            @media print { body { padding: 10px; } @page { size: A4 landscape; margin: 8mm 6mm; } }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-top">
                <div class="header-left">
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
                    <div class="subtitulo-relatorio">Desempenho dos alunos - ${escapeHtml(disciplinaNome)}</div>
                </div>
            </div>
        </div>

        <div class="info-grid">
            <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escolaNome)}</span></div>
            <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${escapeHtml(serieNome)}</span></div>
            <div class="item"><span class="label">📖 DISCIPLINA</span><span class="value">${escapeHtml(disciplinaNome)}</span></div>
            <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml(turmaNome)}</span></div>
            <div class="item"><span class="label">📅 DATA</span><span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
            <div class="item"><span class="label">📊 BIMESTRE</span><span class="value">1º e 2º bimestre</span></div>
        </div>

        <div class="section-title">📊 Acertos por Questão — ${escapeHtml(disciplinaNome)} (${totalAlunos} alunos)</div>

        <div class="questoes-grid">
            ${acertosPorQuestao.length > 0 ? acertosPorQuestao.map(q => {
                return `
                    <div class="questao-card">
                        <div class="q-num">${escapeHtml(q.numero)}</div>
                        <div class="q-result">
                            <span class="acertos">${escapeHtml(q.acertos)}</span>
                            <span class="divider">/</span>
                            <span class="erros">${escapeHtml(q.erros)}</span>
                        </div>
                        <div class="q-bncc">${escapeHtml(q.bncc)}</div>
                    </div>
                `;
            }).join('') : '<div style="grid-column:1/-1;text-align:center;padding:20px;color:#94a3b8;">Nenhum dado disponível.</div>'}
        </div>

        <div class="resumo-grid">
            <div class="resumo-card"><div class="valor green">${totalAcertosGeral}</div><div class="label">✅ Total de Acertos</div></div>
            <div class="resumo-card"><div class="valor red">${totalErrosGeral}</div><div class="label">❌ Total de Erros</div></div>
            <div class="resumo-card"><div class="valor blue">${escapeHtml(media || mediaCalculada + '%')}</div><div class="label">📊 Média da Turma</div></div>
            <div class="resumo-card"><div class="valor purple">${escapeHtml(conceito)}</div><div class="label">📊 Conceito</div></div>
        </div>

        <div class="section-title">📋 Lista de Alunos (${totalAlunos} alunos)</div>

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
                        const conceitoClass = a.conceito ? `badge-${a.conceito.toLowerCase()}` : 'badge-inicial';
                        return `
                            <tr>
                                <td>${escapeHtml(a.posicao)}</td>
                                <td>${escapeHtml(a.numero)}</td>
                                <td class="nome-aluno">${escapeHtml(a.nome)}</td>
                                <td>${escapeHtml(a.serie)}</td>
                                <td class="acertos-cell">${a.acertos}</td>
                                <td class="erros-cell">${a.erros}</td>
                                <td><span class="badge-conceito ${conceitoClass}">${escapeHtml(a.conceito || '—')}</span></td>
                                <td>${escapeHtml(a.escola)}</td>
                                <td>${escapeHtml(a.turma)}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>

        <div class="assinaturas">
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Professor(a) Responsável</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Diretor(a)</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Secretaria Municipal de Educação</div></div>
        </div>

        <div class="footer">
            <span>📄 Documento gerado pelo sistema <strong>CorrigePro</strong></span>
            <span>${dataAtual}</span>
        </div>
    </body>
    </html>
    `;

    const win = window.open('', '_blank');
    if (!win) {
        showToast('⚠️ Permita pop-ups para gerar o PDF.', 'error');
        return;
    }

    win.document.write(html);
    win.document.close();
    win.onload = function() {
        setTimeout(() => { win.focus(); win.print(); }, 500);
    };
    showToast('📄 PDF gerado com sucesso!', 'success');
}

// ═══ IMPRIMIR RESULTADOS MELHORADOS ═══
function imprimirResultadosMelhorados() {
    const tbody = document.getElementById('tb-resultados-filtrado');
    if (!tbody) {
        showToast('❌ Nenhuma tabela encontrada.', 'error');
        return;
    }

    const rows = tbody.querySelectorAll('tr');
    if (rows.length === 0 || (rows.length === 1 && rows[0].textContent.includes('Carregando'))) {
        showToast('⚠️ Nenhum resultado para imprimir. Aplique filtros primeiro.', 'error');
        return;
    }

    const escolaSelect = document.getElementById('filtro-escola');
    const serieSelect = document.getElementById('filtro-serie');
    const turmaSelect = document.getElementById('filtro-turma');
    const provaSelect = document.getElementById('filtro-prova');

    const escolaNome = escolaSelect?.options[escolaSelect.selectedIndex]?.text || 'Todas';
    const serieNome = serieSelect?.options[serieSelect.selectedIndex]?.text || 'Todas';
    const turmaNome = turmaSelect?.options[turmaSelect.selectedIndex]?.text || 'Todas';
    const provaNome = provaSelect?.options[provaSelect.selectedIndex]?.text || 'Todas';

    const conceitoInicial = document.getElementById('conceito-inicial-count')?.textContent || '0';
    const conceitoBasico = document.getElementById('conceito-basico-count')?.textContent || '0';
    const conceitoProficiente = document.getElementById('conceito-proficiente-count')?.textContent || '0';
    const conceitoAvancado = document.getElementById('conceito-avancado-count')?.textContent || '0';
    const totalAlunos = document.getElementById('total-alunos-tabela')?.textContent || '0 alunos';

    const alunosData = [];
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 19) {
            alunosData.push({
                posicao: cells[0].textContent.trim(),
                numero: cells[1].textContent.trim(),
                nome: cells[2].textContent.trim(),
                serie: cells[3].textContent.trim(),
                ptAcertos: cells[4].textContent.trim(),
                ptErros: cells[5].textContent.trim(),
                ptConceito: cells[6].textContent.trim(),
                matAcertos: cells[7].textContent.trim(),
                matErros: cells[8].textContent.trim(),
                matConceito: cells[9].textContent.trim(),
                prodNota: cells[10].textContent.trim().replace('NOTA', '').trim(),
                chAcertos: cells[11].textContent.trim(),
                chErros: cells[12].textContent.trim(),
                chConceito: cells[13].textContent.trim(),
                cnAcertos: cells[14].textContent.trim(),
                cnErros: cells[15].textContent.trim(),
                cnConceito: cells[16].textContent.trim(),
                escola: cells[17].textContent.trim(),
                turma: cells[18].textContent.trim()
            });
        }
    });

    const dataAtual = new Date().toLocaleString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });

    const html = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Resultados — Relatório</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #fff; color: #1e293b; }
            .header { border-bottom: 3px solid #1e293b; padding-bottom: 15px; margin-bottom: 20px; }
            .header-top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
            .header-left .prefeitura { font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; }
            .header-left .secretaria { font-size: 13px; font-weight: 800; color: #1e293b; }
            .header-left .departamento { font-size: 10px; color: #475569; font-weight: 600; }
            .header-left .sisam { font-size: 14px; font-weight: 900; color: #2563eb; }
            .header-right { text-align: right; border-left: 2px solid #e2e8f0; padding-left: 16px; }
            .header-right .titulo { font-size: 18px; font-weight: 800; color: #1e293b; }
            .header-right .sub { font-size: 11px; color: #475569; font-weight: 600; }
            .info-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; background: #f8fafc; padding: 12px 16px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 16px; }
            .info-grid .item .label { font-size: 8px; color: #94a3b8; font-weight: 700; text-transform: uppercase; }
            .info-grid .item .value { font-size: 11px; font-weight: 700; color: #0f172a; margin-top: 1px; }
            .conceitos { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }
            .conceito-card { padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #e2e8f0; }
            .conceito-card .valor { font-size: 22px; font-weight: 900; }
            .conceito-card .label { font-size: 9px; color: #64748b; font-weight: 700; text-transform: uppercase; }
            .ci { background: #fef2f2; border-color: #fecaca; } .ci .valor { color: #ef4444; }
            .cb { background: #fffbeb; border-color: #fde68a; } .cb .valor { color: #f59e0b; }
            .cp { background: #eff6ff; border-color: #bfdbfe; } .cp .valor { color: #3b82f6; }
            .ca { background: #ecfdf5; border-color: #a7f3d0; } .ca .valor { color: #10b981; }
            .table-wrap { overflow-x: auto; border-radius: 8px; border: 1px solid #e2e8f0; }
            table { width: 100%; border-collapse: collapse; font-size: 8px; }
            thead { background: #f1f5f9; }
            th { padding: 6px 3px; text-align: center; font-weight: 700; color: #475569; border-bottom: 2px solid #e2e8f0; font-size: 7px; text-transform: uppercase; }
            td { padding: 4px 3px; border-bottom: 1px solid #f1f5f9; text-align: center; font-size: 8px; }
            tr:nth-child(even) td { background: #fafbfc; }
            .nome-aluno { font-weight: 600; text-align: left; padding-left: 6px; }
            .nota-prod { font-weight: 900; color: #8b5cf6; font-size: 11px; }
            .footer { margin-top: 20px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 8px; color: #94a3b8; }
            @media print { body { padding: 10px; } @page { size: A4 landscape; margin: 8mm 5mm; } }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-top">
                <div class="header-left">
                    <div class="prefeitura">PREFEITURA MUNICIPAL DE</div>
                    <div class="secretaria">SÃO SEBASTIÃO DA BOA VISTA</div>
                    <div class="departamento">SECRETARIA MUNICIPAL DE EDUCAÇÃO — DGP</div>
                    <div class="sisam">SISAM 2026</div>
                </div>
                <div class="header-right">
                    <div class="titulo">🏆 RELATÓRIO DE RESULTADOS</div>
                    <div class="sub">Acertos, erros e conceitos por disciplina</div>
                </div>
            </div>
        </div>

        <div class="info-grid">
            <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escolaNome}</span></div>
            <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${serieNome}</span></div>
            <div class="item"><span class="label">👥 TURMA</span><span class="value">${turmaNome}</span></div>
            <div class="item"><span class="label">📄 PROVA</span><span class="value">${provaNome}</span></div>
            <div class="item"><span class="label">📅 DATA</span><span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
        </div>

        <div style="font-size:12px; font-weight:700; margin-bottom:8px;">
            📊 Distribuição por Conceito — <span style="color:#3b82f6;">${totalAlunos}</span>
        </div>

        <div class="conceitos">
            <div class="conceito-card ci"><div class="valor">${conceitoInicial}</div><div class="label">🔴 Inicial</div></div>
            <div class="conceito-card cb"><div class="valor">${conceitoBasico}</div><div class="label">🟠 Básico</div></div>
            <div class="conceito-card cp"><div class="valor">${conceitoProficiente}</div><div class="label">🔵 Proficiente</div></div>
            <div class="conceito-card ca"><div class="valor">${conceitoAvancado}</div><div class="label">🟢 Avançado</div></div>
        </div>

        <div style="font-size:12px; font-weight:700; margin-bottom:6px;">📋 Lista de Alunos</div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th rowspan="2">Pos.</th>
                        <th rowspan="2">Nº</th>
                        <th rowspan="2" style="text-align:left;">Nome</th>
                        <th rowspan="2">Série</th>
                        <th colspan="3" style="background:#eff6ff;">Português</th>
                        <th colspan="3" style="background:#ecfdf5;">Matemática</th>
                        <th colspan="1" style="background:#f5f3ff;">Produção</th>
                        <th colspan="3" style="background:#fffbeb;">CH</th>
                        <th colspan="3" style="background:#f0fdfa;">CN</th>
                        <th rowspan="2">Escola</th>
                        <th rowspan="2">Turma</th>
                    </tr>
                    <tr>
                        <th style="font-size:6px;">Acertos</th>
                        <th style="font-size:6px;">Erros</th>
                        <th style="font-size:6px;">Conceito</th>
                        <th style="font-size:6px;">Acertos</th>
                        <th style="font-size:6px;">Erros</th>
                        <th style="font-size:6px;">Conceito</th>
                        <th style="font-size:6px;">NOTA</th>
                        <th style="font-size:6px;">Acertos</th>
                        <th style="font-size:6px;">Erros</th>
                        <th style="font-size:6px;">Conceito</th>
                        <th style="font-size:6px;">Acertos</th>
                        <th style="font-size:6px;">Erros</th>
                        <th style="font-size:6px;">Conceito</th>
                    </tr>
                </thead>
                <tbody>
                    ${alunosData.map(a => `
                        <tr>
                            <td>${a.posicao}</td>
                            <td>${a.numero}</td>
                            <td class="nome-aluno">${a.nome}</td>
                            <td>${a.serie}</td>
                            <td>${a.ptAcertos}</td>
                            <td>${a.ptErros}</td>
                            <td>${a.ptConceito}</td>
                            <td>${a.matAcertos}</td>
                            <td>${a.matErros}</td>
                            <td>${a.matConceito}</td>
                            <td class="nota-prod">${a.prodNota}</td>
                            <td>${a.chAcertos}</td>
                            <td>${a.chErros}</td>
                            <td>${a.chConceito}</td>
                            <td>${a.cnAcertos}</td>
                            <td>${a.cnErros}</td>
                            <td>${a.cnConceito}</td>
                            <td>${a.escola}</td>
                            <td>${a.turma}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>

        <div class="footer">
            <span>📄 Documento gerado pelo sistema <strong>CorrigePro</strong></span>
            <span>${dataAtual}</span>
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
    win.onload = () => {
        setTimeout(() => { win.focus(); win.print(); }, 500);
    };
    showToast('📄 Relatório gerado!', 'success');
}

// ═══ GERAR CARTÃO RESPOSTA ═══
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

        const response = await fetch(`${API_URL}/api/gerar_gabarito`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                escola_id: parseInt(escolaId),
                turma_id: parseInt(turmaId),
                aluno_id: parseInt(alunoId),
                prova_id: parseInt(provaId)
            })
        });

        if (!response.ok) {
            throw new Error(`Erro ${response.status} ao gerar cartão`);
        }

        const htmlCartao = await response.text();

        novaAba.document.open();
        novaAba.document.write(htmlCartao);
        novaAba.document.close();

        showToast('✅ Cartão resposta gerado com sucesso!', 'success');

    } catch (erro) {
        console.error('Erro ao gerar cartão:', erro);
        showToast('❌ Erro ao gerar cartão: ' + erro.message, 'error');
    }
}

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

// ═══ GERAR DOCUMENTO DE DESEMPENHO (DISPATCHER) ═══
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

    const isProducao = (data.disciplina === 'Produção de Texto');

    if (isProducao) {
        gerarDocumentoProducao(data);
    } else {
        gerarDocumentoNormal(data);
    }
}

// ═══ PDF — DISCIPLINAS NORMAIS ═══
function gerarDocumentoNormal(data) {
    const btn = document.getElementById('btnGerarDocumento');
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

        let html = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Relatório de Desempenho - ${escapeHtml(aluno.nome)}</title>
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
                <h2>${escapeHtml(prova.titulo || 'Prova')}</h2>
                <div class="sub">${escapeHtml(disciplina)}</div>
            </div>

            <div class="info-grid">
                <div class="item"><span class="label">🏫 Escola:</span> <span class="value">${escapeHtml(escola.nome || '—')}</span></div>
                <div class="item"><span class="label">👥 Turma:</span> <span class="value">${escapeHtml((turma.nome || '') + ' - ' + (turma.serie || ''))}</span></div>
                <div class="item"><span class="label">🎒 Aluno:</span> <span class="value">${escapeHtml(aluno.nome || '—')}</span></div>
                <div class="item"><span class="label">📄 Prova:</span> <span class="value">${escapeHtml(prova.titulo || '—')}</span></div>
                <div class="item"><span class="label">📅 Data:</span> <span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
            </div>

            <div class="resumo">
                <div class="card"><div class="valor blue">${porcentagem}%</div><div class="label">Porcentagem de Acertos</div></div>
                <div class="card"><div class="valor green">${acertos}</div><div class="label">Acertos</div></div>
                <div class="card"><div class="valor red">${erros}</div><div class="label">Erros</div></div>
                <div class="card"><div class="valor purple">${escapeHtml(conceito)}</div><div class="label">Conceito</div></div>
            </div>

            <h3 style="margin: 20px 0 10px;">📖 ${escapeHtml(disciplina)}</h3>
            <div class="questoes-grid">
        `;

        resultadoQuestoes.forEach(q => {
            const acertou = q.acertou;
            const resposta = q.resposta || '—';
            const gab = q.gabarito || '—';
            html += `
                <div class="questao-item ${acertou ? 'acertou' : (q.respondida ? 'errou' : '')}">
                    <div class="q-num">Q${q.numero}</div>
                    <div class="q-resp">${escapeHtml(resposta)}</div>
                    <div class="q-gab">${escapeHtml(gab)}</div>
                    <span class="q-status-text">${acertou ? '✅' : (q.respondida ? '❌' : '—')}</span>
                    ${q.bncc ? `<div style="font-size:6px; color:#8b5cf6; margin-top:2px;">BNCC: ${escapeHtml(q.bncc)}</div>` : ''}
                </div>
            `;
        });

        html += `
            </div>

            <h3 style="margin: 20px 0 10px;">📋 Gabarito Oficial</h3>
            <div class="gabarito-grid">
        `;

        gabarito.forEach((gab, idx) => {
            const codigoBncc = (idx < bncc.length) ? bncc[idx] : '';
            html += `
                <div class="gabarito-item">
                    <div class="q-num">Q${idx+1}</div>
                    <div class="q-resp">${escapeHtml(gab || '—')}</div>
                    ${codigoBncc ? `<div style="font-size:6px; color:#8b5cf6; margin-top:2px;">BNCC: ${escapeHtml(codigoBncc)}</div>` : ''}
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

// ═══ PDF — PRODUÇÃO DE TEXTO ═══
function gerarDocumentoProducao(data) {
    const btn = document.getElementById('btnGerarDocumento');
    try {
        const win = window.open('', '_blank');
        if (!win) {
            showToast('⚠️ Permita pop-ups para gerar o documento!', 'error');
            gerandoDocumento = false;
            btn.disabled = false;
            btn.textContent = '📄 GERAR DOCUMENTO';
            return;
        }

        const {
            escola, turma, aluno, prova, resultadoQuestoes,
            disciplina, notaProducao, conceito,
            questoesStatusHistorico, textosQuestoes
        } = data;

        const dataAtual = new Date().toLocaleString('pt-BR');

        let questoesHTML = '';

        resultadoQuestoes.forEach((q, i) => {
            const statusSalvo = (questoesStatusHistorico && questoesStatusHistorico[i]) || {};
            const situacao = statusSalvo.situacao || '';
            const observacao = statusSalvo.resposta || statusSalvo.observacao || '';
            const tq = (textosQuestoes && textosQuestoes[i]) || {};
            const titulo = (tq.titulo) ? tq.titulo : `Q${q.numero}`;
            const cabecalho = (tq.cabecalho) ? tq.cabecalho : '';
            const headerTexto = cabecalho ? `${titulo} — ${cabecalho}` : titulo;

            const gab = q.gabarito || '';
            let alternativasHTML = '';

            if (gab && gab.trim() !== '' && gab !== '—') {
                const blocos = gab.split(/\n(?=[A-Z]\))/);
                blocos.forEach(bloco => {
                    const m = bloco.match(/^([A-Z])\)\s*([\s\S]*)$/);
                    if (m) {
                        alternativasHTML += `
                            <div class="prod-alt">
                                <span class="prod-alt-letra">${escapeHtml(m[1])}</span>
                                <span class="prod-alt-texto">${escapeHtml(m[2].trim())}</span>
                            </div>
                        `;
                    } else if (bloco.trim()) {
                        alternativasHTML += `<div class="prod-alt"><span class="prod-alt-texto">${escapeHtml(bloco.trim())}</span></div>`;
                    }
                });
            } else {
                alternativasHTML = '<div style="font-size:10px;color:#94a3b8;font-style:italic;">Sem gabarito cadastrado</div>';
            }

            questoesHTML += `
                <div class="prod-questao">
                    <div class="prod-questao-titulo">${escapeHtml(headerTexto)}</div>

                    <div class="prod-label">📋 Gabarito</div>
                    <div class="prod-alternativas">${alternativasHTML}</div>

                    <div class="prod-label">✍️ Observação do Professor</div>
                    <div class="prod-observacao">${escapeHtml(observacao || '—')}</div>

                    <div class="prod-situacao-wrapper">
                        <span class="prod-label" style="margin:0;">📊 Situação de Correção:</span>
                        <span class="prod-situacao">${escapeHtml(situacao || '—')}</span>
                    </div>
                </div>
            `;
        });

        const html = `
            <!DOCTYPE html>
            <html lang="pt-BR">
            <head>
                <meta charset="UTF-8">
                <title>Relatório de Desempenho — ${escapeHtml(aluno.nome)}</title>
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body { font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #fff; color: #1e293b; }

                    .header { border-bottom: 3px solid #1e293b; padding-bottom: 15px; margin-bottom: 20px; }
                    .header-top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
                    .header-left .prefeitura { font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; }
                    .header-left .secretaria { font-size: 13px; font-weight: 800; color: #1e293b; letter-spacing: 0.3px; }
                    .header-left .departamento { font-size: 10px; color: #475569; font-weight: 600; }
                    .header-left .sisam { font-size: 14px; font-weight: 900; color: #2563eb; letter-spacing: 0.5px; }
                    .header-right { text-align: right; border-left: 2px solid #e2e8f0; padding-left: 16px; }
                    .header-right .titulo { font-size: 18px; font-weight: 800; color: #1e293b; letter-spacing: 0.3px; }
                    .header-right .sub { font-size: 11px; color: #475569; font-weight: 600; }

                    .info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 20px; background: #f8fafc; padding: 12px 20px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 16px; }
                    .info-grid .item { display: flex; flex-direction: column; }
                    .info-grid .item .label { font-size: 8px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
                    .info-grid .item .value { font-size: 12px; font-weight: 700; color: #0f172a; margin-top: 2px; }

                    .prod-nota-final {
                        background: linear-gradient(135deg, #f5f3ff, #ede9fe);
                        border: 2px solid #8b5cf6;
                        border-radius: 10px;
                        padding: 16px;
                        text-align: center;
                        margin: 16px 0;
                    }
                    .prod-nota-valor { font-size: 44px; font-weight: 900; color: #8b5cf6; line-height: 1; }
                    .prod-nota-label { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-top: 6px; letter-spacing: 0.3px; }

                    .section-title { font-size: 14px; font-weight: 800; color: #1e293b; margin: 18px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; }

                    .prod-questao {
                        background: #f8fafc;
                        border: 1px solid #e2e8f0;
                        border-left: 4px solid #8b5cf6;
                        border-radius: 8px;
                        padding: 12px 14px;
                        margin-bottom: 12px;
                        page-break-inside: avoid;
                        break-inside: avoid;
                    }
                    .prod-questao-titulo {
                        font-size: 12px;
                        font-weight: 800;
                        color: #8b5cf6;
                        margin-bottom: 8px;
                        padding-bottom: 6px;
                        border-bottom: 1px dashed #cbd5e1;
                    }
                    .prod-label {
                        font-size: 9px;
                        font-weight: 700;
                        color: #64748b;
                        text-transform: uppercase;
                        letter-spacing: 0.4px;
                        margin-bottom: 4px;
                        margin-top: 8px;
                        display: block;
                    }

                    .prod-alternativas {
                        display: flex;
                        gap: 10px;
                        flex-wrap: wrap;
                        margin-bottom: 4px;
                    }
                    .prod-alt {
                        flex: 1;
                        min-width: 200px;
                        background: #fff;
                        border: 1px solid #e2e8f0;
                        border-radius: 6px;
                        padding: 8px 10px;
                        display: flex;
                        gap: 8px;
                        align-items: flex-start;
                    }
                    .prod-alt-letra {
                        flex: 0 0 22px;
                        height: 22px;
                        border-radius: 50%;
                        background: linear-gradient(135deg, #8b5cf6, #6d28d9);
                        color: #fff;
                        font-weight: 900;
                        font-size: 11px;
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                    }
                    .prod-alt-texto {
                        flex: 1;
                        font-size: 10px;
                        color: #1e293b;
                        line-height: 1.4;
                    }

                    .prod-observacao {
                        background: #fff;
                        border: 1px solid #e2e8f0;
                        border-radius: 6px;
                        padding: 8px 10px;
                        font-size: 10px;
                        color: #1e293b;
                        line-height: 1.5;
                        min-height: 32px;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }

                    .prod-situacao-wrapper {
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        margin-top: 10px;
                        padding-top: 8px;
                        border-top: 1px dashed #e2e8f0;
                    }
                    .prod-situacao-wrapper .prod-label {
                        margin: 0;
                        display: inline;
                    }
                    .prod-situacao {
                        display: inline-block;
                        background: #ede9fe;
                        color: #6d28d9;
                        border: 1px solid #c4b5fd;
                        padding: 3px 14px;
                        border-radius: 20px;
                        font-weight: 900;
                        font-size: 12px;
                        line-height: 1.2;
                    }

                    .footer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; flex-wrap: wrap; gap: 8px; }

                    @media print {
                        body { padding: 12px; }
                        @page { size: A4 portrait; margin: 8mm; }
                    }
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="header-top">
                        <div class="header-left">
                            <div class="prefeitura">PREFEITURA MUNICIPAL DE</div>
                            <div class="secretaria">SÃO SEBASTIÃO DA BOA VISTA</div>
                            <div class="departamento">SECRETARIA MUNICIPAL DE EDUCAÇÃO — DGP</div>
                            <div class="sisam">SISAM 2026</div>
                        </div>
                        <div class="header-right">
                            <div class="titulo">📊 RELATÓRIO DE DESEMPENHO</div>
                            <div class="sub">${escapeHtml(disciplina)}</div>
                        </div>
                    </div>
                </div>

                <div class="info-grid">
                    <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escola.nome || '—')}</span></div>
                    <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml((turma.nome || '') + ' - ' + (turma.serie || ''))}</span></div>
                    <div class="item"><span class="label">🎒 ALUNO</span><span class="value">${escapeHtml(aluno.nome || '—')}</span></div>
                    <div class="item"><span class="label">📄 PROVA</span><span class="value">${escapeHtml(prova.titulo || '—')}</span></div>
                    <div class="item"><span class="label">📅 DATA</span><span class="value">${new Date().toLocaleDateString('pt-BR')}</span></div>
                    <div class="item"><span class="label">📚 DISCIPLINA</span><span class="value">${escapeHtml(disciplina)}</span></div>
                </div>

                <div class="prod-nota-final">
                    <div class="prod-nota-valor">${notaProducao.toFixed(1)}</div>
                    <div class="prod-nota-label">⭐ NOTA FINAL — PRODUÇÃO DE TEXTO</div>
                    <div style="margin-top:10px;padding-top:10px;border-top:1px dashed #c4b5fd;display:flex;justify-content:center;align-items:center;gap:8px;">
                        <span style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.3px;">Conceito:</span>
                        <span style="display:inline-block;padding:4px 16px;border-radius:20px;font-weight:900;font-size:13px;background:#ede9fe;color:#6d28d9;border:1px solid #c4b5fd;">${escapeHtml(conceito || '—')}</span>
                    </div>
                </div>

                <div class="section-title">📝 Questões Avaliadas (${resultadoQuestoes.length})</div>
                ${questoesHTML}

                <div class="footer">
                    <span>📄 Documento gerado pelo sistema <strong>CorrigePro</strong></span>
                    <span>${dataAtual}</span>
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

// ═══ IMPRIMIR MATRIZ ═══
function imprimirMatrizVisualizada() {
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

    const descritores = (matriz.descritores || []).map(d => ({
        bncc: d.bncc || '',
        descritor: d.descritor || d.descricao || ''
    }));

    const nivel = matriz.nivel || '—';
    const ano = matriz.ano || '—';
    const disciplina = matriz.disciplina || '—';

    const linhas = [];
    descritores.forEach((d) => {
        const bnccs = d.bncc.split(/\s*-\s*/).filter(b => b.trim() !== '');
        if (bnccs.length > 1) {
            bnccs.forEach(bncc => {
                linhas.push({ bncc: bncc.trim(), descritor: d.descritor });
            });
        } else {
            linhas.push({ bncc: d.bncc, descritor: d.descritor });
        }
    });

    let descritoresHtml = '';
    if (linhas.length === 0) {
        descritoresHtml = '<p style="color:#94a3b8;text-align:center;padding:16px;">Nenhuma habilidade cadastrada.</p>';
    } else {
        descritoresHtml = `
            <table style="width:100%; border-collapse:collapse; margin-top:8px; font-size:13px;">
                <thead>
                    <tr style="background:#f1f5f9; border-bottom:2px solid #2563eb;">
                        <th style="padding:8px 12px; text-align:left; font-weight:700; color:#1e293b; width:25%;">📌 HABILIDADE BNCC</th>
                        <th style="padding:8px 12px; text-align:left; font-weight:700; color:#1e293b; width:75%;">📝 DESCRITORES</th>
                    </tr>
                </thead>
                <tbody>
        `;
        linhas.forEach((linha, idx) => {
            const bncc = linha.bncc || '—';
            const desc = linha.descritor || '—';
            const bgColor = idx % 2 === 0 ? '#ffffff' : '#f8fafc';
            descritoresHtml += `
                <tr style="background:${bgColor}; border-bottom:1px solid #e2e8f0;">
                    <td style="padding:8px 12px; font-weight:600; color:#8b5cf6; vertical-align:top;">${escapeHtml(bncc)}</td>
                    <td style="padding:8px 12px; color:#1e293b; line-height:1.5; vertical-align:top; white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(desc)}</td>
                </tr>
            `;
        });
        descritoresHtml += '</tbody></table>';
    }

    const html = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>${escapeHtml(titulo)}</title>
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; background: #fff; color: #1e293b; }
            .container { max-width: 800px; margin: 0 auto; background: #ffffff; padding: 20px 30px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
            .header { text-align: center; border-bottom: 3px solid #2563eb; padding-bottom: 15px; margin-bottom: 20px; }
            .header h1 { font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.3px; }
            .header .sub { font-size: 14px; color: #475569; margin-top: 4px; }
            .header .data { font-size: 12px; color: #94a3b8; margin-top: 4px; }
            .info-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin: 18px 0 22px; }
            .info-card { background: #f8fafc; border-radius: 8px; padding: 12px 14px; text-align: center; border: 1px solid #e2e8f0; }
            .info-card .label { font-size: 10px; color: #94a3b8; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; }
            .info-card .value { font-size: 18px; font-weight: 800; color: #0f172a; margin-top: 4px; }
            .info-card .value .badge { display: inline-block; padding: 2px 14px; border-radius: 20px; font-size: 14px; font-weight: 700; background: #e2e8f0; color: #1e293b; }
            .section-title { font-size: 16px; font-weight: 700; color: #1e293b; margin: 12px 0 6px; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; }
            .table-wrap { overflow-x: auto; margin-top: 4px; }
            table { width: 100%; border-collapse: collapse; }
            th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.3px; background: #f1f5f9; }
            td, th { padding: 8px 12px; text-align: left; }
            .footer { margin-top: 20px; padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 10px; color: #94a3b8; text-align: center; }
            @media print { body { padding: 10px; } .container { box-shadow: none; border: none; } }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>${escapeHtml(titulo)}</h1>
                <div class="sub">Matriz de Proficiência — SISAM 2026</div>
                <div class="data">${new Date().toLocaleString('pt-BR')}</div>
            </div>

            <div class="info-grid">
                <div class="info-card"><div class="label">📚 Ano</div><div class="value">${escapeHtml(ano)}</div></div>
                <div class="info-card"><div class="label">📖 Disciplina</div><div class="value">${escapeHtml(disciplina)}</div></div>
                <div class="info-card"><div class="label">📊 Nível</div><div class="value"><span class="badge">${escapeHtml(nivel)}</span></div></div>
            </div>

            <div class="section-title">📋 HABILIDADES E DESCRITORES (${linhas.length})</div>
            <div class="table-wrap">${descritoresHtml}</div>

            <div class="footer">Documento gerado pelo sistema CorrigePro — Secretaria Municipal de Educação</div>
        </div>
        <script>
            window.onload = function() { window.print(); };
        <\/script>
    </body>
    </html>
    `;

    win.document.write(html);
    win.document.close();
}