MIN_EDGE_SCORE = 72
MIN_CONFIANCA = 70

ODD_MIN = 1.55
ODD_MAX = 3.50
EV_MIN_DEFAULT = 0.06

EV_MINIMO_POR_MERCADO = {
    "1x2_casa": 0.06,
    "over_2.5": 0.06,
}

REJECT_CODE_EV_LOW = "ev_low"
REJECT_CODE_ODD_LOW = "odd_low"
REJECT_CODE_ODD_HIGH = "odd_high"
REJECT_CODE_LINEUP_UNCONFIRMED = "lineup_unconfirmed"
REJECT_CODE_STEAM_NEGATIVE = "steam_negative"
REJECT_CODE_DAILY_LIMIT = "daily_limit"
REJECT_CODE_PASSED = "passed"

REJECT_REASON_CODES = {
    "gate1_ev": REJECT_CODE_EV_LOW,
    "gate1_odd_low": REJECT_CODE_ODD_LOW,
    "gate1_odd_high": REJECT_CODE_ODD_HIGH,
    "gate2_lineup": REJECT_CODE_LINEUP_UNCONFIRMED,
    "gate3_steam": REJECT_CODE_STEAM_NEGATIVE,
    "gate4_daily_limit": REJECT_CODE_DAILY_LIMIT,
}


def get_market_ev_min(mercado):
    return EV_MINIMO_POR_MERCADO.get(mercado, EV_MIN_DEFAULT)


def build_reject(reason_code, message, gate_name, detalhes=None):
    return {
        "bloqueado_em": gate_name,
        "motivo": message,
        "reason_code": reason_code,
        "detalhes": detalhes or {},
    }
