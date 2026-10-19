// ============================================================
// IMPRESSAO.JS — PDFs, cartões resposta, impressões
// Extraído de script.js — Corte 7
// ✨ REESCRITO COM CABEÇALHO INSTITUCIONAL PADRONIZADO
// ============================================================

// ═══════════════════════════════════════════════════════════════
// 🎨 CABEÇALHO INSTITUCIONAL PADRÃO (usado em TODAS as impressões)
// ═══════════════════════════════════════════════════════════════
function buildCabecalhoInstitucional(titulo, subtitulo) {
    const agora = new Date();
    const dataFormatada = agora.toLocaleDateString('pt-BR', {
        day: '2-digit', month: '2-digit', year: 'numeric'
    });
    const horaFormatada = agora.toLocaleTimeString('pt-BR', {
        hour: '2-digit', minute: '2-digit'
    });

    return `
    <div class="cabecalho-institucional">
        <div class="cabecalho-logo">
            <img src="https://raw.githubusercontent.com/jorg3o3iras/adabee-sistema/main/semed.png" 
                 alt="SEMED" 
                 onerror="this.style.display='none';">
        </div>
        <div class="cabecalho-texto">
            <div class="cab-prefeitura">PREFEITURA MUNICIPAL DE</div>
            <div class="cab-cidade">SÃO SEBASTIÃO DA BOA VISTA</div>
            <div class="cab-secretaria">Secretaria Municipal de Educação</div>
            <div class="cab-departamento">Departamento de Gestão Pedagógica — DGP</div>
        </div>
        <div class="cabecalho-sisam">
            <div class="cab-sisam-titulo">SISAM</div>
            <div class="cab-sisam-ano">2026</div>
            <div class="cab-sisam-sub">Sistema de Correção de Provas</div>
        </div>
    </div>

    <div class="cabecalho-titulo-relatorio">
        <div class="cab-titulo-left">
            <div class="cab-titulo-principal">${titulo}</div>
            <div class="cab-titulo-subtitulo">${subtitulo || ''}</div>
        </div>
        <div class="cab-titulo-right">
            <div class="cab-data-label">📅 Data</div>
            <div class="cab-data-valor">${dataFormatada}</div>
            <div class="cab-hora-valor">${horaFormatada}</div>
        </div>
    </div>
    `;
}

// ═══════════════════════════════════════════════════════════════
// 🎨 CSS BASE PARA TODAS AS IMPRESSÕES
// ═══════════════════════════════════════════════════════════════
function buildCSSBase() {
    return `
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
        font-family: 'Segoe UI', Arial, sans-serif; 
        padding: 20px; 
        background: #fff; 
        color: #1e293b; 
        font-size: 11px;
    }

    /* ══════════ CABEÇALHO INSTITUCIONAL ══════════ */
        .cabecalho-institucional {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 14px 24px;
        background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
        border: 2px solid #2563eb;
        border-radius: 10px 10px 0 0;
        margin-bottom: 0;
    }
    .cabecalho-logo {
        flex: 0 0 auto;
        display: flex;
        align-items: center;
    }
    .cabecalho-logo img {
        height: 70px;
        width: auto;
        object-fit: contain;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
    }
    .cabecalho-texto {
        flex: 1;
        min-width: 0;
        text-align: center;
    }
    .cab-prefeitura { 
        font-size: 9px; 
        font-weight: 600; 
        color: #64748b; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    .cab-cidade { 
        font-size: 16px; 
        font-weight: 900; 
        color: #1e3a8a; 
        letter-spacing: 0.5px;
        margin-bottom: 2px;
    }
    .cab-secretaria { 
        font-size: 11px; 
        font-weight: 700; 
        color: #2563eb; 
        letter-spacing: 0.3px;
    }
    .cab-departamento { 
        font-size: 9px; 
        font-weight: 600; 
        color: #475569; 
        letter-spacing: 0.3px;
    }
    .cabecalho-sisam { 
        text-align: right; 
        padding-left: 16px; 
        border-left: 2px solid #cbd5e1;
    }
    .cab-sisam-titulo { 
        font-size: 20px; 
        font-weight: 900; 
        color: #2563eb; 
        line-height: 1;
        letter-spacing: 1px;
    }
    .cab-sisam-ano { 
        font-size: 12px; 
        font-weight: 900; 
        color: #1e3a8a;
        letter-spacing: 2px;
    }
    .cab-sisam-sub { 
        font-size: 8px; 
        color: #64748b; 
        font-weight: 600; 
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 2px;
    }

    /* ══════════ TÍTULO DO RELATÓRIO ══════════ */
    .cabecalho-titulo-relatorio {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        padding: 14px 20px;
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
        color: #fff;
        border-radius: 0 0 10px 10px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
    }
    .cab-titulo-left { flex: 1; min-width: 0; }
    .cab-titulo-principal { 
        font-size: 18px; 
        font-weight: 900; 
        letter-spacing: 0.5px;
        line-height: 1.2;
    }
    .cab-titulo-subtitulo { 
        font-size: 11px; 
        font-weight: 600; 
        opacity: 0.9;
        margin-top: 3px;
    }
    .cab-titulo-right { 
        text-align: right; 
        padding-left: 16px;
        border-left: 2px solid rgba(255,255,255,0.3);
        flex-shrink: 0;
    }
    .cab-data-label { 
        font-size: 8px; 
        font-weight: 700; 
        opacity: 0.85; 
        text-transform: uppercase; 
        letter-spacing: 0.5px;
    }
    .cab-data-valor { 
        font-size: 13px; 
        font-weight: 900; 
        margin-top: 2px;
    }
    .cab-hora-valor { 
        font-size: 10px; 
        font-weight: 600; 
        opacity: 0.85;
    }

    /* ══════════ INFO GRID (filtros aplicados) ══════════ */
    .info-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px 16px;
        background: #f8fafc;
        padding: 12px 20px;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        margin-bottom: 16px;
    }
    .info-grid .item { display: flex; flex-direction: column; }
    .info-grid .item .label { 
        font-size: 8px; 
        font-weight: 700; 
        color: #94a3b8; 
        text-transform: uppercase; 
        letter-spacing: 0.5px; 
    }
    .info-grid .item .value { 
        font-size: 12px; 
        font-weight: 700; 
        color: #0f172a; 
        margin-top: 2px;
    }

    /* ══════════ TABELAS PADRÃO ══════════ */
    table { 
        width: 100%; 
        border-collapse: collapse; 
        font-size: 10px; 
        margin: 8px 0;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        overflow: hidden;
    }
    thead { background: #f1f5f9; }
    th { 
        padding: 8px 6px; 
        text-align: center; 
        font-weight: 700; 
        color: #475569; 
        border-bottom: 2px solid #cbd5e1; 
        font-size: 8px; 
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    td { 
        padding: 6px 4px; 
        border-bottom: 1px solid #f1f5f9; 
        text-align: center; 
        font-size: 9px; 
        color: #1e293b; 
    }
    tr:nth-child(even) td { background: #fafbfc; }

    /* ══════════ BADGES DE CONCEITO ══════════ */
    .badge-conceito { 
        display: inline-block; 
        padding: 2px 10px; 
        border-radius: 12px; 
        font-size: 8px; 
        font-weight: 700; 
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    .badge-inicial { background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }
    .badge-basico { background: #fffbeb; color: #f59e0b; border: 1px solid #fde68a; }
    .badge-proficiente { background: #eff6ff; color: #3b82f6; border: 1px solid #bfdbfe; }
    .badge-avancado { background: #ecfdf5; color: #10b981; border: 1px solid #a7f3d0; }

    /* ══════════ FOOTER PADRÃO ══════════ */
    .footer-documento {
        margin-top: 20px; 
        padding-top: 12px; 
        border-top: 2px solid #e2e8f0; 
        display: flex; 
        justify-content: space-between; 
        font-size: 8px; 
        color: #64748b; 
        flex-wrap: wrap; 
        gap: 8px;
    }
    .footer-documento strong { color: #2563eb; }

    /* ══════════ ASSINATURAS PADRÃO ══════════ */
    .assinaturas {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 30px;
        margin-top: 30px;
        padding-top: 16px;
        border-top: 1px solid #e2e8f0;
        text-align: center;
    }
    .assinatura-item { display: flex; flex-direction: column; align-items: center; }
    .assinatura-item .linha { 
        width: 180px; 
        border-bottom: 1.5px solid #1e293b; 
        margin-bottom: 4px; 
    }
    .assinatura-item .cargo { 
        font-size: 9px; 
        color: #64748b; 
        font-weight: 600; 
    }

    /* ══════════ IMPRESSÃO ══════════ */
    @media print {
        body { padding: 10px; }
        .cabecalho-institucional { 
            -webkit-print-color-adjust: exact; 
            print-color-adjust: exact; 
        }
        .cabecalho-titulo-relatorio { 
            -webkit-print-color-adjust: exact; 
            print-color-adjust: exact; 
        }
        .badge-conceito { 
            -webkit-print-color-adjust: exact; 
            print-color-adjust: exact; 
        }
        .assinaturas { page-break-inside: avoid; break-inside: avoid; }
    }
    `;
}

// ═══════════════════════════════════════════════════════════════
// 🎯 FOOTER PADRÃO
// ═══════════════════════════════════════════════════════════════
function buildFooterPadrao() {
    const agora = new Date().toLocaleString('pt-BR');
    return `
    <div class="footer-documento">
        <span>📄 Documento gerado pelo sistema <strong>CorrigePro</strong> · SISAM 2026</span>
        <span>Prefeitura de São Sebastião da Boa Vista — SEMED/DGP</span>
        <span>Gerado em ${agora}</span>
    </div>
    `;
}

// ═══════════════════════════════════════════════════════════════
// 🎯 WRAPPER — monta o HTML completo de impressão
// ═══════════════════════════════════════════════════════════════
function buildDocumentoHTML({ titulo, subtitulo, infoFiltros, conteudo, orientacao }) {
    const orientacaoCSS = orientacao === 'portrait' ? 'A4 portrait' : 'A4 landscape';
    return `
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>${titulo}</title>
        <style>
            ${buildCSSBase()}
            @page { size: ${orientacaoCSS}; margin: 8mm 6mm; }
        </style>
    </head>
    <body>
        ${buildCabecalhoInstitucional(titulo, subtitulo)}
        ${infoFiltros ? `<div class="info-grid">${infoFiltros}</div>` : ''}
        ${conteudo}
        ${buildFooterPadrao()}
    </body>
    </html>
    `;
}

// ═══════════════════════════════════════════════════════════════
// 🚀 FUNÇÃO AUXILIAR — abre janela e imprime
// ═══════════════════════════════════════════════════════════════
function abrirEImprimir(html) {
    const win = window.open('', '_blank');
    if (!win) {
        showToast('⚠️ Permita pop-ups para imprimir.', 'error');
        return false;
    }
    win.document.write(html);
    win.document.close();
    win.onload = () => {
        setTimeout(() => { win.focus(); win.print(); }, 400);
    };
    return true;
}

// ═══════════════════════════════════════════════════════════════
// 📋 IMPRIMIR ALUNOS
// ═══════════════════════════════════════════════════════════════
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

    let tbodyHtml = '';
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
            tbodyHtml += `
                <tr>
                    <td>${escapeHtml(cells[0].textContent.trim())}</td>
                    <td>${escapeHtml(cells[1].textContent.trim())}</td>
                    <td style="text-align:left;font-weight:600;">${escapeHtml(cells[2].textContent.trim())}</td>
                    <td>${escapeHtml(cells[3].textContent.trim())}</td>
                    <td>${escapeHtml(cells[4].textContent.trim())}</td>
                    <td>${escapeHtml(cells[5].textContent.trim())}</td>
                    <td>${escapeHtml(cells[6].textContent.trim())}</td>
                </tr>
            `;
        }
    });

    const infoFiltros = `
        <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escolaNome)}</span></div>
        <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml(turmaNome)}</span></div>
        <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${escapeHtml(serieNome)}</span></div>
        <div class="item"><span class="label">👨‍🎓 TOTAL</span><span class="value">${rows.length} alunos</span></div>
    `;

    const conteudo = `
        <h3 style="font-size:13px;font-weight:800;margin:12px 0 8px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📋 Lista de Alunos</h3>
        <table>
            <thead>
                <tr>
                    <th>Nº</th>
                    <th>MATRÍCULA</th>
                    <th style="text-align:left;">NOME COMPLETO</th>
                    <th>SÉRIE</th>
                    <th>TURMA</th>
                    <th>ESCOLA</th>
                    <th>DATA NASC.</th>
                </tr>
            </thead>
            <tbody>${tbodyHtml}</tbody>
        </table>
    `;

    const html = buildDocumentoHTML({
        titulo: '📋 RELATÓRIO DE ALUNOS',
        subtitulo: 'Lista completa de alunos matriculados',
        infoFiltros,
        conteudo,
        orientacao: 'landscape'
    });

    if (abrirEImprimir(html)) {
        showToast('📄 Documento gerado!', 'success');
    }
}

// ═══════════════════════════════════════════════════════════════
// 📊 EXPORTAR RELATÓRIO PDF (Rel. por Turma)
// ═══════════════════════════════════════════════════════════════
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

    // ✅ Detecta se é Produção de Texto
    const isProducaoPDF = (disciplinaNome === 'Produção de Texto');

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
            // ✅ Em Produção, a coluna 4 contém a NOTA (não acertos)
            if (isProducaoPDF) {
                const notaTexto = cells[4]?.textContent.trim() || '';
                // A nota está no formato "NOTA\n10.0" — pega só o número
                const matchNota = notaTexto.match(/(\d+[.,]\d+)/);
                const nota = matchNota ? parseFloat(matchNota[1].replace(',', '.')) : 0;

                alunosData.push({
                    posicao: cells[0]?.textContent.trim() || '',
                    numero: cells[1]?.textContent.trim() || '',
                    nome: cells[2]?.textContent.trim() || '',
                    serie: cells[3]?.textContent.trim() || '',
                    nota: nota,
                    conceito: cells[6]?.textContent.trim() || '',
                    escola: cells[7]?.textContent.trim() || '',
                    turma: cells[8]?.textContent.trim() || ''
                });
            } else {
                const acertos = parseInt(cells[4]?.textContent.trim()) || 0;
                const erros = parseInt(cells[5]?.textContent.trim()) || 0;
                totalAcertosGeral += acertos;
                totalErrosGeral += erros;

                alunosData.push({
                    posicao: cells[0]?.textContent.trim() || '',
                    numero: cells[1]?.textContent.trim() || '',
                    nome: cells[2]?.textContent.trim() || '',
                    serie: cells[3]?.textContent.trim() || '',
                    acertos,
                    erros,
                    conceito: cells[6]?.textContent.trim() || '',
                    escola: cells[7]?.textContent.trim() || '',
                    turma: cells[8]?.textContent.trim() || ''
                });
            }
        }
    });

    const totalAlunos = alunosData.length;

    const acertosPorQuestao = [];
    const acertosGrid = document.getElementById('rel-acertos-grid');
    if (acertosGrid && !isProducaoPDF) {
        const items = acertosGrid.querySelectorAll('.acertos-por-questao-item');
        items.forEach(item => {
            const texto = item.textContent || '';
            const match = texto.match(/Q(\d+)/);
            if (match) {
                const matchNum = texto.match(/(\d+)\s*\/\s*(\d+)/);
                const matchBncc = texto.match(/(EF\d+[A-Z]+\d+)/);
                acertosPorQuestao.push({
                    numero: 'Q' + match[1],
                    acertos: matchNum ? matchNum[1] : '0',
                    erros: matchNum ? matchNum[2] : '0',
                    bncc: matchBncc ? matchBncc[1] : 'N/A'
                });
            }
        });
    }

    const infoFiltros = `
        <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escolaNome)}</span></div>
        <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${escapeHtml(serieNome)}</span></div>
        <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml(turmaNome)}</span></div>
        <div class="item"><span class="label">📖 DISCIPLINA</span><span class="value">${escapeHtml(disciplinaNome)}</span></div>
        <div class="item"><span class="label">👨‍🎓 ALUNOS</span><span class="value">${totalAlunos}</span></div>
        <div class="item"><span class="label">📊 MÉDIA</span><span class="value">${escapeHtml(media)}</span></div>
    `;

    const questoesHTML = acertosPorQuestao.length > 0 
        ? acertosPorQuestao.map(q => `
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center;">
                <div style="font-size:12px;font-weight:800;color:#1e293b;margin-bottom:4px;">${escapeHtml(q.numero)}</div>
                <div style="font-size:14px;font-weight:700;margin:4px 0;">
                    <span style="color:#10b981;">${escapeHtml(q.acertos)}</span>
                    <span style="color:#94a3b8;">/</span>
                    <span style="color:#ef4444;">${escapeHtml(q.erros)}</span>
                </div>
                <div style="font-size:9px;color:#8b5cf6;background:#f5f3ff;padding:2px 8px;border-radius:6px;display:inline-block;font-family:'Courier New',monospace;">${escapeHtml(q.bncc)}</div>
            </div>
        `).join('')
        : '<div style="grid-column:1/-1;text-align:center;padding:20px;color:#94a3b8;">Nenhum dado disponível.</div>';

    // ✅ Tabela adaptada: em Produção mostra NOTA em vez de Acertos/Erros
    const alunosHTML = alunosData.map(a => {
        const conceitoClass = a.conceito ? `badge-${a.conceito.toLowerCase().replace(/\s+/g,'')}` : 'badge-inicial';
        if (isProducaoPDF) {
            return `
                <tr>
                    <td>${escapeHtml(a.posicao)}</td>
                    <td>${escapeHtml(a.numero)}</td>
                    <td style="text-align:left;font-weight:600;">${escapeHtml(a.nome)}</td>
                    <td>${escapeHtml(a.serie)}</td>
                    <td style="color:#8b5cf6;font-weight:900;font-size:13px;">${(a.nota !== undefined && a.nota !== null) ? Number(a.nota).toFixed(1) : '—'}</td>
                    <td><span class="badge-conceito ${conceitoClass}">${escapeHtml(a.conceito || '—')}</span></td>
                    <td>${escapeHtml(a.escola)}</td>
                    <td>${escapeHtml(a.turma)}</td>
                </tr>
            `;
        }
        return `
            <tr>
                <td>${escapeHtml(a.posicao)}</td>
                <td>${escapeHtml(a.numero)}</td>
                <td style="text-align:left;font-weight:600;">${escapeHtml(a.nome)}</td>
                <td>${escapeHtml(a.serie)}</td>
                <td style="color:#10b981;font-weight:700;">${a.acertos}</td>
                <td style="color:#ef4444;font-weight:700;">${a.erros}</td>
                <td><span class="badge-conceito ${conceitoClass}">${escapeHtml(a.conceito || '—')}</span></td>
                <td>${escapeHtml(a.escola)}</td>
                <td>${escapeHtml(a.turma)}</td>
            </tr>
        `;
    }).join('');

    const conteudo = `
        ${!isProducaoPDF ? `
            <h3 style="font-size:13px;font-weight:800;margin:16px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📊 Acertos por Questão — ${escapeHtml(disciplinaNome)}</h3>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:8px;margin-bottom:16px;">
                ${questoesHTML}
            </div>
        ` : ''}

        <div style="display:grid;grid-template-columns:${isProducaoPDF ? '2' : '4'};gap:12px;margin:16px 0;">
            ${!isProducaoPDF ? `
                <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:24px;font-weight:900;color:#10b981;">${totalAcertosGeral}</div>
                    <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">✅ Acertos</div>
                </div>
                <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:24px;font-weight:900;color:#ef4444;">${totalErrosGeral}</div>
                    <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">❌ Erros</div>
                </div>
            ` : ''}
            <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px;text-align:center;">
                <div style="font-size:24px;font-weight:900;color:#3b82f6;">${escapeHtml(media)}</div>
                <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">📊 Média</div>
            </div>
            <div style="background:#f5f3ff;border:1px solid #c4b5fd;border-radius:8px;padding:12px;text-align:center;">
                <div style="font-size:18px;font-weight:900;color:#8b5cf6;">${escapeHtml(conceito)}</div>
                <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">📊 Conceito</div>
            </div>
        </div>

        <h3 style="font-size:13px;font-weight:800;margin:16px 0 8px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📋 Lista de Alunos (${totalAlunos})</h3>
        <table>
            <thead>
                ${isProducaoPDF ? `
                    <tr>
                        <th>POS.</th>
                        <th>Nº</th>
                        <th style="text-align:left;">NOME</th>
                        <th>SÉRIE</th>
                        <th>NOTA</th>
                        <th>CONCEITO</th>
                        <th>ESCOLA</th>
                        <th>TURMA</th>
                    </tr>
                ` : `
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
                `}
            </thead>
            <tbody>${alunosHTML}</tbody>
        </table>

        <div class="assinaturas">
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Professor(a) Responsável</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Diretor(a)</div></div>
            <div class="assinatura-item"><div class="linha"></div><div class="cargo">Secretaria Municipal de Educação</div></div>
        </div>
    `;

    const html = buildDocumentoHTML({
        titulo: '📊 RELATÓRIO POR TURMA',
        subtitulo: `Desempenho dos alunos — ${disciplinaNome}`,
        infoFiltros,
        conteudo,
        orientacao: 'landscape'
    });

    if (abrirEImprimir(html)) {
        showToast('📄 PDF gerado com sucesso!', 'success');
    }
}

// ═══════════════════════════════════════════════════════════════
// 🏆 IMPRIMIR RESULTADOS MELHORADOS
// ═══════════════════════════════════════════════════════════════
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

    const infoFiltros = `
        <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escolaNome)}</span></div>
        <div class="item"><span class="label">📚 SÉRIE</span><span class="value">${escapeHtml(serieNome)}</span></div>
        <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml(turmaNome)}</span></div>
        <div class="item"><span class="label">📄 PROVA</span><span class="value">${escapeHtml(provaNome)}</span></div>
        <div class="item"><span class="label">👨‍🎓 ALUNOS</span><span class="value">${escapeHtml(totalAlunos)}</span></div>
    `;

    const alunosHTML = alunosData.map(a => `
        <tr>
            <td>${escapeHtml(a.posicao)}</td>
            <td>${escapeHtml(a.numero)}</td>
            <td style="text-align:left;font-weight:600;">${escapeHtml(a.nome)}</td>
            <td>${escapeHtml(a.serie)}</td>
            <td>${escapeHtml(a.ptAcertos)}</td>
            <td>${escapeHtml(a.ptErros)}</td>
            <td>${escapeHtml(a.ptConceito)}</td>
            <td>${escapeHtml(a.matAcertos)}</td>
            <td>${escapeHtml(a.matErros)}</td>
            <td>${escapeHtml(a.matConceito)}</td>
            <td style="font-weight:900;color:#8b5cf6;">${escapeHtml(a.prodNota)}</td>
            <td>${escapeHtml(a.chAcertos)}</td>
            <td>${escapeHtml(a.chErros)}</td>
            <td>${escapeHtml(a.chConceito)}</td>
            <td>${escapeHtml(a.cnAcertos)}</td>
            <td>${escapeHtml(a.cnErros)}</td>
            <td>${escapeHtml(a.cnConceito)}</td>
            <td>${escapeHtml(a.escola)}</td>
            <td>${escapeHtml(a.turma)}</td>
        </tr>
    `).join('');

    const conteudo = `
        <h3 style="font-size:13px;font-weight:800;margin:16px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📊 Distribuição por Conceito</h3>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px;text-align:center;">
                <div style="font-size:24px;font-weight:900;color:#ef4444;">${conceitoInicial}</div>
                <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">🔴 Inicial</div>
            </div>
            <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px;text-align:center;">
                <div style="font-size:24px;font-weight:900;color:#f59e0b;">${conceitoBasico}</div>
                <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">🟠 Básico</div>
            </div>
            <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px;text-align:center;">
                <div style="font-size:24px;font-weight:900;color:#3b82f6;">${conceitoProficiente}</div>
                <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">🔵 Proficiente</div>
            </div>
            <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px;text-align:center;">
                <div style="font-size:24px;font-weight:900;color:#10b981;">${conceitoAvancado}</div>
                <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">🟢 Avançado</div>
            </div>
        </div>

        <h3 style="font-size:13px;font-weight:800;margin:16px 0 8px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📋 Lista de Alunos</h3>
        <table style="font-size:8px;">
            <thead>
                <tr>
                    <th rowspan="2">POS.</th>
                    <th rowspan="2">Nº</th>
                    <th rowspan="2" style="text-align:left;">NOME</th>
                    <th rowspan="2">SÉRIE</th>
                    <th colspan="3" style="background:#eff6ff;">PORTUGUÊS</th>
                    <th colspan="3" style="background:#ecfdf5;">MATEMÁTICA</th>
                    <th colspan="1" style="background:#f5f3ff;">PRODUÇÃO</th>
                    <th colspan="3" style="background:#fffbeb;">CIÊNCIAS HUMANAS</th>
                    <th colspan="3" style="background:#f0fdfa;">CIÊNCIAS NATURAIS</th>
                    <th rowspan="2">ESCOLA</th>
                    <th rowspan="2">TURMA</th>
                </tr>
                <tr>
                    <th style="font-size:7px;">ACERTOS</th>
                    <th style="font-size:7px;">ERROS</th>
                    <th style="font-size:7px;">CONCEITO</th>
                    <th style="font-size:7px;">ACERTOS</th>
                    <th style="font-size:7px;">ERROS</th>
                    <th style="font-size:7px;">CONCEITO</th>
                    <th style="font-size:7px;">NOTA</th>
                    <th style="font-size:7px;">ACERTOS</th>
                    <th style="font-size:7px;">ERROS</th>
                    <th style="font-size:7px;">CONCEITO</th>
                    <th style="font-size:7px;">ACERTOS</th>
                    <th style="font-size:7px;">ERROS</th>
                    <th style="font-size:7px;">CONCEITO</th>
                </tr>
            </thead>
            <tbody>${alunosHTML}</tbody>
        </table>
    `;

    const html = buildDocumentoHTML({
        titulo: '🏆 RELATÓRIO DE RESULTADOS',
        subtitulo: 'Acertos, erros e conceitos por disciplina',
        infoFiltros,
        conteudo,
        orientacao: 'landscape'
    });

    if (abrirEImprimir(html)) {
        showToast('📄 Relatório gerado!', 'success');
    }
}

// ═══════════════════════════════════════════════════════════════
// 🎫 GERAR CARTÃO RESPOSTA (mantém chamada ao backend)
// ═══════════════════════════════════════════════════════════════
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

// ═══════════════════════════════════════════════════════════════
// 📄 GERAR DOCUMENTO DE DESEMPENHO — DISPATCHER
// ═══════════════════════════════════════════════════════════════
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

// ═══════════════════════════════════════════════════════════════
// 📄 PDF — DISCIPLINAS NORMAIS
// ═══════════════════════════════════════════════════════════════
function gerarDocumentoNormal(data) {
    const btn = document.getElementById('btnGerarDocumento');
    try {
        const { escola, turma, aluno, prova, resultadoQuestoes, acertos, erros, porcentagem, conceito, disciplina, gabarito, bncc } = data;

        const infoFiltros = `
            <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escola.nome || '—')}</span></div>
            <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml((turma.nome || '') + ' - ' + (turma.serie || ''))}</span></div>
            <div class="item"><span class="label">🎒 ALUNO</span><span class="value">${escapeHtml(aluno.nome || '—')}</span></div>
            <div class="item"><span class="label">📄 PROVA</span><span class="value">${escapeHtml(prova.titulo || '—')}</span></div>
            <div class="item"><span class="label">📚 DISCIPLINA</span><span class="value">${escapeHtml(disciplina)}</span></div>
        `;

        let questoesHTML = '';
        resultadoQuestoes.forEach(q => {
            const acertou = q.acertou;
            const resposta = q.resposta || '—';
            const gab = q.gabarito || '—';
            const bgColor = acertou ? '#ecfdf5' : (q.respondida ? '#fef2f2' : '#f8fafc');
            const borderColor = acertou ? '#10b981' : (q.respondida ? '#ef4444' : '#e2e8f0');
            const respColor = acertou ? '#10b981' : (q.respondida ? '#ef4444' : '#64748b');
            const statusIcon = acertou ? '✅' : (q.respondida ? '❌' : '—');

            questoesHTML += `
                <div style="background:${bgColor};border:2px solid ${borderColor};border-radius:8px;padding:8px 4px;text-align:center;">
                    <div style="font-size:9px;color:#94a3b8;font-weight:700;">Q${q.numero}</div>
                    <div style="font-weight:800;font-size:14px;color:${respColor};margin:2px 0;">${escapeHtml(resposta)}</div>
                    <div style="font-size:8px;color:#94a3b8;">Gab: ${escapeHtml(gab)}</div>
                    <div style="font-size:14px;margin-top:2px;">${statusIcon}</div>
                    ${q.bncc ? `<div style="font-size:7px;color:#8b5cf6;margin-top:2px;background:#f5f3ff;padding:1px 4px;border-radius:4px;">${escapeHtml(q.bncc)}</div>` : ''}
                </div>
            `;
        });

        let gabaritoHTML = '';
        gabarito.forEach((gab, idx) => {
            const codigoBncc = (idx < bncc.length) ? bncc[idx] : '';
            gabaritoHTML += `
                <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:6px 4px;text-align:center;">
                    <div style="font-size:9px;color:#94a3b8;font-weight:700;">Q${idx+1}</div>
                    <div style="font-weight:800;font-size:14px;color:#10b981;">${escapeHtml(gab || '—')}</div>
                    ${codigoBncc ? `<div style="font-size:7px;color:#8b5cf6;margin-top:2px;background:#f5f3ff;padding:1px 4px;border-radius:4px;">${escapeHtml(codigoBncc)}</div>` : ''}
                </div>
            `;
        });

        const conteudo = `
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
                <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:26px;font-weight:900;color:#3b82f6;">${porcentagem}%</div>
                    <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">📊 Porcentagem</div>
                </div>
                <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:26px;font-weight:900;color:#10b981;">${acertos}</div>
                    <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">✅ Acertos</div>
                </div>
                <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:26px;font-weight:900;color:#ef4444;">${erros}</div>
                    <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">❌ Erros</div>
                </div>
                <div style="background:#f5f3ff;border:1px solid #c4b5fd;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:20px;font-weight:900;color:#8b5cf6;">${escapeHtml(conceito)}</div>
                    <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;">📊 Conceito</div>
                </div>
            </div>

            <h3 style="font-size:13px;font-weight:800;margin:16px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📖 Questões — ${escapeHtml(disciplina)}</h3>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:6px;">
                ${questoesHTML}
            </div>

            <h3 style="font-size:13px;font-weight:800;margin:16px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📋 Gabarito Oficial</h3>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:6px;">
                ${gabaritoHTML}
            </div>
        `;

        const html = buildDocumentoHTML({
            titulo: '📊 RELATÓRIO DE DESEMPENHO',
            subtitulo: `Aluno: ${aluno.nome || '—'} · ${disciplina}`,
            infoFiltros,
            conteudo,
            orientacao: 'portrait'
        });

        if (abrirEImprimir(html)) {
            showToast('📄 Documento gerado!', 'success');
        }
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

// ═══════════════════════════════════════════════════════════════
// 📄 PDF — PRODUÇÃO DE TEXTO
// ═══════════════════════════════════════════════════════════════
function gerarDocumentoProducao(data) {
    const btn = document.getElementById('btnGerarDocumento');
    try {
        const {
            escola, turma, aluno, prova, resultadoQuestoes,
            disciplina, notaProducao, conceito,
            questoesStatusHistorico, textosQuestoes
        } = data;

        const infoFiltros = `
            <div class="item"><span class="label">🏫 ESCOLA</span><span class="value">${escapeHtml(escola.nome || '—')}</span></div>
            <div class="item"><span class="label">👥 TURMA</span><span class="value">${escapeHtml((turma.nome || '') + ' - ' + (turma.serie || ''))}</span></div>
            <div class="item"><span class="label">🎒 ALUNO</span><span class="value">${escapeHtml(aluno.nome || '—')}</span></div>
            <div class="item"><span class="label">📄 PROVA</span><span class="value">${escapeHtml(prova.titulo || '—')}</span></div>
            <div class="item"><span class="label">📚 DISCIPLINA</span><span class="value">${escapeHtml(disciplina)}</span></div>
        `;

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
                            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:8px 10px;display:flex;gap:8px;align-items:flex-start;">
                                <span style="flex:0 0 22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#8b5cf6,#6d28d9);color:#fff;font-weight:900;font-size:11px;display:inline-flex;align-items:center;justify-content:center;">${escapeHtml(m[1])}</span>
                                <span style="flex:1;font-size:10px;color:#1e293b;line-height:1.4;">${escapeHtml(m[2].trim())}</span>
                            </div>
                        `;
                    }
                });
            }

            questoesHTML += `
                <div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #8b5cf6;border-radius:8px;padding:12px 14px;margin-bottom:12px;page-break-inside:avoid;break-inside:avoid;">
                    <div style="font-size:12px;font-weight:800;color:#8b5cf6;margin-bottom:8px;padding-bottom:6px;border-bottom:1px dashed #cbd5e1;">${escapeHtml(headerTexto)}</div>

                    <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">📋 Gabarito</div>
                    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px;">${alternativasHTML || '<div style="font-size:10px;color:#94a3b8;font-style:italic;">Sem gabarito cadastrado</div>'}</div>

                    <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">✍️ Observação do Professor</div>
                    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:8px 10px;font-size:10px;color:#1e293b;line-height:1.5;min-height:32px;white-space:pre-wrap;word-wrap:break-word;">${escapeHtml(observacao || '—')}</div>

                    <div style="display:flex;align-items:center;gap:8px;margin-top:10px;padding-top:8px;border-top:1px dashed #e2e8f0;">
                        <span style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;">📊 Situação de Correção:</span>
                        <span style="display:inline-block;background:#ede9fe;color:#6d28d9;border:1px solid #c4b5fd;padding:3px 14px;border-radius:20px;font-weight:900;font-size:12px;">${escapeHtml(situacao || '—')}</span>
                    </div>
                </div>
            `;
        });

        const conteudo = `
            <div style="background:linear-gradient(135deg,#f5f3ff,#ede9fe);border:2px solid #8b5cf6;border-radius:10px;padding:16px;text-align:center;margin:16px 0;">
                <div style="font-size:44px;font-weight:900;color:#8b5cf6;line-height:1;">${notaProducao.toFixed(1)}</div>
                <div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;margin-top:6px;letter-spacing:0.3px;">⭐ NOTA FINAL — PRODUÇÃO DE TEXTO</div>
                <div style="margin-top:10px;padding-top:10px;border-top:1px dashed #c4b5fd;display:flex;justify-content:center;align-items:center;gap:8px;">
                    <span style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.3px;">Conceito:</span>
                    <span style="display:inline-block;padding:4px 16px;border-radius:20px;font-weight:900;font-size:13px;background:#ede9fe;color:#6d28d9;border:1px solid #c4b5fd;">${escapeHtml(conceito || '—')}</span>
                </div>
            </div>

            <h3 style="font-size:13px;font-weight:800;margin:16px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📝 Questões Avaliadas (${resultadoQuestoes.length})</h3>
            ${questoesHTML}
        `;

        const html = buildDocumentoHTML({
            titulo: '📊 RELATÓRIO DE DESEMPENHO',
            subtitulo: `Produção de Texto · Aluno: ${aluno.nome || '—'}`,
            infoFiltros,
            conteudo,
            orientacao: 'portrait'
        });

        if (abrirEImprimir(html)) {
            showToast('📄 Documento gerado!', 'success');
        }
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

// ═══════════════════════════════════════════════════════════════
// 📊 IMPRIMIR MATRIZ DE PROFICIÊNCIA
// ═══════════════════════════════════════════════════════════════
function imprimirMatrizVisualizada() {
    const matriz = window.matrizVisualizando;
    if (!matriz) {
        showToast('❌ Nenhuma matriz para imprimir. Visualize uma matriz primeiro.', 'error');
        return;
    }

    const ano = matriz.ano || '—';
    const disciplina = matriz.disciplina || '—';
    const nivel = matriz.nivel || '—';

    const descritores = (matriz.descritores || []).map(d => ({
        bncc: d.bncc || '',
        descritor: d.descritor || d.descricao || ''
    }));

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

    const descritoresHTML = linhas.length > 0 
        ? linhas.map((linha, idx) => `
            <tr style="background:${idx % 2 === 0 ? '#fff' : '#f8fafc'};">
                <td style="padding:10px 12px;font-weight:700;color:#8b5cf6;font-family:'Courier New',monospace;vertical-align:top;border-bottom:1px solid #e2e8f0;font-size:10px;">${escapeHtml(linha.bncc || '—')}</td>
                <td style="padding:10px 12px;color:#1e293b;line-height:1.5;vertical-align:top;border-bottom:1px solid #e2e8f0;white-space:pre-wrap;font-size:10px;">${escapeHtml(linha.descritor || '—')}</td>
            </tr>
        `).join('')
        : '<tr><td colspan="2" style="padding:20px;text-align:center;color:#94a3b8;">Nenhuma habilidade cadastrada.</td></tr>';

    const infoFiltros = `
        <div class="item"><span class="label">📚 ANO</span><span class="value">${escapeHtml(ano)}</span></div>
        <div class="item"><span class="label">📖 DISCIPLINA</span><span class="value">${escapeHtml(disciplina)}</span></div>
        <div class="item"><span class="label">📊 NÍVEL</span><span class="value">${escapeHtml(nivel)}</span></div>
        <div class="item"><span class="label">📋 HABILIDADES</span><span class="value">${linhas.length}</span></div>
    `;

    const conteudo = `
        <h3 style="font-size:13px;font-weight:800;margin:16px 0 10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">📋 Habilidades e Descritores</h3>
        <table>
            <thead>
                <tr>
                    <th style="width:25%;">📌 HABILIDADE BNCC</th>
                    <th style="width:75%;text-align:left;">📝 DESCRITORES</th>
                </tr>
            </thead>
            <tbody>${descritoresHTML}</tbody>
        </table>
    `;

    const html = buildDocumentoHTML({
        titulo: '📊 MATRIZ DE PROFICIÊNCIA',
        subtitulo: `${ano} · ${disciplina} · Nível ${nivel}`,
        infoFiltros,
        conteudo,
        orientacao: 'portrait'
    });

    if (abrirEImprimir(html)) {
        showToast('📄 Documento gerado!', 'success');
    }
}
