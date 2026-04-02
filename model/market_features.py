import math
from typing import Optional


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def no_vig_probability(odd_principal: Optional[float], odd_oponente: Optional[float]) -> Optional[float]:
    try:
        odd_a = float(odd_principal)
        odd_b = float(odd_oponente)
    except (TypeError, ValueError):
        return None

    if odd_a <= 1.0 or odd_b <= 1.0:
        return None

    inv_a = 1.0 / odd_a
    inv_b = 1.0 / odd_b
    denom = inv_a + inv_b
    if denom <= 0:
        return None
    return _clip01(inv_a / denom)


def _source_quality_score(source_quality: Optional[str]) -> float:
    key = str(source_quality or "fallback").strip().lower()
    if key == "sharp":
        return 1.0
    if key in ("hybrid", "mixed"):
        return 0.75
    if key in ("fallback", "degraded"):
        return 0.5
    return 0.6


def build_market_features(
    odds_novid: Optional[float],
    p_poisson: float,
    odd_abertura: Optional[float] = None,
    odd_atual: Optional[float] = None,
    source_quality: Optional[str] = None,
):
    p_mercado_no_vig = None if odds_novid is None else _clip01(odds_novid)
    p_modelo = _clip01(p_poisson)

    if p_mercado_no_vig is None:
        delta = 0.0
    else:
        delta = p_modelo - p_mercado_no_vig

    volatilidade_curta = 0.0
    try:
        o_open = float(odd_abertura) if odd_abertura is not None else None
        o_now = float(odd_atual) if odd_atual is not None else None
        if o_open and o_now and o_open > 1.0 and o_now > 1.0:
            volatilidade_curta = abs((o_now - o_open) / o_open)
    except (TypeError, ValueError):
        volatilidade_curta = 0.0

    return {
        "p_poisson": p_modelo,
        "p_mercado_no_vig": p_mercado_no_vig,
        "delta_modelo_mercado": round(float(delta), 6),
        "volatilidade_curta_odd": round(float(volatilidade_curta), 6),
        "source_quality_score": _source_quality_score(source_quality),
    }


def carregar_blend_weight(liga: Optional[str], mercado: Optional[str], default_w_poisson: float = 0.65):
    w_poisson = float(default_w_poisson)
    w_mercado = float(1.0 - w_poisson)
    try:
        from data.database import obter_blend_weight

        cfg = obter_blend_weight(liga, mercado)
        if cfg:
            w_poisson = float(cfg.get("w_poisson", w_poisson))
            w_mercado = float(cfg.get("w_mercado", w_mercado))
    except Exception:
        pass

    soma = w_poisson + w_mercado
    if soma <= 0:
        return 0.65, 0.35
    return w_poisson / soma, w_mercado / soma


def blend_probability(
    p_poisson: float,
    p_mercado: Optional[float],
    w: Optional[float] = None,
    liga: Optional[str] = None,
    mercado: Optional[str] = None,
):
    p_p = _clip01(p_poisson)
    if p_mercado is None or not math.isfinite(float(p_mercado)):
        return p_p

    p_m = _clip01(float(p_mercado))

    if w is None:
        w_poisson, w_mercado = carregar_blend_weight(liga, mercado)
    else:
        w_poisson = float(w)
        w_mercado = 1.0 - w_poisson

    soma = w_poisson + w_mercado
    if soma <= 0:
        w_poisson, w_mercado = 0.65, 0.35
    else:
        w_poisson /= soma
        w_mercado /= soma

    p_blend = (w_poisson * p_p) + (w_mercado * p_m)
    return _clip01(p_blend)
