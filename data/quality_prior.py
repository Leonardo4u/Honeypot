try:
    from .database import buscar_metricas_qualidade_liga_mercado
except ImportError:
    from data.database import buscar_metricas_qualidade_liga_mercado


def _clamp(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def calcular_prior_qualidade_mercado_liga(liga, mercado, amostra_minima=30):
    metricas = buscar_metricas_qualidade_liga_mercado(liga, mercado)
    total = int(metricas.get("total", 0))

    if total == 0:
        return {
            "liga": liga,
            "mercado": mercado,
            "amostra": 0,
            "qualidade": "sem_sinal",
            "prior_confianca": -8.0,
            "prior_ranking": -5.0,
            "win_rate": 0.0,
            "roi_pct": 0.0,
            "fonte": metricas.get("fonte", "todas"),
        }

    win_rate = float(metricas.get("win_rate", 0.0))
    roi_pct = float(metricas.get("roi_pct", 0.0))
    peso_amostra = _clamp(total / float(amostra_minima), 0.15, 1.0)

    # Base prior combines hit-rate edge and ROI signal with sample shrinkage.
    sinal_bruto = ((win_rate - 0.5) * 40.0) + (roi_pct * 0.2)
    prior_ranking = _clamp(sinal_bruto * peso_amostra, -8.0, 8.0)
    prior_confianca = _clamp(prior_ranking * 1.25, -10.0, 10.0)

    qualidade = "ok" if total >= amostra_minima else "baixa_amostra"
    if qualidade == "baixa_amostra":
        prior_confianca = _clamp(prior_confianca - 1.5, -10.0, 10.0)

    return {
        "liga": liga,
        "mercado": mercado,
        "amostra": total,
        "qualidade": qualidade,
        "prior_confianca": round(prior_confianca, 4),
        "prior_ranking": round(prior_ranking, 4),
        "win_rate": round(win_rate, 4),
        "roi_pct": round(roi_pct, 4),
        "fonte": metricas.get("fonte", "todas"),
    }
