from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import base64
import json
import sqlite3
from datetime import datetime
import os
import io
import csv
import re
from PIL import Image
import google.generativeai as genai
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURAR BANCO DE DADOS - SUPABASE
# ============================================

SUPABASE_URL = 'postgresql://postgres.hcflxpvwidmbnmtusyol:hdUiT-HuQG%3FpF3%25@aws-1-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require'

def get_db_connection():
    """Conecta ao Supabase"""
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
        print("✅ Conectado ao Supabase!")
        return conn
    except Exception as e:
        print(f"❌ ERRO ao conectar: {e}")
        raise e

def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS escolas (
            id SERIAL PRIMARY KEY, 
            nome TEXT NOT NULL, 
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS turmas (
            id SERIAL PRIMARY KEY, 
            escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
            nome TEXT NOT NULL, 
            serie TEXT DEFAULT '1º Ano', 
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS alunos (
            id SERIAL PRIMARY KEY, 
            turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
            nome TEXT NOT NULL, 
            matricula TEXT, 
            numero_chamada INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS provas (
            id SERIAL PRIMARY KEY, 
            turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
            titulo TEXT NOT NULL, 
            descricao TEXT, 
            gabarito TEXT, 
            data_prova DATE,
            valor_nota REAL DEFAULT 10, 
            quantidade_questoes INTEGER, 
            tipo_questoes TEXT DEFAULT '4',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes (
            id SERIAL PRIMARY KEY, 
            prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
            aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
            respostas TEXT, 
            acertos INTEGER, 
            nota REAL, 
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS correcoes_redacao (
            id SERIAL PRIMARY KEY, 
            prova_id INTEGER REFERENCES provas(id) ON DELETE CASCADE,
            aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
            texto TEXT, 
            nota REAL, 
            feedback TEXT, 
            data_correcao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")

# Inicializar banco
try:
    init_database()
except Exception as e:
    print(f"❌ Erro na inicialização: {e}")

# ============================================
# CONFIGURAR GEMINI AI
# ============================================

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('models/gemini-2.0-flash')
        GEMINI_AVAILABLE = True
        print("✅ Gemini AI configurado!")
    except Exception as e:
        GEMINI_AVAILABLE = False
        print(f"❌ Erro ao configurar Gemini: {e}")
else:
    GEMINI_AVAILABLE = False
    print("⚠️ Gemini não configurado.")

# ============================================
# ROTAS PRINCIPAIS
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/teste', methods=['GET'])
def teste():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({
            'mensagem': 'Servidor funcionando!',
            'status': 'ok',
            'banco': 'PostgreSQL (Supabase)',
            'gemini': GEMINI_AVAILABLE
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# ROTAS DE ESCOLAS
# ============================================

@app.route('/api/escolas', methods=['GET'])
def listar_escolas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM escolas ORDER BY nome")
        escolas = [{'id': row['id'], 'nome': row['nome']} for row in cursor.fetchall()]
        conn.close()
        return jsonify(escolas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/escolas', methods=['POST'])
def criar_escola():
    try:
        dados = request.json
        nome = dados.get('nome')
        if not nome:
            return jsonify({'erro': 'Nome da escola é obrigatório'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO escolas (nome) VALUES (%s) RETURNING id", (nome,))
        escola_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({'id': escola_id, 'mensagem': f'Escola "{nome}" cadastrada com sucesso!'})
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
# ROTAS DE TURMAS
# ============================================

@app.route('/api/turmas', methods=['GET'])
def listar_turmas():
    try:
        escola_id = request.args.get('escola_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if escola_id:
            cursor.execute("SELECT id, escola_id, nome, serie FROM turmas WHERE escola_id = %s ORDER BY nome", (escola_id,))
        else:
            cursor.execute("SELECT id, escola_id, nome, serie FROM turmas ORDER BY nome")
        
        turmas = [{'id': row['id'], 'escola_id': row['escola_id'], 'nome': row['nome'], 'serie': row['serie']} for row in cursor.fetchall()]
        conn.close()
        return jsonify(turmas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas', methods=['POST'])
def criar_turma():
    try:
        dados = request.json
        escola_id = dados.get('escola_id')
        nome = dados.get('nome')
        serie = dados.get('serie', '1º Ano')
        
        if not escola_id or not nome:
            return jsonify({'erro': 'Escola e nome da turma são obrigatórios'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO turmas (escola_id, nome, serie) VALUES (%s, %s, %s) RETURNING id", 
                       (escola_id, nome, serie))
        turma_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': turma_id})
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
# ROTAS DE ALUNOS
# ============================================

@app.route('/api/alunos', methods=['GET'])
def listar_alunos():
    try:
        turma_id = request.args.get('turma_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if turma_id:
            cursor.execute("""
                SELECT a.id, a.turma_id, a.nome, a.matricula, a.numero_chamada, t.nome as turma_nome
                FROM alunos a 
                LEFT JOIN turmas t ON a.turma_id = t.id
                WHERE a.turma_id = %s 
                ORDER BY a.numero_chamada
            """, (turma_id,))
        else:
            cursor.execute("""
                SELECT a.id, a.turma_id, a.nome, a.matricula, a.numero_chamada, t.nome as turma_nome
                FROM alunos a 
                LEFT JOIN turmas t ON a.turma_id = t.id
                ORDER BY a.numero_chamada
            """)
        
        alunos = [{
            'id': row['id'], 
            'turma_id': row['turma_id'], 
            'nome': row['nome'], 
            'matricula': row['matricula'], 
            'numero_chamada': row['numero_chamada'],
            'turma_nome': row['turma_nome']
        } for row in cursor.fetchall()]
        
        conn.close()
        return jsonify(alunos)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/alunos', methods=['POST'])
def criar_aluno():
    try:
        dados = request.json
        turma_id = dados.get('turma_id')
        nome = dados.get('nome')
        matricula = dados.get('matricula', '')
        numero_chamada = dados.get('numero_chamada')
        
        if not turma_id or not nome:
            return jsonify({'erro': 'Turma e nome do aluno são obrigatórios'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alunos (turma_id, nome, matricula, numero_chamada) 
            VALUES (%s, %s, %s, %s) 
            RETURNING id
        """, (turma_id, nome, matricula, numero_chamada))
        
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
# ROTAS DE PROVAS - CORRIGIDAS
# ============================================

@app.route('/api/provas', methods=['GET'])
def listar_provas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.titulo, p.descricao, p.gabarito, p.data_prova, 
                   p.valor_nota, p.quantidade_questoes, p.tipo_questoes, 
                   t.nome as turma_nome, p.turma_id
            FROM provas p 
            LEFT JOIN turmas t ON p.turma_id = t.id 
            ORDER BY p.data_prova DESC
        """)
        
        provas = []
        for row in cursor.fetchall():
            provas.append({
                'id': row['id'], 
                'titulo': row['titulo'], 
                'descricao': row['descricao'],
                'gabarito_array': json.loads(row['gabarito']) if row['gabarito'] else [],
                'data_prova': row['data_prova'], 
                'valor_nota': row['valor_nota'],
                'quantidade_questoes': row['quantidade_questoes'] or 0,
                'tipo_questoes': row['tipo_questoes'] or '4',
                'turma_nome': row['turma_nome'], 
                'turma_id': row['turma_id']
            })
        conn.close()
        return jsonify(provas)
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas', methods=['POST'])
def criar_prova():
    try:
        dados = request.json
        turma_id = dados.get('turma_id')
        titulo = dados.get('titulo')
        descricao = dados.get('descricao', '')
        gabarito = dados.get('gabarito', [])
        data_prova = dados.get('data_prova')
        valor_nota = dados.get('valor_nota', 10)
        tipo_questoes = dados.get('tipo_questoes', '4')
        
        # VALIDAÇÃO CORRIGIDA
        if not turma_id:
            return jsonify({'erro': 'Turma é obrigatória'}), 400
        if not titulo:
            return jsonify({'erro': 'Título da prova é obrigatório'}), 400
        if not data_prova:
            return jsonify({'erro': 'Data da prova é obrigatória'}), 400
        if not gabarito or len(gabarito) == 0:
            return jsonify({'erro': 'Gabarito é obrigatório'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO provas (turma_id, titulo, descricao, gabarito, quantidade_questoes, data_prova, valor_nota, tipo_questoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) 
            RETURNING id
        """, (
            turma_id, titulo, descricao,
            json.dumps(gabarito), len(gabarito),
            data_prova, valor_nota, tipo_questoes
        ))
        prova_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'id': prova_id, 'mensagem': 'Prova criada com sucesso!'})
    except Exception as e:
        print(f"Erro ao criar prova: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/provas/<int:prova_id>', methods=['DELETE'])
def deletar_prova(prova_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correcoes WHERE prova_id = %s", (prova_id,))
        cursor.execute("DELETE FROM provas WHERE id = %s", (prova_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Prova excluída com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# ============================================
# CORREÇÃO DE PROVAS
# ============================================

def detectar_respostas_gemini(imagem_base64, num_opcoes=4):
    try:
        if not GEMINI_AVAILABLE:
            return [], 0.0
        
        if ',' in imagem_base64:
            imagem_base64 = imagem_base64.split(',')[1]
        
        imagem_bytes = base64.b64decode(imagem_base64)
        img = Image.open(io.BytesIO(imagem_bytes))
        img.thumbnail((1024, 1024))
        
        opcoes = 'ABCDE'[:num_opcoes]
        opcoes_str = ', '.join(list(opcoes))
        
        prompt = f"""[SISTEMA DE CORREÇÃO DE PROVAS]

ANALISE ESTA IMAGEM:
- É uma folha de respostas com questões numeradas
- Cada questão tem {num_opcoes} bolinhas: {opcoes_str}
- O aluno marcou UMA bolinha por questão (a mais escura)

TAREFA:
Liste APENAS as letras das bolinhas marcadas, na ordem das questões.

FORMATO OBRIGATÓRIO (exemplo para 10 questões):
A, B, C, A, B, C, A, B, C, D

REGRAS:
- Use SOMENTE letras maiúsculas ({opcoes_str})
- Separe por vírgula e espaço
- NÃO adicione explicações
- Se não conseguir ver, responda: NENHUMA

Responda SOMENTE a lista de letras."""
        
        response = model.generate_content([prompt, img])
        texto = response.text.strip().upper()
        
        print(f"🤖 Gemini respondeu: {texto[:200]}")
        
        letras_validas = set(opcoes)
        respostas = [c for c in texto if c in letras_validas]
        
        if len(respostas) >= 3:
            print(f"✅ Detectadas {len(respostas)} respostas")
            return respostas, 90.0
        elif len(respostas) > 0:
            return respostas, 70.0
        
        return None, 0.0
        
    except Exception as e:
        print(f"❌ Erro no Gemini: {e}")
        return None, 0.0

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
        cursor.execute("SELECT gabarito, tipo_questoes FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        
        if not prova:
            conn.close()
            return jsonify({'erro': 'Prova não encontrada'}), 404
        
        gabarito = json.loads(prova['gabarito']) if prova['gabarito'] else []
        tipo_questoes = int(prova['tipo_questoes'] or 4)
        
        respostas_detectadas, confianca = detectar_respostas_gemini(imagem, tipo_questoes)
        
        if not respostas_detectadas:
            conn.close()
            return jsonify({'erro': 'Não foi possível detectar as respostas.'}), 400
        
        while len(respostas_detectadas) < len(gabarito):
            respostas_detectadas.append('?')
        
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
        
        nota = (acertos / len(gabarito)) * 10 if gabarito else 0
        
        cursor.execute("SELECT nome FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        aluno_nome = aluno['nome'] if aluno else 'Aluno'
        
        cursor.execute("""
            INSERT INTO correcoes (prova_id, aluno_id, respostas, acertos, nota, data_correcao) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (prova_id, aluno_id, json.dumps(respostas_detectadas), acertos, nota, datetime.now()))
        conn.commit()
        conn.close()
        
        return jsonify({
            'aluno': aluno_nome,
            'respostas_detectadas': respostas_detectadas,
            'acertos': acertos,
            'total': len(gabarito),
            'nota': round(nota, 1),
            'percentual': round((acertos / len(gabarito)) * 100, 1),
            'correcoes': correcoes,
            'confianca_media': round(confianca, 1),
            'tipo_questoes': tipo_questoes,
            'metodo': 'Gemini AI'
        })
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# CORREÇÃO DE REDAÇÃO
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
        
        if not GEMINI_AVAILABLE:
            return jsonify({'erro': 'Gemini AI não está disponível'}), 500
        
        if imagem and not texto:
            if ',' in imagem:
                imagem = imagem.split(',')[1]
            imagem_bytes = base64.b64decode(imagem)
            img = Image.open(io.BytesIO(imagem_bytes))
            img.thumbnail((1024, 1024))
            
            prompt = """[SISTEMA DE CORREÇÃO DE REDAÇÃO]
            
            Leia a redação da imagem e transcreva o texto completo.
            Mantenha a formatação e parágrafos originais.
            Responda APENAS com o texto transcrito."""
            
            response = model.generate_content([prompt, img])
            texto = response.text
        elif texto:
            texto = texto
        else:
            return jsonify({'erro': 'Não foi possível obter o texto da redação'}), 400
        
        prompt = f"""[SISTEMA DE CORREÇÃO DE REDAÇÃO]

TEXTO DA REDAÇÃO:
{texto}

ANÁLISE:
1. Avalie a redação quanto a:
   - Coerência e coesão
   - Clareza e organização
   - Vocabulário e gramática
   - Conteúdo e argumentação
   - Criatividade

2. Atribua uma nota de 0 a 10.

3. Dê um conceito: Excelente, Bom, Regular, Insuficiente

4. Forneça feedback detalhado.

FORMATO DE RESPOSTA:
NOTA: [valor]
CONCEITO: [conceito]
FEEDBACK: [feedback detalhado com sugestões de melhoria]"""

        response = model.generate_content(prompt)
        resultado = response.text
        
        nota_match = re.search(r'NOTA:\s*([\d.]+)', resultado, re.IGNORECASE)
        nota = float(nota_match.group(1)) if nota_match else 0
        
        conceito_match = re.search(r'CONCEITO:\s*([A-Za-záéíóúâêôçãõ]+)', resultado, re.IGNORECASE)
        conceito = conceito_match.group(1) if conceito_match else 'Não avaliado'
        
        feedback_match = re.search(r'FEEDBACK:\s*(.*?)(?=$)', resultado, re.DOTALL | re.IGNORECASE)
        feedback = feedback_match.group(1).strip() if feedback_match else resultado
        
        if prova_id and aluno_id:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO correcoes_redacao (prova_id, aluno_id, texto, nota, feedback, data_correcao) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (prova_id, aluno_id, texto, nota, feedback, datetime.now()))
            conn.commit()
            conn.close()
        
        return jsonify({
            'nota': round(nota, 1),
            'conceito': conceito,
            'feedback': feedback,
            'texto_original': texto,
            'metodo': 'Gemini AI'
        })
        
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'erro': str(e)}), 500

# ============================================
# GERAR GABARITO
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
        
        cursor.execute("SELECT nome, serie FROM turmas WHERE id = %s", (turma_id,))
        turma = cursor.fetchone()
        nome_turma = turma['nome'] if turma else "TURMA"
        serie = turma['serie'] if turma else "1º Ano"
        
        cursor.execute("SELECT nome, numero_chamada FROM alunos WHERE id = %s", (aluno_id,))
        aluno = cursor.fetchone()
        nome_aluno = aluno['nome'] if aluno else "ALUNO"
        numero = str(aluno['numero_chamada']) if aluno and aluno['numero_chamada'] else ""
        
        cursor.execute("SELECT titulo FROM provas WHERE id = %s", (prova_id,))
        prova = cursor.fetchone()
        nome_prova = prova['titulo'] if prova else "PROVA"
        
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
        .circulo {{ display: inline-block; width: 22px; height: 22px; border: 2px solid #333; border-radius: 50%; background: white; }}
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
                                    <span class="circulo"></span>
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
            <button class="secundario" onclick="baixarPDF()">💾 SALVAR PDF</button>
        </div>
    </div>
    <script>
        function baixarPDF() {{ window.print(); }}
        document.querySelectorAll('.opcoes').forEach(grupo => {{
            const opcoes = grupo.querySelectorAll('.opcao');
            opcoes.forEach(opcao => {{
                opcao.addEventListener('click', function() {{
                    opcoes.forEach(opt => {{
                        opt.querySelector('.circulo').style.backgroundColor = 'white';
                        opt.querySelector('.circulo').style.border = '2px solid #333';
                    }});
                    this.querySelector('.circulo').style.backgroundColor = 'black';
                    this.querySelector('.circulo').style.border = '2px solid black';
                }});
            }});
        }});
    </script>
</body>
</html>"""
        
        return html, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        print(f"Erro: {e}")
        return f"<h3>Erro: {str(e)}</h3>", 500

# ============================================
# DEMAIS ROTAS - CORRIGIDAS
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
                   c.acertos, c.nota, c.data_correcao
            FROM correcoes c 
            JOIN alunos a ON c.aluno_id = a.id 
            JOIN provas p ON c.prova_id = p.id
            ORDER BY c.data_correcao DESC 
            LIMIT 50
        """)
        
        historico = [{
            'id': row['id'], 
            'aluno_nome': row['aluno_nome'], 
            'prova_titulo': row['prova_titulo'],
            'acertos': row['acertos'], 
            'nota': round(row['nota'], 1), 
            'data_correcao': row['data_correcao']
        } for row in cursor.fetchall()]
        
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
        cursor.execute("""
            SELECT 
                COUNT(*) as total_corrigidas,
                COALESCE(AVG(nota), 0) as media_nota,
                COALESCE(MAX(nota), 0) as maior_nota,
                COALESCE(MIN(nota), 0) as menor_nota
            FROM correcoes 
            WHERE prova_id = %s
        """, (prova_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return jsonify({
            'geral': {
                'total_corrigidas': row['total_corrigidas'] if row else 0,
                'media_nota': round(row['media_nota'], 1) if row else 0,
                'maior_nota': round(row['maior_nota'], 1) if row else 0,
                'menor_nota': round(row['menor_nota'], 1) if row else 0
            }
        })
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/status_ia', methods=['GET'])
def status_ia():
    return jsonify({
        'treinada': True,
        'usando_ia': True,
        'gemini_disponivel': GEMINI_AVAILABLE,
        'status': '🧠 Gemini AI ativo!' if GEMINI_AVAILABLE else '⚠️ Gemini não configurado',
        'metodo': 'Gemini AI',
        'banco': 'PostgreSQL (Supabase)'
    })

@app.route('/api/exportar', methods=['GET'])
def exportar_resultados():
    prova_id = request.args.get('prova_id')
    if not prova_id:
        return jsonify({'erro': 'Prova não informada'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.nome, a.matricula, c.acertos, c.nota, c.data_correcao
            FROM correcoes c 
            JOIN alunos a ON c.aluno_id = a.id 
            WHERE c.prova_id = %s
        """, (prova_id,))
        
        resultados = cursor.fetchall()
        conn.close()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Aluno', 'Matrícula', 'Acertos', 'Nota', 'Data'])
        for r in resultados:
            writer.writerow([r['nome'], r['matricula'] or '', r['acertos'], r['nota'], r['data_correcao']])
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=prova_{prova_id}_resultados.csv'
        }
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/ip_info', methods=['GET'])
def ip_info():
    return jsonify({
        'ip': 'render.com', 
        'porta': 10000, 
        'url': 'https://adabee-sistema-3.onrender.com'
    })

@app.route('/api/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if request.method == 'GET':
        return jsonify({'param1': 80, 'param2': 25})
    return jsonify({'mensagem': 'ok'})

@app.route('/api/alternar_ia', methods=['POST'])
def alternar_ia():
    return jsonify({'usando_ia': True})

@app.route('/api/treinar_ia', methods=['POST'])
def treinar_ia():
    return jsonify({'status': 'ok', 'mensagem': '✅ Gemini AI está pronto!'})

@app.route('/api/calibrar', methods=['POST'])
def calibrar():
    return jsonify({'sucesso': True, 'mensagem': 'Gemini AI não precisa de calibração!'})

@app.route('/api/testar_gemini', methods=['POST'])
def testar_gemini():
    try:
        dados = request.json
        imagem = dados.get('imagem')
        if not imagem:
            return jsonify({'erro': 'Imagem não fornecida'}), 400
        if ',' in imagem:
            imagem = imagem.split(',')[1]
        imagem_bytes = base64.b64decode(imagem)
        img = Image.open(io.BytesIO(imagem_bytes))
        img.thumbnail((800, 800))
        prompt = "Descreva o que você vê nesta imagem. Liste as letras A, B, C, D, E se aparecerem."
        response = model.generate_content([prompt, img])
        return jsonify({'resposta_bruta': response.text, 'sucesso': True})
    except Exception as e:
        return jsonify({'erro': str(e), 'sucesso': False}), 500

@app.route('/api/diagnosticar_banco', methods=['GET'])
def diagnosticar_banco():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as teste")
        row = cursor.fetchone()
        conn.close()
        return jsonify({
            'status': 'sucesso',
            'banco': 'PostgreSQL (Supabase)',
            'detalhes': {
                'teste_query': 'OK',
                'conexao': 'Estabelecida com sucesso'
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'erro',
            'banco': 'Não conectado',
            'detalhes': {'erro': str(e)}
        }), 500

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
