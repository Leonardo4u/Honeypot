"""
signal_policy_v2.py
====================
Bloco 1 de 3 — EV mínimo dinâmico por mercado + Steam gate ponderado

Substitui os limiares fixos de signal_policy.py por funções que consideram:
  - EV mínimo: varia por mercado, casa e custo operacional estimado
  - Steam gate: Δodd × w_book × w_tempo (não queda fixa)

Design:
  - Tudo parametrizável via dicionários — sem magic numbers espalhados
  - Cada função retorna um namedtuple com decisão + componentes (auditabilidade)
  - Integra com o logger existente via structured dict (sem acoplamento)
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 1. EV MÍNIMO DINÂMICO POR MERCADO
# ════════════════════════════════════════════════════════════════════════════

class Mercado(str, Enum):
    HOME_WIN    = "home_win"
    DRAW        = "draw"
    AWAY_WIN    = "away_win"
    OVER_25     = "over_2.5"
    UNDER_25    = "under_2.5"
    OVER_15     = "over_1.5"
    UNDER_15    = "under_1.5"
    BTTS_SIM    = "btts_yes"
    BTTS_NAO    = "btts_no"
    ASIAN_HCP   = "asian_handicap"
    PLACAR_EX   = "exact_score"

# Custo operacional estimado por mercado:
# Inclui: risco de limitação de conta, spread bid-ask médio, latência de execução.
# Mercados exóticos têm custo maior pois expõem o modelo mais rapidamente aos books.
_EV_BASE: dict[Mercado, float] = {
    Mercado.HOME_WIN:  0.030,   # mercado mais líquido, menor custo
    Mercado.DRAW:      0.038,   # mais ruidoso, exige mais margem
    Mercado.AWAY_WIN:  0.033,
    Mercado.OVER_25:   0.028,   # totais são eficientes, mas menos exposição
    Mercado.UNDER_25:  0.032,   # under: ZIP corrige bem, mas mercado é cínico
    Mercado.OVER_15:   0.025,
    Mercado.UNDER_15:  0.035,
    Mercado.BTTS_SIM:  0.030,
    Mercado.BTTS_NAO:  0.040,   # BTTS No é raro e arriscado de operar
    Mercado.ASIAN_HCP: 0.025,   # handicap asiático: spread menor nos exchanges
    Mercado.PLACAR_EX: 0.055,   # exótico: alto custo, alta variância
}

# Modificadores aditivos por contexto
_EV_MOD_LIQUIDEZ_BAIXA  = +0.015  # jogos com volume < threshold
_EV_MOD_BOOK_LIMITADOR  = +0.020  # books conhecidos por limitar (bet365, William Hill)
_EV_MOD_JOGO_TARDIO     = +0.008  # < 2h para kickoff: spread aumenta
_EV_MOD_AUTOMATIZADO    = -0.005  # execução 100% automatizada: custo marginal baixo


@dataclass
class EVDecisao:
    mercado: str
    ev_calculado: float
    ev_minimo: float
    aprovado: bool
    componentes: dict
    motivo_rejeicao: Optional[str] = None


class EVMinimoPolicy:
    """
    Calcula EV mínimo exigido por aposta considerando mercado e contexto.

    Uso:
        policy = EVMinimoPolicy(execucao_automatizada=True)
        decisao = policy.avaliar(
            mercado="over_2.5",
            ev_calculado=0.031,
            book="pinnacle",
            minutos_ate_jogo=180,
            volume_estimado=50_000,
        )
        if decisao.aprovado:
            ...
    """

    def __init__(
        self,
        execucao_automatizada: bool = True,
        volume_minimo_liquido: float = 20_000,  # abaixo disso = baixa liquidez
        books_limitadores: Optional[set[str]] = None,
        override_por_mercado: Optional[dict[str, float]] = None,
    ):
        self.automatizado     = execucao_automatizada
        self.vol_min          = volume_minimo_liquido
        self.books_limit      = books_limitadores or {"bet365", "william_hill", "betfair_sportsbook"}
        self.overrides        = override_por_mercado or {}

    def ev_minimo(
        self,
        mercado: str,
        book: str = "",
        minutos_ate_jogo: float = 360,
        volume_estimado: float = 100_000,
    ) -> tuple[float, dict]:
        """
        Retorna EV mínimo exigido e decomposição dos componentes.
        """
        try:
            m = Mercado(mercado)
        except ValueError:
            m = None

        base = self.overrides.get(mercado) or (_EV_BASE.get(m, 0.035) if m else 0.035)

        mods = {"base": base}

        # Modificador: liquidez
        if volume_estimado < self.vol_min:
            mods["baixa_liquidez"] = _EV_MOD_LIQUIDEZ_BAIXA
        else:
            mods["baixa_liquidez"] = 0.0

        # Modificador: book limitador
        if book.lower() in self.books_limit:
            mods["book_limitador"] = _EV_MOD_BOOK_LIMITADOR
        else:
            mods["book_limitador"] = 0.0

        # Modificador: tempo até o jogo
        if minutos_ate_jogo < 120:
            mods["jogo_tardio"] = _EV_MOD_JOGO_TARDIO
        else:
            mods["jogo_tardio"] = 0.0

        # Modificador: automação
        if self.automatizado:
            mods["automatizado"] = _EV_MOD_AUTOMATIZADO
        else:
            mods["automatizado"] = 0.0

        total = sum(mods.values())
        return round(total, 4), mods

    def avaliar(
        self,
        mercado: str,
        ev_calculado: float,
        book: str = "",
        minutos_ate_jogo: float = 360,
        volume_estimado: float = 100_000,
    ) -> EVDecisao:
        ev_min, componentes = self.ev_minimo(mercado, book, minutos_ate_jogo, volume_estimado)
        aprovado = ev_calculado >= ev_min
        motivo   = None if aprovado else (
            f"EV {ev_calculado:.4f} < mínimo {ev_min:.4f} "
            f"(gap: {ev_min - ev_calculado:.4f})"
        )
        decisao = EVDecisao(
            mercado=mercado,
            ev_calculado=round(ev_calculado, 4),
            ev_minimo=ev_min,
            aprovado=aprovado,
            componentes=componentes,
            motivo_rejeicao=motivo,
        )
        logger.debug("ev_minimo_policy", extra={"decisao": vars(decisao)})
        return decisao


# ════════════════════════════════════════════════════════════════════════════
# 2. STEAM GATE PONDERADO
# ════════════════════════════════════════════════════════════════════════════

# Peso por bookmaker — reflete qualidade do sinal (quanto o book é sharp-friendly)
# Pinnacle/Betfair Exchange: sinal de referência
# Books de varejo: podem estar rebalanceando livro, não steam real
_BOOK_WEIGHTS: dict[str, float] = {
    "pinnacle":           1.00,   # referência máxima
    "betfair_exchange":   0.95,   # exchange = ação real
    "sbobet":             0.90,
    "asian_handicap_mkt": 0.88,
    "matchbook":          0.82,
    "marathonbet":        0.78,
    "bet365":             0.45,   # varejo, rebalanceia muito
    "william_hill":       0.42,
    "paddy_power":        0.40,
    "betfair_sportsbook": 0.38,   # não é o exchange
    "bwin":               0.35,
    "unibet":             0.35,
    "default":            0.50,
}

# Peso temporal: quanto mais próximo do kickoff, mais o mercado já foi digerido
# Muito perto (< 30min): pode ser ajuste de balanceamento, não informação nova
# Zona ótima de sinal: 60-240min antes
def _peso_tempo(minutos_ate_jogo: float) -> float:
    """
    Curva de peso temporal para steam.

    Pico em ~120min antes do jogo (informação mais valiosa).
    Decai para ambos os lados:
      - Muito cedo (> 720min): menor convicção dos sharps
      - Muito tarde (< 30min): ruído de balanceamento de livro

    Modelado como gaussiana truncada em log-tempo.
    """
    if minutos_ate_jogo <= 0:
        return 0.0
    if minutos_ate_jogo < 15:
        return 0.10   # muito perto: quase sempre ruído

    # Pico aos 120 minutos
    mu_log  = math.log(120)
    sig_log = 1.2          # largura da curva em log scale
    log_t   = math.log(minutos_ate_jogo)
    peso    = math.exp(-0.5 * ((log_t - mu_log) / sig_log) ** 2)
    return round(min(1.0, peso), 4)


@dataclass
class SteamDecisao:
    delta_odd_pct: float       # variação percentual da odd
    w_book: float              # peso do bookmaker
    w_tempo: float             # peso temporal
    steam_score: float         # Δodd × w_book × w_tempo
    limiar: float              # limiar configurado
    aprovado: bool             # True = steam real detectado (aposta a favor)
    rejeitado_por_steam: bool  # True = sinal contrário, bloquear aposta
    direcao: str               # "FAVOR" | "CONTRA" | "NEUTRO"
    componentes: dict


class SteamGatePolicy:
    """
    Avalia se o movimento de linha representa steam real de apostadores profissionais.

    steam_score = |Δodd_pct| × w_book × w_tempo

    Lógica de decisão:
      - steam_score >= limiar_ativo E direção FAVOR → sinal positivo (confirma aposta)
      - steam_score >= limiar_ativo E direção CONTRA → bloquear (sharps contra nós)
      - steam_score < limiar_ativo → ignorar movimento (ruído)

    Direção:
      - FAVOR: odd do lado que queremos apostar está CAINDO (mercado valoriza igual a nós)
      - CONTRA: odd está SUBINDO (sharps indo contra a nossa posição)
    """

    def __init__(
        self,
        limiar_steam_score: float = 0.025,   # score mínimo para considerar steam real
        limiar_bloqueio:    float = 0.018,   # score para bloquear mesmo sem confirmar
        book_weights: Optional[dict[str, float]] = None,
    ):
        self.limiar_ativo   = limiar_steam_score
        self.limiar_block   = limiar_bloqueio
        self.book_weights   = book_weights or _BOOK_WEIGHTS

    def _w_book(self, book: str) -> float:
        return self.book_weights.get(book.lower(), self.book_weights["default"])

    def avaliar(
        self,
        odd_abertura: float,
        odd_atual: float,
        book: str,
        minutos_ate_jogo: float,
        nossa_direcao: str = "down",   # "down" = queremos odd caindo (apostar em evento)
    ) -> SteamDecisao:
        """
        Avalia movimento de linha.

        Args:
            odd_abertura: odd no momento de abertura do mercado
            odd_atual: odd mais recente
            book: bookmaker fonte
            minutos_ate_jogo: minutos restantes até o kickoff
            nossa_direcao: "down" se apostamos que evento vai acontecer (queremos queda)
                           "up" se apostamos contra (ex: lay, queremos alta)
        """
        if odd_abertura <= 0:
            raise ValueError(f"odd_abertura inválida: {odd_abertura}")

        delta_pct  = (odd_atual - odd_abertura) / odd_abertura
        w_book     = self._w_book(book)
        w_tempo    = _peso_tempo(minutos_ate_jogo)
        steam_sc   = abs(delta_pct) * w_book * w_tempo

        # Direção do steam vs nossa posição
        if abs(delta_pct) < 0.005:
            direcao = "NEUTRO"
        elif delta_pct < 0 and nossa_direcao == "down":
            direcao = "FAVOR"    # odd caiu, mercado indo na nossa direção
        elif delta_pct > 0 and nossa_direcao == "up":
            direcao = "FAVOR"
        else:
            direcao = "CONTRA"   # mercado indo contra nós

        aprovado          = steam_sc >= self.limiar_ativo and direcao == "FAVOR"
        rejeitado_steam   = steam_sc >= self.limiar_block and direcao == "CONTRA"

        componentes = {
            "delta_odd_pct":     round(delta_pct, 4),
            "w_book":            round(w_book, 3),
            "w_tempo":           round(w_tempo, 3),
            "steam_score":       round(steam_sc, 5),
            "limiar_ativo":      self.limiar_ativo,
            "limiar_bloqueio":   self.limiar_block,
        }

        decisao = SteamDecisao(
            delta_odd_pct=round(delta_pct, 4),
            w_book=w_book,
            w_tempo=w_tempo,
            steam_score=round(steam_sc, 5),
            limiar=self.limiar_ativo,
            aprovado=aprovado,
            rejeitado_por_steam=rejeitado_steam,
            direcao=direcao,
            componentes=componentes,
        )

        if rejeitado_steam:
            logger.warning(
                "steam_gate_bloqueio",
                extra={
                    "book": book,
                    "steam_score": decisao.steam_score,
                    "delta_pct": decisao.delta_odd_pct,
                    "minutos": minutos_ate_jogo,
                }
            )
        elif aprovado:
            logger.info(
                "steam_gate_confirmacao",
                extra={"book": book, "steam_score": decisao.steam_score}
            )

        return decisao

    def avaliar_multiplos_books(
        self,
        movimentos: list[dict],   # [{odd_ab, odd_at, book, minutos}, ...]
        nossa_direcao: str = "down",
        quorum_books: int = 2,    # quantos books precisam confirmar steam
    ) -> dict:
        """
        Consenso de steam entre múltiplos books.

        Requer quórum de confirmações para declarar steam real.
        Muito mais robusto que sinal de um único book.
        """
        decisoes = [
            self.avaliar(
                m["odd_abertura"], m["odd_atual"],
                m["book"], m["minutos_ate_jogo"],
                nossa_direcao,
            )
            for m in movimentos
        ]

        n_favor  = sum(1 for d in decisoes if d.aprovado)
        n_contra = sum(1 for d in decisoes if d.rejeitado_por_steam)
        score_medio = sum(d.steam_score for d in decisoes) / len(decisoes)

        # Steam ponderado pelo peso de cada book
        score_ponderado = sum(
            d.steam_score * d.w_book for d in decisoes
        ) / max(sum(d.w_book for d in decisoes), 1e-9)

        return {
            "n_books":              len(decisoes),
            "n_confirmacoes":       n_favor,
            "n_bloqueios":          n_contra,
            "quorum_atingido":      n_favor >= quorum_books,
            "steam_score_medio":    round(score_medio, 5),
            "steam_score_ponderado":round(score_ponderado, 5),
            "consenso":             (
                "FORTE"  if n_favor >= quorum_books and score_ponderado > self.limiar_ativo * 1.5
                else "MODERADO" if n_favor >= quorum_books
                else "BLOQUEADO" if n_contra >= quorum_books
                else "INCONCLUSIVO"
            ),
            "decisoes_por_book": [
                {"book": m["book"], "score": d.steam_score, "direcao": d.direcao}
                for m, d in zip(movimentos, decisoes)
            ],
        }


# ════════════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO — Gate combinado (EV + Steam)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class GateCombinado:
    """Resultado do gate duplo EV + Steam."""
    aprovado: bool
    ev_decisao: EVDecisao
    steam_decisao: Optional[SteamDecisao]
    motivo_final: str
    log_estruturado: dict


def gate_ev_steam(
    mercado: str,
    ev_calculado: float,
    odd_abertura: float,
    odd_atual: float,
    book: str,
    minutos_ate_jogo: float,
    nossa_direcao: str = "down",
    ev_policy: Optional[EVMinimoPolicy] = None,
    steam_policy: Optional[SteamGatePolicy] = None,
    volume_estimado: float = 100_000,
) -> GateCombinado:
    """
    Gate combinado: EV mínimo dinâmico + Steam ponderado.

    Lógica:
      1. EV insuficiente → rejeita (independente do steam)
      2. Steam CONTRA → rejeita mesmo com EV suficiente
      3. EV OK + Steam neutro/favor → aprova

    Isso garante que não entramos em apostas onde o mercado
    está se movendo ativamente contra nossa posição.
    """
    ev_pol    = ev_policy    or EVMinimoPolicy()
    steam_pol = steam_policy or SteamGatePolicy()

    ev_dec    = ev_pol.avaliar(mercado, ev_calculado, book, minutos_ate_jogo, volume_estimado)
    steam_dec = steam_pol.avaliar(odd_abertura, odd_atual, book, minutos_ate_jogo, nossa_direcao)

    if not ev_dec.aprovado:
        aprovado = False
        motivo   = f"EV insuficiente: {ev_dec.motivo_rejeicao}"
    elif steam_dec.rejeitado_por_steam:
        aprovado = False
        motivo   = (
            f"Steam CONTRA detectado: score={steam_dec.steam_score:.4f}, "
            f"book={book}, Δodd={steam_dec.delta_odd_pct:.2%}"
        )
    else:
        aprovado = True
        motivo   = (
            f"Aprovado: EV={ev_calculado:.4f}>={ev_dec.ev_minimo:.4f}, "
            f"steam={steam_dec.direcao} (score={steam_dec.steam_score:.4f})"
        )

    log = {
        "gate": "ev_steam",
        "mercado": mercado,
        "aprovado": aprovado,
        "ev_calculado": ev_calculado,
        "ev_minimo": ev_dec.ev_minimo,
        "steam_score": steam_dec.steam_score,
        "steam_direcao": steam_dec.direcao,
        "book": book,
        "minutos_ate_jogo": minutos_ate_jogo,
        "motivo": motivo,
    }
    logger.info("gate_ev_steam", extra=log)

    return GateCombinado(
        aprovado=aprovado,
        ev_decisao=ev_dec,
        steam_decisao=steam_dec,
        motivo_final=motivo,
        log_estruturado=log,
    )


# ════════════════════════════════════════════════════════════════════════════
# DEMO
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    print("=" * 65)
    print("SIGNAL POLICY V2 — EV Dinâmico + Steam Gate Ponderado")
    print("=" * 65)

    ev_policy    = EVMinimoPolicy(execucao_automatizada=True)
    steam_policy = SteamGatePolicy(limiar_steam_score=0.025, limiar_bloqueio=0.018)

    cenarios = [
        {
            "nome":            "Over 2.5 em Pinnacle, 3h antes, steam a favor",
            "mercado":         "over_2.5",
            "ev_calculado":    0.031,
            "odd_abertura":    1.90,
            "odd_atual":       1.84,   # caiu 3.2% — steam a favor (over está sendo comprado)
            "book":            "pinnacle",
            "minutos":         180,
        },
        {
            "nome":            "Home win em bet365, 45min antes, steam contra",
            "mercado":         "home_win",
            "ev_calculado":    0.038,
            "odd_abertura":    2.10,
            "odd_atual":       2.22,   # subiu — sharps indo contra home
            "book":            "bet365",
            "minutos":         45,
        },
        {
            "nome":            "Draw em Pinnacle, 2h antes, EV insuficiente",
            "mercado":         "draw",
            "ev_calculado":    0.021,   # abaixo do mínimo para draw
            "odd_abertura":    3.40,
            "odd_atual":       3.38,
            "book":            "pinnacle",
            "minutos":         120,
        },
        {
            "nome":            "Asian HCP em SBOBet, 90min, steam forte a favor",
            "mercado":         "asian_handicap",
            "ev_calculado":    0.029,
            "odd_abertura":    1.95,
            "odd_atual":       1.88,   # queda de 3.6%
            "book":            "sbobet",
            "minutos":         90,
        },
    ]

    for c in cenarios:
        print(f"\n{'─'*65}")
        print(f"  {c['nome']}")
        result = gate_ev_steam(
            mercado=c["mercado"],
            ev_calculado=c["ev_calculado"],
            odd_abertura=c["odd_abertura"],
            odd_atual=c["odd_atual"],
            book=c["book"],
            minutos_ate_jogo=c["minutos"],
            ev_policy=ev_policy,
            steam_policy=steam_policy,
        )
        status = "✓ APROVADO" if result.aprovado else "✗ REJEITADO"
        print(f"  {status}")
        print(f"  EV: {result.ev_decisao.ev_calculado:.4f} vs mínimo {result.ev_decisao.ev_minimo:.4f}")
        print(f"  Steam: score={result.steam_decisao.steam_score:.5f}  dir={result.steam_decisao.direcao}")
        print(f"  Motivo: {result.motivo_final}")

    print(f"\n{'─'*65}")
    print("  MULTI-BOOK STEAM CONSENSUS")
    movimentos = [
        {"odd_abertura": 1.90, "odd_atual": 1.84, "book": "pinnacle",       "minutos_ate_jogo": 150},
        {"odd_abertura": 1.91, "odd_atual": 1.85, "book": "sbobet",         "minutos_ate_jogo": 150},
        {"odd_abertura": 1.93, "odd_atual": 1.91, "book": "bet365",         "minutos_ate_jogo": 150},
        {"odd_abertura": 1.90, "odd_atual": 1.88, "book": "betfair_exchange","minutos_ate_jogo": 150},
    ]
    consenso = steam_policy.avaliar_multiplos_books(movimentos, nossa_direcao="down", quorum_books=2)
    print(f"  Consenso: {consenso['consenso']}")
    print(f"  Score ponderado: {consenso['steam_score_ponderado']:.5f}")
    print(f"  Confirmações: {consenso['n_confirmacoes']}/{consenso['n_books']}")
    print("  Por book:")
    for d in consenso["decisoes_por_book"]:
        print(f"    {d['book']:22s}  score={d['score']:.5f}  dir={d['direcao']}")

    # EV mínimo por todos os mercados (tabela de referência)
    print(f"\n{'─'*65}")
    print("  TABELA EV MÍNIMO (Pinnacle, 3h antes, sistema automatizado)")
    for m in Mercado:
        ev_min, mods = ev_policy.ev_minimo(m.value, book="pinnacle", minutos_ate_jogo=180)
        print(f"  {m.value:20s}: {ev_min:.4f}  (base={mods['base']:.3f})")
