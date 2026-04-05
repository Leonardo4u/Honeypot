import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from telegram import Bot
from model.picks_log import PickLogger


def _registrar_settlement(context: Dict[str, Any], sinal_id: int, avaliacao: Dict[str, Any]) -> bool:
    try:
        context["atualizar_resultado"](sinal_id, avaliacao["resultado"], avaliacao["lucro"])
        return True
    except Exception as exc:
        context["marcar_ciclo_degradado"](
            "critical_persistence_update_resultado",
            {"sinal_id": sinal_id, "erro": str(exc)},
        )
        return False


def _sync_picks_log_from_db(context: Dict[str, Any]) -> None:
    csv_path = os.path.join(context["BOT_DATA_DIR"], "picks_log.csv")
    db_candidates = [
        os.path.join(context["BOT_DATA_DIR"], "edge_protocol.db"),
        context["DB_PATH"],
    ]
    db_path = next((p for p in db_candidates if p and os.path.exists(p)), context["DB_PATH"])
    try:
        summary = PickLogger(csv_path).sync_from_db(db_path)
        if summary.get("updated", 0) > 0:
            print(
                "picks_log sync: "
                f"{summary['updated']} atualizados "
                f"(matched={summary['matched']}, unmatched={summary['unmatched']})"
            )
    except Exception as exc:
        context["log_event"](
            "runtime",
            "settlement",
            "picks_log_sync",
            "warning",
            "picks_log_sync_failed",
            {"erro": str(exc)},
        )


def _atualizar_clv_settlement(
    context: Dict[str, Any],
    sinal_id: int,
    jogo: str,
    mercado: str,
    liga_nome: Optional[str],
    outcome: int,
) -> None:
    odd_fechamento = None
    try:
        liga_key = context["LIGA_KEY_MAP"].get(liga_nome, "soccer_epl")
        odd_fechamento = context["buscar_odd_fechamento_pinnacle"](jogo, mercado, liga_key)
        if odd_fechamento:
            context["atualizar_clv"](
                sinal_id,
                odd_fechamento,
                outcome=outcome,
                db_path=context["DB_PATH"],
            )
    except Exception as exc:
        context["log_event"](
            "runtime",
            "settlement",
            f"sinal_{sinal_id}",
            "warning",
            "clv_update_failed",
            {"erro": str(exc)},
        )

    if context["MODEL_SHADOW_MODE"]:
        try:
            context["liquidar_shadow_predictions_por_sinal"](
                liga=liga_nome,
                jogo=jogo,
                mercado=mercado,
                outcome=int(outcome),
                closing_odds=odd_fechamento,
            )
        except Exception as exc:
            context["log_event"](
                "runtime",
                "shadow",
                f"sinal_{sinal_id}",
                "warning",
                "shadow_settlement_failed",
                {"erro": str(exc)},
            )


async def _executar_side_effects_pos_settlement(
    context: Dict[str, Any],
    sinal_id: int,
    avaliacao: Dict[str, Any],
    bot: Bot,
    ids_msg: Optional[Sequence[Optional[int]]],
) -> None:
    try:
        estado = context["atualizar_banca"](avaliacao["lucro"])
        print(f"Banca: R${estado['banca_atual']:.2f}")
    except Exception as exc:
        print(f"Erro banca: {exc}")

    try:
        acertou = avaliacao["resultado"] == "verde"
        brier = context["atualizar_brier"](sinal_id, acertou)
        if brier is not None:
            print(f"Brier #{sinal_id}: {brier:.4f} {'[OK]' if brier < 0.25 else ''}")
    except Exception as exc:
        print(f"Erro Brier: {exc}")

    if ids_msg:
        reacao = "[OK]" if avaliacao["resultado"] == "verde" else "[ERRO]"
        if ids_msg[0]:
            try:
                await bot.set_message_reaction(
                    chat_id=context["CANAL_VIP"],
                    message_id=ids_msg[0],
                    reaction=[reacao],
                )
            except Exception as exc:
                context["log_event"](
                    "telegram",
                    "reaction",
                    f"sinal_{sinal_id}",
                    "failed",
                    "telegram_reaction_error",
                    {"erro": str(exc), "canal": "VIP", "sinal_id": sinal_id},
                )
        if ids_msg[1]:
            try:
                await bot.set_message_reaction(
                    chat_id=context["CANAL_FREE"],
                    message_id=ids_msg[1],
                    reaction=[reacao],
                )
            except Exception as exc:
                context["log_event"](
                    "telegram",
                    "reaction",
                    f"sinal_{sinal_id}",
                    "failed",
                    "telegram_reaction_error",
                    {"erro": str(exc), "canal": "FREE", "sinal_id": sinal_id},
                )

    try:
        estado_banca = context["carregar_estado_banca"]()
        context["atualizar_excel"](
            {
                "acao": "resultado",
                "aposta": {
                    "id": str(sinal_id),
                    "odd_fechamento": None,
                    "resultado": avaliacao["resultado"].capitalize(),
                    "retorno": avaliacao["lucro"],
                    "banca_apos": estado_banca["banca_atual"],
                    "data": datetime.now().strftime("%Y-%m-%d"),
                },
            }
        )
    except Exception as exc:
        if not context["MINIMAL_RUNTIME_OUTPUT"]:
            print(f"Erro update Excel (resultado): {exc}")


async def processar_settlement(context: Dict[str, Any]) -> None:
    """Processa liquidacao de sinais pendentes e side effects associados."""
    if "verificar_resultados" in sys.modules:
        _vr = sys.modules["verificar_resultados"]
    else:
        from data import verificar_resultados as _vr

    buscar_resultado_jogo = _vr.buscar_resultado_jogo
    avaliar_mercado = _vr.avaliar_mercado

    bot = Bot(token=context["TOKEN"])
    conn = sqlite3.connect(context["DB_PATH"])
    c = conn.cursor()
    c.execute(
        """
        SELECT id, jogo, mercado, odd, horario, fixture_id_api, fixture_data_api, liga
        FROM sinais
        WHERE status = 'pendente'
        """
    )
    pendentes = c.fetchall()
    conn.close()

    if not pendentes:
        return

    print(f"\nVerificando {len(pendentes)} sinais pendentes...")
    resultado_registrado = False

    for sinal in pendentes:
        if len(sinal) < 7:
            context["log_event"](
                "runtime",
                "settlement",
                "pending_row",
                "warning",
                "pending_row_shape_invalid",
                {"row_len": len(sinal)},
            )
            continue

        sinal_id = sinal[0]
        jogo = sinal[1]
        mercado = sinal[2]
        odd = sinal[3]
        horario = sinal[4]
        fixture_id_api = sinal[5]
        fixture_data_api = sinal[6]
        liga = sinal[7] if len(sinal) >= 8 else None

        try:
            times = jogo.split(" vs ")
            if len(times) != 2:
                continue

            time_casa, time_fora = times
            resultado = buscar_resultado_jogo(
                time_casa.strip(),
                time_fora.strip(),
                data=fixture_data_api,
                horario=horario,
                fixture_id=fixture_id_api,
                liga=liga,
            )

            if resultado and (resultado.get("fixture_id_api") or resultado.get("fixture_data_api")):
                try:
                    context["atualizar_fixture_referencia"](
                        sinal_id,
                        fixture_id_api=resultado.get("fixture_id_api"),
                        fixture_data_api=resultado.get("fixture_data_api"),
                    )
                except Exception as exc:
                    print(f"Erro persistindo fixture #{sinal_id}: {exc}")

            if not resultado or resultado["status"] != "finalizado":
                continue

            avaliacao = avaliar_mercado(resultado, mercado, odd)
            if not avaliacao:
                continue

            if not _registrar_settlement(context, sinal_id, avaliacao):
                continue
            resultado_registrado = True

            outcome = 1 if str(avaliacao.get("resultado", "")).lower() == "verde" else 0
            _atualizar_clv_settlement(context, sinal_id, jogo, mercado, liga, outcome)
            _sync_picks_log_from_db(context)

            conn2 = sqlite3.connect(context["DB_PATH"])
            c2 = conn2.cursor()
            c2.execute("SELECT message_id_vip, message_id_free FROM sinais WHERE id = ?", (sinal_id,))
            ids_msg = c2.fetchone()
            conn2.close()

            await _executar_side_effects_pos_settlement(context, sinal_id, avaliacao, bot, ids_msg)
            print(f"Resultado: #{sinal_id} - {avaliacao['resultado'].upper()}")

        except Exception as exc:
            print(f"Erro #{sinal_id}: {exc}")

    if resultado_registrado:
        try:
            if "exportar_excel" in sys.modules and hasattr(sys.modules["exportar_excel"], "gerar_excel"):
                sys.modules["exportar_excel"].gerar_excel()
            else:
                context["gerar_excel"]()
            print("Excel atualizado.")
        except Exception as exc:
            print(f"Erro Excel: {exc}")

    if context["MODEL_SHADOW_MODE"]:
        try:
            promo = context["evaluate_shadow_promotion"](
                window_days=context["MODEL_SHADOW_PROMOTION_WINDOW_DAYS"],
                bootstrap_iters=context["MODEL_SHADOW_BOOTSTRAP_ITERS"],
            )
            context["log_event"](
                "runtime",
                "shadow",
                "promotion_check",
                "promote" if promo.get("recommend_promote") else "hold",
                "shadow_promotion_evaluated",
                promo,
            )
        except Exception as exc:
            context["log_event"](
                "runtime",
                "shadow",
                "promotion_check",
                "warning",
                "shadow_promotion_eval_failed",
                {"erro": str(exc)},
            )
