// ═══════════════════════════════ SALVAR GABARITO - CORRIGIDO ═══════════════════════════════
async function saveGab() {
    try {
        // Coletar respostas do gabarito
        const selects = document.querySelectorAll('.gab-select');
        const respostas = [];
        let todosPreenchidos = true;
        
        selects.forEach(s => {
            if (s.value && s.value !== '') {
                respostas.push(s.value);
            } else {
                todosPreenchidos = false;
                respostas.push('');
            }
        });
        
        // Verificar se todas as questões foram preenchidas
        if (!todosPreenchidos) {
            const confirmar = confirm('⚠️ Nem todas as questões foram preenchidas. Deseja continuar mesmo assim?');
            if (!confirmar) return;
        }
        
        // Verificar se há respostas
        const respostasValidas = respostas.filter(r => r && r !== '');
        if (respostasValidas.length === 0) {
            showToast('⚠️ Preencha pelo menos uma questão do gabarito!', 'error');
            return;
        }
        
        // Obter dados adicionais
        const provaId = document.getElementById('gab-prova').value;
        const serie = document.getElementById('gab-serie').value;
        const total = document.getElementById('gab-total').value;
        const ptsAcerto = document.getElementById('pts-acerto').value || 0.5;
        const penalidade = document.getElementById('penalidade').value || 'Sem penalidade';
        const questoesAnuladas = document.getElementById('questoes-anuladas').value || '';
        
        if (!provaId || provaId === '') {
            showToast('❌ Selecione uma prova primeiro!', 'error');
            return;
        }
        
        console.log('📝 Salvando gabarito para prova ID:', provaId);
        console.log('📝 Respostas:', respostas);
        console.log('📝 Dados completos:', { provaId, serie, total, ptsAcerto, penalidade, questoesAnuladas });
        
        showToast('💾 Salvando gabarito...', 'info');
        
        // Construir a URL
        const url = `${API_URL}/api/gabaritos`;
        console.log('📤 Enviando para:', url);
        
        // Criar payload
        const payload = {
            prova_id: parseInt(provaId),
            respostas: respostas,
            serie: serie,
            total_questoes: parseInt(total),
            alternativas: '4',
            pontos_por_acerto: parseFloat(ptsAcerto),
            penalidade: penalidade,
            questoes_anuladas: questoesAnuladas
        };
        
        console.log('📦 Payload:', payload);
        
        // Enviar para o backend
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        console.log('📥 Resposta do servidor:', result);
        
        if (response.ok && result.id) {
            showToast(`✅ ${result.mensagem || 'Gabarito salvo com sucesso!'}`, 'success');
            
            // Marcar todos os selects como filled
            selects.forEach(s => {
                if (s.value && s.value !== '') s.classList.add('filled');
            });
            
            // Recarregar a lista de gabaritos
            await carregarGabaritos();
            
            // Atualizar o select de provas
            await carregarProvasSelect();
            
            // Recarregar a página de provas
            carregarProvas();
            
            // Mostrar toast com detalhes
            if (result.total_questoes) {
                showToast(`📊 ${result.total_questoes} questões salvas`, 'success');
            }
            
        } else {
            const mensagemErro = result.erro || 'Erro desconhecido';
            showToast(`❌ Erro ao salvar gabarito: ${mensagemErro}`, 'error');
            console.error('❌ Erro ao salvar gabarito:', result);
        }
        
    } catch (erro) {
        console.error('❌ Erro ao salvar gabarito:', erro);
        showToast(`❌ Erro ao salvar gabarito: ${erro.message}`, 'error');
    }
}
