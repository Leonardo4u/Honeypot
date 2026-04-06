"""
Cliente API-Football para resultado de partidas e estatisticas por fixture.

Requisitos atendidos:
- Chave em API_FOOTBALL_KEY
- Controle diario em api_football_usage.json com reset automatico por data
- Bloqueio preventivo em 90 requests/dia
- Persistencia de estatisticas em fixture_stats
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import requests


class ApiFootball:
    BASE_URL = "https://v3.football.api-sports.io"
    DAILY_SOFT_LIMIT = 90

    def __init__(
        self,
        db_path: Optional[str] = None,
        api_key: Optional[str] = None,
        usage_file: Optional[str] = None,
        timeout: int = 12,
    ) -> None:
        self.db_path = db_path or os.path.join("data", "edge_protocol.db")
        self.api_key = (api_key or os.environ.get("API_FOOTBALL_KEY") or "").strip()
        self.timeout = int(timeout)
        self.usage_file = usage_file or os.path.join(
            os.path.dirname(__file__), "data", "api_football_usage.json"
        )
        os.makedirs(os.path.dirname(self.usage_file), exist_ok=True)
        self._criar_tabela_se_necessario(self.db_path)

    def _usage_template(self) -> Dict[str, Any]:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "count": 0,
            "blocked": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_usage(self) -> Dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        if not os.path.exists(self.usage_file):
            return self._usage_template()

        try:
            with open(self.usage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return self._usage_template()

        if str(data.get("date")) != today:
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
            print(f"[ApiFootball] Aviso: falha ao salvar usage file: {exc}")

    def _checar_limite(self) -> bool:
        usage = self._load_usage()
        count = int(usage.get("count", 0))
        if count >= self.DAILY_SOFT_LIMIT:
            usage["blocked"] = True
            self._save_usage(usage)
            print(
                f"[ApiFootball] Limite preventivo diario atingido: {count}/{self.DAILY_SOFT_LIMIT}. "
                "Chamadas bloqueadas."
            )
            return False
        return True

    def _contar_request(self) -> None:
        usage = self._load_usage()
        usage["count"] = int(usage.get("count", 0)) + 1
        if int(usage["count"]) >= self.DAILY_SOFT_LIMIT:
            usage["blocked"] = True
        self._save_usage(usage)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-apisports-key": self.api_key,
        }

    @staticmethod
    def _similaridade(nome1: str, nome2: str) -> float:
        return round(
            SequenceMatcher(None, (nome1 or "").lower().strip(), (nome2 or "").lower().strip()).ratio() * 100.0,
            2,
        )

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            print("[ApiFootball] Aviso: API_FOOTBALL_KEY nao definido no ambiente.")
            return None
        if not self._checar_limite():
            return None

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            self._contar_request()
            if resp.status_code != 200:
                print(f"[ApiFootball] HTTP {resp.status_code} em {endpoint}.")
                return None
            payload = resp.json()
        except Exception as exc:
            print(f"[ApiFootball] Erro de rede em {endpoint}: {exc}")
            return None

        if not isinstance(payload, dict):
            return None
        return payload

    def buscar_resultado(self, time_casa: str, time_fora: str, data: str) -> Optional[Dict[str, Any]]:
        payload = self._get("fixtures", {"date": str(data)})
        if not payload:
            return None

        melhor = None
        melhor_score = 0.0

        for fixture in payload.get("response", []) or []:
            try:
                home = str(fixture.get("teams", {}).get("home", {}).get("name", ""))
                away = str(fixture.get("teams", {}).get("away", {}).get("name", ""))
                score_home = self._similaridade(time_casa, home)
                score_away = self._similaridade(time_fora, away)
                score = (score_home + score_away) / 2.0
                if score > melhor_score:
                    melhor_score = score
                    melhor = fixture
            except Exception:
                continue

        if not melhor or melhor_score < 80.0:
            return None

        try:
            status = str(melhor.get("fixture", {}).get("status", {}).get("short", ""))
            gols_casa = melhor.get("goals", {}).get("home")
            gols_fora = melhor.get("goals", {}).get("away")
            fixture_id = melhor.get("fixture", {}).get("id")
            if status != "FT":
                return None
            if gols_casa is None or gols_fora is None:
                return None

            return {
                "placar_casa": int(gols_casa),
                "placar_fora": int(gols_fora),
                "fixture_id": int(fixture_id) if fixture_id is not None else None,
                "status": status,
            }
        except Exception:
            return None

    @staticmethod
    def _coletar_stat(item_stats: List[Dict[str, Any]], key_contains: str) -> Optional[Any]:
        key = key_contains.lower()
        for item in item_stats:
            nome = str(item.get("type", "")).lower()
            if key in nome:
                return item.get("value")
        return None

    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        txt = str(val).replace("%", "").strip()
        if txt == "":
            return None
        try:
            return float(txt)
        except Exception:
            return None

    @staticmethod
    def _to_int(val: Any) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(float(str(val).strip()))
        except Exception:
            return None

    def buscar_stats(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        payload = self._get("fixtures/statistics", {"fixture": int(fixture_id)})
        if not payload:
            return None

        response = payload.get("response", []) or []
        if len(response) < 2:
            return None

        try:
            home_stats = response[0].get("statistics", []) or []
            away_stats = response[1].get("statistics", []) or []

            xg_casa = self._to_float(self._coletar_stat(home_stats, "expected goals"))
            xg_fora = self._to_float(self._coletar_stat(away_stats, "expected goals"))
            posse_casa = self._to_float(self._coletar_stat(home_stats, "ball possession"))
            chutes_gol_casa = self._to_int(self._coletar_stat(home_stats, "shots on goal"))
            chutes_gol_fora = self._to_int(self._coletar_stat(away_stats, "shots on goal"))

            return {
                "xg_casa": xg_casa,
                "xg_fora": xg_fora,
                "posse_casa": posse_casa,
                "chutes_gol_casa": chutes_gol_casa,
                "chutes_gol_fora": chutes_gol_fora,
            }
        except Exception:
            return None

    def _criar_tabela_se_necessario(self, db_path: str) -> None:
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS fixture_stats (
                    fixture_id INTEGER PRIMARY KEY,
                    data TEXT,
                    jogo TEXT,
                    xg_casa REAL,
                    xg_fora REAL,
                    posse_casa REAL,
                    chutes_gol_casa INTEGER,
                    chutes_gol_fora INTEGER,
                    criado_em TEXT
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            print(f"[ApiFootball] Falha ao criar fixture_stats: {exc}")

    def salvar_stats(self, fixture_id: int, jogo: str, data: str, stats: Dict[str, Any], db_path: Optional[str] = None) -> bool:
        path = db_path or self.db_path
        try:
            conn = sqlite3.connect(path)
            c = conn.cursor()
            c.execute(
                """
                INSERT OR REPLACE INTO fixture_stats (
                    fixture_id,
                    data,
                    jogo,
                    xg_casa,
                    xg_fora,
                    posse_casa,
                    chutes_gol_casa,
                    chutes_gol_fora,
                    criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(fixture_id),
                    str(data),
                    str(jogo),
                    stats.get("xg_casa"),
                    stats.get("xg_fora"),
                    stats.get("posse_casa"),
                    stats.get("chutes_gol_casa"),
                    stats.get("chutes_gol_fora"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            print(f"[ApiFootball] Falha ao salvar stats fixture_id={fixture_id}: {exc}")
            return False


if __name__ == "__main__":
    api = ApiFootball()
    teste = api.buscar_resultado("Arsenal", "Chelsea", datetime.now().strftime("%Y-%m-%d"))
    print(f"Teste buscar_resultado: {teste}")
    if teste and teste.get("fixture_id"):
        stats = api.buscar_stats(int(teste["fixture_id"]))
        print(f"Teste buscar_stats: {stats}")
