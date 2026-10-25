#!/bin/bash
echo "=========================================="
echo "🚀 INICIANDO BUILD DO CORRIGEPRO v4.0"
echo "=========================================="

# Instalar dependências de SISTEMA (para OpenCV e pyzbar)
echo "📦 Instalando dependências de sistema..."

# Detecta o gerenciador de pacotes (apt para Debian/Ubuntu)
if command -v apt-get > /dev/null; then
    apt-get update
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libzbar0 \
        libpq-dev \
        gcc \
        wget \
        curl
    echo "✅ Dependências de sistema instaladas via apt"
else
    echo "⚠️ apt-get não encontrado. Assumindo que as libs já estão instaladas."
fi

# Verificar libzbar (CRÍTICO para QR Code)
echo "🔍 Verificando libzbar..."
if ldconfig -p | grep -q libzbar; then
    echo "✅ libzbar0 OK"
else
    echo "❌ libzbar0 NÃO encontrada! O QR Code não vai funcionar."
fi

# Instalar dependências Python
echo "📦 Instalando dependências Python..."
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

# Verificar imports críticos
echo "🔍 Verificando imports críticos..."
python -c "import cv2; print(f'✅ OpenCV {cv2.__version__}')" || echo "❌ OpenCV falhou"
python -c "import numpy; print(f'✅ Numpy {numpy.__version__}')" || echo "❌ Numpy falhou"
python -c "from pyzbar.pyzbar import decode; print('✅ pyzbar OK')" || echo "⚠️ pyzbar falhou (QR Code não vai funcionar)"
python -c "import qrcode; print('✅ qrcode OK')" || echo "⚠️ qrcode falhou"

echo "=========================================="
echo "✅ BUILD CONCLUÍDO COM SUCESSO!"
echo "=========================================="
