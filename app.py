from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import io
import csv
import re
from datetime import datetime
import os
from PIL import Image
import psycopg2
from psycopg2.extras import RealDictCursor
import pytesseract
import hashlib
import secrets
from functools import wraps

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================

SUPABASE_URL = 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require'

def get_db_connection():
    try:
        conn = psycopg2.connect(
            SUPABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=15,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3
        )
        return conn
    except Exception as e:
        print(f"❌ ERRO ao conectar: {e}")
        raise e

def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ESCOLAS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS escolas (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                inep TEXT,
                municipio TEXT,
                estado TEXT,
                telefone TEXT,
                diretor TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # TURMAS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS turmas (
                id SERIAL PRIMARY KEY,
                escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                serie TEXT DEFAULT '1º Ano',
                turno TEXT DEFAULT 'Manhã',
                professor TEXT,
                capacidade INTEGER DEFAULT 35,
                ano_letivo INTEGER DEFAULT 2025,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ALUNOS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alunos (
                id SERIAL PRIMARY KEY,
                turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                matricula TEXT,
                numero_chamada INTEGER,
                data_nascimento DATE,
                genero TEXT,
                responsavel TEXT,
                telefone TEXT,
                email TEXT,
                observacoes TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # PROVAS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS provas (
                id SERIAL PRIMARY KEY,
                turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
                titulo TEXT NOT NULL,
                disciplina TEXT,
                bimestre TEXT,
                descricao TEXT,
                gabarito TEXT,
                data_prova DATE,
                valor_nota REAL DEFAULT 10,
                quantidade_questoes INTEGER,
                tipo_questoes TEXT DEFAULT '4',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # GABARITOS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gabaritos (
                id SERIAL PRIMARY KEY,
                prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                serie TEXT NOT NULL,
                total_questoes INTEGER DEFAULT 20,
                alternativas TEXT DEFAULT 'A,B,C,D',
                respostas TEXT,
                pontos_por_acerto REAL DEFAULT 0.5,
                penalidade REAL DEFAULT 0,
                questoes_anuladas TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # CORRECOES
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS correcoes (
                id SERIAL PRIMARY KEY,
                prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                respostas TEXT,
                acertos INTEGER,
                nota REAL,
                data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metodo_ia TEXT DEFAULT 'hibrido',
                confianca REAL DEFAULT 0
            )
        ''')
        
        # CORRECOES_REDACAO
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS correcoes_redacao (
                id SERIAL PRIMARY KEY,
                prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
                aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
                texto TEXT,
                nota REAL,
                feedback TEXT,
                metricas JSONB,
                data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metodo_ia TEXT DEFAULT 'hibrido'
            )
        ''')
        
        # CONFIGURACOES
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracoes (
                id SERIAL PRIMARY KEY,
                chave TEXT UNIQUE NOT NULL,
                valor TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # USUARIOS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT DEFAULT 'usuario',
                nome TEXT,
                email TEXT,
                ativo BOOLEAN DEFAULT TRUE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # INSERIR USUÁRIOS PADRÃO
        cursor.execute("INSERT INTO usuarios (username, senha_hash, perfil, nome) VALUES ('admin', 'admin', 'admin', 'Administrador') ON CONFLICT (username) DO NOTHING")
        cursor.execute("INSERT INTO usuarios (username, senha_hash, perfil, nome) VALUES ('usuario', '123', 'usuario', 'Usuário Padrão') ON CONFLICT (username) DO NOTHING")
        
        # INSERIR CONFIGURAÇÕES PADRÃO
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('nota_maxima', '10') ON CONFLICT (chave) DO NOTHING")
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('nota_minima_aprovacao', '5') ON CONFLICT (chave) DO NOTHING")
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('metodo_correcao', 'hibrido') ON CONFLICT (chave) DO NOTHING")
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('confianca_minima', '0.7') ON CONFLICT (chave) DO NOTHING")
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('param1', '80') ON CONFLICT (chave) DO NOTHING")
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('param2', '25') ON CONFLICT (chave) DO NOTHING")
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")

# ============================================
# CLASSE CORRETOR HÍBRIDO
# ============================================

class CorretorHibrido:
    @staticmethod
    def preprocessar_imagem(imagem_base64):
        try:
            if ',' in imagem_base64:
                imagem_base64 = imagem_base64.split(',')[1]
            imagem_bytes = base64.b64decode(imagem_base64)
            nparr = np.frombuffer(imagem_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            height, width = img.shape[:2]
            if width > 1200:
                scale = 1200 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = cv2.resize(img, (new_width, new_height))
            return img
        except Exception as e:
            print(f"Erro no pré-processamento: {e}")
            return None
    
    @staticmethod
    def detectar_bolinhas_com_preenchimento(imagem_base64):
        try:
            img = CorretorHibrido.preprocessar_imagem(imagem_base64)
            if img is None:
                return None
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            gray = clahe.apply(gray)
            
            _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            bolinhas = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 50 < area < 400:
                    M = cv2.moments(cnt)
                    if M['m00'] > 0:
                        cx = int(M['m10'] / M['m00'])
                        cy = int(M['m01'] / M['m00'])
                        perimeter = cv2.arcLength(cnt, True)
                        if perimeter > 0:
                            circularity = 4 * np.pi * area / (perimeter * perimeter)
                            if circularity > 0.5:
                                mask = np.zeros_like(gray)
                                cv2.drawContours(mask, [cnt], -1, 255, -1)
                                roi = cv2.bitwise_and(gray, gray, mask=mask)
                                pixels = roi[roi > 0]
                                if len(pixels) > 0:
                                    intensidade_media = np.mean(pixels)
                                    preenchimento = 1 - (intensidade_media / 255)
                                    bolinhas.append({
                                        'x': cx,
                                        'y': cy,
                                        'area': area,
                                        'preenchimento': preenchimento,
                                        'intensidade': intensidade_media
                                    })
            return bolinhas
        except Exception as e:
            print(f"Erro ao detectar bolinhas: {e}")
            return None
    
    @staticmethod
    def detectar_respostas_com_preenchimento(imagem_base64, num_opcoes=4):
        try:
            bolinhas = CorretorHibrido.detectar_bolinhas_com_preenchimento(imagem_base64)
            if not bolinhas or len(bolinhas) == 0:
                return None, 0.0, 'Nenhuma bolinha detectada'
            
            bolinhas.sort(key=lambda b: b['y'])
            linhas = []
            linha_atual = []
            y_anterior = bolinhas[0]['y']
            tolerancia_y = 20
            
            for bolinha in bolinhas:
                if abs(bolinha['y'] - y_anterior) > tolerancia_y and linha_atual:
                    linhas.append(linha_atual)
                    linha_atual = []
                linha_atual.append(bolinha)
                y_anterior = bolinha['y']
            
            if linha_atual:
                linhas.append(linha_atual)
            
            respostas = []
            letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            
            for idx, linha in enumerate(linhas, start=1):
                if idx > 50:
                    break
                linha.sort(key=lambda b: b['x'])
                linha = linha[:num_opcoes]
                if len(linha) == 0:
                    respostas.append((idx, '?'))
                    continue
                
                melhor_preenchimento = -1
                melhor_pos = -1
                
                for pos, bolinha in enumerate(linha):
                    if bolinha['preenchimento'] > melhor_preenchimento:
                        melhor_preenchimento = bolinha['preenchimento']
                        melhor_pos = pos
                
                if melhor_pos >= 0 and melhor_preenchimento > 0.20:
                    resposta = letras[melhor_pos] if melhor_pos < len(letras) else '?'
                    respostas.append((idx, resposta))
                else:
                    respostas.append((idx, '?'))
            
            if len(respostas) == 0:
                return None, 0.0, 'Nenhuma resposta detectada'
            
            respostas.sort(key=lambda x: x[0])
            letras_respostas = [r[1] for r in respostas]
            validas = sum(1 for r in letras_respostas if r != '?')
            confianca = round((validas / len(letras_respostas)) * 100, 1)
            
            return letras_respostas, confianca, 'Preenchimento'
            
        except Exception as e:
            print(f"Erro na detecção por preenchimento: {e}")
            return None, 0.0, 'Erro'
    
    @staticmethod
    def detectar_respostas_hibrido(imagem_base64, num_opcoes=4):
        respostas, confianca, metodo = CorretorHibrido.detectar_respostas_com_preenchimento(imagem_base64, num_opcoes)
        if respostas and len(respostas) >= 3:
            return respostas, confianca, metodo
        return None, 0.0, 'Nenhum método funcionou'

# ============================================
# CLASSE PARA CORREÇÃO DE REDAÇÃO
# ============================================

class CorretorRedacaoHibrido:
    @staticmethod
    def extrair_texto_ocr(imagem_base64):
        try:
            if ',' in imagem_base64:
                imagem_base64 = imagem_base64.split(',')[1]
            imagem_bytes = base64.b64decode(imagem_base64)
            nparr = np.frombuffer(imagem_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            custom_config = r'--oem 3 --psm 6 -l por'
            text = pytesseract.image_to_string(binary, config=custom_config)
            return text.strip() if text.strip() else None
        except Exception as e:
            print(f"Erro ao extrair texto: {e}")
            return None
    
    @staticmethod
    def analisar_redacao(texto):
        palavras = texto.split()
        num_palavras = len(palavras)
        num_frases = len(re.split(r'[.!?]+', texto)) - 1
        num_paragrafos = len(texto.split('\n\n')) if '\n\n' in texto else 1
        
        palavras_unicas = len(set([p.lower() for p in palavras]))
        proporcao_vocabulario = (palavras_unicas / num_palavras) * 100 if num_palavras > 0 else 0
        
        conectores = ['e', 'mas', 'porém', 'contudo', 'entretanto', 'portanto', 'assim', 'logo', 'pois', 'porque', 'além', 'também', 'bem como', 'da mesma forma', 'outrossim', 'todavia', 'conquanto', 'embora', 'apesar', 'enquanto', 'quando', 'como', 'onde', 'cujo', 'que', 'qual', 'quem']
        num_conectores = sum(1 for p in palavras if p.lower() in conectores)
        
        if num_palavras >= 200:
            nota_coerencia = 8.0
        elif num_palavras >= 150:
            nota_coerencia = 6.0
        elif num_palavras >= 100:
            nota_coerencia = 4.0
        elif num_palavras >= 50:
            nota_coerencia = 2.0
        else:
            nota_coerencia = 0.0
        
        if num_paragrafos >= 3 and num_frases >= 8:
            nota_estrutura = 8.0
        elif num_paragrafos >= 2 and num_frases >= 5:
            nota_estrutura = 6.0
        elif num_paragrafos >= 1 and num_frases >= 3:
            nota_estrutura = 4.0
        else:
            nota_estrutura = 2.0
        
        if proporcao_vocabulario >= 60:
            nota_vocabulario = 8.0
        elif proporcao_vocabulario >= 45:
            nota_vocabulario = 6.0
        elif proporcao_vocabulario >= 30:
            nota_vocabulario = 4.0
        else:
            nota_vocabulario = 2.0
        
        if num_conectores >= 10:
            nota_gramatica = 8.0
        elif num_conectores >= 6:
            nota_gramatica = 6.0
        elif num_conectores >= 3:
            nota_gramatica = 4.0
        else:
            nota_gramatica = 2.0
        
        nota_final = (nota_coerencia * 0.3 + nota_estrutura * 0.25 + 
                     nota_vocabulario * 0.25 + nota_gramatica * 0.2)
        nota_final = round(nota_final * 2) / 2
        
        feedback_parts = []
        
        if num_palavras >= 200:
            feedback_parts.append("✅ Ótimo desenvolvimento do tema. Texto bem extenso e detalhado.")
        elif num_palavras >= 150:
            feedback_parts.append("✅ Bom desenvolvimento. Continue expandindo suas ideias.")
        elif num_palavras >= 100:
            feedback_parts.append("📝 Desenvolvimento razoável. Tente aprofundar mais seus argumentos.")
        elif num_palavras >= 50:
            feedback_parts.append("⚠️ Texto curto. É importante desenvolver mais suas ideias.")
        else:
            feedback_parts.append("❌ Texto muito curto. É necessário desenvolver mais o conteúdo.")
        
        if num_paragrafos >= 3:
            feedback_parts.append("✅ Boa organização em parágrafos. Estrutura clara.")
        elif num_paragrafos >= 2:
            feedback_parts.append("📝 Estrutura razoável. Tente dividir melhor em parágrafos.")
        else:
            feedback_parts.append("⚠️ Poucos parágrafos. Organize melhor suas ideias.")
        
        if proporcao_vocabulario >= 60:
            feedback_parts.append("✅ Vocabulário rico e variado. Ótimo uso de palavras.")
        elif proporcao_vocabulario >= 45:
            feedback_parts.append("✅ Bom vocabulário. Continue expandindo seu repertório.")
        else:
            feedback_parts.append("📝 Vocabulário limitado. Busque usar palavras mais variadas.")
        
        if num_conectores >= 8:
            feedback_parts.append("✅ Excelente uso de conectores. Texto muito coeso.")
        elif num_conectores >= 5:
            feedback_parts.append("✅ Bom uso de conectores. Texto coeso.")
        else:
            feedback_parts.append("📝 Poucos conectores. Use mais palavras de ligação.")
        
        dicas = []
        if num_palavras < 150:
            dicas.append("📌 Escreva mais sobre o tema, desenvolvendo cada argumento.")
        if num_paragrafos < 3:
            dicas.append("📌 Divida seu texto em introdução, desenvolvimento e conclusão.")
        if proporcao_vocabulario < 45:
            dicas.append("📌 Busque sinônimos e evite repetir as mesmas palavras.")
        if num_conectores < 5:
            dicas.append("📌 Use mais conectores como 'portanto', 'contudo', 'além disso'.")
        
        if dicas:
            feedback_parts.append("\n💡 **Dicas para melhorar:**")
            feedback_parts.extend(dicas)
        
        if nota_final >= 8:
            conceito = "Excelente"
        elif nota_final >= 6:
            conceito = "Bom"
        elif nota_final >= 4:
            conceito = "Regular"
        else:
            conceito = "Insuficiente"
        
        feedback_completo = "\n\n".join(feedback_parts)
        
        metricas = {
            'palavras': num_palavras,
            'frases': num_frases,
            'paragrafos': num_paragrafos,
            'palavras_unicas': palavras_unicas,
            'proporcao_vocabulario': round(proporcao_vocabulario, 1),
            'conectores': num_conectores,
            'nota_coerencia': round(nota_coerencia, 1),
            'nota_estrutura': round(nota_estrutura, 1),
            'nota_vocabulario': round(nota_vocabulario, 1),
            'nota_gramatica': round(nota_gramatica, 1)
        }
        
        return nota_final, conceito, feedback_completo, metricas
    
    @staticmethod
    def corrigir_redacao_hibrido(imagem_base64=None, texto=None):
        if not texto and imagem_base64:
            texto = CorretorRedacaoHibrido.extrair_texto_ocr(imagem_base64)
        
        if not texto:
            return None, 0.0, None, "Não foi possível extrair o texto", None
        
        nota, conceito, feedback, metricas = CorretorRedacaoHibrido.analisar_redacao(texto)
        
        return texto, nota, conceito, feedback, metricas, 'OCR + Análise Avançada'

# ============================================
# ROTAS - AUTENTICAÇÃO
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    try:
        dados = request.json
        username = dados.get('username')
        senha = dados.get('senha')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE username = %s AND senha_hash = %s AND ativo = TRUE", (username, senha))
        usuario = cursor.fetchone()
        conn.close()
        
        if usuario:
            return jsonify({
                'sucesso': True,
                'usuario': usuario['username'],
                'perfil': usuario['perfil'],
                'nome': usuario['nome']
            })
        else:
            return jsonify({'sucesso': False, 'mensagem': 'Usuário ou senha inválidos'}), 401
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - ESCOLAS
# ============================================

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM escolas ORDER BY nome")
        escolas = []
        for row in cursor.fetchall():
            escolas.append({
                'id': row['id'],
                'nome': row['nome'],
                'inep': row.get('inep'),
                'municipio': row.get('municipio'),
                'estado': row.get('estado'),
                'telefone': row.get('telefone'),
                'diretor': row.get('diretor')
            })
        conn.close()
        return jsonify(escolas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO escolas (nome, inep, municipio, estado, telefone, diretor)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            dados.get('nome'),
            dados.get('inep'),
            dados.get('municipio'),
            dados.get('estado'),
            dados.get('telefone'),
            dados.get('diretor')
        ))
        escola_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': escola_id, 'mensagem': 'Escola cadastrada com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:escola_id>', methods=['PUT'])
def atualizar_escola(escola_id):
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE escolas SET 
                nome = %s, inep = %s, municipio = %s, estado = %s, 
                telefone = %s, diretor = %s
            WHERE id = %s
        """, (
            dados.get('nome'),
            dados.get('inep'),
            dados.get('municipio'),
            dados.get('estado'),
            dados.get('telefone'),
            dados.get('diretor'),
            escola_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Escola atualizada com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas/<int:escola_id>', methods=['DELETE'])
def deletar_escola(escola_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM escolas WHERE id = %s", (escola_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Escola excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - TURMAS
# ============================================

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    try:
        escola_id = request.args.get('escola_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if escola_id:
            cursor.execute("""
                SELECT t.*, e.nome as escola_nome 
                FROM turmas t 
                LEFT JOIN escolas e ON t.escola_id = e.id 
                WHERE t.escola_id = %s 
                ORDER BY t.serie, t.nome
            """, (escola_id,))
        else:
            cursor.execute("""
                SELECT t.*, e.nome as escola_nome 
                FROM turmas t 
                LEFT JOIN escolas e ON t.escola_id = e.id 
                ORDER BY t.serie, t.nome
            """)
        
        turmas = []
        for row in cursor.fetchall():
            turmas.append({
                'id': row['id'],
                'escola_id': row['escola_id'],
                'escola_nome': row.get('escola_nome'),
                'nome': row['nome'],
                'serie': row['serie'],
                'turno': row.get('turno'),
                'professor': row.get('professor'),
                'capacidade': row.get('capacidade'),
                'ano_letivo': row.get('ano_letivo')
            })
        conn.close()
        return jsonify(turmas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO turmas (escola_id, nome, serie, turno, professor, capacidade, ano_letivo)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            dados.get('escola_id'),
            dados.get('nome'),
            dados.get('serie', '1º Ano'),
            dados.get('turno', 'Manhã'),
            dados.get('professor'),
            dados.get('capacidade', 35),
            dados.get('ano_letivo', 2025)
        ))
        turma_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': turma_id, 'mensagem': 'Turma cadastrada com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:turma_id>', methods=['DELETE'])
def deletar_turma(turma_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM turmas WHERE id = %s", (turma_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Turma excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - ALUNOS
# ============================================

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    try:
        turma_id = request.args.get('turma_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if turma_id:
            cursor.execute("""
                SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
                FROM alunos a 
                LEFT JOIN turmas t ON a.turma_id = t.id 
                LEFT JOIN escolas e ON t.escola_id = e.id 
                WHERE a.turma_id = %s 
                ORDER BY a.numero_chamada
            """, (turma_id,))
        else:
            cursor.execute("""
                SELECT a.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
                FROM alunos a 
                LEFT JOIN turmas t ON a.turma_id = t.id 
                LEFT JOIN escolas e ON t.escola_id = e.id 
                ORDER BY a.numero_chamada
            """)
        
        alunos = []
        for row in cursor.fetchall():
            alunos.append({
                'id': row['id'],
                'turma_id': row['turma_id'],
                'turma_nome': row.get('turma_nome'),
                'turma_serie': row.get('turma_serie'),
                'escola_nome': row.get('escola_nome'),
                'nome': row['nome'],
                'matricula': row.get('matricula'),
                'numero_chamada': row.get('numero_chamada'),
                'data_nascimento': str(row.get('data_nascimento')) if row.get('data_nascimento') else None,
                'genero': row.get('genero'),
                'responsavel': row.get('responsavel'),
                'telefone': row.get('telefone'),
                'email': row.get('email'),
                'observacoes': row.get('observacoes')
            })
        conn.close()
        return jsonify(alunos)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alunos (turma_id, nome, matricula, numero_chamada, data_nascimento, 
                genero, responsavel, telefone, email, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            dados.get('turma_id'),
            dados.get('nome'),
            dados.get('matricula'),
            dados.get('numero_chamada'),
            dados.get('data_nascimento'),
            dados.get('genero'),
            dados.get('responsavel'),
            dados.get('telefone'),
            dados.get('email'),
            dados.get('observacoes')
        ))
        aluno_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': aluno_id, 'mensagem': 'Aluno cadastrado com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos/<int:aluno_id>', methods=['DELETE'])
def deletar_aluno(aluno_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alunos WHERE id = %s", (aluno_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Aluno excluído com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - PROVAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, t.nome as turma_nome, t.serie as turma_serie, e.nome as escola_nome
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            LEFT JOIN escolas e ON t.escola_id = e.id 
            ORDER BY p.data_prova DESC
        """)
        
        provas = []
        for row in cursor.fetchall():
            provas.append({
                'id': row['id'],
                'turma_id': row['turma_id'],
                'turma_nome': row.get('turma_nome'),
                'turma_serie': row.get('turma_serie'),
                'escola_nome': row.get('escola_nome'),
                'titulo': row['titulo'],
                'disciplina': row.get('disciplina'),
                'bimestre': row.get('bimestre'),
                'descricao': row.get('descricao'),
                'gabarito': json.loads(row['gabarito']) if row['gabarito'] else [],
                'data_prova': str(row['data_prova']) if row['data_prova'] else None,
                'valor_nota': row['valor_nota'],
                'quantidade_questoes': row['quantidade_questoes'] or 0,
                'tipo_questoes': row['tipo_questoes'] or '4'
            })
        conn.close()
        return jsonify(provas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, disciplina, bimestre, descricao, 
                gabarito, data_prova, valor_nota, quantidade_questoes, tipo_questoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            dados.get('turma_id'),
            dados.get('titulo'),
            dados.get('disciplina'),
            dados.get('bimestre'),
            dados.get('descricao'),
            json.dumps(dados.get('gabarito', [])),
            dados.get('data_prova'),
            dados.get('valor_nota', 10),
            len(dados.get('gabarito', [])),
            dados.get('tipo_questoes', '4')
        ))
        prova_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': prova_id, 'mensagem': 'Prova criada com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correcoes WHERE prova_id = %s", (prova_id,))
        cursor.execute("DELETE FROM correcoes_redacao WHERE prova_id = %s", (prova_id,))
        cursor.execute("DELETE FROM gabaritos WHERE prova_id = %s", (prova_id,))
        cursor.execute("DELETE FROM provas WHERE id = %s", (prova_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Prova excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - GABARITOS
# ============================================

@app.route('/api/gabaritos', methods=['POST'])
def salvar_gabarito():
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gabaritos (prova_id, serie, total_questoes, alternativas, 
                respostas, pontos_por_acerto, penalidade, questoes_anuladas)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            dados.get('prova_id'),
            dados.get('serie'),
            dados.get('total_questoes', 20),
            dados.get('alternativas', 'A,B,C,D'),
            json.dumps(dados.get('respostas', [])),
            dados.get('pontos_por_acerto', 0.5),
            dados.get('penalidade', 0),
            dados.get('questoes_anuladas', '')
        ))
        gabarito_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': gabarito_id, 'mensagem': 'Gabarito salvo com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/gabaritos/<int:prova_id>', methods=['GET'])
def buscar_gabarito(prova_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gabaritos WHERE prova_id = %s ORDER BY id DESC LIMIT 1", (prova_id,))
        gabarito = cursor.fetchone()
        conn.close()
        if gabarito:
            return jsonify({
                'id': gabarito['id'],
                'prova_id': gabarito['prova_id'],
                'serie': gabarito['serie'],
                'total_questoes': gabarito['total_questoes'],
                'alternativas': gabarito['alternativas'],
                'respostas': json.loads(gabarito['respostas']) if gabarito['respostas'] else [],
                'pontos_por_acerto': gabarito['pontos_por_acerto'],
                'penalidade': gabarito['penalidade'],
                'questoes_anuladas': gabarito['questoes_anuladas']
            })
        return jsonify(None)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - CORREÇÃO DE PROVAS
# ============================================

@app.route('/api/corrigir', methods=['POST'])
def corrigir_prova():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        prova_id = dados.get('prova_id')
        aluno_id = dados.get('aluno_id')
        
        if not imagem or not prova_id or not aluno_id:
            return jsonify({'erro': 'Dados incompletos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT gabarito, tipo_questoes, titulo, valor_nota FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova['gabarito']) if prova['gabarito'] else []
        tipo_questoes = int(prova['tipo_questoes'] or 4)
        titulo_prova = prova['titulo']
        valor_nota = prova['valor_nota'] or 10
        
        corretor = CorretorHibrido()
        respostas_detectadas, confianca, metodo = corretor.detectar_respostas_hibrido(imagem, tipo_questoes)
        
        if not respostas_detectadas:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as respostas'}), 400
        
        while len(respostas_detectadas) < len(gabarito):
            respostas_detectadas.append('?')
        respostas_detectadas = respostas_detectadas[:len(gabarito)]
        
        acertos = 0
        correcoes = []
        for i in range(len(gabarito)):
            resposta = respostas_detectadas[i] if i < len(respostas_detectadas) else '?'
            correta = resposta == gabarito[i] if resposta != '?' else False
            if correta:
                acertos += 1
            correcoes.append({
                'questao': i+1, 
                'resposta': resposta, 
                'gabarito': gabarito[i], 
                'correta': correta
            })
        
        nota = (acertos / len(gabarito)) * valor_nota if gabarito else 0
        
        cursor.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        aluno_nome = aluno['nome'] if aluno else 'Aluno'
        
        cursor.execute("""
            INSERT INTO correcoes (prova_id, aluno_id, respostas, acertos, nota, data_correcao, metodo_ia, confianca) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (prova_id, aluno_id, json.dumps(respostas_detectadas), acertos, nota, datetime.now(), metodo, confianca))
        conn.commit()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome,
            'prova': titulo_prova,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round((acertos / len(gabarito)) * 100, 1) if gabarito else 0,
            'correcoes': correcoes,
            'confianca': round(confianca, 1),
            'metodo_ia': metodo,
            'tipo_questoes': tipo_questoes
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - CORREÇÃO DE REDAÇÃO
# ============================================

@app.route('/api/corrigir_redacao', methods=['POST'])
def corrigir_redacao():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        texto = dados.get('texto')
        prova_id = dados.get('prova_id')
        aluno_id = dados.get('aluno_id')
        
        if not imagem and not texto:
            return jsonify({'erro': 'Forneça imagem ou texto da redação'}), 400
        
        corretor = CorretorRedacaoHibrido()
        resultado = corretor.corrigir_redacao_hibrido(imagem, texto)
        
        if resultado is None or resultado[0] is None:
            return jsonify({'erro': 'Não foi possível processar a redação'}), 400
        
        texto_corrigido, nota, conceito, feedback, metricas, metodo = resultado
        
        if prova_id and aluno_id:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO correcoes_redacao (prova_id, aluno_id, texto, nota, feedback, metricas, data_correcao, metodo_ia) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (prova_id, aluno_id, texto_corrigido, nota, feedback, json.dumps(metricas), datetime.now(), metodo))
                conn.commit()
                conn.close()
        
        cores = {
            'Excelente': '#28a745',
            'Bom': '#17a2b8',
            'Regular': '#ffc107',
            'Insuficiente': '#dc3545'
        }
        
        return jsonify({
            'nota': round(nota, 1),
            'conceito': conceito,
            'cor_conceito': cores.get(conceito, '#6c757d'),
            'feedback': feedback,
            'metricas': metricas,
            'texto_original': texto_corrigido[:500] + ('...' if len(texto_corrigido) > 500 else ''),
            'texto_completo': texto_corrigido,
            'metodo_ia': metodo
        })
        
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - DASHBOARD E ESTATÍSTICAS
# ============================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM escolas")
        row = cursor.fetchone()
        total_escolas = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*) FROM turmas")
        row = cursor.fetchone()
        total_turmas = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*) FROM alunos")
        row = cursor.fetchone()
        total_alunos = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*) FROM provas")
        row = cursor.fetchone()
        total_provas = row['count'] if row else 0
        
        cursor.execute("SELECT COUNT(*), COALESCE(AVG(nota), 0) FROM correcoes")
        row = cursor.fetchone()
        
        conn.close()
        return jsonify({
            'total_escolas': total_escolas,
            'total_turmas': total_turmas,
            'total_alunos': total_alunos,
            'total_provas': total_provas,
            'total_correcoes': row['count'] if row else 0,
            'media_geral': round(row['coalesce'], 1) if row and row['coalesce'] else 0
        })
    except Exception as e:
        print(f"Erro no dashboard: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/historico', methods=['GET'])
def historico():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, a.nome as aluno_nome, p.titulo as prova_titulo, 
                   c.acertos, c.nota, c.data_correcao, c.metodo_ia
            FROM correcoes c 
            JOIN alunos a ON c.aluno_id = a.id 
            JOIN provas p ON c.prova_id = p.id
            ORDER BY c.data_correcao DESC 
            LIMIT 50
        """)
        
        historico = []
        for row in cursor.fetchall():
            historico.append({
                'id': row['id'],
                'aluno_nome': row['aluno_nome'],
                'prova_titulo': row['prova_titulo'],
                'acertos': row['acertos'],
                'nota': round(row['nota'], 1),
                'data_correcao': str(row['data_correcao']),
                'metodo_ia': row['metodo_ia'] or 'Desconhecido'
            })
        conn.close()
        return jsonify(historico)
    except Exception as e:
        return jsonify([])

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Estatísticas gerais
        cursor.execute("""
            SELECT 
                COUNT(*) as total_corrigidas,
                COALESCE(AVG(nota), 0) as media_nota,
                COALESCE(MAX(nota), 0) as maior_nota,
                COALESCE(MIN(nota), 0) as menor_nota
            FROM correcoes 
            WHERE prova_id = %s
        """, (prova_id,))
        geral = cursor.fetchone()
        
        # Estatísticas por método
        cursor.execute("""
            SELECT 
                metodo_ia,
                COUNT(*) as qtd,
                COALESCE(AVG(nota), 0) as media_metodo
            FROM correcoes 
            WHERE prova_id = %s
            GROUP BY metodo_ia
        """, (prova_id,))
        metodos = cursor.fetchall()
        
        # Distribuição de notas
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN nota < 2 THEN '0-2'
                    WHEN nota < 4 THEN '2-4'
                    WHEN nota < 6 THEN '4-6'
                    WHEN nota < 8 THEN '6-8'
                    ELSE '8-10'
                END as faixa,
                COUNT(*) as quantidade
            FROM correcoes 
            WHERE prova_id = %s
            GROUP BY faixa
            ORDER BY faixa
        """, (prova_id,))
        distribuicao = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'geral': {
                'total_corrigidas': geral['total_corrigidas'] if geral else 0,
                'media_nota': round(geral['media_nota'] if geral else 0, 1),
                'maior_nota': round(geral['maior_nota'] if geral else 0, 1),
                'menor_nota': round(geral['menor_nota'] if geral else 0, 1)
            },
            'metodos': [{'metodo': m['metodo_ia'] or 'Desconhecido', 'qtd': m['qtd'], 'media': round(m['media_metodo'], 1)} for m in metodos],
            'distribuicao': [{'faixa': d['faixa'], 'quantidade': d['quantidade']} for d in distribuicao]
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                a.numero_chamada,
                a.nome as aluno_nome,
                a.matricula,
                c.acertos,
                c.nota,
                c.data_correcao,
                c.metodo_ia
            FROM correcoes c 
            JOIN alunos a ON c.aluno_id = a.id 
            WHERE c.prova_id = %s
            ORDER BY a.numero_chamada
        """, (prova_id,))
        
        resultados = cursor.fetchall()
        conn.close()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Nº Chamada', 'Aluno', 'Matrícula', 'Acertos', 'Nota', 'Data', 'Método IA'])
        for r in resultados:
            writer.writerow([
                r['numero_chamada'] or '',
                r['aluno_nome'],
                r['matricula'] or '',
                r['acertos'],
                round(r['nota'], 1),
                str(r['data_correcao']),
                r['metodo_ia'] or 'Desconhecido'
            ])
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=prova_{prova_id}_resultados.csv'
        }
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - CONFIGURAÇÕES
# ============================================

@app.route('/api/configuracoes', methods=['GET'])
def get_configuracoes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT chave, valor FROM configuracoes")
        configs = {}
        for row in cursor.fetchall():
            configs[row['chave']] = row['valor']
        conn.close()
        return jsonify(configs)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/configuracoes', methods=['POST'])
def salvar_configuracoes():
    try:
        dados = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        for chave, valor in dados.items():
            cursor.execute("""
                INSERT INTO configuracoes (chave, valor, atualizado_em) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (chave) DO UPDATE SET 
                    valor = EXCLUDED.valor, 
                    atualizado_em = EXCLUDED.atualizado_em
            """, (chave, str(valor), datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Configurações salvas com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - GERAR GABARITO (FOLHA DE RESPOSTAS)
# ============================================

@app.route('/api/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        dados = request.json
        escola_id = dados.get('escola_id')
        turma_id = dados.get('turma_id')
        aluno_id = dados.get('aluno_id')
        prova_id = dados.get('prova_id')
        qtd_questoes = dados.get('quantidade_questoes', 20)
        tipo_questoes = dados.get('tipo_questoes', '4')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT nome FROM escolas WHERE id = %s", (escola_id,))
        escola = cursor.fetchone()
        nome_escola = escola['nome'] if escola else "ESCOLA"
        
        cursor.execute("SELECT nome, serie, turno, professor FROM turmas WHERE id = %s", (turma_id,))
        turma = cursor.fetchone()
        nome_turma = turma['nome'] if turma else "TURMA"
        serie = turma['serie'] if turma else "1º Ano"
        turno = turma['turno'] if turma else "Manhã"
        professor = turma['professor'] if turma else ""
        
        cursor.execute("SELECT nome, numero_chamada FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        nome_aluno = aluno['nome'] if aluno else "ALUNO"
        numero = str(aluno['numero_chamada']) if aluno and aluno['numero_chamada'] else ""
        
        cursor.execute("SELECT titulo, tipo_questoes FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        nome_prova = prova['titulo'] if prova else "PROVA"
        if prova and prova['tipo_questoes']:
            tipo_questoes = prova['tipo_questoes']
        
        conn.close()
        
        if tipo_questoes == '3':
            opcoes = ['A', 'B', 'C']
            titulo_opcoes = "3 OPÇÕES (A, B, C)"
        else:
            opcoes = ['A', 'B', 'C', 'D']
            titulo_opcoes = "4 OPÇÕES (A, B, C, D)"
        
        if int(qtd_questoes) > 30:
            qtd_questoes = 30
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Folha de Respostas - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; padding: 15px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 10px; }}
        .folha {{ padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 15px; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        .header h2 {{ color: #4CAF50; font-size: 20px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; background: #f9f9f9; padding: 10px; border-radius: 8px; font-size: 12px; }}
        .info-item {{ display: flex; gap: 8px; }}
        .info-label {{ font-weight: bold; color: #555; min-width: 70px; }}
        .info-value {{ color: #333; border-bottom: 1px solid #ccc; min-width: 120px; }}
        .instrucoes {{ background: #FFF3CD; padding: 8px; border-radius: 5px; margin-bottom: 15px; font-size: 10px; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #4CAF50; color: white; padding: 6px; text-align: center; font-size: 12px; }}
        td {{ padding: 6px; border-bottom: 1px solid #ddd; }}
        .questao-num {{ font-weight: bold; width: 50px; text-align: center; font-size: 12px; }}
        .opcoes {{ display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }}
        .opcao {{ display: inline-flex; flex-direction: column; align-items: center; gap: 3px; min-width: 45px; }}
        .circulo {{ display: inline-block; width: 22px; height: 22px; border: 2px solid #333; border-radius: 50%; background: white; cursor: pointer; }}
        .opcao span:last-child {{ font-weight: bold; font-size: 11px; }}
        .rodape {{ margin-top: 15px; text-align: center; font-size: 9px; color: #999; border-top: 1px solid #ddd; padding-top: 10px; }}
        .botoes {{ text-align: center; margin: 15px; padding: 10px; background: #f8f9fa; border-radius: 8px; }}
        button {{ background: #4CAF50; color: white; padding: 10px 25px; border: none; border-radius: 5px; font-size: 14px; cursor: pointer; margin: 0 10px; }}
        button:hover {{ background: #45a049; }}
        button.secundario {{ background: #2196F3; }}
        @media print {{ body {{ background: white; padding: 0; margin: 0; }} .container {{ box-shadow: none; }} .botoes {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="folha">
            <div class="header">
                <h2>🐝🧠 AdaBee AI - FOLHA DE RESPOSTAS</h2>
                <p>{titulo_opcoes} - {serie}</p>
            </div>
            <div class="info-grid">
                <div class="info-item"><span class="info-label">ESCOLA:</span><span class="info-value">{nome_escola}</span></div>
                <div class="info-item"><span class="info-label">TURMA:</span><span class="info-value">{nome_turma}</span></div>
                <div class="info-item"><span class="info-label">ALUNO:</span><span class="info-value">{nome_aluno}</span></div>
                <div class="info-item"><span class="info-label">Nº:</span><span class="info-value">{numero}</span></div>
                <div class="info-item"><span class="info-label">PROVA:</span><span class="info-value">{nome_prova}</span></div>
                <div class="info-item"><span class="info-label">DATA:</span><span class="info-value">___/___/______</span></div>
            </div>
            <div class="instrucoes">📌 Preencha COMPLETAMENTE a bolinha com caneta PRETA. Marque UMA por questão.</div>
            <table>
                <thead><tr><th>Q</th><th colspan="{len(opcoes)}">RESPOSTAS ({', '.join(opcoes)})</th></tr></thead>
                <tbody>"""
        
        for i in range(1, int(qtd_questoes) + 1):
            html += f"""
                    <tr>
                        <td class="questao-num">{i}</td>
                        <td colspan="{len(opcoes)}" style="text-align:center">
                            <div class="opcoes">"""
            for opcao in opcoes:
                html += f"""
                                <label class="opcao">
                                    <span class="circulo" onclick="marcar(this)"></span>
                                    <span>{opcao}</span>
                                </label>"""
            html += """
                            </div>
                        </td>
                    </tr>"""
        
        html += f"""
                </tbody>
            </table>
            <div class="rodape">AdaBee AI - Preencha completamente a bolinha | Use caneta PRETA</div>
        </div>
        <div class="botoes">
            <button onclick="window.print()">🖨️ IMPRIMIR</button>
            <button class="secundario" onclick="window.print()">💾 SALVAR PDF</button>
        </div>
    </div>
    <script>
        function marcar(el) {{
            const grupo = el.closest('.opcoes');
            grupo.querySelectorAll('.circulo').forEach(c => {{
                c.style.backgroundColor = 'white';
                c.style.border = '2px solid #333';
            }});
            el.style.backgroundColor = 'black';
            el.style.border = '2px solid black';
        }}
    </script>
</body>
</html>"""
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        print(f"Erro ao gerar gabarito: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS - IP E STATUS
# ============================================

@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    return jsonify({
        'ip': 'render.com', 
        'porta': 10000, 
        'url': 'https://adabee-sistema-3.onrender.com'
    })

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'metodos_disponiveis': {
            'Contorno': True,
            'OpenCV': True,
            'OCR': True,
            'Analise_Avancada': True
        },
        'metodo_ativo': 'Híbrido (Contorno + OpenCV + OCR + Análise Avançada)',
        'status': '🧠 Sistema híbrido ativo!',
        'banco': 'PostgreSQL (Supabase)',
        'vantagens': [
            '✅ 100% gratuito',
            '✅ Sem limites de uso',
            '✅ Correção de provas com detecção por contorno',
            '✅ Correção de redações com análise avançada'
        ]
    })

@app.route('/api/testar_conexao', methods=['GET'])
def testar_conexao():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({
            'conectado': True,
            'banco': 'PostgreSQL (Supabase)',
            'mensagem': '✅ Conectado ao Supabase!'
        })
    except Exception as e:
        return jsonify({
            'conectado': False,
            'erro': str(e)
        }), 500

# ============================================
# ROTA PRINCIPAL
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'erro': 'Rota não encontrada',
        'mensagem': 'Verifique se a URL está correta'
    }), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({
        'erro': 'Erro interno do servidor',
        'mensagem': str(e)
    }), 500

# ============================================
# INICIALIZAR E RODAR
# ============================================

if __name__ == '__main__':
    try:
        init_database()
    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")
    
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Servidor rodando na porta {port}")
    print("🧠 Sistema Híbrido - Contorno + OpenCV + OCR + Análise Avançada de Redação")
    app.run(host='0.0.0.0', port=port, debug=False)
