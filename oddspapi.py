"""
Cliente OddsPapi para leitura de odds Pinnacle e atualizacao de CLV.

Requisitos atendidos:
- Chave em ODDSPAPI_KEY
- Controle de uso mensal em oddspapi_usage.json
- Bloqueio preventivo ao atingir 950 requests/mes
- Metodos para fechamento, pregame, CLV e persistencia no SQLite
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests


class OddsPapi:
    BASE_URL = "https://api.oddspapi.io/v4"
    MONTHLY_SOFT_LIMIT = 950

    def __init__(
        self,
        api_key: Optional[str] = None,
        usage_file: Optional[str] = None,
        timeout: int = 12,
    ) -> None:
        self.api_key = (api_key or os.environ.get("ODDSPAPI_KEY") or "").strip()
        self.timeout = int(timeout)
        self.usage_file = usage_file or os.path.join(
            os.path.dirname(__file__), "data", "oddspapi_usage.json"
        )
        os.makedirs(os.path.dirname(self.usage_file), exist_ok=True)

    def _usage_template(self) -> Dict[str, Any]:
        return {
            "month": datetime.now().strftime("%Y-%m"),
            "count": 0,
            "blocked": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_usage(self) -> Dict[str, Any]:
        current_month = datetime.now().strftime("%Y-%m")
        if not os.path.exists(self.usage_file):
            return self._usage_template()

        try:
            with open(self.usage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return self._usage_template()

        if str(data.get("month")) != current_month:
            return self._usage_template()

        if "count" not in data:
            data["count"] = 0
        if "blocked" not in data:
            data["blocked"] = False
        return data

    def _save_usage(self, data: Dict[str, Any]) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
        except Exception as exc:
            print(f"[OddsPapi] Aviso: falha ao salvar usage file: {exc}")

    def _checar_limite(self) -> bool:
        usage = self._load_usage()
        count = int(usage.get("count", 0))
        if count >= self.MONTHLY_SOFT_LIMIT:
            usage["blocked"] = True
            self._save_usage(usage)
            print(
                f"[OddsPapi] Limite preventivo atingido: {count}/{self.MONTHLY_SOFT_LIMIT}. "
                "Chamadas bloqueadas."
            )
            return False
        return True

    def _contar_request(self) -> None:
        usage = self._load_usage()
        usage["count"] = int(usage.get("count", 0)) + 1
        if int(usage["count"]) >= self.MONTHLY_SOFT_LIMIT:
            usage["blocked"] = True
        self._save_usage(usage)

    @staticmethod
    def _split_jogo(jogo: str) -> Optional[Tuple[str, str]]:
        partes = str(jogo or "").split(" vs ")
        if len(partes) != 2:
            return None
        return partes[0].strip(), partes[1].strip()

    @staticmethod
    def _similaridade(a: str, b: str) -> float:
        return SequenceMatcher(None, (a or "").lower().strip(), (b or "").lower().strip()).ratio()

    def _request_odds(self, data_ref: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        if not self.api_key:
            print("[OddsPapi] Aviso: ODDSPAPI_KEY nao definido no ambiente.")
            return None
        if not self._checar_limite():
            return None

        params: Dict[str, Any] = {
            "apiKey": self.api_key,
            "sport": "soccer",
            "bookmakers": "pinnacle",
            "markets": "h2h,totals",
        }
        if data_ref:
            # Mantido como parametro opcional para suportar provedores que aceitam filtro de data.
            params["date"] = str(data_ref)

        try:
            resp = requests.get(f"{self.BASE_URL}/odds", params=params, timeout=self.timeout)
            self._contar_request()
            if resp.status_code != 200:
                print(f"[OddsPapi] HTTP {resp.status_code} ao buscar odds.")
                return None
            payload = resp.json()
        except Exception as exc:
            print(f"[OddsPapi] Erro de rede ao buscar odds: {exc}")
            return None

        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "events", "odds"):
                if isinstance(payload.get(key), list):
                    return payload.get(key)
        return None

    def _match_evento(self, eventos: List[Dict[str, Any]], jogo: str) -> Optional[Dict[str, Any]]:
        times = self._split_jogo(jogo)
        if not times:
            return None

        home_ref, away_ref = times
        melhor_score = 0.0
        melhor_evento: Optional[Dict[str, Any]] = None

        for ev in eventos:
            home = str(ev.get("home_team") or ev.get("homeTeam") or "")
            away = str(ev.get("away_team") or ev.get("awayTeam") or "")
            s1 = self._similaridade(home_ref, home)
            s2 = self._similaridade(away_ref, away)
            score = (s1 + s2) / 2.0
            if score > melhor_score:
                melhor_score = score
                melhor_evento = ev

        if melhor_score >= 0.80:
            return melhor_evento
        return None

    @staticmethod
    def _extrair_bookmakers(evento: Dict[str, Any]) -> List[Dict[str, Any]]:
        bookmakers = evento.get("bookmakers")
        if isinstance(bookmakers, list):
            return bookmakers

        sites = evento.get("sites")
        if isinstance(sites, list):
            return sites

        return []

    @staticmethod
    def _normalizar_market_key(m: Dict[str, Any]) -> str:
        return str(m.get("key") or m.get("market") or "").lower().strip()

    @staticmethod
    def _normalizar_outcome_name(o: Dict[str, Any]) -> str:
        return str(o.get("name") or o.get("label") or "").lower().strip()

    @staticmethod
    def _price(o: Dict[str, Any]) -> Optional[float]:
        for k in ("price", "odd", "odds", "value"):
            value = o.get(k)
            if value is not None:
                try:
                    return float(value)
                except Exception:
                    return None
        return None

    def _odd_h2h(self, evento: Dict[str, Any], mercado: str) -> Optional[float]:
        times = self._split_jogo(str(evento.get("home_team") or evento.get("homeTeam") or "") + " vs " + str(evento.get("away_team") or evento.get("awayTeam") or ""))
        home_name = times[0].lower() if times else "home"
        away_name = times[1].lower() if times else "away"

        for bm in self._extrair_bookmakers(evento):
            key = str(bm.get("key") or bm.get("site_key") or "").lower()
            if "pinnacle" not in key:
                continue

            for m in bm.get("markets", []) or []:
                if self._normalizar_market_key(m) != "h2h":
                    continue
                for o in m.get("outcomes", []) or []:
                    nome = self._normalizar_outcome_name(o)
                    if mercado == "1x2_casa" and ("home" in nome or nome == home_name):
                        return self._price(o)
                    if mercado == "1x2_fora" and ("away" in nome or nome == away_name):
                        return self._price(o)
                    if mercado == "1x2_empate" and ("draw" in nome or nome == "empate"):
                        return self._price(o)
        return None

    def _odd_totals_over25(self, evento: Dict[str, Any]) -> Optional[float]:
        for bm in self._extrair_bookmakers(evento):
            key = str(bm.get("key") or bm.get("site_key") or "").lower()
            if "pinnacle" not in key:
                continue

            for m in bm.get("markets", []) or []:
                if self._normalizar_market_key(m) != "totals":
                    continue
                for o in m.get("outcomes", []) or []:
                    nome = self._normalizar_outcome_name(o)
                    point = o.get("point") if o.get("point") is not None else o.get("handicap")
                    try:
                        point_val = float(point)
                    except Exception:
                        point_val = None

                    if point_val == 2.5 and ("over" in nome or nome == "mais de"):
                        return self._price(o)
        return None

    def buscar_odd_fechamento(self, jogo: str, mercado: str, data: str) -> Optional[float]:
        eventos = self._request_odds(data_ref=data)
        if not eventos:
            return None

        evento = self._match_evento(eventos, jogo)
        if not evento:
            return None

        if mercado == "over_2.5":
            return self._odd_totals_over25(evento)
        if mercado in {"1x2_casa", "1x2_fora", "1x2_empate"}:
            return self._odd_h2h(evento, mercado)
        return None

    def buscar_odds_pregame(self, jogo: str, mercado: str) -> Optional[float]:
        eventos = self._request_odds(data_ref=None)
        if not eventos:
            return None

        evento = self._match_evento(eventos, jogo)
        if not evento:
            return None

        if mercado == "over_2.5":
            return self._odd_totals_over25(evento)
        if mercado in {"1x2_casa", "1x2_fora", "1x2_empate"}:
            return self._odd_h2h(evento, mercado)
        return None

    @staticmethod
    def calcular_clv(odd_entrada: float, odd_fechamento: float) -> float:
        try:
            oe = float(odd_entrada)
            of = float(odd_fechamento)
            if of <= 0:
                return 0.0
            return round(((oe / of) - 1.0) * 100.0, 3)
        except Exception:
            return 0.0

    @staticmethod
    def oportunidade_valor(odd_atual: float, pinnacle_odd: float, threshold_pct: float = 2.0) -> bool:
        try:
            oa = float(odd_atual)
            op = float(pinnacle_odd)
            if oa <= 0:
                return False
            delta_pct = ((op - oa) / oa) * 100.0
            return delta_pct > float(threshold_pct)
        except Exception:
            return False

    def atualizar_clv_tracking(
        self,
        sinal_id: int,
        odd_fechamento: float,
        clv_percentual: float,
        db_path: str,
    ) -> bool:
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute(
                """
                UPDATE clv_tracking
                SET odd_fechamento = ?,
                    clv_percentual = ?,
                    timestamp_fechamento = ?,
                    status = 'fechado'
                WHERE sinal_id = ?
                """,
                (
                    float(odd_fechamento),
                    float(clv_percentual),
                    datetime.now(timezone.utc).isoformat(),
                    int(sinal_id),
                ),
            )
            conn.commit()
            updated = c.rowcount > 0
            conn.close()
            return updated
        except Exception as exc:
            print(f"[OddsPapi] Falha ao atualizar clv_tracking sinal_id={sinal_id}: {exc}")
            return False


def processar_clv_finalizados(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Atualiza CLV em sinais finalizados recentes com clv_tracking ainda aguardando.

    Filtro:
    - sinais.status = 'finalizado'
    - clv_tracking.status = 'aguardando'
    - janela de dias configuravel (padrao 7)
    """
    ctx = context or {}
    db_path = str(ctx.get("DB_PATH") or os.path.join("data", "edge_protocol.db"))
    dias = int(ctx.get("ODDSPAPI_CLV_DAYS") or 7)

    client = OddsPapi()
    resumo = {"lidos": 0, "atualizados": 0, "falhas": 0}

    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT s.id, s.jogo, s.mercado, s.data, ct.odd_entrada
            FROM sinais s
            JOIN clv_tracking ct ON ct.sinal_id = s.id
            WHERE s.status = 'finalizado'
              AND ct.status = 'aguardando'
              AND date(s.data) >= date('now', ?)
            ORDER BY date(s.data) DESC, s.id DESC
            """,
            (f"-{dias} day",),
        )
        rows = c.fetchall()
        conn.close()
    except Exception as exc:
        print(f"[OddsPapi] Falha ao listar sinais para CLV: {exc}")
        resumo["falhas"] += 1
        return resumo

    for sinal_id, jogo, mercado, data_ref, odd_entrada in rows:
        resumo["lidos"] += 1
        try:
            odd_close = client.buscar_odd_fechamento(str(jogo), str(mercado), str(data_ref))
            if odd_close is None:
                continue
            clv = client.calcular_clv(float(odd_entrada or 0), float(odd_close))
            ok = client.atualizar_clv_tracking(int(sinal_id), float(odd_close), float(clv), db_path)
            if ok:
                resumo["atualizados"] += 1
                print(f"[OddsPapi] CLV atualizado sinal={sinal_id} odd_close={odd_close:.3f} clv={clv:+.3f}%")
        except Exception as exc:
            print(f"[OddsPapi] Falha sinal={sinal_id}: {exc}")
            resumo["falhas"] += 1

    return resumo


if __name__ == "__main__":
    client = OddsPapi()
    teste = client.buscar_odds_pregame("Arsenal vs Chelsea", "1x2_casa")
    print(f"Teste buscar_odds_pregame: {teste}")
