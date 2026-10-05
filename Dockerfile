FROM python:3.11-slim

# Instalar TODAS as dependências de sistema necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libzbar0 \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# 2 workers + 4 threads cada, timeout maior para OpenCV
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:10000", \
     "--timeout", "180", \
     "--workers", "2", \
     "--threads", "4", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
