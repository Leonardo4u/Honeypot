from datetime import datetime, timezone


def inferir_escalacao_confirmada(jogo, agora_utc=None):
    explicit_keys = ("lineup_confirmed", "lineups_confirmed", "escalacao_confirmada")
    for key in explicit_keys:
        if key in jogo:
            return bool(jogo.get(key)), f"feed:{key}"

    status = str(jogo.get("lineup_status", "")).strip().lower()
    if status in ("confirmed", "confirmada", "ok"):
        return True, "feed:lineup_status"
    if status in ("unconfirmed", "nao_confirmada", "no_confirmada", "pending", "unknown"):
        return False, "feed:lineup_status"

    horario_str = jogo.get("horario") or jogo.get("commence_time")
    if not horario_str:
        return False, "fallback:no_schedule"

    try:
        kickoff_utc = datetime.strptime(horario_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return False, "fallback:invalid_schedule"

    now_utc = agora_utc or datetime.now(timezone.utc)
    minutos_ate_jogo = (kickoff_utc - now_utc).total_seconds() / 60.0

    # Allow pre-lineup window candidates, but require explicit confirmation near kickoff.
    if minutos_ate_jogo <= 75:
        return False, "fallback:kickoff_close"
    return True, "fallback:pre_lineup_window"


def calcular_variacao_odd_gate(steam_data):
    if not steam_data:
        return 0.0
    try:
        return float(steam_data.get("magnitude", 0.0))
    except (TypeError, ValueError, AttributeError):
        return 0.0


def calcular_sinais_hoje_gate(sinais_hoje_base, candidatos_aprovados):
    base = max(0, int(sinais_hoje_base))
    aprovados = max(0, int(candidatos_aprovados))
    return base + aprovados
