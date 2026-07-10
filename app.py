        function salvarCorrecaoManual() {
            const qtd = correcaoManualData.quantidade || 20;
            const respostas = correcaoManualData.respostasAluno || [];
            const gabarito = correcaoManualData.gabarito || [];
            let acertos = 0;
            for (let i = 0; i < qtd; i++) {
                const resp = i < respostas.length ? respostas[i] : '';
                const gab = i < gabarito.length ? gabarito[i] : '';
                if (resp && resp.toUpperCase() === gab.toUpperCase()) { acertos++; }
            }
            const nota = Math.min((acertos * correcaoManualData.valorPorQuestao), correcaoManualData.notaMaxima || 10);
            
            // Verificar se temos os dados necessários
            if (!correcaoManualData.provaId) {
                showToast('❌ ID da prova não disponível. Tente corrigir novamente com IA.', 'error');
                return;
            }
            
            showToast('💾 Salvando correção manual...', 'info');
            
            const dadosCorrecao = { 
                prova_id: correcaoManualData.provaId, 
                aluno_id: correcaoManualData.alunoId, 
                respostas: respostas, 
                acertos: acertos, 
                nota: nota, 
                total: qtd 
            };
            
            console.log('📤 Dados da correção manual:', dadosCorrecao);
            
            fetch(API_URL + '/api/corrigir_manual', { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' }, 
                body: JSON.stringify(dadosCorrecao) 
            })
            .then(response => response.json())
            .then(data => {
                console.log('📥 Resposta do servidor:', data);
                if (data.sucesso) {
                    showToast('✅ Correção manual salva! Nota: ' + nota.toFixed(1), 'success');
                    closeM('m-correcao-manual');
                    
                    // Atualizar a nota na interface
                    const notaEl = document.getElementById('ia-nota'); 
                    if (notaEl) { 
                        notaEl.textContent = nota.toFixed(1); 
                        notaEl.style.color = nota >= 5 ? 'var(--green)' : 'var(--red)'; 
                    }
                    
                    const statusEl = document.getElementById('ia-status'); 
                    if (statusEl) { 
                        const status = nota >= 5 ? 'APROVADO' : 'REPROVADO'; 
                        const badgeClass = nota >= 5 ? 'badge-green' : 'badge-red'; 
                        statusEl.textContent = status; 
                        statusEl.className = 'badge ' + badgeClass; 
                    }
                    
                    // Adicionar badge manual
                    const header = document.querySelector('.card-glow-green .card-header .btn-group'); 
                    if (header) { 
                        const oldBadge = header.querySelector('.badge-manual'); 
                        if (oldBadge) oldBadge.remove(); 
                        const manualBadge = document.createElement('span'); 
                        manualBadge.className = 'badge badge-orange badge-manual'; 
                        manualBadge.textContent = '✏️ Manual'; 
                        header.appendChild(manualBadge); 
                    }
                    
                    // Atualizar respostas na interface
                    const respContainer = document.getElementById('ia-resp'); 
                    if (respContainer && respostas.length > 0) { 
                        const gabarito = correcaoManualData.gabarito || []; 
                        respContainer.innerHTML = respostas.map((resp, i) => { 
                            const ok = resp === gabarito[i]; 
                            return '<span style="background:' + (ok ? 'rgba(16,185,129,.2)' : 'rgba(239,68,68,.2)') + ';border:1px solid ' + (ok ? 'rgba(16,185,129,.4)' : 'rgba(239,68,68,.4)') + ';padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;color:' + (ok ? 'var(--green)' : 'var(--red)') + ';">Q' + (i + 1) + ':' + resp + '</span>'; 
                        }).join(''); 
                    }
                    
                    const compContainer = document.getElementById('ia-comp'); 
                    if (compContainer && respostas.length > 0) { 
                        const gabarito = correcaoManualData.gabarito || []; 
                        compContainer.innerHTML = respostas.map((resp, i) => { 
                            const ok = resp === gabarito[i]; 
                            return '<div style="text-align:center;"><div style="font-size:9px;color:var(--text3);margin-bottom:2px;">Q' + (i + 1) + '</div><div style="background:' + (ok ? 'rgba(16,185,129,.2)' : 'rgba(239,68,68,.2)') + ';border:1px solid ' + (ok ? 'rgba(16,185,129,.4)' : 'rgba(239,68,68,.4)') + ';border-radius:6px;padding:4px 2px;font-size:11px;font-weight:800;color:' + (ok ? 'var(--green)' : 'var(--red)') + ';">' + resp + '</div></div>'; 
                        }).join(''); 
                    }
                    
                    const confiancaEl = document.getElementById('confianca-badge'); 
                    if (confiancaEl) { 
                        confiancaEl.textContent = '100% conf.'; 
                    }
                    
                    setTimeout(() => { 
                        carregarResultados(); 
                        carregarDashboard(); 
                        carregarUltimasCorrecoes(); 
                    }, 500);
                    
                } else { 
                    // Tratar erro específico de chave estrangeira
                    const erroMsg = data.erro || 'Erro desconhecido';
                    if (erroMsg.includes('foreign key constraint') || erroMsg.includes('prova_id')) {
                        showToast('⚠️ A prova não existe mais no sistema. Tente corrigir novamente com IA.', 'warning');
                        // Tentar recarregar os dados da prova
                        const provaId = correcaoManualData.provaId;
                        if (provaId) {
                            fetch(API_URL + '/api/provas/' + provaId)
                                .then(r => r.json())
                                .then(prova => {
                                    if (prova && prova.id) {
                                        showToast('✅ Prova recarregada. Tente salvar novamente.', 'success');
                                    } else {
                                        showToast('❌ Prova não encontrada. Faça uma nova correção.', 'error');
                                        closeM('m-correcao-manual');
                                    }
                                })
                                .catch(() => {
                                    showToast('❌ Não foi possível recarregar a prova.', 'error');
                                });
                        }
                    } else {
                        showToast('❌ Erro ao salvar: ' + erroMsg, 'error');
                    }
                }
            })
            .catch(erro => { 
                console.error('Erro ao salvar correção manual:', erro);
                showToast('❌ Erro ao salvar correção: ' + erro.message, 'error'); 
            });
        }
