import os
import sys
import sqlite3
import requests
import pandas as pd
import numpy as np

# Garante que os modulos do projeto sao encontrados
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "data"))
sys.path.insert(0, os.path.join(ROOT_DIR, "model"))

DB_PATH = os.path.join(ROOT_DIR, "data", "edge_protocol.db")

LIGAS_FOOTBALL_DATA = {
    "Premier League": "E0",
    "La Liga": "SP1",
    "Serie A": "I1",
    "Bundesliga": "D1",
    "Ligue 1": "F1",
}

# Brasileirao nao esta disponivel no Football-Data
# Usar medias_gols.json como fallback para times brasileiros
TEMPORADAS = ["2425", "2324", "2223", "2122", "2021"]
REQUEST_HEADERS = {"User-Agent": "edge-protocol-calibration/1.1"}


def baixar_dados_historicos():
    os.makedirs(os.path.join(ROOT_DIR, "data", "historico"), exist_ok=True)
    total = 0

    for liga, codigo in sorted(LIGAS_FOOTBALL_DATA.items(), key=lambda item: item[0]):
        pasta_liga = os.path.join(ROOT_DIR, "data", "historico", liga)
        os.makedirs(pasta_liga, exist_ok=True)
        total_liga = 0

        for temp in TEMPORADAS:
            url = f"https://www.football-data.co.uk/mmz4281/{temp}/{codigo}.csv"
            path = os.path.join(pasta_liga, f"{temp}.csv")

            if os.path.exists(path):
                try:
                    df_existing = pd.read_csv(path, on_bad_lines="skip")
                    jogos = len(df_existing)
                    print(f"[CACHE] {liga} {temp}: {jogos} jogos")
                    total += jogos
                    total_liga += jogos
                    continue
                except Exception as e:
                    print(f"[CACHE-ERRO] {liga} {temp}: {e} -> redownload")

            try:
                r = requests.get(url, timeout=15, headers=REQUEST_HEADERS)
                if r.status_code == 200 and len(r.content) > 500:
                    with open(path, "wb") as f:
                        f.write(r.content)
                    df = pd.read_csv(path, on_bad_lines="skip")
                    jogos = len(df)
                    total += jogos
                    total_liga += jogos
                    print(f"[OK] {liga} {temp}: {jogos} jogos")
                else:
                    print(f"[--] {liga} {temp}: nao encontrado")
            except Exception as e:
                print(f"[ERRO] {liga} {temp}: {e}")
                continue

        print(f"[LIGA] {liga}: {total_liga} jogos acumulados")

    print(f"\nTotal: {total} jogos disponiveis")
    return total


def carregar_historico():
    dfs = []

    for liga in LIGAS_FOOTBALL_DATA:
        for temp in TEMPORADAS:
            path = os.path.join(ROOT_DIR, "data", "historico", liga, f"{temp}.csv")
            if not os.path.exists(path):
                continue

            try:
                # copy() evita fragmentacao interna em CSVs com muitas colunas
                # antes de adicionarmos colunas auxiliares como liga/temporada.
                df = pd.read_csv(path, on_bad_lines="skip").copy()
                df["liga"] = liga
                df["temporada"] = temp

                # Mapear colunas do Football-Data para nomes padrao internos
                rename = {
                    "HomeTeam": "time_casa",
                    "AwayTeam": "time_fora",
                    "FTHG": "gols_casa",
                    "FTAG": "gols_fora",
                    "PSH": "odd_pinn_casa",
                    "PSD": "odd_pinn_empate",
                    "PSA": "odd_pinn_fora",
                    "B365H": "odd_b365_casa",
                    "B365D": "odd_b365_empate",
                    "B365A": "odd_b365_fora",
                    "BbAv>2.5": "odd_over25",
                    "BbAv<2.5": "odd_under25",
                    "Date": "data_jogo",
                }
                df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

                cols_base = ["liga", "temporada", "time_casa", "time_fora", "gols_casa", "gols_fora"]
                cols_extra = [
                    "odd_pinn_casa",
                    "odd_pinn_empate",
                    "odd_pinn_fora",
                    "odd_b365_casa",
                    "odd_b365_empate",
                    "odd_b365_fora",
                    "odd_over25",
                    "odd_under25",
                    "data_jogo",
                ]
                cols = cols_base + [c for c in cols_extra if c in df.columns]

                df = df[cols].dropna(subset=["gols_casa", "gols_fora", "time_casa", "time_fora"])
                df["gols_casa"] = df["gols_casa"].astype(int)
                df["gols_fora"] = df["gols_fora"].astype(int)

                if "data_jogo" in df.columns:
                    df["data_jogo"] = pd.to_datetime(
                        df["data_jogo"],
                        errors="coerce",
                        dayfirst=True,
                    )
                    df["data_jogo"] = df["data_jogo"].dt.strftime("%Y-%m-%d")

                dfs.append(df)
            except Exception as e:
                print(f"Erro {liga}/{temp}: {e}")

    if not dfs:
        return None

    df_total = pd.concat(dfs, ignore_index=True)
    sort_cols = [c for c in ["liga", "temporada", "data_jogo", "time_casa", "time_fora"] if c in df_total.columns]
    if sort_cols:
        df_total = df_total.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    print(f"Carregados: {len(df_total)} jogos")
    print(df_total.groupby("liga").size().rename("jogos").to_string())
    return df_total


def calibrar_rho_por_liga(df):
    from poisson import estimar_rho, RHO_POR_LIGA

    print("\n=== CALIBRACAO RHO POR LIGA ===")
    print(f"{'Liga':<28} {'Atual':>8} {'Calibrado':>10} {'Delta':>8} {'N jogos':>8}")

    rho_calibrado = {}
    ligas_unicas = sorted(df["liga"].dropna().unique().tolist())

    for liga in ligas_unicas:
        df_l = df[df["liga"] == liga]
        dados = df_l[["gols_casa", "gols_fora"]].to_dict("records")
        rho = estimar_rho(dados)
        rho_calibrado[liga] = rho

        atual = RHO_POR_LIGA.get(liga, -0.10)
        delta = rho - atual
        print(f"{liga:<28} {atual:>8.4f} {rho:>10.4f} {delta:>+8.4f} {len(dados):>8}")

    print("Observacao: ligas com menos de 50 jogos usam fallback de rho padrao.")

    print("\nCopie os valores acima e atualize RHO_POR_LIGA em poisson.py")
    return rho_calibrado


def calcular_brier_historico(df, n_amostras=1000, random_state=42):
    from poisson import calcular_probabilidades
    from xg_understat import calcular_media_gols_com_xg

    print(f"\n=== BRIER SCORE HISTORICO (amostra: {n_amostras} jogos) ===")
    amostra = df.sample(min(n_amostras, len(df)), random_state=random_state)

    brier_scores = []
    sem_xg = 0

    for _, row in amostra.iterrows():
        try:
            xg_c, xg_f, fonte = calcular_media_gols_com_xg(row["time_casa"], row["time_fora"])
            probs = calcular_probabilidades(xg_c, xg_f, liga=row["liga"])

            gc, gf = int(row["gols_casa"]), int(row["gols_fora"])
            if gc > gf:
                resultado = "casa"
            elif gc == gf:
                resultado = "empate"
            else:
                resultado = "fora"

            # Brier para a probabilidade mais alta (o que o bot apostaria)
            prob_max = max(probs["prob_casa"], probs["prob_empate"], probs["prob_fora"])
            if probs["prob_casa"] >= prob_max:
                acertou = 1 if resultado == "casa" else 0
            elif probs["prob_empate"] >= prob_max:
                acertou = 1 if resultado == "empate" else 0
            else:
                acertou = 1 if resultado == "fora" else 0

            brier_scores.append((prob_max - acertou) ** 2)

            if fonte == "medias" or fonte == "médias":
                sem_xg += 1
        except Exception:
            continue

    if not brier_scores:
        print("Nenhum dado processado.")
        return {
            "brier_score": None,
            "jogos_processados": 0,
            "sem_xg": 0,
            "sem_xg_pct": 0.0,
            "classificacao": "sem_dados",
            "amostra_solicitada": int(n_amostras),
            "seed": random_state,
        }

    brier = sum(brier_scores) / len(brier_scores)
    sem_xg_pct = (sem_xg / len(brier_scores) * 100)
    print(f"Jogos processados: {len(brier_scores)}")
    print(f"Sem dados xG (usou medias): {sem_xg} ({sem_xg_pct:.0f}%)")
    print(f"Brier Score: {brier:.4f}", end="  ->  ")
    if brier < 0.20:
        print("EXCELENTE")
        classificacao = "excelente"
    elif brier < 0.25:
        print("BOM")
        classificacao = "bom"
    else:
        print("MODELO PRECISA DE AJUSTE")
        classificacao = "ajuste"

    return {
        "brier_score": round(float(brier), 4),
        "jogos_processados": len(brier_scores),
        "sem_xg": sem_xg,
        "sem_xg_pct": round(float(sem_xg_pct), 2),
        "classificacao": classificacao,
        "amostra_solicitada": int(n_amostras),
        "seed": random_state,
    }


def _odd_valida(valor):
    if valor is None:
        return None
    if pd.isna(valor):
        return None
    try:
        odd = float(valor)
    except Exception:
        return None
    if odd <= 1.30:
        return None
    return odd


def calcular_win_rate_historico(df):
    from poisson import calcular_probabilidades, calcular_prob_over_under
    from xg_understat import calcular_media_gols_com_xg

    print("\n=== WIN RATE HISTORICO DO MODELO ===")

    mercados = {
        "over_2.5": {"total": 0, "wins": 0, "lucro": 0.0, "ev_soma": 0.0},
        "1x2_casa": {"total": 0, "wins": 0, "lucro": 0.0, "ev_soma": 0.0},
        "1x2_fora": {"total": 0, "wins": 0, "lucro": 0.0, "ev_soma": 0.0},
    }
    ev_min = 0.06
    amostra_minima = 30

    for _, row in df.iterrows():
        try:
            xg_c, xg_f, _ = calcular_media_gols_com_xg(row["time_casa"], row["time_fora"])
            gc, gf = int(row["gols_casa"]), int(row["gols_fora"])

            odd_over = _odd_valida(row.get("odd_over25"))
            probs_ou = calcular_prob_over_under(xg_c, xg_f, 2.5)
            probs_1x2 = calcular_probabilidades(xg_c, xg_f, liga=row["liga"])

            odd_casa = _odd_valida(row.get("odd_pinn_casa")) or _odd_valida(row.get("odd_b365_casa"))
            odd_fora = _odd_valida(row.get("odd_pinn_fora")) or _odd_valida(row.get("odd_b365_fora"))

            # Over 2.5
            if odd_over:
                ev = probs_ou["prob_over"] * odd_over - 1
                if ev >= ev_min:
                    ganhou = (gc + gf) > 2.5
                    lucro = round(odd_over - 1, 4) if ganhou else -1.0
                    mercados["over_2.5"]["total"] += 1
                    mercados["over_2.5"]["wins"] += int(ganhou)
                    mercados["over_2.5"]["lucro"] += lucro
                    mercados["over_2.5"]["ev_soma"] += ev

            # 1x2 Casa
            if odd_casa:
                ev = probs_1x2["prob_casa"] * odd_casa - 1
                if ev >= ev_min:
                    ganhou = gc > gf
                    lucro = round(odd_casa - 1, 4) if ganhou else -1.0
                    mercados["1x2_casa"]["total"] += 1
                    mercados["1x2_casa"]["wins"] += int(ganhou)
                    mercados["1x2_casa"]["lucro"] += lucro
                    mercados["1x2_casa"]["ev_soma"] += ev

            # 1x2 Fora
            if odd_fora:
                ev = probs_1x2["prob_fora"] * odd_fora - 1
                if ev >= ev_min:
                    ganhou = gf > gc
                    lucro = round(odd_fora - 1, 4) if ganhou else -1.0
                    mercados["1x2_fora"]["total"] += 1
                    mercados["1x2_fora"]["wins"] += int(ganhou)
                    mercados["1x2_fora"]["lucro"] += lucro
                    mercados["1x2_fora"]["ev_soma"] += ev
        except Exception:
            continue

    print(f"\n{'Mercado':<12} {'Sinais':>8} {'Win Rate':>10} {'ROI':>8} {'Lucro':>10} {'Qualidade':>11}")
    print("-" * 52)
    resumo = {}
    for mercado, r in mercados.items():
        total = r["total"]
        wr = (r["wins"] / total * 100) if total > 0 else 0.0
        roi = (r["lucro"] / total * 100) if total > 0 else 0.0
        qualidade = "baixa_amostra" if 0 < total < amostra_minima else ("sem_sinal" if total == 0 else "ok")
        print(f"{mercado:<12} {total:>8} {wr:>9.1f}% {roi:>+7.2f}% {r['lucro']:>+10.2f}u {qualidade:>11}")
        resumo[mercado] = {
            "total": total,
            "wins": r["wins"],
            "lucro": round(float(r["lucro"]), 4),
            "ev_soma": round(float(r["ev_soma"]), 4),
            "win_rate_pct": round(float(wr), 2),
            "roi_pct": round(float(roi), 2),
            "qualidade": qualidade,
        }

    return resumo


def popular_banco_historico(df, n_max=2000):
    from poisson import calcular_probabilidades, calcular_prob_over_under
    from xg_understat import calcular_media_gols_com_xg
    from database import garantir_schema_historico_sinais

    print(f"\n=== POPULANDO BANCO COM HISTORICO (max {n_max} registros) ===")

    garantir_schema_historico_sinais(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Verificar se tabela sinais existe
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sinais'")
    if not c.fetchone():
        print("Tabela 'sinais' nao encontrada. Pulando populacao historica.")
        conn.close()
        return 0

    amostra = df.sample(min(n_max, len(df)), random_state=42)
    inseridos = 0
    duplicados = 0
    falhas = 0
    ev_min = 0.06

    for _, row in amostra.iterrows():
        try:
            xg_c, xg_f, _ = calcular_media_gols_com_xg(row["time_casa"], row["time_fora"])
            gc, gf = int(row["gols_casa"]), int(row["gols_fora"])

            probs_ou = calcular_prob_over_under(xg_c, xg_f, 2.5)
            _ = calcular_probabilidades(xg_c, xg_f, liga=row["liga"])

            # Odd Over 2.5 - tenta coluna dedicada, fallback para b365
            odd_over = _odd_valida(row.get("odd_over25"))
            if not odd_over:
                odd_over = _odd_valida(row.get("odd_b365_casa"))
            if not odd_over:
                odd_over = 1.85

            ev_over = probs_ou["prob_over"] * float(odd_over) - 1

            if ev_over >= ev_min:
                ganhou = (gc + gf) > 2.5
                resultado = "verde" if ganhou else "vermelho"
                lucro = round(float(odd_over) - 1, 4) if ganhou else -1.0
                data = str(row.get("data_jogo", "2024-01-01"))[:10]

                c.execute(
                    """
                    INSERT OR IGNORE INTO sinais
                    (data, liga, jogo, mercado, odd, ev_estimado,
                     edge_score, stake_unidades, status, resultado,
                     lucro_unidades, fonte)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        data,
                        row["liga"],
                        f"{row['time_casa']} vs {row['time_fora']}",
                        "over_2.5",
                        float(odd_over),
                        round(ev_over, 4),
                        75,
                        1.0,
                        "finalizado",
                        resultado,
                        lucro,
                        "historico",
                    ),
                )
                if c.rowcount == 0:
                    duplicados += 1
                else:
                    inseridos += 1
        except Exception:
            falhas += 1
            continue

    conn.commit()
    conn.close()
    print(
        f"Backfill historico: inseridos={inseridos} | "
        f"duplicados={duplicados} | falhas={falhas}"
    )
    print("calcular_confianca_calibrada() ja pode usar esses dados.")
    return {
        "inseridos": inseridos,
        "duplicados": duplicados,
        "falhas": falhas,
    }


def rodar_calibracao_completa():
    print("=" * 55)
    print("  CALIBRACAO EDGE PROTOCOL")
    print("=" * 55)

    print("\n[1/6] Baixando dados historicos (Football-Data.co.uk)...")
    total = baixar_dados_historicos()
    if total == 0:
        print("ERRO: sem dados. Verificar conexao com internet.")
        return

    print("\n[2/6] Carregando e normalizando CSVs...")
    df = carregar_historico()
    if df is None or len(df) == 0:
        print("ERRO: nenhum dado carregado.")
        return

    print("\n[3/6] Calibrando rho por liga...")
    _ = calibrar_rho_por_liga(df)

    print("\n[4/6] Calculando Brier Score historico...")
    brier = calcular_brier_historico(df, n_amostras=1000)

    print("\n[5/6] Calculando win rate historico do modelo...")
    calcular_win_rate_historico(df)

    print("\n[6/6] Populando banco com historico...")
    popular_banco_historico(df, n_max=2000)

    print("\n" + "=" * 55)
    print("  CALIBRACAO CONCLUIDA")
    print("=" * 55)
    print("\nPROXIMOS PASSOS:")
    print("1. Abrir poisson.py e atualizar RHO_POR_LIGA")
    print("   com os valores calibrados mostrados acima")
    print("2. O banco ja tem historico - forma_recente.py")
    print("   vai usar calcular_confianca_calibrada() automaticamente")
    print("3. Este script nao altera poisson.py automaticamente")
    print("   (apenas mostra os valores calibrados para aplicacao manual)")
    if brier and brier.get("brier_score") is not None:
        if brier["brier_score"] < 0.20:
            print("4. Brier Score EXCELENTE - modelo bem calibrado")
        elif brier["brier_score"] < 0.25:
            print("4. Brier Score BOM - monitorar com dados reais")
        else:
            print("4. Brier Score ALTO - revisar xG de entrada do modelo")
    print("\nRODAR: python calibrar_modelo.py")


if __name__ == "__main__":
    rodar_calibracao_completa()
