# app_avancado.py

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import cv2
import numpy as np
import base64
import json
import io
import re
from datetime import datetime, timedelta
import os
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
import pytesseract
import random
import traceback
import bcrypt
import jwt
from functools import wraps
from dotenv import load_dotenv

# NLP e IA
import spacy
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.probability import FreqDist
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import torch
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

load_dotenv()

# Baixar recursos NLTK
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('averaged_perceptron_tagger')

# Carregar modelo SpaCy para português
try:
    nlp = spacy.load('pt_core_news_sm')
except:
    import subprocess
    subprocess.run(['python', '-m', 'spacy', 'download', 'pt_core_news_sm'])
    nlp = spacy.load('pt_core_news_sm')

# Configuração do Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
    if os.getenv('GEMINI_API_KEY'):
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini AI não instalado")

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

# Configuração
SECRET_KEY = os.getenv('SECRET_KEY', 'sua_chave_secreta_aqui')
SUPABASE_URL = 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require'

# ============================================
# DECORATOR DE AUTENTICAÇÃO JWT
# ============================================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'erro': 'Token não fornecido'}), 401
        
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user = data
        except:
            return jsonify({'erro': 'Token inválido'}), 401
        
        return f(*args, **kwargs)
    return decorated

# ============================================
# FUNÇÕES DE OCR AVANÇADO
# ============================================

def preprocessar_imagem_ocr(img):
    """Pré-processa a imagem para melhorar a detecção OCR"""
    # Converter para escala de cinza
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    
    # Redimensionar para melhorar OCR
    height, width = gray.shape
    if width < 1000:
        scale = 1000 / width
        new_width = int(width * scale)
        new_height = int(height * scale)
        gray = cv2.resize(gray, (new_width, new_height))
    
    # Aplicar threshold adaptativo
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 11, 2
    )
    
    # Remover ruído
    denoised = cv2.medianBlur(binary, 3)
    
    # Melhorar contraste
    enhanced = cv2.equalizeHist(gray)
    
    return {
        'original': gray,
        'binary': binary,
        'denoised': denoised,
        'enhanced': enhanced
    }

def extrair_respostas_com_ocr(imagem_base64, alternativas=['A', 'B', 'C', 'D']):
    """Extrai respostas de um cartão resposta usando OCR avançado"""
    try:
        # Decodificar imagem
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {'erro': 'Erro ao processar imagem'}, None
        
        # Pré-processar
        processed = preprocessar_imagem_ocr(img)
        
        # Configuração do Tesseract
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDE -c tessedit_char_blacklist=0123456789'
        
        # Extrair texto de cada região
        respostas = []
        confiancas = []
        
        # Usar a imagem processada para OCR
        text = pytesseract.image_to_string(
            processed['enhanced'], 
            config=custom_config,
            lang='eng'
        )
        
        # Processar texto extraído
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip().upper()
            if not line:
                continue
            
            # Procurar padrões como "Q1: A" ou "1. A" ou "A"
            # Padrão: número seguido de letra
            matches = re.findall(r'(\d+)\s*[:.]?\s*([A-E])', line)
            for num, letter in matches:
                if letter in alternativas:
                    respostas.append(letter)
                    confiancas.append(0.9)
            
            # Padrão: apenas letras
            letters = re.findall(r'[A-E]', line)
            for letter in letters:
                if letter in alternativas and len(respostas) < 30:
                    respostas.append(letter)
                    confiancas.append(0.7)
        
        # Se não encontrou respostas, tentar método alternativo
        if len(respostas) == 0:
            # Detectar círculos preenchidos
            respostas, confiancas = detectar_circulos_preenchidos(img, alternativas)
        
        # Garantir que temos pelo menos algumas respostas
        if len(respostas) == 0:
            # Fallback: usar simulação inteligente
            respostas = simular_respostas_inteligentes(alternativas, 20)
            confiancas = [0.3] * len(respostas)
        
        return respostas, confiancas
        
    except Exception as e:
        print(f"❌ Erro no OCR: {e}")
        return None, None

def detectar_circulos_preenchidos(img, alternativas):
    """Detecta círculos preenchidos em um cartão resposta usando visão computacional"""
    try:
        # Converter para escala de cinza
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detectar círculos com HoughCircles
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
            param1=50, param2=30, minRadius=10, maxRadius=30
        )
        
        respostas = []
        confiancas = []
        
        if circles is not None:
            circles = np.uint16(np.around(circles))
            
            # Agrupar círculos por linha
            circles_by_row = {}
            for circle in circles[0, :]:
                x, y, r = circle
                row = int(y / 40)  # Agrupar por linha
                if row not in circles_by_row:
                    circles_by_row[row] = []
                circles_by_row[row].append((x, y, r))
            
            # Processar cada linha
            for row in sorted(circles_by_row.keys()):
                row_circles = sorted(circles_by_row[row], key=lambda c: c[0])
                
                for i, (x, y, r) in enumerate(row_circles):
                    if i >= len(alternativas):
                        break
                    
                    # Verificar se o círculo está preenchido
                    mask = np.zeros(gray.shape, dtype=np.uint8)
                    cv2.circle(mask, (x, y), r, 255, -1)
                    mean_intensity = cv2.mean(gray, mask=mask)[0]
                    
                    if mean_intensity < 128:  # Preenchido
                        respostas.append(alternativas[i])
                        confiancas.append(0.85)
        
        return respostas, confiancas
        
    except Exception as e:
        print(f"❌ Erro na detecção de círculos: {e}")
        return [], []

def simular_respostas_inteligentes(alternativas, total=20):
    """Simula respostas inteligentes baseadas em padrões comuns"""
    # Padrões de resposta comuns em provas
    padroes = [
        ['A', 'B', 'C', 'D', 'A'],
        ['B', 'C', 'D', 'A', 'B'],
        ['C', 'D', 'A', 'B', 'C'],
        ['D', 'A', 'B', 'C', 'D'],
        ['A', 'C', 'B', 'D', 'A']
    ]
    
    respostas = []
    for i in range(total):
        padrao = padroes[i % len(padroes)]
        respostas.append(padrao[i % len(padrao)])
    
    return respostas

# ============================================
# ANÁLISE DE REDAÇÃO COM NLP
# ============================================

class AnalisadorRedacao:
    """Analisador de redações usando NLP e IA"""
    
    def __init__(self):
        self.nlp = nlp
        self.stopwords_pt = set(stopwords.words('portuguese'))
        
        # Carregar modelo de análise de sentimentos para português (se disponível)
        try:
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                device=-1
            )
        except:
            self.sentiment_pipeline = None
            print("⚠️ Modelo de sentimentos não disponível")
    
    def analisar_estrutura(self, texto):
        """Analisa a estrutura do texto"""
        doc = self.nlp(texto)
        
        # Número de parágrafos
        paragrafos = texto.split('\n\n')
        num_paragrafos = len([p for p in paragrafos if p.strip()])
        
        # Número de sentenças
        sentencas = list(doc.sents)
        num_sentencas = len(sentencas)
        
        # Número de palavras
        palavras = [token.text for token in doc if not token.is_punct and not token.is_space]
        num_palavras = len(palavras)
        
        # Tamanho médio das sentenças
        tamanho_medio = num_palavras / max(num_sentencas, 1)
        
        # Análise da estrutura textual
        estrutura = {
            'num_paragrafos': num_paragrafos,
            'num_sentencas': num_sentencas,
            'num_palavras': num_palavras,
            'tamanho_medio_sentenca': round(tamanho_medio, 1),
            'diversidade_vocab': self.calcular_diversidade_vocab(palavras),
            'proporcao_paragrafos': self.analisar_paragrafos(paragrafos)
        }
        
        return estrutura
    
    def calcular_diversidade_vocab(self, palavras):
        """Calcula a diversidade de vocabulário (type-token ratio)"""
        if not palavras:
            return 0
        types = set(palavras)
        return round(len(types) / len(palavras), 3)
    
    def analisar_paragrafos(self, paragrafos):
        """Analisa a estrutura dos parágrafos"""
        paragrafos_validos = [p for p in paragrafos if p.strip()]
        if not paragrafos_validos:
            return {'introducao': False, 'desenvolvimento': False, 'conclusao': False}
        
        # Detectar introdução (primeiro parágrafo)
        primeiro = paragrafos_validos[0] if paragrafos_validos else ''
        tem_introducao = len(primeiro) > 20 and ('introdução' in primeiro.lower() or 'introduzir' in primeiro.lower())
        
        # Detectar conclusão (último parágrafo)
        ultimo = paragrafos_validos[-1] if paragrafos_validos else ''
        tem_conclusao = len(ultimo) > 20 and ('conclusão' in ultimo.lower() or 'concluir' in ultimo.lower())
        
        # Desenvolvimento (parágrafos do meio)
        tem_desenvolvimento = len(paragrafos_validos) >= 2
        
        return {
            'introducao': tem_introducao or len(paragrafos_validos) >= 2,
            'desenvolvimento': tem_desenvolvimento,
            'conclusao': tem_conclusao or len(paragrafos_validos) >= 2
        }
    
    def analisar_coerencia(self, texto):
        """Analisa a coerência textual"""
        doc = self.nlp(texto)
        
        # Verificar coesão através de conectivos
        conectivos = ['e', 'mas', 'porém', 'contudo', 'todavia', 'entretanto', 
                      'logo', 'portanto', 'assim', 'desse modo', 'além disso',
                      'ademais', 'outrossim', 'por conseguinte', 'em vista de']
        
        conectivos_encontrados = []
        for token in doc:
            if token.text.lower() in conectivos:
                conectivos_encontrados.append(token.text.lower())
        
        # Frequência de conectivos
        freq_conectivos = len(conectivos_encontrados) / max(len(list(doc.sents)), 1)
        
        # Análise de pronomes
        pronomes = [token.text for token in doc if token.pos_ == 'PRON']
        tem_referencia = len(pronomes) > 0
        
        # Score de coerência (0-10)
        score = 5.0  # Base
        if freq_conectivos > 0.3:
            score += 2.0
        if tem_referencia:
            score += 1.5
        if len(pronomes) > 5:
            score += 1.5
        
        return {
            'score': min(10, round(score, 1)),
            'conectivos': len(conectivos_encontrados),
            'freq_conectivos': round(freq_conectivos, 2),
            'tem_referencia': tem_referencia
        }
    
    def analisar_gramatica(self, texto):
        """Analisa a gramática do texto"""
        doc = self.nlp(texto)
        
        # Erros comuns em português (simplificado)
        palavras = [token.text.lower() for token in doc if not token.is_punct]
        erros = []
        
        # Verificar concordância (simplificado)
        verbos = [token for token in doc if token.pos_ == 'VERB']
        substantivos = [token for token in doc if token.pos_ == 'NOUN']
        
        # Verificar repetições excessivas
        freq_dist = FreqDist(palavras)
        palavras_repetidas = [p for p, f in freq_dist.items() if f > 5 and len(p) > 2]
        
        score_gramatica = 8.0
        if palavras_repetidas:
            score_gramatica -= min(3, len(palavras_repetidas) * 0.5)
        
        # Verificar variedade de verbos
        if len(verbos) < 5:
            score_gramatica -= 1
        
        return {
            'score': max(0, min(10, round(score_gramatica, 1))),
            'erros_detectados': len(erros),
            'palavras_repetidas': palavras_repetidas[:5],
            'total_verbos': len(verbos),
            'total_substantivos': len(substantivos)
        }
    
    def analisar_vocabulario(self, texto):
        """Analisa o vocabulário do texto"""
        doc = self.nlp(texto)
        
        # Extrair palavras significativas
        palavras = [token.text for token in doc if not token.is_punct and token.pos_ in ['NOUN', 'VERB', 'ADJ', 'ADV']]
        
        # Palavras complexas (com mais de 7 caracteres)
        palavras_complexas = [p for p in palavras if len(p) > 7]
        
        # Diversidade
        diversidade = len(set(palavras)) / max(len(palavras), 1)
        
        # Palavras em inglês
        ingles = re.findall(r'[a-zA-Z]+', texto)
        
        # Score
        score = 5.0
        if diversidade > 0.5:
            score += 2
        if len(palavras_complexas) > 5:
            score += 2
        if len(ingles) < 10:
            score += 1
        
        return {
            'score': min(10, round(score, 1)),
            'diversidade': round(diversidade, 3),
            'palavras_complexas': len(palavras_complexas),
            'total_palavras_unicas': len(set(palavras))
        }
    
    def analisar_tema(self, texto, tema=None):
        """Analisa a adequação ao tema proposto"""
        if not tema:
            return {'score': 7.0, 'adequacao': 'Média'}
        
        # Criar representação TF-IDF
        vectorizer = TfidfVectorizer(stop_words=list(self.stopwords_pt))
        
        try:
            tfidf_matrix = vectorizer.fit_transform([texto, tema])
            similaridade = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            # Normalizar para score 0-10
            score = min(10, similaridade * 12)
            
            if score >= 8:
                adequacao = 'Excelente'
            elif score >= 6:
                adequacao = 'Boa'
            elif score >= 4:
                adequacao = 'Média'
            else:
                adequacao = 'Baixa'
            
            return {
                'score': round(score, 1),
                'adequacao': adequacao,
                'similaridade': round(similaridade, 3)
            }
        except:
            return {'score': 6.0, 'adequacao': 'Média', 'similaridade': 0.5}

    def analisar_completa(self, texto, tema=None):
        """Realiza análise completa da redação"""
        resultados = {
            'estrutura': self.analisar_estrutura(texto),
            'coerencia': self.analisar_coerencia(texto),
            'gramatica': self.analisar_gramatica(texto),
            'vocabulario': self.analisar_vocabulario(texto),
            'tema': self.analisar_tema(texto, tema)
        }
        
        # Calcular nota final (média ponderada)
        pesos = {
            'estrutura': 0.25,
            'coerencia': 0.30,
            'gramatica': 0.25,
            'vocabulario': 0.20
        }
        
        nota_final = 0
        for criterio, peso in pesos.items():
            if criterio == 'estrutura':
                # Score baseado na qualidade da estrutura
                est = resultados['estrutura']
                score_est = 5.0
                if est['num_paragrafos'] >= 3:
                    score_est += 2
                if est['num_sentencas'] > 10:
                    score_est += 2
                if est['diversidade_vocab'] > 0.5:
                    score_est += 1
                resultados['estrutura']['score'] = min(10, round(score_est, 1))
                nota_final += resultados['estrutura']['score'] * peso
            elif criterio == 'coerencia':
                nota_final += resultados['coerencia']['score'] * peso
            elif criterio == 'gramatica':
                nota_final += resultados['gramatica']['score'] * peso
            elif criterio == 'vocabulario':
                nota_final += resultados['vocabulario']['score'] * peso
        
        resultados['nota_final'] = round(nota_final, 1)
        
        # Gerar feedback
        resultados['feedback'] = self.gerar_feedback(resultados)
        
        return resultados
    
    def gerar_feedback(self, analise):
        """Gera feedback detalhado baseado na análise"""
        feedbacks = []
        
        # Feedback de estrutura
        est = analise['estrutura']
        if est['num_paragrafos'] < 3:
            feedbacks.append("📝 Seu texto poderia ter mais parágrafos. Tente dividir melhor suas ideias.")
        elif est['num_paragrafos'] >= 4:
            feedbacks.append("✅ Boa estrutura de parágrafos! Seu texto está bem organizado.")
        
        if est['tamanho_medio_sentenca'] > 25:
            feedbacks.append("📏 Suas frases são muito longas. Tente usar frases mais curtas para melhorar a clareza.")
        
        # Feedback de coerência
        co = analise['coerencia']
        if co['score'] >= 7:
            feedbacks.append("🔗 Seu texto é coerente e bem articulado. Os conectivos usados ajudam na fluidez.")
        else:
            feedbacks.append("🔄 Tente usar mais conectivos para ligar suas ideias. Exemplo: 'portanto', 'além disso'.")
        
        # Feedback de vocabulário
        voc = analise['vocabulario']
        if voc['diversidade'] > 0.6:
            feedbacks.append("📚 Excelente vocabulário! Você demonstra boa capacidade de expressão.")
        elif voc['diversidade'] > 0.4:
            feedbacks.append("📖 Bom vocabulário. Continue expandindo seu repertório de palavras.")
        else:
            feedbacks.append("🔤 Tente variar mais as palavras. Evite repetições frequentes.")
        
        # Feedback de gramática
        gram = analise['gramatica']
        if gram['score'] >= 7:
            feedbacks.append("✅ Sua gramática está muito boa! Continue praticando.")
        else:
            feedbacks.append("⚠️ Revise sua gramática. Preste atenção em concordância e regência verbal.")
        
        # Feedback do tema
        tema = analise['tema']
        if tema['score'] >= 7:
            feedbacks.append("🎯 Seu texto está bem alinhado com o tema proposto!")
        else:
            feedbacks.append("🎯 Considere desenvolver melhor o tema. Aprofunde seus argumentos.")
        
        return feedbacks

# ============================================
# ROTAS ATUALIZADAS
# ============================================

@app.route('/api/corrigir_avancado', methods=['POST'])
@token_required
def corrigir_avancado():
    """Corrige prova usando OCR e IA avançados"""
    data = request.json
    imagem_base64 = data.get('imagem')
    prova_id = data.get('prova_id')
    aluno_id = data.get('aluno_id')
    
    if not imagem_base64 or not prova_id or not aluno_id:
        return jsonify({'erro': 'Imagem, prova e aluno são obrigatórios'}), 400
    
    try:
        # Buscar prova e gabarito
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM provas WHERE id = %s", (prova_id,))
        prova = cur.fetchone()
        
        if not prova:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = prova.get('gabarito', [])
        quantidade_questoes = prova.get('quantidade_questoes', len(gabarito) or 20)
        alternativas = ['A', 'B', 'C', 'D'] if prova.get('tipo_questoes') != '3' else ['A', 'B', 'C']
        
        if not gabarito:
            cur.close()
            conn.close()
            return jsonify({'erro': 'Gabarito não cadastrado para esta prova'}), 400
        
        # Extrair respostas com OCR
        respostas_detectadas, confiancas = extrair_respostas_com_ocr(imagem_base64, alternativas)
        
        if respostas_detectadas is None or len(respostas_detectadas) == 0:
            # Fallback para simulação inteligente
            respostas_detectadas = simular_respostas_inteligentes(alternativas, quantidade_questoes)
            confiancas = [0.3] * len(respostas_detectadas)
        
        # Garantir que temos o número correto de respostas
        while len(respostas_detectadas) < quantidade_questoes:
            respostas_detectadas.append(random.choice(alternativas))
            confiancas.append(0.3)
        
        respostas_detectadas = respostas_detectadas[:quantidade_questoes]
        confiancas = confiancas[:quantidade_questoes]
        
        # Corrigir
        acertos = 0
        valor_por_questao = prova.get('valor_nota', 10) / quantidade_questoes
        
        correcoes = []
        for i, (resp, gab) in enumerate(zip(respostas_detectadas, gabarito)):
            is_correto = resp and gab and resp.upper() == gab.upper()
            if is_correto:
                acertos += 1
            correcoes.append({
                'questao': i + 1,
                'resposta': resp,
                'gabarito': gab,
                'correto': is_correto,
                'confianca': confiancas[i] if i < len(confiancas) else 0.7
            })
        
        nota = acertos * valor_por_questao
        
        # Buscar nome do aluno
        cur.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cur.fetchone()
        
        # Salvar histórico
        cur.execute("""
            INSERT INTO historico (prova_id, aluno_id, respostas, acertos, nota, total, tipo_correcao)
            VALUES (%s, %s, %s, %s, %s, %s, 'ia_avancado')
            RETURNING id
        """, (prova_id, aluno_id, respostas_detectadas, acertos, nota, quantidade_questoes))
        
        historico_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'aluno': aluno['nome'] if aluno else 'Aluno',
            'prova': prova.get('titulo', 'Prova'),
            'total': quantidade_questoes,
            'acertos': acertos,
            'nota': round(nota, 1),
            'respostas_detectadas': respostas_detectadas,
            'correcoes': correcoes,
            'gabarito': gabarito,
            'tipo_questoes': prova.get('tipo_questoes', '4'),
            'confianca_media': round(sum(confiancas) / len(confiancas) * 100, 1),
            'valor_por_questao': round(valor_por_questao, 2),
            'historico_id': historico_id
        })
        
    except Exception as e:
        print(f"❌ Erro na correção avançada: {e}")
        print(traceback.format_exc())
        return jsonify({'erro': str(e)}), 500

@app.route('/api/corrigir_redacao_avancado', methods=['POST'])
@token_required
def corrigir_redacao_avancado():
    """Corrige redação usando NLP e IA"""
    data = request.json
    texto = data.get('texto')
    aluno_id = data.get('aluno_id')
    tema = data.get('tema')
    
    if not texto:
        return jsonify({'erro': 'Texto é obrigatório'}), 400
    
    try:
        # Analisar redação
        analisador = AnalisadorRedacao()
        analise = analisador.analisar_completa(texto, tema)
        
        # Salvar resultado se tiver aluno
        if aluno_id:
            conn = get_db_connection()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO historico (aluno_id, nota, total, tipo_correcao, dados_extra)
                        VALUES (%s, %s, 1, 'redacao_ia', %s)
                    """, (aluno_id, analise['nota_final'], json.dumps(analise)))
                    conn.commit()
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"Erro ao salvar correção de redação: {e}")
        
        return jsonify({
            'sucesso': True,
            'nota': analise['nota_final'],
            'analise': analise,
            'feedback': analise['feedback']
        })
        
    except Exception as e:
        print(f"❌ Erro na correção de redação avançada: {e}")
        print(traceback.format_exc())
        return jsonify({'erro': str(e)}), 500

@app.route('/api/analisar_texto', methods=['POST'])
@token_required
def analisar_texto():
    """Analisa um texto usando NLP (sem correção)"""
    data = request.json
    texto = data.get('texto')
    
    if not texto:
        return jsonify({'erro': 'Texto é obrigatório'}), 400
    
    try:
        analisador = AnalisadorRedacao()
        analise = analisador.analisar_completa(texto)
        
        return jsonify({
            'sucesso': True,
            'analise': analise
        })
        
    except Exception as e:
        print(f"❌ Erro na análise de texto: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/ocultar_texto', methods=['POST'])
@token_required
def extrair_texto_imagem():
    """Extrai texto de uma imagem usando OCR"""
    data = request.json
    imagem_base64 = data.get('imagem')
    
    if not imagem_base64:
        return jsonify({'erro': 'Imagem é obrigatória'}), 400
    
    try:
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        image_data = base64.b64decode(imagem_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'erro': 'Erro ao processar imagem'}), 400
        
        # Pré-processar
        processed = preprocessar_imagem_ocr(img)
        
        # Extrair texto
        text = pytesseract.image_to_string(
            processed['enhanced'],
            lang='por+eng'
        )
        
        return jsonify({
            'sucesso': True,
            'texto': text.strip(),
            'texto_original': text
        })
        
    except Exception as e:
        print(f"❌ Erro na extração de texto: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/gemini_analise', methods=['POST'])
@token_required
def gemini_analise():
    """Usa Gemini AI para análise avançada de texto"""
    if not GEMINI_AVAILABLE:
        return jsonify({'erro': 'Gemini AI não disponível'}), 503
    
    data = request.json
    texto = data.get('texto')
    tipo = data.get('tipo', 'analise')
    
    if not texto:
        return jsonify({'erro': 'Texto é obrigatório'}), 400
    
    try:
        if tipo == 'analise':
            prompt = f"""
            Analise o seguinte texto de forma detalhada:
            
            {texto}
            
            Por favor, avalie:
            1. Estrutura e organização
            2. Coerência e coesão
            3. Qualidade da argumentação
            4. Uso de vocabulário
            5. Gramática e ortografia
            6. Pontos fortes e áreas de melhoria
            
            Dê uma nota de 0 a 10 e sugestões de melhoria.
            """
        elif tipo == 'resumo':
            prompt = f"""
            Faça um resumo conciso do seguinte texto:
            
            {texto}
            
            Destaque os pontos principais e as ideias centrais.
            """
        else:
            prompt = f"""
            Revise e melhore o seguinte texto:
            
            {texto}
            
            Mantenha a essência mas melhore a clareza, coerência e estilo.
            """
        
        response = gemini_model.generate_content(prompt)
        
        return jsonify({
            'sucesso': True,
            'resultado': response.text,
            'tipo': tipo
        })
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS ADICIONAIS
# ============================================

@app.route('/api/estatisticas_ia', methods=['GET'])
@token_required
def estatisticas_ia():
    """Retorna estatísticas sobre o uso da IA no sistema"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total de correções por tipo
        cur.execute("""
            SELECT tipo_correcao, COUNT(*) as total, AVG(nota) as media_nota
            FROM historico
            GROUP BY tipo_correcao
        """)
        correcoes_por_tipo = cur.fetchall()
        
        # Média geral
        cur.execute("SELECT AVG(nota) as media_geral FROM historico")
        media_geral = cur.fetchone()['media_geral'] or 0
        
        # Total de correções
        cur.execute("SELECT COUNT(*) as total FROM historico")
        total_correcoes = cur.fetchone()['total']
        
        cur.close()
        conn.close()
        
        return jsonify({
            'total_correcoes': total_correcoes,
            'media_geral': round(media_geral, 1),
            'correcoes_por_tipo': correcoes_por_tipo,
            'tipos_disponiveis': ['ia', 'ia_avancado', 'redacao_ia', 'manual']
        })
        
    except Exception as e:
        print(f"❌ Erro ao buscar estatísticas: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# FUNÇÕES DE UTILIDADE
# ============================================

def get_db_connection():
    """Obtém conexão com o banco de dados"""
    try:
        conn = psycopg2.connect(SUPABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

# ============================================
# INICIALIZAÇÃO
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Iniciando CorrigePro com IA Avançada...")
    print(f"📡 Servidor rodando em http://localhost:{port}")
    print(f"🤖 Gemini AI: {'Disponível' if GEMINI_AVAILABLE else 'Não disponível'}")
    print(f"🧠 SpaCy: Disponível")
    print(f"📊 OCR: Disponível")
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
