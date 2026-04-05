"""Normalizacao de nomes de times com foco em aliases BR."""

from typing import Any


ALIASES = {
    "Vasco DA Gama": "Vasco da Gama",
    "Vasco da Gama": "Vasco da Gama",
    "Atletico-MG": "Atletico Mineiro",
    "Atltico Mineiro": "Atletico Mineiro",
    "Atletico Mineiro": "Atletico Mineiro",
    "Sao Paulo": "So Paulo",
    "So Paulo": "So Paulo",
    "Fluminense FC": "Fluminense",
    "Bragantino-SP": "RB Bragantino",
}


def normalize(name: Any) -> str:
    """Normaliza nome de time para forma canonica sem quebrar em entradas desconhecidas."""
    if name is None:
        return ""
    try:
        raw = str(name).strip()
    except Exception:
        return ""
    if not raw:
        return ""
    return ALIASES.get(raw, raw)


def normalize_df(df, col: str):
    """Aplica normalizacao em uma coluna de DataFrame in-place e retorna o proprio df."""
    if df is None:
        return df
    if not hasattr(df, "columns"):
        return df
    if col not in df.columns:
        return df
    try:
        df[col] = df[col].apply(normalize)
    except Exception:
        # Nunca interrompe pipeline por falha de normalizacao.
        return df
    return df
