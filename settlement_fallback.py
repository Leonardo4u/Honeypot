"""
Fallback de settlement para sinais presos em status pendente.

Objetivo:
- Encontrar sinais antigos que ficaram pendentes.
- Tentar resolver placar por camadas de fallback (API-Football -> Sofascore -> Flashscore).
- Liquidar automaticamente mercados suportados.
- Marcar casos sem resultado para intervencao manual.

Uso standalone:
    python settlement_fallback.py

Uso por import:
    from settlement_fallback import processar_fallback
    processar_fallback()
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
from api_football import ApiFootball

DEFAULT_DB_PATH = os.path.join("data", "edge_protocol.db")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_HOST = "v3.football.api-sports.io"
REQUEST_TIMEOUT = 12
STALE_DAYS_DEFAULT = 2

STATUS_FINALIZADO_API = {"FT", "AET", "PEN"}


@dataclass
class SinalPendente:
    sinal_id: int
    data: str
    jogo: str
    mercado: str
    odd: float
    stake_unidades: float
    fixture_id_api: Optional[str]
    fixture_data_api: Optional[str]


@dataclass
class ResultadoBusca:
    gols_casa: int
    gols_fora: int
    fonte: str


@dataclass
class Liquidacao:
    sinal_id: int
    jogo: str
    placar: str
    mercado: str
    resultado: str
    lucro: float


def _normalizar_nome_time(nome: Any) -> str:
    txt = unicodedata.normalize("NFKD", str(nome or ""))
    txt = txt.encode("ascii", "ignore").decode("ascii")
    txt = " ".join(txt.lower().replace("-", " ").split())
    return txt


def _split_jogo(jogo: str) -> Optional[Tuple[str, str]]:
    partes = str(jogo or "").split(" vs ")
    if len(partes) != 2:
        return None
    return partes[0].strip(), partes[1].strip()


def _score_nomes(home_ref: str, away_ref: str, home_api: str, away_api: str) -> int:
    a = _normalizar_nome_time(home_ref)
    b = _normalizar_nome_time(away_ref)
    c = _normalizar_nome_time(home_api)
    d = _normalizar_nome_time(away_api)

    score = 0
    if a == c:
        score += 10
    elif a in c or c in a:
        score += 6

    if b == d:
        score += 10
    elif b in d or d in b:
        score += 6

    return score


def _safe_request_json(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def _safe_request_text(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def _headers_api_football() -> Dict[str, str]:
    return {
        "x-rapidapi-host": API_FOOTBALL_HOST,
        "x-rapidapi-key": API_FOOTBALL_KEY,
    }


def _buscar_resultado_api_football(time_casa: str, time_fora: str, data_ref: str, fixture_id_api: Optional[str]) -> Optional[ResultadoBusca]:
    if not API_FOOTBALL_KEY:
        return None

    headers = _headers_api_football()

    # Tentativa 1: fixture_id direto
    if fixture_id_api:
        payload = _safe_request_json(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"id": str(fixture_id_api), "timezone": "America/Sao_Paulo"},
        )
        try:
            fixtures = payload.get("response", []) if isinstance(payload, dict) else []
            if fixtures:
                fx = fixtures[0]
                status_short = str(fx.get("fixture", {}).get("status", {}).get("short", ""))
                if status_short in STATUS_FINALIZADO_API:
                    g_home = fx.get("goals", {}).get("home")
                    g_away = fx.get("goals", {}).get("away")
                    if g_home is not None and g_away is not None:
                        return ResultadoBusca(int(g_home), int(g_away), "api-football:fixture_id")
        except Exception:
            pass

    # Tentativa 2: janela por data + match de nomes
    try:
        base_dt = datetime.strptime(str(data_ref), "%Y-%m-%d")
    except Exception:
        base_dt = datetime.now()

    candidatos: List[Tuple[int, Dict[str, Any]]] = []

    for offset in (-2, -1, 0, 1, 2):
        data_alvo = (base_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        payload = _safe_request_json(
            "https://v3.football.api-sports.io/fixtures",
            headers=headers,
            params={"date": data_alvo, "timezone": "America/Sao_Paulo"},
        )
        if not isinstance(payload, dict):
            continue

        for fx in payload.get("response", []) or []:
            home = str(fx.get("teams", {}).get("home", {}).get("name", ""))
            away = str(fx.get("teams", {}).get("away", {}).get("name", ""))
            score = _score_nomes(time_casa, time_fora, home, away)
            if score > 0:
                candidatos.append((score, fx))

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: item[0], reverse=True)
    melhor = candidatos[0][1]

    try:
        status_short = str(melhor.get("fixture", {}).get("status", {}).get("short", ""))
        if status_short not in STATUS_FINALIZADO_API:
            return None
        g_home = melhor.get("goals", {}).get("home")
        g_away = melhor.get("goals", {}).get("away")
        if g_home is None or g_away is None:
            return None
        return ResultadoBusca(int(g_home), int(g_away), "api-football:date_window")
    except Exception:
        return None


def _buscar_resultado_sofascore(time_casa: str, time_fora: str, data_ref: str) -> Optional[ResultadoBusca]:
    # Busca publica por texto no endpoint de busca do Sofascore.
    query = f"{time_casa} {time_fora}"
    url = "https://api.sofascore.com/api/v1/search/all"
    payload = _safe_request_json(url, params={"q": query})
    if not isinstance(payload, dict):
        return None

    eventos = payload.get("results", []) or []
    data_key = str(data_ref)

    candidatos: List[Tuple[int, int]] = []

    for item in eventos:
        try:
            entity = item.get("entity", {}) or {}
            if str(item.get("type", "")).lower() != "event":
                continue
            event_id = entity.get("id")
            if event_id is None:
                continue

            home = str(entity.get("homeTeam", {}).get("name", ""))
            away = str(entity.get("awayTeam", {}).get("name", ""))
            score_nomes = _score_nomes(time_casa, time_fora, home, away)
            if score_nomes <= 0:
                continue

            start_ts = entity.get("startTimestamp")
            score_data = 0
            if start_ts is not None:
                try:
                    dt = datetime.fromtimestamp(int(start_ts), tz=timezone.utc).strftime("%Y-%m-%d")
                    if dt == data_key:
                        score_data = 10
                    elif dt[:7] == data_key[:7]:
                        score_data = 4
                except Exception:
                    pass

            candidatos.append((score_nomes + score_data, int(event_id)))
        except Exception:
            continue

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x[0], reverse=True)

    for _, event_id in candidatos[:5]:
        detalhe = _safe_request_json(f"https://api.sofascore.com/api/v1/event/{event_id}")
        if not isinstance(detalhe, dict):
            continue
        try:
            event = detalhe.get("event", {}) or {}
            status_desc = str(event.get("status", {}).get("type", "")).lower()
            if "finished" not in status_desc:
                continue

            home_score = event.get("homeScore", {}) or {}
            away_score = event.get("awayScore", {}) or {}
            g_home = home_score.get("current")
            g_away = away_score.get("current")
            if g_home is None or g_away is None:
                continue
            return ResultadoBusca(int(g_home), int(g_away), "sofascore")
        except Exception:
            continue

    return None


def _buscar_resultado_flashscore(time_casa: str, time_fora: str, data_ref: str) -> Optional[ResultadoBusca]:
    # Fallback simples: tenta encontrar placar em script JSON-LD da pagina de busca.
    # Quando o site bloquear ou nao houver correspondencia confiavel, retorna None.
    query = quote_plus(f"{time_casa} {time_fora} {data_ref}")
    url = f"https://www.flashscore.com/search/?q={query}"
    html = _safe_request_text(url)
    if not html:
        return None

    try:
        # Busca padrao "digit-digit" no contexto da pagina.
        # E uma heuristica conservadora, por isso exige nomes dos times no html.
        home_ok = _normalizar_nome_time(time_casa) in _normalizar_nome_time(html)
        away_ok = _normalizar_nome_time(time_fora) in _normalizar_nome_time(html)
        if not (home_ok and away_ok):
            return None

        m = re.search(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b", html)
        if not m:
            return None

        g_home = int(m.group(1))
        g_away = int(m.group(2))
        return ResultadoBusca(g_home, g_away, "flashscore")
    except Exception:
        return None


def _buscar_resultado_com_fallback(sinal: SinalPendente, api_client: Optional[ApiFootball] = None) -> Optional[ResultadoBusca]:
    pares = _split_jogo(sinal.jogo)
    if not pares:
        return None

    time_casa, time_fora = pares

    # Camada 1: cliente ApiFootball com controle de cota diario.
    if api_client is not None:
        try:
            r = api_client.buscar_resultado(time_casa, time_fora, sinal.data)
            if r:
                return ResultadoBusca(
                    gols_casa=int(r.get("placar_casa", 0)),
                    gols_fora=int(r.get("placar_fora", 0)),
                    fonte="api-football-client",
                )
        except Exception:
            pass

    # Camada 2: API-Football direta legado.
    try:
        resultado = _buscar_resultado_api_football(time_casa, time_fora, sinal.data, sinal.fixture_id_api)
        if resultado:
            return resultado
    except Exception:
        pass

    # Camada 3: Sofascore
    try:
        resultado = _buscar_resultado_sofascore(time_casa, time_fora, sinal.data)
        if resultado:
            return resultado
    except Exception:
        pass

    # Camada 4: Flashscore
    try:
        resultado = _buscar_resultado_flashscore(time_casa, time_fora, sinal.data)
        if resultado:
            return resultado
    except Exception:
        pass

    return None


def _avaliar_mercado(mercado: str, gols_casa: int, gols_fora: int) -> Optional[str]:
    total = gols_casa + gols_fora

    if mercado == "over_2.5":
        return "verde" if total > 2.5 else "vermelho"
    if mercado == "1x2_casa":
        return "verde" if gols_casa > gols_fora else "vermelho"
    if mercado == "1x2_empate":
        return "verde" if gols_casa == gols_fora else "vermelho"
    if mercado == "1x2_fora":
        return "verde" if gols_fora > gols_casa else "vermelho"

    return None


def _calcular_lucro(resultado: str, odd: float, stake: float) -> float:
    if resultado == "verde":
        return round((float(odd) - 1.0) * float(stake), 4)
    return round(-float(stake), 4)


def _detectar_sinais_presos(conn: sqlite3.Connection, stale_days: int) -> List[SinalPendente]:
    c = conn.cursor()

    limite = (datetime.now() - timedelta(days=int(stale_days))).strftime("%Y-%m-%d")

    c.execute(
        """
        SELECT
            s.id,
            s.data,
            s.jogo,
            s.mercado,
            COALESCE(s.odd, 0),
            COALESCE(s.stake_unidades, 0),
            s.fixture_id_api,
            s.fixture_data_api
        FROM sinais s
        WHERE s.status = 'pendente'
          AND date(s.data) < date(?)
        ORDER BY date(s.data), s.id
        """,
        (limite,),
    )

    rows = c.fetchall()
    sinais: List[SinalPendente] = []
    for row in rows:
        sinais.append(
            SinalPendente(
                sinal_id=int(row[0]),
                data=str(row[1] or ""),
                jogo=str(row[2] or ""),
                mercado=str(row[3] or ""),
                odd=float(row[4] or 0.0),
                stake_unidades=float(row[5] or 0.0),
                fixture_id_api=str(row[6]) if row[6] is not None else None,
                fixture_data_api=str(row[7]) if row[7] is not None else None,
            )
        )
    return sinais


def _atualizar_liquidacao(conn: sqlite3.Connection, sinal: SinalPendente, resultado: str, lucro: float) -> None:
    c = conn.cursor()

    c.execute(
        """
        UPDATE sinais
        SET status = 'finalizado', resultado = ?, lucro_unidades = ?
        WHERE id = ?
        """,
        (resultado, float(lucro), int(sinal.sinal_id)),
    )

    c.execute(
        """
        UPDATE clv_tracking
        SET status = 'liquidado_manual'
        WHERE sinal_id = ? AND status = 'aguardando'
        """,
        (int(sinal.sinal_id),),
    )

    conn.commit()


def processar_fallback(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Processa fallback de settlement para sinais presos.

    Compatibilidade:
    - standalone (sem context)
    - scheduler style (context opcional)
    """
    ctx = context or {}
    db_path = str(ctx.get("DB_PATH") or DEFAULT_DB_PATH)
    stale_days = int(ctx.get("SETTLEMENT_FALLBACK_DAYS") or STALE_DAYS_DEFAULT)

    resumo = {
        "processados": 0,
        "verdes": 0,
        "vermelhos": 0,
        "lucro_liquido": 0.0,
        "manual": [],
        "erros": [],
    }

    try:
        conn = sqlite3.connect(db_path)
    except Exception as exc:
        msg = f"Falha ao abrir banco {db_path}: {exc}"
        print(msg)
        resumo["erros"].append(msg)
        return resumo

    try:
        sinais = _detectar_sinais_presos(conn, stale_days=stale_days)
    except Exception as exc:
        msg = f"Falha ao detectar sinais presos: {exc}"
        print(msg)
        resumo["erros"].append(msg)
        conn.close()
        return resumo

    if not sinais:
        print("Nenhum sinal preso encontrado para fallback.")
        conn.close()
        return resumo

    api_client = ApiFootball(db_path=db_path)

    print(f"Fallback settlement: {len(sinais)} sinais presos detectados (stale_days={stale_days}).")

    liquidacoes: List[Liquidacao] = []

    for sinal in sinais:
        try:
            resultado_busca = _buscar_resultado_com_fallback(sinal, api_client=api_client)
            if not resultado_busca:
                resumo["manual"].append(
                    {
                        "id": sinal.sinal_id,
                        "jogo": sinal.jogo,
                        "mercado": sinal.mercado,
                        "data": sinal.data,
                        "motivo": "resultado_nao_encontrado",
                    }
                )
                continue

            resultado = _avaliar_mercado(sinal.mercado, resultado_busca.gols_casa, resultado_busca.gols_fora)
            if resultado is None:
                resumo["manual"].append(
                    {
                        "id": sinal.sinal_id,
                        "jogo": sinal.jogo,
                        "mercado": sinal.mercado,
                        "data": sinal.data,
                        "motivo": "mercado_nao_suportado",
                    }
                )
                continue

            lucro = _calcular_lucro(resultado, sinal.odd, sinal.stake_unidades)
            _atualizar_liquidacao(conn, sinal, resultado, lucro)

            placar = f"{resultado_busca.gols_casa}x{resultado_busca.gols_fora}"
            liquidacoes.append(
                Liquidacao(
                    sinal_id=sinal.sinal_id,
                    jogo=sinal.jogo,
                    placar=placar,
                    mercado=sinal.mercado,
                    resultado=resultado,
                    lucro=lucro,
                )
            )

            resumo["processados"] += 1
            if resultado == "verde":
                resumo["verdes"] += 1
            else:
                resumo["vermelhos"] += 1
            resumo["lucro_liquido"] = round(float(resumo["lucro_liquido"]) + float(lucro), 4)

            print(
                f"{sinal.sinal_id} | {sinal.jogo} | {placar} | {sinal.mercado} | "
                f"{resultado} | {lucro:+.4f}"
            )
        except Exception as exc:
            erro = f"Erro no sinal {sinal.sinal_id}: {exc}"
            print(erro)
            resumo["erros"].append(erro)
            continue

    conn.close()

    print("\nResumo fallback settlement")
    print(f"- total processados: {resumo['processados']}")
    print(f"- verdes: {resumo['verdes']}")
    print(f"- vermelhos: {resumo['vermelhos']}")
    print(f"- lucro liquido: {resumo['lucro_liquido']:+.4f}")

    if resumo["manual"]:
        print("- requer intervencao manual:")
        for item in resumo["manual"]:
            print(
                "  "
                f"{item['id']} | {item['jogo']} | {item['mercado']} | {item['data']} | {item['motivo']}"
            )

    return resumo


if __name__ == "__main__":
    processar_fallback(context=None)
