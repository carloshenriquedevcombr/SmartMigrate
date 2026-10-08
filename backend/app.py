from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import io
import os
import re

# Pasta do frontend (index.html), servida pelo próprio Flask na rota "/"
FRONTEND_DIR = os.environ.get(
    "FRONTEND_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"),
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # Limite de upload: 50 MB
CORS(app)  # Permite comunicação com o frontend

# ==========================================
# CENTRAL DE REGRAS DE NEGÓCIO EM PYTHON
# ==========================================
# O status é decidido pela FAIXA inteira (soma do faturamento da faixa),
# igual à planilha ANÁLISE MIGRAÇÕES MÓVEL:
#   M0 a M6   -> sempre FORA DO MAILING
#   M7 a M16  -> UPGRADE se o crescimento da faixa for >= 10%, senão FORA DO MAILING
#   M17+      -> nunca fica fora: < 0% DOWNGRADE, >= 5% UPGRADE, entre 0% e 5% PADRÃO
REGRAS = {
    "FAIXA_1_FIM": 6,  # M0 até M6
    "FAIXA_2_FIM": 16,  # M7 até M16
    "UPGRADE_MIN_M7": 10,  # Crescimento mín. 10%
    "UPGRADE_MIN_M17": 5,  # Crescimento mín. 5%
}

FAIXAS = ["M0 a M6", "M7 a M16", "M17+"]


def faixa_do_m(m):
    if m <= REGRAS["FAIXA_1_FIM"]:
        return "M0 a M6"
    if m <= REGRAS["FAIXA_2_FIM"]:
        return "M7 a M16"
    return "M17+"


def status_da_faixa(faixa, crescimento, qtd):
    if faixa == "M0 a M6":
        return "FORA DO MAILING"
    if faixa == "M7 a M16":
        # Sem linhas na faixa, vale a regra padrão dela (upgrade obrigatório)
        if qtd == 0 or crescimento >= REGRAS["UPGRADE_MIN_M7"]:
            return "UPGRADE"
        return "FORA DO MAILING"
    if crescimento < 0:
        return "DOWNGRADE"
    if crescimento >= REGRAS["UPGRADE_MIN_M17"]:
        return "UPGRADE"
    return "PADRÃO"


def extrair_gb(nome_produto):
    """Franquia em GB a partir do nome do produto (ex: '6GB', '1,5 GB', '200MB')."""
    if not isinstance(nome_produto, str):
        return 0
    achados = re.findall(r"(\d+(?:[.,]\d+)?)\s*(GB|MB)", nome_produto, re.IGNORECASE)
    if not achados:
        return 0
    valor, unidade = achados[-1]
    gb = float(valor.replace(",", "."))
    if unidade.upper() == "MB":
        gb = gb / 1000
    return int(gb) if gb.is_integer() else gb


# Nomes aceitos para a coluna do número da linha (sem diferenciar maiúsculas)
COLUNAS_TELEFONE = ["telefone", "linha", "numero", "número", "numerolinha", "celular", "msisdn", "fone"]


def achar_coluna_telefone(df):
    normalizadas = {str(c).strip().lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for nome in COLUNAS_TELEFONE:
        if nome in normalizadas:
            return normalizadas[nome]
    return None


def formatar_telefone(valor):
    """Converte o telefone lido do Excel em texto, sem o '.0' de números float."""
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


@app.route("/")
def index():
    resposta = send_from_directory(FRONTEND_DIR, "index.html")
    resposta.headers["Cache-Control"] = "no-store"  # Sempre pega a versão nova após um deploy
    return resposta


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/analisar", methods=["POST"])
def analisar():
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files["file"]
    
    try:
        # Lendo o Excel utilizando Pandas
        contents = file.read()
        df = pd.read_excel(io.BytesIO(contents))

        # Padronizando colunas essenciais
        df["M"] = pd.to_numeric(df.get("M", 0), errors="coerce").fillna(0).astype(int)
        df["FaturamentoAtual"] = (
            pd.to_numeric(df.get("FaturamentoAtual", 0), errors="coerce")
            .fillna(0)
            .astype(float)
        )
        df["FaturamentoPara"] = (
            pd.to_numeric(df.get("FaturamentoPara", 0), errors="coerce")
            .fillna(0)
            .astype(float)
        )
        df["ProdutoPlanta"] = (
            df.get("ProdutoPlanta", "Sem Informação").astype(str).fillna("Sem Informação")
        )
        df["ProdutoRecomendacao"] = (
            df.get("ProdutoRecomendacao", "Sem Informação")
            .astype(str)
            .fillna("Sem Informação")
        )

        coluna_telefone = achar_coluna_telefone(df)

        # 1) Soma o faturamento de cada faixa para decidir o status da faixa inteira
        df["Faixa"] = df["M"].apply(faixa_do_m)
        resumo_crm = []
        status_por_faixa = {}
        total_count, total_atual, total_novo = 0, 0.0, 0.0
        for faixa in FAIXAS:
            dados = df[df["Faixa"] == faixa]
            qtd = int(len(dados))
            atual = float(dados["FaturamentoAtual"].sum())
            novo = float(dados["FaturamentoPara"].sum())
            crescimento = ((novo - atual) / atual * 100) if atual > 0 else 0.0
            status = status_da_faixa(faixa, crescimento, qtd)
            status_por_faixa[faixa] = status
            total_count += qtd
            total_atual += atual
            total_novo += novo
            resumo_crm.append({
                "faixa": faixa,
                "qtd": qtd,
                "atual": atual,
                "novo": novo,
                "crescimento": round(crescimento, 2),
                "status": status,
            })

        crescimento_geral = (
            ((total_novo - total_atual) / total_atual * 100) if total_atual > 0 else 0.0
        )

        # 2) Cada linha segue o status da sua faixa. Fora do mailing continua no plano atual.
        fora_mailing, dentro_mailing = [], []
        contagem_planta, contagem_final = {}, {}
        for _, row in df.iterrows():
            planta = row["ProdutoPlanta"]
            recomendacao = row["ProdutoRecomendacao"]
            status = status_por_faixa[row["Faixa"]]
            linha = {
                "telefone": formatar_telefone(row[coluna_telefone]) if coluna_telefone else "",
                "m": int(row["M"]),
                "produto": planta,
                "gb": extrair_gb(planta),
            }
            if status == "FORA DO MAILING":
                plano_final = planta
                fora_mailing.append(linha)
            else:
                plano_final = recomendacao
                linha.update({
                    "produto_novo": recomendacao,
                    "gb_novo": extrair_gb(recomendacao),
                    "status": status,
                })
                dentro_mailing.append(linha)

            contagem_planta[planta] = contagem_planta.get(planta, 0) + 1
            contagem_final[plano_final] = contagem_final.get(plano_final, 0) + 1

        # Agrupa as listas por M e plano atual
        def ordem_linha(x):
            return (x["m"], x["gb"], x["produto"].lower(), x.get("gb_novo", 0), x.get("produto_novo", "").lower(), x["telefone"])

        fora_mailing.sort(key=ordem_linha)
        dentro_mailing.sort(key=ordem_linha)

        # Produtos e Franquias
        def processar_produtos(dicionario):
            lista = []
            qtd_tot, gb_tot = 0, 0.0
            for prod, qtd in sorted(dicionario.items(), key=lambda x: x[1], reverse=True):
                gb_prod = extrair_gb(prod) * qtd
                qtd_tot += qtd
                gb_tot += gb_prod
                lista.append({"nome": prod, "qtd": qtd, "gb": gb_prod})
            return lista, qtd_tot, gb_tot

        planta_lista, q_p, gb_p = processar_produtos(contagem_planta)
        rec_lista, q_r, gb_r = processar_produtos(contagem_final)

        return jsonify({
            "success": True,
            "resumo_crm": resumo_crm,
            "totais_crm": {
                "count": total_count,
                "atual": total_atual,
                "novo": total_novo,
                "crescimento": round(crescimento_geral, 2),
            },
            "fora_mailing": fora_mailing,
            "dentro_mailing": dentro_mailing,
            "planta": {"itens": planta_lista, "total_qtd": q_p, "total_gb": gb_p},
            "recomendacao": {
                "itens": rec_lista,
                "total_qtd": q_r,
                "total_gb": gb_r,
            },
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    # Apenas para desenvolvimento local. Em produção use o gunicorn (ver README).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
