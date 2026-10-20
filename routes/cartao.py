# ============================================================
# ROUTES/CARTAO.PY — Geração de cartão resposta + folha redação
# com validação de escola
# ============================================================

import base64
import io
import logging
import os
import traceback
from datetime import datetime

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from core.db import get_db_connection
from core.utils import get_escola_id
from services.evalbee import gerar_mapa_template_padrao, salvar_mapa_template


bp = Blueprint('cartao', __name__, url_prefix='/api')


# ═══════════════════════════════════════════════════════════════
# 🎨 HELPERS DE IMAGEM (inalterados)
# ═══════════════════════════════════════════════════════════════
def gerar_qrcode_base64(dados):
    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(dados)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        logging.info(f"✅ QR Code gerado para: {dados[:50]}...")
        return b64

    except Exception as e:
        logging.error(f"❌ Erro ao gerar QR Code: {e}")
        traceback.print_exc()
        return ""


def carregar_logo_base64(nome_arquivo):
    """Carrega a logo do disco e devolve como data URL (base64)."""
    try:
        if not nome_arquivo or not os.path.isfile(nome_arquivo):
            logging.warning(f"⚠️ Logo não encontrada: {nome_arquivo}")
            return ''
        with open(nome_arquivo, 'rb') as f:
            dados = f.read()
        b64 = base64.b64encode(dados).decode('utf-8')
        ext = nome_arquivo.lower().rsplit('.', 1)[-1]
        mime = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'svg': 'image/svg+xml',
            'webp': 'image/webp',
        }.get(ext, 'image/png')
        logging.info(f"✅ Logo carregada: {nome_arquivo} ({len(dados)} bytes)")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        logging.error(f"❌ Erro ao carregar logo: {e}")
        return ''


# ═══════════════════════════════════════════════════════════════
# 🎫 GERAR GABARITO/CARTÃO RESPOSTA (com validação de escola)
# ═══════════════════════════════════════════════════════════════
@bp.route('/gerar_gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json or {}

        campos_obrigatorios = ['escola_id', 'turma_id', 'aluno_id', 'prova_id']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({'erro': f'Campo "{campo}" é obrigatório'}), 400

        escola_id = data.get('escola_id')
        turma_id = data.get('turma_id')
        aluno_id = data.get('aluno_id')
        prova_id = data.get('prova_id')

        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco de dados'}), 500

        # 🔒 Escola da sessão (None = admin → vê tudo)
        escola_sessao = get_escola_id()

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Buscar aluno (agora inclui escola_id para validação)
        cur.execute("""
            SELECT a.nome, a.escola_id, e.nome as escola_nome,
                   t.nome as turma_nome, t.serie
            FROM alunos a
            LEFT JOIN turmas t ON a.turma_id = t.id
            LEFT JOIN escolas e ON a.escola_id = e.id
            WHERE a.id = %s
        """, (aluno_id,))
        aluno = cur.fetchone()

        cur.execute("SELECT p.* FROM provas p WHERE p.id = %s", (prova_id,))
        prova = cur.fetchone()

        cur.close()
        conn.close()

        if not aluno or not prova:
            return jsonify({'erro': 'Aluno ou prova não encontrados'}), 404

        # 🔒 Valida acesso à escola do aluno
        if escola_sessao is not None and aluno.get('escola_id') != escola_sessao:
            return jsonify({'erro': 'Acesso negado a este aluno'}), 403

        # 🛡️ Valida que a prova também pertence à escola da sessão
        prova_escola_id = prova.get('escola_id') if isinstance(prova, dict) else prova[8] if len(prova) > 8 else None
        if escola_sessao is not None and prova_escola_id is not None and prova_escola_id != escola_sessao:
            return jsonify({'erro': 'Acesso negado a esta prova'}), 403

        nome_aluno = aluno['nome']
        escola_nome = aluno['escola_nome'] or ''
        turma_nome = aluno['turma_nome'] or ''
        LOGO_ARQUIVO = 'logotipo cartão resposta.png'
        logo_base64 = carregar_logo_base64(LOGO_ARQUIVO)
        logo_html = (
            f'<img src="{logo_base64}" alt="Logo" '
            f'style="height:20mm; max-width:100%; object-fit:contain; '
            f'margin:0 auto 1.5mm auto; display:block;">'
            if logo_base64 else ''
        )
        serie = prova.get('serie', '')
        titulo_prova = prova.get('titulo', 'Prova')
        disciplina_prova = (prova.get('disciplina') or '').strip()

        tipo_questoes = int(prova.get('tipo_questoes', 4))
        alternativas = ['A', 'B', 'C', 'D', 'E'][:tipo_questoes]
        quantidade_questoes = int(prova.get('quantidade_questoes', 20))

        # ═══════════════════════════════════════════════════════════
        # FOLHA DE REDAÇÃO
        # ═══════════════════════════════════════════════════════════
        if disciplina_prova == 'Redação':
            logging.info(f"📝 Gerando FOLHA DE REDAÇÃO para {nome_aluno}")

            qr_dados_red = f"ALUNO:{aluno_id}|PROVA:{prova_id}|ESCOLA:{escola_id}|TURMA:{turma_id}"
            qr_base64_red = gerar_qrcode_base64(qr_dados_red)

            num_linhas = quantidade_questoes if quantidade_questoes >= 10 else 30
            num_linhas = min(num_linhas, 50)

            linhas_pautadas = ""
            for i in range(1, num_linhas + 1):
                linhas_pautadas += f'''
                <div style="display:flex;align-items:center;margin-bottom:1.5mm;">
                    <div style="width:8mm;font-size:7pt;color:#999;text-align:right;padding-right:1.5mm;font-family:monospace;">{i:02d}</div>
                    <div style="flex:1;border-bottom:0.25mm solid #ccc;height:7.5mm;"></div>
                </div>
                '''

            html_redacao = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Folha de Redação - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        @page {{ size: A4 portrait; margin: 0; }}
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 10px; display: flex; justify-content: center; }}
        .folha {{ width: 210mm; height: 297mm; background: #fff; position: relative; box-shadow: 0 2px 20px rgba(0,0,0,0.15); }}

        .fiducial {{ position: absolute; width: 10mm; height: 10mm; background: #000; z-index: 100; }}
        .fiducial::after {{ content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 4mm; height: 4mm; background: #fff; border-radius: 50%; }}
        .fiducial-tl {{ left: 15mm; top: 15mm; }}
        .fiducial-tr {{ right: 15mm; top: 15mm; }}
        .fiducial-bl {{ left: 15mm; bottom: 15mm; }}
        .fiducial-br {{ right: 15mm; bottom: 15mm; }}

        .qr-code-bloco {{ position: absolute; top: 28mm; right: 15mm; width: 35mm; height: 35mm; z-index: 50; }}
        .qr-code-bloco img {{ width: 100%; height: 100%; display: block; border: 0.3mm solid #000; padding: 1mm; background: #fff; }}

        .header {{ position: absolute; left: 25mm; top: 25mm; width: 170mm; height: 52mm; border-bottom: 1.5px solid #000; padding-bottom: 2mm; }}
        .header-titulo {{ font-size: 8pt; font-weight: bold; text-align: center; letter-spacing: 0.5px; }}
        .header-cartao {{ font-size: 14pt; font-weight: 900; text-align: center; border: 2px solid #000; display: inline-block; padding: 1mm 8mm; margin: 1mm auto; }}
        .header-prova {{ font-size: 9pt; font-weight: bold; text-align: center; margin-top: 1mm; }}
        .header-escola {{ font-size: 7pt; color: #333; text-align: center; }}
        .header-aluno {{ font-size: 9pt; margin-top: 2.5mm; padding: 0 2mm; }}
        .header-linha {{ margin-top: 1.5mm; padding: 0 2mm; font-size: 9pt; }}
        .campo {{ border-bottom: 0.3mm solid #000; display: inline-block; min-width: 40mm; padding: 0 1mm; }}

        .instrucoes {{ position: absolute; left: 25mm; top: 75mm; width: 160mm; font-size: 7pt; padding: 1.5mm 3mm; background: #f0f0f0; border: 0.3mm solid #999; line-height: 1.4; }}

        .area-redacao {{ position: absolute; left: 25mm; top: 83mm; width: 160mm; height: 202mm; }}
        .area-redacao-titulo {{ font-size: 8pt; font-weight: 700; color: #333; margin-bottom: 2mm; border-bottom: 0.3mm solid #000; padding-bottom: 1mm; }}

        .rodape {{ position: absolute; left: 25mm; right: 25mm; bottom: 20mm; font-size: 6pt; color: #666; border-top: 1px solid #ccc; padding-top: 1mm; display: flex; justify-content: space-between; }}

        .btn-print {{ position: absolute; bottom: 5mm; left: 50%; transform: translateX(-50%); padding: 3mm 10mm; background: #000; color: #fff; border: none; font-size: 11pt; font-weight: bold; cursor: pointer; border-radius: 2mm; }}

        @media print {{
            body {{ background: #fff; padding: 0; }}
            .folha {{ box-shadow: none; }}
            .btn-print {{ display: none; }}
            .fiducial, .fiducial::after {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>
    <div class="folha">
        <div class="fiducial fiducial-tl"></div>
        <div class="fiducial fiducial-tr"></div>
        <div class="fiducial fiducial-bl"></div>
        <div class="fiducial fiducial-br"></div>

        <div class="qr-code-bloco">
            <img src="data:image/png;base64,{qr_base64_red}" alt="QR Code">
        </div>

        <div class="header">
            {logo_html}
            <div class="header-titulo">SECRETARIA MUN. DE EDUCAÇÃO — SISAM 2026</div>
            <div style="text-align:center;">
                <div class="header-cartao">FOLHA DE REDAÇÃO</div>
            </div>
            <div class="header-prova">{titulo_prova}</div>
            <div class="header-escola">{escola_nome} | Série: {serie} | Turma: {turma_nome}</div>
            <div class="header-aluno"><strong>Aluno(a):</strong> {nome_aluno}</div>
            <div class="header-linha">
                <strong>Data:</strong> <span class="campo">{datetime.now().strftime('%d/%m/%Y')}</span>
                &nbsp;&nbsp;
                <strong>Nº:</strong> <span class="campo" style="min-width:20mm;"></span>
            </div>
        </div>

        <div class="instrucoes">
            <strong>⚠️ INSTRUÇÕES:</strong>
            Escreva com caneta <strong>preta ou azul</strong>. Não rasure. Letra legível. Respeite as margens.
            Use uma linha por linha de texto. Não escreva fora da área pautada.
        </div>

        <div class="area-redacao">
            <div class="area-redacao-titulo">✍️ TEXTO DEFINITIVO</div>
            {linhas_pautadas}
        </div>

        <div class="rodape">
            <span>Gerado por CorrigePro — {datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
            <span>Página 1/1</span>
        </div>

        <button class="btn-print" onclick="window.print()">🖨️ IMPRIMIR</button>
    </div>
</body>
</html>
"""
            return html_redacao, 200, {'Content-Type': 'text/html'}

        # ═══════════════════════════════════════════════════════════
        # CARTÃO RESPOSTA (bolhas)
        # ═══════════════════════════════════════════════════════════
        num_colunas_real = 1 if quantidade_questoes <= 12 else 2

        mapa_template = gerar_mapa_template_padrao(
            quantidade_questoes, alternativas, num_colunas_real
        )

        salvar_mapa_template(
            prova_id, aluno_id, tipo_questoes, quantidade_questoes,
            num_colunas_real,
            mapa_template
        )

        logging.info(f"🎨 Cartão gerado: {len(mapa_template)} bolhas salvas")

        qr_dados = f"ALUNO:{aluno_id}|PROVA:{prova_id}|ESCOLA:{escola_id}|TURMA:{turma_id}"
        qr_base64 = gerar_qrcode_base64(qr_dados)
        logging.info(f"📷 QR Code gerado: {qr_dados}")

        bolhas_html = ""
        linhas_num_html = ""
        questoes = {}

        for b in mapa_template:
            q = b['questao']
            if q not in questoes:
                questoes[q] = []
            questoes[q].append(b)

        for q_num in sorted(questoes.keys()):
            bolhas_q = questoes[q_num]
            for b in bolhas_q:
                x_mm = b['x_mm']
                y_mm = b['y_mm']
                left_mm = x_mm - 3.5
                top_mm = y_mm - 3.5

                bolhas_html += f'''
                <div class="bolha-abs" style="left:{left_mm}mm; top:{top_mm}mm;">{b['alternativa']}</div>
                '''

            y_num = bolhas_q[0]['y_mm']
            x_num = bolhas_q[0]['x_mm'] - 12.0
            linhas_num_html += f'''
            <div class="num-abs" style="left:{x_num}mm; top:{y_num - 3.5}mm;">{q_num:02d}</div>
            '''

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Cartão Resposta - {nome_aluno}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        @page {{ size: A4 portrait; margin: 0; }}
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 10px; display: flex; justify-content: center; }}
        .folha {{ width: 210mm; height: 297mm; background: #fff; position: relative; box-shadow: 0 2px 20px rgba(0,0,0,0.15); }}
        .fiducial {{ position: absolute; width: 10mm; height: 10mm; background: #000; z-index: 100; }}
        .fiducial::after {{ content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 4mm; height: 4mm; background: #fff; border-radius: 50%; }}
        .fiducial-tl {{ left: 15mm; top: 15mm; }}
        .fiducial-tr {{ right: 15mm; top: 15mm; }}
        .fiducial-bl {{ left: 15mm; bottom: 15mm; }}
        .fiducial-br {{ right: 15mm; bottom: 15mm; }}
        .qr-code-bloco {{ position: absolute; top: 28mm; right: 15mm; width: 41mm; height: 41mm; z-index: 50; }}
        .qr-code-bloco img {{ width: 100%; height: 100%; display: block; border: 1px solid #000; padding: 1mm; background: #fff; }}
        .header-abs {{ position: absolute; left: 25mm; top: 25mm; width: 170mm; height: 65mm; text-align: center; border-bottom: 1.5px solid #000; display: flex; flex-direction: column; justify-content: flex-end; padding-bottom: 2mm; overflow: hidden; }}
        .header-titulo {{ font-size: 8pt; font-weight: bold; letter-spacing: 0.5px; }}
        .header-cartao {{ font-size: 12pt; font-weight: 900; border: 2px solid #000; display: inline-block; padding: 1mm 6mm; margin: 1mm auto; }}
        .header-prova {{ font-size: 8pt; font-weight: bold; margin-top: 1mm; }}
        .header-escola {{ font-size: 7pt; color: #333; }}
        .header-aluno {{ font-size: 9pt; margin-top: 1mm; text-align: left; padding: 0 2mm; }}
        .header-assinatura {{ font-size: 9pt; margin-top: 1mm; padding: 0 2mm; text-align: left; }}
        .instrucoes {{ font-size: 6pt; font-weight: bold; padding: 0.8mm; background: #f0f0f0; border: 1px solid #999; margin-top: 0.5mm; }}
        .bolha-abs {{ position: absolute; width: 7mm; height: 7mm; border: 1.5px solid #666; border-radius: 50%; background: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 9pt; font-weight: 900; color: #000; line-height: 1; }}
        .num-abs {{ position: absolute; font-size: 9pt; font-weight: 900; line-height: 7mm; height: 7mm; text-align: right; padding-right: 1mm; border-right: 1.5px solid #000; width: 10mm; }}
        .rodape {{ position: absolute; left: 25mm; right: 25mm; bottom: 20mm; font-size: 6pt; color: #666; border-top: 1px solid #ccc; padding-top: 1mm; display: flex; justify-content: space-between; }}
        .btn-print {{ position: absolute; bottom: 5mm; left: 50%; transform: translateX(-50%); padding: 3mm 10mm; background: #000; color: #fff; border: none; font-size: 11pt; font-weight: bold; cursor: pointer; border-radius: 2mm; }}
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .folha {{ box-shadow: none; }}
            .btn-print {{ display: none; }}
            .fiducial, .fiducial::after {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
            .bolha-abs {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>
    <div class="folha">
        <div class="fiducial fiducial-tl"></div>
        <div class="fiducial fiducial-tr"></div>
        <div class="fiducial fiducial-bl"></div>
        <div class="fiducial fiducial-br"></div>

        <div class="qr-code-bloco">
            <img src="data:image/png;base64,{qr_base64}" alt="QR Code">
        </div>

        <div class="header-abs">
            {logo_html}
            <div class="header-titulo">SECRETARIA MUN. DE EDUCAÇÃO — SISAM 2026</div>
            <div class="header-cartao">CARTÃO RESPOSTA</div>
            <div class="header-prova">{titulo_prova}</div>
            <div class="header-escola">{escola_nome} | Série: {serie} | Turma: {turma_nome}</div>
            <div class="header-aluno">
                <strong>Aluno(a):</strong> {nome_aluno} &nbsp;&nbsp; <strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y')}
            </div>
            <div class="header-assinatura">
                <strong>Assinatura do Aluno(a):</strong>
                <span style="display:inline-block; border-bottom:1.5px solid #000; width:85mm; height:5mm; margin-left:2mm; vertical-align:bottom;"></span>
            </div>
            <div class="instrucoes">
                ⚠️ PINTE SOMENTE UM CIRCULO POR QUESTAO — USE CANETA PRETA OU AZUL — NÃO RASURE -
            </div>
        </div>

        {bolhas_html}
        {linhas_num_html}

        <div class="rodape">
            <span>Gerado por CorrigePro — {datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
            <span>Página 1/1</span>
        </div>

        <button class="btn-print" onclick="window.print()">🖨️ IMPRIMIR</button>
    </div>
</body>
</html>
"""
        return html, 200, {'Content-Type': 'text/html'}

    except Exception as e:
        print(f"❌ Erro ao gerar cartão: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
