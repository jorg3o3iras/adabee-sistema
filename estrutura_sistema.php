<?php
// ============================================================
// LISTADOR COMPLETO DE PASTAS E ARQUIVOS
// ============================================================
// Acesse: http://seudominio.com/listar_arquivos.php
// ============================================================

// ============================================================
// CONFIGURAÇÕES
// ============================================================

// Pastas a serem ignoradas
$pastasIgnoradas = [
    '.', '..', '.git', '.vscode', 'node_modules', 'vendor',
    'tmp', 'temp', 'cache', 'logs', 'backup', 'uploads',
    'cgi-bin', '.well-known', 'error_log'
];

// Arquivos a serem ignorados
$arquivosIgnorados = [
    '.', '..', '.htaccess', '.gitignore', '.env',
    'listar_arquivos.php', 'estrutura_pastas.php', 'estrutura_sistema.php'
];

// ============================================================
// FUNÇÃO PRINCIPAL - LISTAR TODOS OS ARQUIVOS
// ============================================================

function listarTodosArquivos($dir, $nivel = 0, $ignoradosPastas = [], $ignoradosArquivos = []) {
    $resultado = [];
    
    if (!is_dir($dir)) {
        return $resultado;
    }
    
    $itens = scandir($dir);
    
    // Separar pastas e arquivos
    $pastas = [];
    $arquivos = [];
    
    foreach ($itens as $item) {
        // Pular itens ignorados
        if (in_array($item, $ignoradosPastas) || in_array($item, $ignoradosArquivos)) {
            continue;
        }
        
        $caminho = $dir . DIRECTORY_SEPARATOR . $item;
        
        if (is_dir($caminho)) {
            $pastas[] = $item;
        } else {
            $arquivos[] = $item;
        }
    }
    
    // Ordenar
    sort($pastas);
    sort($arquivos);
    
    // Adicionar pastas primeiro
    foreach ($pastas as $pasta) {
        $caminho = $dir . DIRECTORY_SEPARATOR . $pasta;
        
        // Tentar ler a pasta
        try {
            $filhos = listarTodosArquivos($caminho, $nivel + 1, $ignoradosPastas, $ignoradosArquivos);
        } catch (Exception $e) {
            $filhos = [];
        }
        
        // Contar arquivos dentro da pasta
        $totalArquivos = 0;
        $totalPastas = 0;
        $tamanhoTotal = 0;
        
        foreach ($filhos as $filho) {
            if ($filho['tipo'] === 'pasta') {
                $totalPastas++;
            } else {
                $totalArquivos++;
                $tamanhoTotal += $filho['tamanho'] ?? 0;
            }
        }
        
        $resultado[] = [
            'nome' => $pasta,
            'caminho' => $caminho,
            'nivel' => $nivel,
            'tipo' => 'pasta',
            'filhos' => $filhos,
            'total_pastas' => $totalPastas,
            'total_arquivos' => $totalArquivos,
            'tamanho_total' => $tamanhoTotal,
            'tamanho_formatado' => formatarTamanho($tamanhoTotal)
        ];
    }
    
    // Depois arquivos
    foreach ($arquivos as $arquivo) {
        $caminho = $dir . DIRECTORY_SEPARATOR . $arquivo;
        $ext = pathinfo($arquivo, PATHINFO_EXTENSION);
        $tamanho = filesize($caminho);
        $modificacao = filemtime($caminho);
        $permissao = substr(sprintf('%o', fileperms($caminho)), -4);
        
        $resultado[] = [
            'nome' => $arquivo,
            'caminho' => $caminho,
            'nivel' => $nivel,
            'tipo' => 'arquivo',
            'extensao' => $ext,
            'tamanho' => $tamanho,
            'tamanho_formatado' => formatarTamanho($tamanho),
            'modificacao' => $modificacao,
            'modificacao_formatada' => date('d/m/Y H:i:s', $modificacao),
            'permissao' => $permissao
        ];
    }
    
    return $resultado;
}

function formatarTamanho($bytes) {
    if ($bytes === 0) return '0 B';
    $k = 1024;
    $tamanhos = ['B', 'KB', 'MB', 'GB'];
    $i = floor(log($bytes) / log($k));
    return number_format($bytes / pow($k, $i), 2, ',', '.') . ' ' . $tamanhos[$i];
}

function getIcone($tipo, $ext = '') {
    if ($tipo === 'pasta') {
        return '📁';
    }
    
    $icones = [
        'php' => '🐘',
        'html' => '🌐',
        'css' => '🎨',
        'js' => '⚡',
        'json' => '📋',
        'sql' => '🗄️',
        'txt' => '📝',
        'md' => '📄',
        'ini' => '⚙️',
        'xml' => '📰',
        'log' => '📜',
        'pdf' => '📕',
        'png' => '🖼️',
        'jpg' => '🖼️',
        'jpeg' => '🖼️',
        'gif' => '🖼️',
        'svg' => '🖼️',
        'ico' => '🖼️',
        'zip' => '📦',
        'rar' => '📦',
        'gz' => '📦',
        'exe' => '⚙️',
        'bat' => '⚙️',
        'sh' => '🐚',
        'py' => '🐍',
        'rb' => '💎',
        'java' => '☕',
        'c' => '⚙️',
        'cpp' => '⚙️',
        'h' => '⚙️',
        'hpp' => '⚙️',
    ];
    
    return $icones[$ext] ?? '📄';
}

// ============================================================
// EXECUTAR
// ============================================================

$diretorioRaiz = __DIR__;
$estrutura = listarTodosArquivos(
    $diretorioRaiz, 
    0, 
    $pastasIgnoradas, 
    $arquivosIgnorados
);

// ============================================================
// CONTAR TUDO
// ============================================================

function contarTudo($itens, &$totalPastas = 0, &$totalArquivos = 0, &$tamanhoTotal = 0) {
    foreach ($itens as $item) {
        if ($item['tipo'] === 'pasta') {
            $totalPastas++;
            contarTudo($item['filhos'], $totalPastas, $totalArquivos, $tamanhoTotal);
        } else {
            $totalArquivos++;
            $tamanhoTotal += $item['tamanho'] ?? 0;
        }
    }
}

$totalPastas = 0;
$totalArquivos = 0;
$tamanhoTotal = 0;
contarTudo($estrutura, $totalPastas, $totalArquivos, $tamanhoTotal);

?>
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📂 Listar Arquivos - CAD ESCOLAR</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: #e6edf6; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 24px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.1); }
        .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 30px; border-bottom: 3px solid #0b2b4a; padding-bottom: 20px; }
        .header h1 { color: #0b2b4a; font-size: 28px; }
        .header h1 i { color: #3b8fc2; }
        .badge { background: #0b2b4a; color: white; padding: 8px 20px; border-radius: 40px; font-size: 14px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 30px; }
        .stat-card { background: #f6faff; border: 1px solid #dde8f5; border-radius: 16px; padding: 16px 20px; text-align: center; }
        .stat-card .numero { font-size: 28px; font-weight: 700; color: #0b2b4a; }
        .stat-card .label { color: #4f6f8f; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }
        .stat-card .icon { font-size: 20px; color: #3b8fc2; opacity: 0.6; }
        .search-box { margin-bottom: 20px; display: flex; gap: 12px; flex-wrap: wrap; }
        .search-box input { padding: 10px 18px; border: 2px solid #dde8f5; border-radius: 12px; font-size: 14px; flex: 1; min-width: 200px; }
        .search-box input:focus { border-color: #0b2b4a; outline: none; }
        .search-box select { padding: 10px 18px; border: 2px solid #dde8f5; border-radius: 12px; font-size: 14px; background: white; }
        .tree { padding: 10px 0; font-size: 14px; }
        .tree-item { display: flex; align-items: center; padding: 4px 8px; border-radius: 4px; transition: 0.2s; cursor: default; margin: 1px 0; }
        .tree-item:hover { background: #f0f6fe; }
        .tree-item .indent { display: inline-block; width: 20px; }
        .tree-item .icon { margin-right: 8px; font-size: 16px; width: 28px; text-align: center; }
        .tree-item .nome { font-weight: 500; }
        .tree-item .nome-pasta { color: #0b2b4a; font-weight: 700; }
        .tree-item .nome-arquivo { color: #1a3a57; }
        .tree-item .ext { color: #7a8fa5; font-size: 12px; margin-left: 4px; }
        .tree-item .info { margin-left: 12px; font-size: 12px; color: #7a8fa5; }
        .tree-item .info i { margin-right: 4px; }
        .tree-item .tamanho { background: #eef4fc; padding: 1px 10px; border-radius: 12px; font-size: 11px; color: #1a4a6e; margin-left: 8px; }
        .tree-item .data { font-size: 11px; color: #95a5a6; margin-left: 8px; }
        .tree-item .permissao { font-size: 11px; color: #7a8fa5; margin-left: 8px; font-family: monospace; }
        .tree-item .linha-conexao { display: inline-block; width: 20px; text-align: center; color: #c9d9ea; font-size: 14px; }
        .children { margin-left: 20px; border-left: 2px dashed #dde8f5; padding-left: 8px; }
        .hidden { display: none; }
        .toggle-btn { background: transparent; border: none; cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: 0.2s; font-size: 12px; }
        .toggle-btn:hover { background: #dde8f5; }
        .footer { text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dde8f5; color: #4f6f8f; font-size: 13px; }
        .footer strong { color: #0b2b4a; }
        .download-btn { background: #1e7b4a; color: white; border: none; padding: 10px 24px; border-radius: 40px; cursor: pointer; font-weight: 600; font-size: 14px; transition: 0.3s; }
        .download-btn:hover { background: #2a8f5a; transform: scale(1.02); }
        .breadcrumb { color: #4f6f8f; font-size: 13px; margin-bottom: 16px; padding: 8px 16px; background: #f6faff; border-radius: 8px; border: 1px solid #dde8f5; }
        .breadcrumb i { color: #3b8fc2; }
        .destaque { background: #fff3e0; border-left: 3px solid #b8862b; }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .container { padding: 16px; }
            .header h1 { font-size: 20px; }
            .stats { grid-template-columns: repeat(2, 1fr); }
            .tree-item { font-size: 13px; padding: 3px 6px; }
            .tree-item .info { display: none; }
            .tree-item .data { display: none; }
            .tree-item .permissao { display: none; }
        }
    </style>
</head>
<body>
<div class="container">
    <!-- HEADER -->
    <div class="header">
        <div>
            <h1><i class="fas fa-folder-tree"></i> Explorador de Arquivos</h1>
            <p style="color: #4f6f8f; margin-top: 4px;">
                <i class="fas fa-server"></i> Servidor: <strong><?= $_SERVER['SERVER_NAME'] ?></strong>
                &nbsp;|&nbsp; <i class="fas fa-folder"></i> Raiz: <strong><?= $diretorioRaiz ?></strong>
                &nbsp;|&nbsp; <i class="fas fa-calendar-alt"></i> <?= date('d/m/Y H:i:s') ?>
            </p>
        </div>
        <div>
            <button class="download-btn" onclick="window.print()">
                <i class="fas fa-print"></i> Imprimir / PDF
            </button>
        </div>
    </div>

    <!-- BREADCRUMB -->
    <div class="breadcrumb">
        <i class="fas fa-home"></i> 
        <?php
        $caminhoCompleto = explode(DIRECTORY_SEPARATOR, $diretorioRaiz);
        $caminhoAtual = '';
        foreach ($caminhoCompleto as $parte) {
            if ($parte) {
                $caminhoAtual .= DIRECTORY_SEPARATOR . $parte;
                echo ' / <span style="color:#0b2b4a;font-weight:600;">' . $parte . '</span>';
            }
        }
        ?>
    </div>

    <!-- STATS -->
    <div class="stats">
        <div class="stat-card">
            <div class="icon"><i class="fas fa-folder"></i></div>
            <div class="numero"><?= $totalPastas ?></div>
            <div class="label">Pastas</div>
        </div>
        <div class="stat-card">
            <div class="icon"><i class="fas fa-file"></i></div>
            <div class="numero"><?= $totalArquivos ?></div>
            <div class="label">Arquivos</div>
        </div>
        <div class="stat-card">
            <div class="icon"><i class="fas fa-weight-hanging"></i></div>
            <div class="numero"><?= formatarTamanho($tamanhoTotal) ?></div>
            <div class="label">Espaço Total</div>
        </div>
        <div class="stat-card">
            <div class="icon"><i class="fas fa-code"></i></div>
            <div class="numero">PHP</div>
            <div class="label">Backend</div>
        </div>
    </div>

    <!-- BUSCA -->
    <div class="search-box">
        <input type="text" id="busca" placeholder="🔍 Buscar arquivo ou pasta..." oninput="filtrarArvore()">
        <select id="filtroTipo" onchange="filtrarArvore()">
            <option value="todos">📋 Todos os tipos</option>
            <option value="pasta">📁 Pastas</option>
            <option value="php">🐘 PHP</option>
            <option value="html">🌐 HTML</option>
            <option value="css">🎨 CSS</option>
            <option value="js">⚡ JavaScript</option>
            <option value="sql">🗄️ SQL</option>
            <option value="json">📋 JSON</option>
            <option value="txt">📝 TXT</option>
            <option value="md">📄 Markdown</option>
            <option value="log">📜 Log</option>
            <option value="xml">📰 XML</option>
            <option value="png">🖼️ Imagem</option>
            <option value="jpg">🖼️ Imagem</option>
        </select>
    </div>

    <!-- ÁRVORE DE ARQUIVOS -->
    <div class="tree" id="arvore">
        <?php
        function renderizarArvore($itens, $nivel = 0) {
            foreach ($itens as $item) {
                $nome = $item['nome'];
                $tipo = $item['tipo'];
                $ext = $item['extensao'] ?? '';
                $temFilhos = $tipo === 'pasta' && !empty($item['filhos']);
                
                // Classes
                $classeNome = $tipo === 'pasta' ? 'nome-pasta' : 'nome-arquivo';
                
                // Ícone
                $icone = getIcone($tipo, $ext);
                
                // Informações
                $infoExtra = '';
                if ($tipo === 'arquivo') {
                    $tam = $item['tamanho_formatado'] ?? '0 B';
                    $mod = $item['modificacao_formatada'] ?? '';
                    $perm = $item['permissao'] ?? '';
                    $infoExtra = "<span class='tamanho'>{$tam}</span>";
                    $infoExtra .= $mod ? "<span class='data'><i class='far fa-clock'></i> {$mod}</span>" : '';
                    $infoExtra .= $perm ? "<span class='permissao'>{$perm}</span>" : '';
                } else {
                    $qtd = count($item['filhos']);
                    $tam = $item['tamanho_formatado'] ?? '0 B';
                    $infoExtra = "<span class='info'><i class='fas fa-cubes'></i> {$qtd} itens</span>";
                    $infoExtra .= "<span class='tamanho'>{$tam}</span>";
                }
                
                // Seta
                $seta = '';
                if ($temFilhos) {
                    $seta = "<button class='toggle-btn' onclick='togglePasta(this)'>
                        <i class='fas fa-chevron-down'></i>
                    </button>";
                }
                
                // Linha de conexão
                $linha = '';
                if ($nivel > 0) {
                    $linha = '├─';
                }
                
                echo "<div class='tree-item' data-nome='" . strtolower($nome) . "' data-tipo='{$tipo}' data-ext='{$ext}'>";
                echo "<span class='linha-conexao'>{$linha}</span>";
                echo "<span class='icon'>{$icone}</span>";
                echo "<span class='{$classeNome}'>{$nome}</span>";
                if ($ext && $tipo === 'arquivo') echo "<span class='ext'>.{$ext}</span>";
                echo "{$seta}";
                echo "{$infoExtra}";
                echo "</div>";
                
                // Filhos
                if ($temFilhos) {
                    echo "<div class='children' id='children_" . md5($nome . $nivel) . "'>";
                    renderizarArvore($item['filhos'], $nivel + 1);
                    echo "</div>";
                }
            }
        }
        
        renderizarArvore($estrutura);
        ?>
    </div>

    <!-- FOOTER -->
    <div class="footer">
        <p>
            <i class="fas fa-code"></i> 
            <strong>CAD ESCOLAR</strong> · v5.0 · Compatível com Educacenso 2026
            <br>
            <i class="fas fa-user-code"></i> Desenvolvido por Jorge Antonio Morais da Costa
            <br>
            <i class="fas fa-folder"></i> <strong><?= $totalPastas ?></strong> pastas · 
            <i class="fas fa-file"></i> <strong><?= $totalArquivos ?></strong> arquivos · 
            <i class="fas fa-weight-hanging"></i> <strong><?= formatarTamanho($tamanhoTotal) ?></strong>
        </p>
    </div>
</div>

<script>
// ============================================================
// FUNÇÕES DE INTERAÇÃO
// ============================================================

function togglePasta(btn) {
    const div = btn.closest('.tree-item');
    const children = div.nextElementSibling;
    const icon = btn.querySelector('i');
    
    if (children) {
        if (children.classList.contains('hidden')) {
            children.classList.remove('hidden');
            icon.className = 'fas fa-chevron-down';
        } else {
            children.classList.add('hidden');
            icon.className = 'fas fa-chevron-right';
        }
    }
}

function filtrarArvore() {
    const busca = document.getElementById('busca').value.toLowerCase().trim();
    const filtroTipo = document.getElementById('filtroTipo').value;
    
    const itens = document.querySelectorAll('.tree-item');
    
    itens.forEach(item => {
        const nome = item.dataset.nome || '';
        const tipo = item.dataset.tipo || '';
        const ext = item.dataset.ext || '';
        
        let mostrar = true;
        
        // Filtro por busca
        if (busca && !nome.includes(busca)) {
            mostrar = false;
        }
        
        // Filtro por tipo
        if (filtroTipo !== 'todos') {
            if (filtroTipo === 'pasta' && tipo !== 'pasta') {
                mostrar = false;
            } else if (filtroTipo !== 'pasta' && ext !== filtroTipo) {
                mostrar = false;
            }
        }
        
        item.style.display = mostrar ? '' : 'none';
    });
    
    // Abrir pastas que contêm itens visíveis
    document.querySelectorAll('.children').forEach(children => {
        const temVisivel = children.querySelector('.tree-item:not([style*="display: none"])');
        const pai = children.previousElementSibling;
        
        if (pai) {
            const btn = pai.querySelector('.toggle-btn');
            if (temVisivel && busca) {
                children.classList.remove('hidden');
                if (btn) {
                    const icon = btn.querySelector('i');
                    icon.className = 'fas fa-chevron-down';
                }
            } else if (busca && !temVisivel) {
                children.classList.add('hidden');
                if (btn) {
                    const icon = btn.querySelector('i');
                    icon.className = 'fas fa-chevron-right';
                }
            }
        }
    });
}

// Abrir tudo inicialmente
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.children').forEach(children => {
        children.classList.remove('hidden');
    });
});
</script>
</body>
</html>