from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import numpy as np
import io

app = Flask(__name__)
CORS(app)  # Permite comunicação com o frontend

# ==========================================
# CENTRAL DE REGRAS DE NEGÓCIO EM PYTHON
# ==========================================
REGRAS = {
    "FAIXA_1_FIM": 6,  # M0 até M6
    "FAIXA_2_FIM": 16,  # M7 até M16
    "UPGRADE_MIN_M7": 10,  # Crescimento mín. 10%
    "UPGRADE_MIN_M17": 5,  # Crescimento mín. 5%
}


def extrair_gb(nome_produto):
  if not isinstance(nome_produto, str):
    return 0
  if "0.2" in nome_produto or "0,2" in nome_produto:
    return 0.2
  import re

  match = re.search(r"(\d+)\s*GB", nome_produto, re.IGNORECASE)
  return int(match.group(1)) if match else 0


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

    faixas_resultado = {
        "M0 a M6": {"count": 0, "atual": 0.0, "novo": 0.0},
        "M7 a M16": {"count": 0, "atual": 0.0, "novo": 0.0},
        "M17+": {"count": 0, "atual": 0.0, "novo": 0.0},
    }

    contagem_planta = {}
    contagem_recomendacao = {}
    tem_m17_mais = False

    for _, row in df.iterrows():
      m = row["M"]
      fat_atual = row["FaturamentoAtual"]
      fat_novo = row["FaturamentoPara"]
      planta = row["ProdutoPlanta"]
      recomendacao = row["ProdutoRecomendacao"]

      crescimento = (
          ((fat_novo - fat_atual) / fat_atual * 100) if fat_atual > 0 else 0.0
      )

      # Classificação por faixa de meses
      if m <= REGRAS["FAIXA_1_FIM"]:
        fx = "M0 a M6"
      elif m <= REGRAS["FAIXA_2_FIM"]:
        fx = "M7 a M16"
      else:
        fx = "M17+"
        tem_m17_mais = True

      faixas_resultado[fx]["count"] += 1
      faixas_resultado[fx]["atual"] += fat_atual
      faixas_resultado[fx]["novo"] += fat_novo

      contagem_planta[planta] = contagem_planta.get(planta, 0) + 1
      contagem_recomendacao[recomendacao] = (
          contagem_recomendacao.get(recomendacao, 0) + 1
      )

    # Montando estrutura de resposta para o Frontend
    resumo_crm = []
    total_count, total_atual, total_novo = 0, 0.0, 0.0

    for nome_fx, f in faixas_resultado.items():
      if f["count"] == 0:
        continue
      total_count += f["count"]
      total_atual += f["atual"]
      total_novo += f["novo"]

      crescimento_fx = (
          ((f["novo"] - f["atual"]) / f["atual"] * 100) if f["atual"] > 0 else 0.0
      )
      status = "-"

      if nome_fx == "M0 a M6":
        status = "FORA DO MAILING"
      elif nome_fx == "M7 a M16":
        status = (
            "UPGRADE" if crescimento_fx >= REGRAS["UPGRADE_MIN_M7"] else "FORA DO MAILING"
        )
      elif nome_fx == "M17+":
        if crescimento_fx < 0:
          status = "DOWNGRADE"
        elif crescimento_fx >= REGRAS["UPGRADE_MIN_M17"]:
          status = "UPGRADE"
        elif crescimento_fx >= 0:
          status = "PADRÃO"
        else:
          status = "FORA DO MAILING"

      resumo_crm.append({
          "faixa": nome_fx,
          "qtd": f["count"],
          "atual": f["atual"],
          "novo": f["novo"],
          "crescimento": round(crescimento_fx, 2),
          "status": status,
      })

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
        "tem_m17_mais": tem_m17_mais,
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
  app.run(debug=True, port=5000)