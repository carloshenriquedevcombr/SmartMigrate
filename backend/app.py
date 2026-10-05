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
REGRAS = {
    "FAIXA_1_FIM": 6,  # M0 até M6
    "FAIXA_2_FIM": 16,  # M7 até M16
    "FAIXA_3_FIM": 22,  # M17 até M22
    "UPGRADE_MIN_M7": 10,  # Crescimento mín. 10%
    "UPGRADE_MIN_M17": 5,  # Crescimento mín. 5%
}


def extrair_gb(nome_produto):
    if not isinstance(nome_produto, str):
        return 0
    if "0.2" in nome_produto or "0,2" in nome_produto:
        return 0.2
    
    match = re.search(r"(\d+)\s*GB", nome_produto, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def converter_red_limite(valor_str):
    """
    Converte o limite em string vindo do frontend (ex: '-9,78%') para float (-9.78).
    """
    if not valor_str:
        return 0.0
    
    # Remove o símbolo de porcentagem e espaços
    valor_limpo = valor_str.replace('%', '').strip()
    # Substitui a vírgula brasileira por ponto para conversão matemática
    valor_limpo = valor_limpo.replace(',', '.')
    
    try:
        return float(valor_limpo)
    except ValueError:
        return 0.0


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/analisar", methods=["POST"])
def analisar():
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    # 1. Capturando o Red. Limite obrigatório do Frontend
    red_limite_str = request.form.get("red_limite")
    if not red_limite_str:
        return jsonify({"error": "O valor do Red. Limite é obrigatório para a análise."}), 400
    
    red_limite_float = converter_red_limite(red_limite_str)
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

        # Agora agrupamos por (Faixa, Status) para ter granularidade de linha a linha
        faixas_resultado = {}
        contagem_planta = {}
        contagem_recomendacao = {}
        tem_m23_mais = False

        for _, row in df.iterrows():
            m = row["M"]
            fat_atual = row["FaturamentoAtual"]
            fat_novo = row["FaturamentoPara"]
            planta = row["ProdutoPlanta"]
            recomendacao = row["ProdutoRecomendacao"]

            # Calcula o delta (crescimento) individual do cliente (registro a registro)
            crescimento_linha = (
                ((fat_novo - fat_atual) / fat_atual * 100) if fat_atual > 0 else 0.0
            )

            status = "-"
            fx = "-"

            # Classificação por faixa de meses e aplicação de regras
            if m <= REGRAS["FAIXA_1_FIM"]:
                fx = "M0 a M6"
                status = "FORA DO MAILING"
                
            elif m <= REGRAS["FAIXA_2_FIM"]:
                fx = "M7 a M16"
                if crescimento_linha >= REGRAS["UPGRADE_MIN_M7"]:
                    status = "UPGRADE"
                else:
                    status = "FORA DO MAILING"
                    
            elif m <= REGRAS["FAIXA_3_FIM"]:
                fx = "M17 a M22"
                # Regra 3: M entre 17 e 22, valor negativo = Fora do Mailing independentemente do limite
                if crescimento_linha < 0:
                    status = "FORA DO MAILING"
                elif crescimento_linha >= REGRAS["UPGRADE_MIN_M17"]:
                    status = "UPGRADE"
                else:
                    status = "PADRÃO"
                    
            else:
                fx = "M23+"
                tem_m23_mais = True
                if crescimento_linha < 0:
                    # Comparação Matemática: Verifica se o valor analisado está ABAIXO do limite informado
                    if crescimento_linha < red_limite_float:
                        status = "FORA DO MAILING"
                    else: # Se está no limite ou é um valor maior (ex: -8.00 >= -9.78)
                        status = "DOWNGRADE"
                elif crescimento_linha >= REGRAS["UPGRADE_MIN_M17"]:
                    status = "UPGRADE"
                else:
                    status = "PADRÃO"

            # Agregação dos resultados
            chave_agrupamento = f"{fx}|{status}"
            if chave_agrupamento not in faixas_resultado:
                faixas_resultado[chave_agrupamento] = {"faixa": fx, "status": status, "count": 0, "atual": 0.0, "novo": 0.0}
            
            faixas_resultado[chave_agrupamento]["count"] += 1
            faixas_resultado[chave_agrupamento]["atual"] += fat_atual
            faixas_resultado[chave_agrupamento]["novo"] += fat_novo

            contagem_planta[planta] = contagem_planta.get(planta, 0) + 1
            contagem_recomendacao[recomendacao] = (
                contagem_recomendacao.get(recomendacao, 0) + 1
            )

        # Montando estrutura de resposta para o Frontend
        resumo_crm = []
        total_count, total_atual, total_novo = 0, 0.0, 0.0

        for f in faixas_resultado.values():
            if f["count"] == 0:
                continue
                
            total_count += f["count"]
            total_atual += f["atual"]
            total_novo += f["novo"]

            crescimento_grupo = (
                ((f["novo"] - f["atual"]) / f["atual"] * 100) if f["atual"] > 0 else 0.0
            )

            resumo_crm.append({
                "faixa": f["faixa"],
                "qtd": f["count"],
                "atual": f["atual"],
                "novo": f["novo"],
                "crescimento": round(crescimento_grupo, 2),
                "status": f["status"],
            })

        # Ordenar resumo (opcional, para exibir organizado na tabela do HTML)
        ordem_faixas = {"M0 a M6": 1, "M7 a M16": 2, "M17 a M22": 3, "M23+": 4}
        resumo_crm.sort(key=lambda x: (ordem_faixas.get(x["faixa"], 5), x["status"]))

        crescimento_geral = (
            ((total_novo - total_atual) / total_atual * 100)
            if total_atual > 0
            else 0.0
        )

        # Produtos e Franquias
        def processar_produtos(dicionario):
            lista = []
            qtd_tot, gb_tot = 0, 0.0
            for prod, qtd in sorted(dicionario.items(), key=lambda x: x[1], reverse=True):
                gb_unit = extrair_gb(prod)
                gb_prod = gb_unit * qtd
                qtd_tot += qtd
                gb_tot += gb_prod
                lista.append({"nome": prod, "qtd": qtd, "gb": gb_prod})
            return lista, qtd_tot, gb_tot

        planta_lista, q_p, gb_p = processar_produtos(contagem_planta)
        rec_lista, q_r, gb_r = processar_produtos(contagem_recomendacao)

        return jsonify({
            "success": True,
            "resumo_crm": resumo_crm,
            "totais_crm": {
                "count": total_count,
                "atual": total_atual,
                "novo": total_novo,
                "crescimento": round(crescimento_geral, 2),
            },
            "tem_m23_mais": tem_m23_mais,
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
