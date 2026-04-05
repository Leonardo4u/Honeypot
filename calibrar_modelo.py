import os
import sqlite3
import argparse
import requests
import pandas as pd
import numpy as np
import json
import time
import random
from io import StringIO
from datetime import datetime, timezone

from model.team_name_normalizer import normalize_df

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT_DIR, "data"))
HISTORICO_DIR = os.path.join(BOT_DATA_DIR, "historico")
DB_PATH = os.path.join(BOT_DATA_DIR, "edge_protocol.db")
CALIBRACAO_LIGAS_PATH = os.path.join(BOT_DATA_DIR, "calibracao_ligas.json")
MEDIAS_GOLS_PATH = os.path.join(BOT_DATA_DIR, "medias_gols.json")
PICKS_LOG_PATH = os.path.join(BOT_DATA_DIR, "picks_log.csv")

LIGAS_FOOTBALL_DATA = {
    # Brasileirao not available on football-data.co.uk - use API-Football source.
    "Premier League": "E0",
    "La Liga": "SP1",
    "Serie A": "I1",
    "Bundesliga": "D1",
    "Ligue 1": "F1",
}

LIGAS_API_FOOTBALL_HIST = {
    "Brasileirao Serie A": "BRA1",
}

KNOWN_TEAMS = {
    "E0": {"Arsenal", "Chelsea", "Liverpool", "Man City", "Tottenham"},
    "D1": {"Bayern Munich", "Dortmund", "Leverkusen", "RB Leipzig", "Stuttgart"},
    "SP1": {"Barcelona", "Real Madrid", "Atletico Madrid", "Sevilla", "Valencia"},
    "I1": {"Juventus", "Inter", "Milan", "Napoli", "Roma"},
    "F1": {"Paris SG", "Marseille", "Lyon", "Monaco", "Lille"},
    "BRA1": {"Flamengo", "Palmeiras", "Sao Paulo", "Corinthians", "Atletico-MG"},
}

TEAM_ALIASES = {
    "ath madrid": "atletico madrid",
    "man city": "man city",
    "paris sg": "paris sg",
    "inter": "inter",
}

HISTORICAL_SEASONS = int(os.getenv("EDGE_HISTORICAL_SEASONS", "3"))
REQUEST_HEADERS = {"User-Agent": "edge-protocol-calibration/1.1"}


def _all_leagues_map():
    merged = {}
    merged.update(LIGAS_FOOTBALL_DATA)
    merged.update(LIGAS_API_FOOTBALL_HIST)
    return merged


def _cleanup_deprecated_brazil_files():
    """Remove artefatos antigos do football-data mapeados incorretamente para Brasil."""
    for fname in ("historico_B1.csv", "historico_B2.csv", "historico_BRA2.csv"):
        path = os.path.join(BOT_DATA_DIR, fname)
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"[CLEANUP] removido arquivo legado: {path}")
            except Exception as exc:
                print(f"[WARN] falha removendo {path}: {exc}")


def _validate_known_teams(df_norm, league_code, league_name, sample_size=5):
    """Bloqueia datasets com equipes de liga incorreta para evitar corrupcao silenciosa."""
    anchors = KNOWN_TEAMS.get(str(league_code), set())
    if not anchors:
        return True, None

    teams = set()
    for col in ("time_casa", "time_fora"):
        if col in df_norm.columns:
            teams.update(str(v).strip() for v in df_norm[col].dropna().unique().tolist() if str(v).strip())
    if not teams:
        return False, f"WRONG DATA: sem times validos para {league_name} ({league_code}) - skipping"

    def _normalize_team_name(name):
        key = " ".join(str(name).strip().lower().replace(".", "").replace("-", " ").split())
        return TEAM_ALIASES.get(key, key)

    anchors_norm = {_normalize_team_name(a) for a in anchors}
    teams_norm = {_normalize_team_name(t) for t in teams}
    if not (anchors_norm & teams_norm):
        return (
            False,
            f"WRONG DATA: expected {league_name} but got different team universe - skipping",
        )

    sample_n = min(int(sample_size), len(teams))
    sampled_acc = []
    matched = False
    teams_list = list(teams)
    for seed in (42, 43, 44):
        sampled = random.Random(seed).sample(teams_list, sample_n)
        sampled_acc.extend(sampled)
        sampled_norm = {_normalize_team_name(t) for t in sampled}
        if anchors_norm & sampled_norm:
            matched = True
            break

    if not matched:
        return (
            False,
            f"WRONG DATA: expected {league_name} anchors {sorted(anchors)} but sampled {sampled_acc[:sample_n]} - skipping",
        )

    return True, None


def salvar_calibracao_ligas(rho_calibrado, amostra_por_liga=None):
    amostra_por_liga = amostra_por_liga or {}
    payload = {
        "atualizado_em": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fonte": "calibrar_modelo.py",
        "ligas": {},
    }

    for liga, rho in rho_calibrado.items():
        payload["ligas"][liga] = {
            "rho": float(rho),
            "home_advantage": 1.0,
            "amostra_jogos": int(amostra_por_liga.get(liga, 0)),
        }

    try:
        os.makedirs(os.path.dirname(CALIBRACAO_LIGAS_PATH), exist_ok=True)
        with open(CALIBRACAO_LIGAS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Calibracao salva em: {CALIBRACAO_LIGAS_PATH}")
        return True
    except Exception as e:
        print(f"[WARN] Falha ao salvar calibracao runtime: {e}")
        return False


def _escrever_calibracao_ligas(ligas_payload: dict):
    """Escreve calibracao por liga no formato consumido pelo runtime do Poisson."""
    os.makedirs(os.path.dirname(CALIBRACAO_LIGAS_PATH), exist_ok=True)
    with open(CALIBRACAO_LIGAS_PATH, "w", encoding="utf-8") as f:
        json.dump(ligas_payload, f, ensure_ascii=False, indent=2)


def _normalizar_liga_payload(payload):
    """Normaliza payload de calibracao para um dict de ligas -> params."""
    if not isinstance(payload, dict):
        return {}
    if "ligas" in payload and isinstance(payload.get("ligas"), dict):
        return payload["ligas"]
    return payload


def _season_codes(seasons_back=HISTORICAL_SEASONS):
    """Gera códigos YYYY da temporada atual + N anteriores."""
    now = datetime.now(timezone.utc)
    start_year = (now.year % 100) if now.month >= 7 else ((now.year - 1) % 100)
    out = []
    for i in range(max(0, int(seasons_back)) + 1):
        y0 = (start_year - i) % 100
        y1 = (y0 + 1) % 100
        out.append(f"{y0:02d}{y1:02d}")
    return out


def _download_csv_with_retry(url, attempts=3, backoff_seconds=0.8):
    """Baixa CSV com retry/backoff e classificação de falhas sem derrubar o pipeline."""
    last_error = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        try:
            response = requests.get(url, timeout=15, headers=REQUEST_HEADERS)
            if response.status_code == 404:
                return None, "not_found", None
            if response.status_code in (429,) or 500 <= response.status_code <= 599:
                if attempt < attempts:
                    time.sleep(backoff_seconds * attempt)
                    continue
                return None, "http_error", f"http_{response.status_code}"
            if response.status_code >= 400:
                return None, "http_error", f"http_{response.status_code}"

            text = response.content.decode("utf-8", errors="replace")
            try:
                df = pd.read_csv(StringIO(text), on_bad_lines="skip")
            except Exception as exc:
                return None, "malformed", str(exc)
            if df is None or len(df) == 0:
                return None, "empty", "empty_csv"
            return df, "ok", None
        except requests.Timeout as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            return None, "timeout", last_error
        except requests.ConnectionError as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            return None, "connection_error", last_error
        except Exception as exc:
            return None, "unknown_error", str(exc)
    return None, "unknown_error", last_error


def _normalize_history_df(df_raw, liga_nome, temporada):
    """Normaliza colunas do Football-Data para schema interno base."""
    df = df_raw.copy()
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
    df["liga"] = liga_nome
    df["temporada"] = temporada

    required = ["time_casa", "time_fora", "gols_casa", "gols_fora"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"coluna obrigatoria ausente: {col}")

    cols_base = ["liga", "temporada", "time_casa", "time_fora", "gols_casa", "gols_fora", "data_jogo"]
    cols_extra = [
        "odd_pinn_casa",
        "odd_pinn_empate",
        "odd_pinn_fora",
        "odd_b365_casa",
        "odd_b365_empate",
        "odd_b365_fora",
        "odd_over25",
        "odd_under25",
    ]
    keep = [c for c in (cols_base + cols_extra) if c in df.columns]
    df = df[keep].dropna(subset=["time_casa", "time_fora", "gols_casa", "gols_fora"]).copy()
    df["gols_casa"] = pd.to_numeric(df["gols_casa"], errors="coerce")
    df["gols_fora"] = pd.to_numeric(df["gols_fora"], errors="coerce")
    df = df.dropna(subset=["gols_casa", "gols_fora"])
    df["gols_casa"] = df["gols_casa"].astype(int)
    df["gols_fora"] = df["gols_fora"].astype(int)

    if "data_jogo" in df.columns:
        df["data_jogo"] = pd.to_datetime(df["data_jogo"], errors="coerce", dayfirst=True)
        df["data_jogo"] = df["data_jogo"].dt.strftime("%Y-%m-%d")

    return df


def _team_counts(df_league):
    """Conta partidas por time (casa+fora) para cobertura de amostra."""
    counts = {}
    for team in df_league.get("time_casa", []):
        counts[str(team)] = counts.get(str(team), 0) + 1
    for team in df_league.get("time_fora", []):
        counts[str(team)] = counts.get(str(team), 0) + 1
    return counts


def fetch_history_multi_season(seasons_back=HISTORICAL_SEASONS, leagues_map=None):
    """Baixa e consolida histórico multi-season por liga; salva `historico_<code>.csv`."""
    os.makedirs(HISTORICO_DIR, exist_ok=True)
    leagues = leagues_map or LIGAS_FOOTBALL_DATA
    seasons = _season_codes(seasons_back)
    merged_by_code = {}
    report = {}

    for liga_nome, code in sorted(leagues.items(), key=lambda x: x[0]):
        per_season = []
        fetched = []
        warnings = []
        liga_dir = os.path.join(HISTORICO_DIR, liga_nome)
        os.makedirs(liga_dir, exist_ok=True)

        for season in seasons:
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
            df_raw, status, err = _download_csv_with_retry(url)
            time.sleep(1.0)
            if status == "ok" and df_raw is not None:
                try:
                    df_norm = _normalize_history_df(df_raw, liga_nome, season)
                    is_ok, reason = _validate_known_teams(df_norm, code, liga_nome)
                    if not is_ok:
                        warnings.append(f"{season}: {reason}")
                        continue
                    per_season.append(df_norm)
                    fetched.append(season)
                    raw_path = os.path.join(liga_dir, f"{season}.csv")
                    df_raw.to_csv(raw_path, index=False)
                except Exception as exc:
                    warnings.append(f"{season}: malformed ({exc})")
            elif status == "not_found":
                warnings.append(f"{season}: 404")
            else:
                warnings.append(f"{season}: {status}{' - ' + str(err) if err else ''}")

        if not per_season:
            report[code] = {
                "league": liga_nome,
                "seasons_fetched": fetched,
                "total_matches": 0,
                "teams_found": 0,
                "min_n": 0,
                "max_n": 0,
                "warnings": warnings,
            }
            continue

        merged = pd.concat(per_season, ignore_index=True)
        if "data_jogo" not in merged.columns:
            merged["data_jogo"] = ""
        merged = merged.drop_duplicates(subset=["time_casa", "time_fora", "data_jogo"], keep="first").reset_index(drop=True)
        merged_path = os.path.join(BOT_DATA_DIR, f"historico_{code}.csv")
        merged.to_csv(merged_path, index=False)
        merged_by_code[code] = merged

        counts = _team_counts(merged)
        n_values = list(counts.values()) or [0]
        report[code] = {
            "league": liga_nome,
            "seasons_fetched": fetched,
            "total_matches": int(len(merged)),
            "teams_found": int(len(counts)),
            "min_n": int(min(n_values)),
            "max_n": int(max(n_values)),
            "warnings": warnings,
        }

    print("\n=== HISTORICAL FETCH SUMMARY ===")
    for code, info in sorted(report.items(), key=lambda x: x[0]):
        print(
            f"{info['league']} ({code}) | seasons={info['seasons_fetched']} "
            f"| matches={info['total_matches']} | teams={info['teams_found']} "
            f"| n[min,max]=[{info['min_n']},{info['max_n']}]"
        )
        for w in info.get("warnings", []):
            print(f"  [WARN] {w}")

    return {"merged_by_code": merged_by_code, "report": report}


def baixar_dados_historicos():
    """Compat: mantém assinatura antiga e baixa janela padrão multi-season."""
    result = fetch_history_multi_season(seasons_back=HISTORICAL_SEASONS)
    return sum(info.get("total_matches", 0) for info in result["report"].values())


def carregar_historico():
    dfs = []
    for liga, code in _all_leagues_map().items():
        merged_path = os.path.join(BOT_DATA_DIR, f"historico_{code}.csv")
        if not os.path.exists(merged_path):
            continue
        try:
            df = pd.read_csv(merged_path, on_bad_lines="skip")
            if str(code).startswith("BRA"):
                normalize_df(df, "time_casa")
                normalize_df(df, "time_fora")
            if "liga" not in df.columns:
                df["liga"] = liga
            dfs.append(df)
        except Exception as e:
            print(f"Erro lendo {merged_path}: {e}")

    if not dfs:
        return None

    df_total = pd.concat(dfs, ignore_index=True)
    sort_cols = [c for c in ["liga", "temporada", "data_jogo", "time_casa", "time_fora"] if c in df_total.columns]
    if sort_cols:
        df_total = df_total.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    print(f"Carregados: {len(df_total)} jogos")
    print(df_total.groupby("liga").size().rename("jogos").to_string())
    return df_total


def build_coverage_report(merged_by_code=None, min_n=50):
    """Calcula cobertura por liga/time e sinaliza times com n insuficiente."""
    if merged_by_code is None:
        merged_by_code = {}
        for liga, code in _all_leagues_map().items():
            path = os.path.join(BOT_DATA_DIR, f"historico_{code}.csv")
            if os.path.exists(path):
                try:
                    merged_by_code[code] = pd.read_csv(path, on_bad_lines="skip")
                except Exception:
                    continue

    per_league = {}
    all_team_counts = []
    leagues_with_n50 = []
    for liga, code in _all_leagues_map().items():
        df = merged_by_code.get(code)
        if df is None or len(df) == 0:
            continue
        if str(code).startswith("BRA"):
            normalize_df(df, "time_casa")
            normalize_df(df, "time_fora")
        counts = _team_counts(df)
        for c in counts.values():
            all_team_counts.append(c)
        if counts and min(counts.values()) >= int(min_n):
            leagues_with_n50.append(liga)
        per_league[code] = {
            "league": liga,
            "teams": counts,
            "mean_n": (sum(counts.values()) / len(counts)) if counts else 0.0,
        }

    return {
        "per_league": per_league,
        "mean_n_per_team": (sum(all_team_counts) / len(all_team_counts)) if all_team_counts else 0.0,
        "leagues_all_teams_n50": leagues_with_n50,
    }


def print_coverage_report(coverage, min_n=50):
    """Imprime cobertura por liga/time no formato de auditoria operacional."""
    print("\n=== COVERAGE REPORT ===")
    for code, payload in sorted(coverage.get("per_league", {}).items(), key=lambda x: x[0]):
        print(f"[{payload['league']}|{code}] mean_n={payload['mean_n']:.2f}")
        teams = payload.get("teams", {})
        for team, n in sorted(teams.items(), key=lambda kv: (-kv[1], kv[0])):
            status = "OK" if int(n) >= int(min_n) else "INSUFFICIENT"
            print(f"  - {team}: n={int(n)} [{status}]")


def rebuild_medias_from_history(merged_by_code=None):
    """Recalcula medias_gols.json a partir do histórico consolidado multi-season."""
    if merged_by_code is None:
        merged_by_code = {}
        for liga, code in _all_leagues_map().items():
            path = os.path.join(BOT_DATA_DIR, f"historico_{code}.csv")
            if os.path.exists(path):
                try:
                    merged_by_code[code] = pd.read_csv(path, on_bad_lines="skip")
                except Exception:
                    continue

    stats = {}
    for _code, df in merged_by_code.items():
        if df is None or len(df) == 0:
            continue
        if str(_code).startswith("BRA"):
            normalize_df(df, "time_casa")
            normalize_df(df, "time_fora")
        for _, row in df.iterrows():
            tc = str(row.get("time_casa", "")).strip()
            tf = str(row.get("time_fora", "")).strip()
            gc = float(row.get("gols_casa", 0) or 0)
            gf = float(row.get("gols_fora", 0) or 0)

            if tc:
                s = stats.setdefault(tc, {"gols_casa_for": 0.0, "gols_casa_against": 0.0, "jogos_casa": 0, "gols_fora_for": 0.0, "gols_fora_against": 0.0, "jogos_fora": 0})
                s["gols_casa_for"] += gc
                s["gols_casa_against"] += gf
                s["jogos_casa"] += 1
            if tf:
                s = stats.setdefault(tf, {"gols_casa_for": 0.0, "gols_casa_against": 0.0, "jogos_casa": 0, "gols_fora_for": 0.0, "gols_fora_against": 0.0, "jogos_fora": 0})
                s["gols_fora_for"] += gf
                s["gols_fora_against"] += gc
                s["jogos_fora"] += 1

    medias = {}
    for team, s in stats.items():
        jc = max(1, int(s["jogos_casa"]))
        jf = max(1, int(s["jogos_fora"]))
        medias[team] = {
            "casa": round(float(s["gols_casa_for"]) / jc, 2),
            "fora": round(float(s["gols_fora_for"]) / jf, 2),
            "gols_sofridos_casa": round(float(s["gols_casa_against"]) / jc, 2),
            "gols_sofridos_fora": round(float(s["gols_fora_against"]) / jf, 2),
        }

    os.makedirs(os.path.dirname(MEDIAS_GOLS_PATH), exist_ok=True)
    with open(MEDIAS_GOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(medias, f, ensure_ascii=False, indent=2)
    print(f"medias_gols.json reconstruido em: {MEDIAS_GOLS_PATH} | teams={len(medias)}")
    return medias


def _print_coverage_comparison(before_cov, after_cov, min_n=50):
    """Imprime comparação before/after de cobertura para auditoria de promoção."""
    before_mean = before_cov.get("mean_n_per_team", 0.0)
    after_mean = after_cov.get("mean_n_per_team", 0.0)
    print("\n=== COVERAGE BEFORE/AFTER ===")
    print(f"mean n per team: before={before_mean:.2f} -> after={after_mean:.2f}")
    print("leagues with all teams n >= 50 (before):", before_cov.get("leagues_all_teams_n50", []))
    print("leagues with all teams n >= 50 (after): ", after_cov.get("leagues_all_teams_n50", []))


def calibrar_rho_por_liga(df):
    from model.poisson import estimar_rho, RHO_POR_LIGA

    print("\n=== CALIBRACAO RHO POR LIGA ===")
    print(f"{'Liga':<28} {'Atual':>8} {'Calibrado':>10} {'Delta':>8} {'N jogos':>8}")

    rho_calibrado = {}
    amostra_por_liga = {}
    ligas_unicas = sorted(df["liga"].dropna().unique().tolist())

    for liga in ligas_unicas:
        df_l = df[df["liga"] == liga]
        dados = df_l[["gols_casa", "gols_fora"]].to_dict("records")
        amostra_por_liga[liga] = len(dados)
        rho = estimar_rho(dados, league_name=liga, debug=True)
        rho_calibrado[liga] = rho

        atual = RHO_POR_LIGA.get(liga, -0.10)
        delta = rho - atual
        print(f"{liga:<28} {atual:>8.4f} {rho:>10.4f} {delta:>+8.4f} {len(dados):>8}")

    print("Observacao: ligas com menos de 50 jogos usam fallback de rho padrao.")
    salvar_calibracao_ligas(rho_calibrado, amostra_por_liga=amostra_por_liga)
    print("\nCalibracao runtime atualizada automaticamente.")
    return rho_calibrado


def build_ligas_calibration(min_matches=50, recency_halflife=38, preloaded_df=None):
    """Constroi `calibracao_ligas.json` com rho/home_advantage/recency_halflife por liga."""
    print("=== BUILD CALIBRACAO POR LIGA ===")
    if preloaded_df is None:
        total = baixar_dados_historicos()
        if total == 0:
            print("Sem dados historicos para calibrar.")
            return {}
        df = carregar_historico()
    else:
        df = preloaded_df
    if df is None or len(df) == 0:
        print("Sem partidas validas para calibracao.")
        return {}

    from model.poisson import estimar_rho

    ligas_payload = {}
    summary_rows = []
    ligas = sorted(df["liga"].dropna().unique().tolist())
    for liga in ligas:
        df_l = df[df["liga"] == liga].copy()
        n_matches = int(len(df_l))
        if n_matches < int(min_matches):
            print(f"[SKIP] {liga}: n={n_matches} < min_matches={int(min_matches)}")
            continue

        dados = df_l[["gols_casa", "gols_fora"]].to_dict("records")
        rho = float(estimar_rho(dados, recency_halflife=recency_halflife, league_name=liga, debug=True))

        mean_home = float(df_l["gols_casa"].mean()) if n_matches > 0 else 1.0
        mean_away = float(df_l["gols_fora"].mean()) if n_matches > 0 else 1.0
        if mean_away <= 0:
            home_advantage = 1.0
        else:
            home_advantage = max(0.5, min(1.5, mean_home / mean_away))

        ligas_payload[liga] = {
            "rho": round(rho, 4),
            "home_advantage": round(float(home_advantage), 4),
            "recency_halflife": int(recency_halflife),
        }
        summary_rows.append((liga, n_matches, rho, home_advantage))

    first_run = (not os.path.exists(CALIBRACAO_LIGAS_PATH)) or (os.path.getsize(CALIBRACAO_LIGAS_PATH) == 0)
    # INTEGRATION: arquivo consumido por model/poisson.py para rho/home_advantage/halflife por liga.
    _escrever_calibracao_ligas(ligas_payload)
    print(f"Calibracao por liga salva em: {CALIBRACAO_LIGAS_PATH}")

    if first_run:
        print("\nleague                      n_matches      rho   home_advantage")
        print("---------------------------------------------------------------")
        for liga, n_matches, rho, home_adv in summary_rows:
            print(f"{liga:<26} {n_matches:>9d} {rho:>8.4f} {home_adv:>16.4f}")

    return ligas_payload


def calcular_brier_historico(df, n_amostras=1000, random_state=42):
    from model.poisson import calcular_probabilidades
    from data.xg_understat import calcular_media_gols_com_xg

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
    from model.poisson import calcular_probabilidades, calcular_prob_over_under
    from data.xg_understat import calcular_media_gols_com_xg

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
    from model.poisson import calcular_probabilidades, calcular_prob_over_under
    from data.xg_understat import calcular_media_gols_com_xg
    from data.database import garantir_schema_historico_sinais

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

    _cleanup_deprecated_brazil_files()

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
    print("1. Revisar data/calibracao_ligas.json se desejar auditoria dos parametros")
    print("2. O banco ja tem historico - forma_recente.py")
    print("   vai usar calcular_confianca_calibrada() automaticamente")
    print("3. poisson.py aplica rho/home_advantage por liga automaticamente")
    print("   usando o arquivo de calibracao salvo neste processo")
    if brier and brier.get("brier_score") is not None:
        if brier["brier_score"] < 0.20:
            print("4. Brier Score EXCELENTE - modelo bem calibrado")
        elif brier["brier_score"] < 0.25:
            print("4. Brier Score BOM - monitorar com dados reais")
        else:
            print("4. Brier Score ALTO - revisar xG de entrada do modelo")
    print("\nRODAR: python calibrar_modelo.py")


def parse_args(argv=None):
    """Parseia argumentos da CLI de calibracao."""
    parser = argparse.ArgumentParser(description="Calibracao de modelo e ligas")
    parser.add_argument("--fetch-history", action="store_true", help="Baixa e consolida histórico multi-season")
    parser.add_argument("--fetch-historico-br", action="store_true", help="Busca histórico BR via API-Football (BRA1)")
    parser.add_argument("--seasons", type=int, default=HISTORICAL_SEASONS, help="Qtde de temporadas passadas além da atual")
    parser.add_argument("--check-coverage", action="store_true", help="Mostra cobertura n por liga/time")
    parser.add_argument("--build-ligas", action="store_true", help="Gera calibracao_ligas.json com rho/home_advantage")
    parser.add_argument("--min-matches", type=int, default=50, help="Minimo de jogos por liga para calibrar")
    parser.add_argument("--walk-forward-validate", action="store_true", help="Executa validacao walk-forward com picks_log")
    parser.add_argument("--wf-train-months", type=int, default=12)
    parser.add_argument("--wf-val-months", type=int, default=3)
    parser.add_argument("--wf-test-months", type=int, default=3)
    return parser.parse_args(argv)


def _run_walk_forward_validation(train_months=12, val_months=3, test_months=3):
    if not os.path.exists(PICKS_LOG_PATH):
        print(f"[WF] picks_log inexistente: {PICKS_LOG_PATH}")
        return []

    df = pd.read_csv(PICKS_LOG_PATH)
    if df.empty or "outcome" not in df.columns:
        print("[WF] sem dados com outcome no picks_log")
        return []

    df = df[df["outcome"].isin([0, 1])].copy()
    if df.empty:
        print("[WF] nenhuma linha settled para validacao")
        return []

    date_col = "timestamp" if "timestamp" in df.columns else None
    if not date_col:
        print("[WF] coluna timestamp ausente no picks_log")
        return []

    rows = []
    for _, r in df.iterrows():
        try:
            rows.append(
                {
                    "date": str(r.get(date_col) or ""),
                    "prob": float(r.get("calibrated_prob_model") or 0.0),
                    "odd": float(r.get("odds_at_pick") or 0.0),
                    "stake": float(r.get("kelly_stake") or 1.0),
                    "outcome": int(r.get("outcome")),
                }
            )
        except Exception:
            continue

    if len(rows) < 60:
        print(f"[WF] amostra insuficiente para folds robustos: {len(rows)}")
        return []

    from model.walk_forward import WalkForwardValidator
    from data.database import registrar_walk_forward_result

    wf = WalkForwardValidator(
        train_months=int(train_months),
        val_months=int(val_months),
        test_months=int(test_months),
    )

    # Baseline temporal: sem tuning intrafold, apenas avaliacao OOS da serie.
    folds = wf.run_folds(
        rows,
        fit_fn=lambda train_rows: None,
        select_fn=lambda val_rows: {"mode": "baseline"},
        apply_fn=lambda params, test_rows: test_rows,
    )

    for fold in folds:
        registrar_walk_forward_result(
            fold_id=fold.fold_id,
            data_inicio=fold.data_inicio,
            data_fim=fold.data_fim,
            brier_val=fold.brier_val,
            brier_test=fold.brier_test,
            roi_test=fold.roi_test,
            n_picks=fold.n_picks,
        )

    print(f"[WF] folds gerados: {len(folds)}")
    for fold in folds:
        print(
            f"  - {fold.fold_id} {fold.data_inicio}->{fold.data_fim} "
            f"brier_test={fold.brier_test:.4f} roi_test={fold.roi_test:.4f} n={fold.n_picks}"
        )
    return folds


def main(argv=None):
    """Entrypoint CLI para calibracao completa ou build de ligas."""
    args = parse_args(argv)
    if args.fetch_history:
        _cleanup_deprecated_brazil_files()
        before_cov = build_coverage_report(min_n=args.min_matches)
        fetched = fetch_history_multi_season(seasons_back=args.seasons)
        if args.fetch_historico_br:
            try:
                from atualizar_stats import fetch_historico_br_ligas

                br_payload = fetch_historico_br_ligas(seasons=args.seasons)
                for code, br_rows in br_payload.items():
                    if br_rows is not None and len(br_rows) >= int(args.min_matches):
                        fetched["merged_by_code"][code] = pd.DataFrame(br_rows)
            except Exception as exc:
                print(f"[WARN] falha no fetch historico BR via API-Football: {exc}")

        rebuild_medias_from_history()
        after_cov = build_coverage_report(min_n=args.min_matches)
        _print_coverage_comparison(before_cov, after_cov, min_n=args.min_matches)
        print_coverage_report(after_cov, min_n=args.min_matches)
        if args.build_ligas:
            merged_df = carregar_historico()
            build_ligas_calibration(
                min_matches=args.min_matches,
                recency_halflife=38,
                preloaded_df=merged_df,
            )
        return 0

    if args.fetch_historico_br:
        try:
            from atualizar_stats import fetch_historico_br_ligas

            before_cov = build_coverage_report(min_n=args.min_matches)
            br_payload = fetch_historico_br_ligas(seasons=args.seasons)
            merged_by_code = {}
            for code, br_rows in br_payload.items():
                if br_rows is not None and len(br_rows) >= int(args.min_matches):
                    merged_by_code[code] = pd.DataFrame(br_rows)
            rebuild_medias_from_history()
            after_cov = build_coverage_report(min_n=args.min_matches)
            _print_coverage_comparison(before_cov, after_cov, min_n=args.min_matches)
            print_coverage_report(after_cov, min_n=args.min_matches)
            if args.build_ligas:
                merged_df = carregar_historico()
                build_ligas_calibration(
                    min_matches=args.min_matches,
                    recency_halflife=38,
                    preloaded_df=merged_df,
                )
        except Exception as exc:
            print(f"[WARN] falha no fetch historico BR via API-Football: {exc}")
        return 0

    if args.check_coverage:
        cov = build_coverage_report(min_n=args.min_matches)
        print_coverage_report(cov, min_n=args.min_matches)
        return 0

    if args.walk_forward_validate:
        _run_walk_forward_validation(
            train_months=args.wf_train_months,
            val_months=args.wf_val_months,
            test_months=args.wf_test_months,
        )
        return 0

    if args.build_ligas:
        build_ligas_calibration(min_matches=args.min_matches)
        return 0

    rodar_calibracao_completa()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
