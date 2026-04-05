import asyncio
import json as _json
from typing import Any, Callable, Dict, Optional, Tuple, Type

from telegram import Bot


def formatar_alerta_operacional(alerta: Dict[str, Any], playbook_link: str) -> Tuple[str, Dict[str, Any]]:
    """Monta mensagem e detalhes normalizados para alerta operacional."""
    detalhes = dict(alerta.get("detalhes") or {})
    detalhes["playbook_link"] = playbook_link
    texto = (
        f"ALERTA OPERACIONAL [{alerta.get('severidade', 'warning').upper()}]\n"
        f"Codigo: {alerta.get('codigo', 'unknown_alert')}\n"
        f"Playbook: {alerta.get('playbook', 'n/a')}\n"
        f"Link: {detalhes.get('playbook_link', playbook_link)}\n"
        f"Detalhes: {_json.dumps(detalhes, ensure_ascii=False)}"
    )
    return texto, detalhes


def formatar_alerta_drift(alerta: Dict[str, Any]) -> str:
    """Monta a mensagem de drift historico para Telegram."""
    return (
        "ALERTA DRIFT (rolling)\n\n"
        f"Metrica: {alerta.get('metrica')}\n"
        f"Segmento: {alerta.get('segmento_tipo')}={alerta.get('segmento_valor')}\n"
        f"Periodo: {alerta.get('periodo_inicio')} ate {alerta.get('periodo_fim')}\n"
        f"Persistencia minima: {alerta.get('min_persistencia')} semanas\n"
        f"Valor atual: {alerta.get('valor_atual')}"
    )


async def emitir(
    tipo: str,
    mensagem: str,
    token: Optional[str],
    chat_id: Optional[str],
    log_event_fn: Optional[Callable[..., Any]] = None,
    bot_cls: Type[Bot] = Bot,
) -> bool:
    """Envia mensagem de alerta com tratamento seguro de CancelledError."""
    if not token or not chat_id:
        return False

    try:
        await bot_cls(token=token).send_message(chat_id=chat_id, text=mensagem)
        return True
    except asyncio.CancelledError:
        return False
    except Exception as exc:
        if callable(log_event_fn):
            reason = "drift_alert_send_failed" if tipo == "drift" else "alert_send_failed"
            etapa = "drift" if tipo == "drift" else "slo"
            log_event_fn("runtime", etapa, "telegram", "warning", reason, {"erro": str(exc)})
        return False


async def emitir_alerta_operacional(
    alerta: Dict[str, Any],
    token: Optional[str],
    chat_id: Optional[str],
    playbook_link: str,
    registrar_alerta_fn: Optional[Callable[..., Any]],
    log_event_fn: Optional[Callable[..., Any]],
    bot_cls: Type[Bot] = Bot,
) -> bool:
    """Registra e envia alerta operacional."""
    texto, detalhes = formatar_alerta_operacional(alerta, playbook_link)

    if callable(registrar_alerta_fn):
        registrar_alerta_fn(
            severidade=alerta.get("severidade", "warning"),
            codigo=alerta.get("codigo", "unknown_alert"),
            playbook_id=alerta.get("playbook"),
            detalhes=detalhes,
        )

    if callable(log_event_fn):
        log_event_fn(
            "runtime",
            "slo",
            alerta.get("codigo", "unknown"),
            alerta.get("severidade", "warning"),
            alerta.get("playbook"),
            detalhes,
        )

    return await emitir(
        "operacional",
        texto,
        token=token,
        chat_id=chat_id,
        log_event_fn=log_event_fn,
        bot_cls=bot_cls,
    )


def emitir_alerta_drift_historico(
    alerta: Optional[Dict[str, Any]],
    token: Optional[str],
    chat_id: Optional[str],
    log_event_fn: Optional[Callable[..., Any]],
    bot_cls: Type[Bot] = Bot,
) -> None:
    """Envia alerta de drift no loop corrente ou via asyncio.run quando necessario."""
    if not alerta:
        return
    if not token or not chat_id:
        return

    msg = formatar_alerta_drift(alerta)

    try:
        bot = bot_cls(token=token)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(bot.send_message(chat_id=chat_id, text=msg))
            return

        coro = bot.send_message(chat_id=chat_id, text=msg)
        task = loop.create_task(coro)
        if not isinstance(task, asyncio.Task) and not asyncio.isfuture(task) and not hasattr(task, "get_coro"):
            coro.close()
            return

        def _log_task_exception(done_task: asyncio.Task[Any]) -> None:
            try:
                exc = done_task.exception()
            except Exception as cb_err:
                if callable(log_event_fn):
                    log_event_fn(
                        "runtime",
                        "drift",
                        "telegram",
                        "warning",
                        "drift_alert_send_failed",
                        {"erro": str(cb_err)},
                    )
                return

            if exc and callable(log_event_fn):
                log_event_fn(
                    "runtime",
                    "drift",
                    "telegram",
                    "warning",
                    "drift_alert_send_failed",
                    {"erro": str(exc)},
                )

        task.add_done_callback(_log_task_exception)
    except Exception as exc:
        if callable(log_event_fn):
            log_event_fn(
                "runtime",
                "drift",
                "telegram",
                "warning",
                "drift_alert_send_failed",
                {"erro": str(exc)},
            )
