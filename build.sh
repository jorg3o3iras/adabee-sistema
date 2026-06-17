#!/bin/bash
echo "=========================================="
echo "🚀 INICIANDO BUILD DO ADABEE AI"
echo "=========================================="

# Instalar Tesseract e dependências
echo "📦 Instalando Tesseract OCR..."
apt-get update
apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \
    libtesseract-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    wget \
    curl

# Verificar instalação do Tesseract
echo "✅ Verificando Tesseract..."
tesseract --version || echo "⚠️ Tesseract não encontrado!"

# Instalar dependências Python
echo "📦 Instalando dependências Python..."
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

echo "=========================================="
echo "✅ BUILD CONCLUÍDO COM SUCESSO!"
echo "=========================================="
