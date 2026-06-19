function editarProva(id) {
    showToast('⏳ Carregando prova...', 'info');
    
    fetch(API_URL + '/api/provas/' + id, {
        method: 'GET',
        headers: {
            'Accept': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    })
    .then(prova => {
        if (prova.erro) {
            showToast('❌ ' + prova.erro, 'error');
            return;
        }
        
        const is1Ano = prova.turma_serie && prova.turma_serie.startsWith('1');
        const gabarito = prova.gabarito || [];
        
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(10px);
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            overflow-y: auto;
        `;
        
        overlay.innerHTML = `
            <div style="background: var(--surface); border: 1px solid var(--border2); border-radius: 16px; padding: 28px; max-width: 800px; width: 100%; max-height: 90vh; overflow-y: auto; position: relative; box-shadow: 0 32px 80px rgba(0,0,0,0.6);">
                
                <button onclick="this.closest('div[style*=\"position: fixed\"]').remove()" style="position: sticky; top: 0; float: right; background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.4); color: #fc8181; width: 36px; height: 36px; border-radius: 50%; font-size: 20px; cursor: pointer; z-index: 10; transition: all 0.2s; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
                    ✕
                </button>

                <div style="border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px;">
                    <h2 style="font-size: 22px; font-weight: 800; color: var(--text);">📄 ${prova.titulo || 'Prova'}</h2>
                    <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; font-size: 13px; color: var(--text2);">
                        <span>🏷️ Disciplina: <strong style="color: var(--text);">${prova.disciplina || '—'}</strong></span>
                        <span>📚 Série: <strong style="color: var(--text);">${prova.turma_serie || '—'}</strong></span>
                        <span>👥 Turma: <strong style="color: var(--text);">${prova.turma_nome || '—'}</strong></span>
                        <span>📅 Data: <strong style="color: var(--text);">${prova.data_prova || '—'}</strong></span>
                        <span>📊 Questões: <strong style="color: var(--text);">${gabarito.length || 0}</strong></span>
                        <span style="background: ${is1Ano ? 'rgba(139,92,246,0.15)' : 'rgba(59,130,246,0.15)'}; padding: 2px 10px; border-radius: 20px; border: 1px solid ${is1Ano ? 'rgba(139,92,246,0.3)' : 'rgba(59,130,246,0.3)'};">
                            ${is1Ano ? '🔵 3 alternativas (A,B,C)' : '🟦 4 alternativas (A,B,C,D)'}
                        </span>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <h3 style="font-size: 14px; font-weight: 700; color: var(--text2); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                        ✅ Gabarito da Prova
                    </h3>
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(60px, 1fr)); gap: 6px; max-height: 300px; overflow-y: auto; padding: 4px;">
                        ${gabarito.length > 0 ? gabarito.map((resp, i) => `
                            <div style="background: var(--bg2); border: 1px solid var(--border2); border-radius: 8px; padding: 8px 4px; text-align: center;">
                                <div style="font-size: 9px; color: var(--text3); font-weight: 700; margin-bottom: 2px;">Q${i+1}</div>
                                <div style="font-size: 16px; font-weight: 800; color: var(--green); background: rgba(16,185,129,0.1); border-radius: 6px; padding: 4px 0;">
                                    ${resp || '—'}
                                </div>
                            </div>
                        `).join('') : `
                            <div style="grid-column: 1 / -1; text-align: center; color: var(--text3); padding: 20px;">
                                ⚠️ Nenhum gabarito cadastrado para esta prova
                            </div>
                        `}
                    </div>
                </div>

                <div style="display: flex; gap: 10px; flex-wrap: wrap; padding-top: 16px; border-top: 1px solid var(--border);">
                    <button onclick="go('corrigir-ia')" class="btn btn-purple" style="flex: 1; justify-content: center;">
                        🤖 Corrigir com IA
                    </button>
                    <button onclick="this.closest('div[style*=\"position: fixed\"]').remove()" class="btn btn-outline" style="flex: 1; justify-content: center;">
                        ✕ Fechar
                    </button>
                    <button onclick="window.print()" class="btn btn-outline" style="flex: 0 1 auto;">
                        🖨️ Imprimir
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        
        overlay.addEventListener('click', function(e) {
            if (e.target === this) this.remove();
        });
        
        showToast('👁️ Visualizando: ' + prova.titulo, 'success');
    })
    .catch(erro => {
        console.error('Erro ao carregar prova:', erro);
        showToast('❌ Erro ao visualizar prova: ' + erro.message, 'error');
    });
}
