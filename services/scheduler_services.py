import json
import logging
import sqlite3
import traceback


logger = logging.getLogger(__name__)


class DataCollectionService:
    def __init__(self, fetcher, formatter, health_counter):
        self._fetcher = fetcher
        self._formatter = formatter
        self._health_counter = health_counter

    def collect_by_league(self, liga_key, provider_health):
        fetch_result = self._fetcher(liga_key)
        self._health_counter(provider_health, fetch_result.get("status"))
        dados_api = fetch_result.get("data", [])
        jogos = self._formatter(dados_api)
        return fetch_result, jogos


class ObservabilityService:
    def __init__(self, log_event_fn):
        self._log_event = log_event_fn

    def warning_payload(self, job_nome, jogo, mercado, etapa, reason_code, error):
        payload = {
            "job_nome": job_nome,
            "jogo": jogo,
            "mercado": mercado,
            "etapa": etapa,
            "reason_code": reason_code,
            "erro": str(error),
            "traceback": traceback.format_exc(),
        }
        logger.warning("scheduler_warning %s", json.dumps(payload, ensure_ascii=False))
        self._log_event(
            "runtime",
            etapa,
            f"{jogo}|{mercado}",
            "warning",
            reason_code,
            payload,
        )


class FallbackEvaluationService:
    def __init__(self, registrar_fallback_cycle_detail, observability):
        self._registrar = registrar_fallback_cycle_detail
        self._observability = observability

    def persist_fallback_detail(self, job_nome, janela_chave, liga, jogo, mercado, motivo_fallback, detalhes):
        try:
            self._registrar(
                job_nome=job_nome,
                janela_chave=janela_chave,
                liga=liga,
                jogo=jogo,
                mercado=mercado,
                motivo_fallback=motivo_fallback,
                detalhes=detalhes,
            )
        except (sqlite3.DatabaseError, TypeError, ValueError) as exc:
            self._observability.warning_payload(
                job_nome=job_nome or "analise",
                jogo=jogo or "unknown",
                mercado=mercado or "unknown",
                etapa="fallback_detail",
                reason_code="fallback_detail_log_failed",
                error=exc,
            )


class DispatchSettlementService:
    def should_dispatch(self, analise):
        return bool(analise and analise.get("decisao") != "DESCARTAR")
