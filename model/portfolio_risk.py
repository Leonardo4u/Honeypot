"""
portfolio_risk.py
==================
Bloco 3 de 3 — Veto de correlação com Kelly marginal de portfólio

Problema:
  Kelly individual trata cada aposta como independente.
  Na prática, se você tem Arsenal -1 AH e Arsenal Over 2.5 abertas ao mesmo tempo,
  ambas dependem do mesmo evento raiz (Arsenal marcando muitos gols).
  O risco conjunto é muito maior que a soma dos riscos individuais.

Solução:
  1. Matriz de correlação pré-definida por tipo de aposta × mesmo evento/liga
  2. Kelly marginal: f_marginal = f_kelly × (1 - ρ_portfolio)
  3. Veto explícito quando exposição correlacionada excede limiar de portfólio
  4. Exposição máxima por time/evento como guardrail independente

Referências:
  - Kelly (1956) - A new interpretation of information rate
  - Thorp (2008) - The Kelly Criterion in Blackjack Sports Betting and the Stock Market
  - McLain (2019) - Portfolio Kelly Criterion for Correlated Bets
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# MATRIZ DE CORRELAÇÃO POR TIPO DE APOSTA
# ════════════════════════════════════════════════════════════════════════════

# Correlação entre mercados no MESMO jogo (estimada empiricamente)
# ρ > 0: apostas tendem a ganhar/perder juntas
# ρ < 0: apostas tendem a ser complementares
# Nota: correlações abaixo são entre as apostas na direção que você as faz
#       (ex: over + home win → ρ alto porque ambas melhoram com jogo aberto)

CORRELACAO_MESMO_JOGO: dict[frozenset, float] = {
    # Resultado + Totais (mesma direção)
    frozenset({"home_win", "over_2.5"}):   0.42,
    frozenset({"home_win", "over_1.5"}):   0.38,
    frozenset({"away_win", "over_2.5"}):   0.35,
    frozenset({"home_win", "btts_yes"}):   0.30,
    frozenset({"away_win", "btts_yes"}):   0.28,

    # Resultado + Totais (direção oposta)
    frozenset({"home_win", "under_2.5"}):  -0.20,  # home ganha fechado = possível
    frozenset({"away_win", "under_2.5"}):  -0.18,

    # Dupla exposição ao mesmo resultado
    frozenset({"home_win", "asian_handicap"}): 0.68,   # quase sempre idêntico
    frozenset({"over_2.5", "over_1.5"}):       0.82,   # over_1.5 implica over_2.5 parcialmente
    frozenset({"btts_yes", "over_2.5"}):       0.55,

    # Draw correlacionado negativamente com ambos os lados
    frozenset({"draw", "home_win"}):  -0.75,
    frozenset({"draw", "away_win"}):  -0.60,
    frozenset({"draw", "btts_yes"}):  +0.22,

    # Placar exato correlacionado com resultado
    frozenset({"exact_score", "home_win"}):  0.50,
    frozenset({"exact_score", "over_2.5"}):  0.45,
}

# Correlação padrão para pares não mapeados no MESMO jogo
CORRELACAO_MESMO_JOGO_DEFAULT = 0.15

# Correlação entre jogos diferentes na MESMA liga (mesma rodada)
CORRELACAO_MESMA_LIGA = 0.05

# Correlação entre jogos de ligas diferentes
CORRELACAO_CROSS_LIGA = 0.02


def correlacao_par(
    mercado_a: str,
    mercado_b: str,
    mesmo_jogo: bool,
    mesma_liga: bool = False,
) -> float:
    """Retorna correlação estimada entre dois mercados."""
    if not mesmo_jogo:
        return CORRELACAO_MESMA_LIGA if mesma_liga else CORRELACAO_CROSS_LIGA

    chave = frozenset({mercado_a, mercado_b})
    return CORRELACAO_MESMO_JOGO.get(chave, CORRELACAO_MESMO_JOGO_DEFAULT)


# ════════════════════════════════════════════════════════════════════════════
# POSIÇÕES ABERTAS
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class PosicaoAberta:
    """Uma aposta aberta no portfólio."""
    bet_id:       str
    match_id:     str
    liga:         str
    time_home:    str
    time_away:    str
    mercado:      str
    odd:          float
    stake:        float
    p_modelo:     float
    kelly_individual: float

    @property
    def exposicao(self) -> float:
        """Perda máxima potencial (= stake)."""
        return self.stake

    @property
    def ganho_potencial(self) -> float:
        return self.stake * (self.odd - 1.0)

    @property
    def times_envolvidos(self) -> set[str]:
        return {self.time_home, self.time_away}


# ════════════════════════════════════════════════════════════════════════════
# GESTOR DE PORTFÓLIO
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class KellyMarginalDecisao:
    """Resultado da avaliação Kelly marginal."""
    aprovado:             bool
    kelly_individual:     float     # Kelly sem considerar portfólio
    kelly_marginal:       float     # Kelly ajustado pela correlação
    stake_recomendado:    float     # em unidades monetárias
    rho_portfolio:        float     # correlação ponderada com portfólio atual
    exposicao_evento:     float     # exposição total no mesmo evento
    exposicao_time:       float     # exposição total nos mesmos times
    motivo_veto:          Optional[str]
    componentes:          dict


class PortfolioRiskManager:
    """
    Gerencia risco de portfólio com Kelly marginal e veto de correlação.

    Fluxo para cada nova aposta candidata:
      1. Calcular correlação com cada posição aberta
      2. ρ_portfolio = média ponderada das correlações pelo stake
      3. kelly_marginal = kelly_individual × (1 - ρ_portfolio)
      4. Verificar guardrails: exposição por evento e por time
      5. Aprovar/vetar com stake ajustado
    """

    def __init__(
        self,
        bankroll: float,
        kelly_fracao: float = 0.25,             # Kelly fracionário global
        max_exposicao_evento_pct: float = 0.06, # máx 6% do bankroll num mesmo jogo
        max_exposicao_time_pct: float = 0.08,   # máx 8% em times do mesmo clube
        max_exposicao_liga_pct: float = 0.15,   # máx 15% na mesma liga
        max_correlacao_portfolio: float = 0.55, # veto se ρ_portfolio > 55%
        min_kelly_marginal: float = 0.005,       # veta se kelly_marginal < 0.5%
    ):
        self.bankroll          = bankroll
        self.kelly_fracao      = kelly_fracao
        self.max_exp_evento    = max_exposicao_evento_pct
        self.max_exp_time      = max_exposicao_time_pct
        self.max_exp_liga      = max_exposicao_liga_pct
        self.max_rho           = max_correlacao_portfolio
        self.min_kelly_marg    = min_kelly_marginal
        self.posicoes: list[PosicaoAberta] = []

    # ── Kelly individual ─────────────────────────────────────────────────────

    def kelly_individual(self, p_modelo: float, odd: float) -> float:
        """f* = (b×p - q) / b × fracao"""
        b = odd - 1.0
        q = 1.0 - p_modelo
        f_full = (b * p_modelo - q) / b
        return max(0.0, f_full * self.kelly_fracao)

    # ── Correlação com portfólio ─────────────────────────────────────────────

    def rho_portfolio(
        self,
        candidato: PosicaoAberta,
        posicoes: Optional[list[PosicaoAberta]] = None,
    ) -> tuple[float, list[dict]]:
        """
        Correlação ponderada da candidata com o portfólio atual.

        ρ_portfolio = Σ(stake_i × ρ_i) / Σ(stake_i)

        Retorna (ρ_portfolio, lista de pares com correlação individual).
        """
        abertas = posicoes or self.posicoes
        if not abertas:
            return 0.0, []

        soma_ponderada = 0.0
        soma_stakes    = 0.0
        pares          = []

        for pos in abertas:
            mesmo_jogo  = pos.match_id == candidato.match_id
            mesma_liga  = pos.liga == candidato.liga and not mesmo_jogo
            rho         = correlacao_par(candidato.mercado, pos.mercado, mesmo_jogo, mesma_liga)
            soma_ponderada += rho * pos.stake
            soma_stakes    += pos.stake
            pares.append({
                "bet_id":    pos.bet_id,
                "mercado":   pos.mercado,
                "match_id":  pos.match_id,
                "rho":       round(rho, 3),
                "stake":     pos.stake,
            })

        rho_total = soma_ponderada / soma_stakes if soma_stakes > 0 else 0.0
        return round(rho_total, 4), pares

    # ── Exposições ───────────────────────────────────────────────────────────

    def exposicao_evento(self, match_id: str) -> float:
        return sum(p.stake for p in self.posicoes if p.match_id == match_id)

    def exposicao_times(self, times: set[str]) -> float:
        return sum(p.stake for p in self.posicoes if p.times_envolvidos & times)

    def exposicao_liga(self, liga: str) -> float:
        return sum(p.stake for p in self.posicoes if p.liga == liga)

    # ── Avaliação principal ──────────────────────────────────────────────────

    def avaliar(
        self,
        match_id: str,
        liga: str,
        time_home: str,
        time_away: str,
        mercado: str,
        odd: float,
        p_modelo: float,
        bet_id: str = "candidato",
    ) -> KellyMarginalDecisao:
        """
        Avalia se a aposta candidata deve ser aceita e com qual stake.

        Returns:
            KellyMarginalDecisao com stake recomendado e componentes explicativos.
        """
        # Kelly sem portfólio
        k_ind = self.kelly_individual(p_modelo, odd)

        # Candidato temporário para calcular correlações
        candidato = PosicaoAberta(
            bet_id=bet_id,
            match_id=match_id,
            liga=liga,
            time_home=time_home,
            time_away=time_away,
            mercado=mercado,
            odd=odd,
            stake=k_ind * self.bankroll,  # stake provisório
            p_modelo=p_modelo,
            kelly_individual=k_ind,
        )

        # Correlação com portfólio
        rho, pares = self.rho_portfolio(candidato)

        # Kelly marginal
        k_marginal = k_ind * (1.0 - rho)
        stake_cand = k_marginal * self.bankroll

        # Guardrails de exposição
        exp_evento = self.exposicao_evento(match_id) + stake_cand
        exp_time   = self.exposicao_times({time_home, time_away}) + stake_cand
        exp_liga   = self.exposicao_liga(liga) + stake_cand

        componentes = {
            "kelly_individual":     round(k_ind, 5),
            "rho_portfolio":        round(rho, 4),
            "kelly_marginal":       round(k_marginal, 5),
            "stake_bruto":          round(stake_cand, 2),
            "exp_evento_pos":       round(exp_evento, 2),
            "exp_evento_pct":       round(exp_evento / self.bankroll, 4),
            "exp_time_pos":         round(exp_time, 2),
            "exp_time_pct":         round(exp_time / self.bankroll, 4),
            "exp_liga_pos":         round(exp_liga, 2),
            "exp_liga_pct":         round(exp_liga / self.bankroll, 4),
            "pares_correlacionados": pares[:5],   # top 5 para log
        }

        # Verificar vetos por ordem de prioridade
        motivo_veto = None

        if k_ind <= 0:
            motivo_veto = f"Kelly individual ≤ 0: sem edge (p={p_modelo:.4f}, odd={odd})"

        elif rho > self.max_rho:
            motivo_veto = (
                f"ρ_portfolio={rho:.3f} > limite={self.max_rho:.3f} — "
                f"correlação excessiva com portfólio atual"
            )

        elif k_marginal < self.min_kelly_marg:
            motivo_veto = (
                f"Kelly marginal={k_marginal:.4f} < mínimo={self.min_kelly_marg:.4f} "
                f"após desconto de correlação"
            )

        elif exp_evento / self.bankroll > self.max_exp_evento:
            motivo_veto = (
                f"Exposição no evento={exp_evento/self.bankroll:.2%} > "
                f"limite={self.max_exp_evento:.2%} (bankroll)"
            )

        elif exp_time / self.bankroll > self.max_exp_time:
            motivo_veto = (
                f"Exposição nos times={exp_time/self.bankroll:.2%} > "
                f"limite={self.max_exp_time:.2%}"
            )

        elif exp_liga / self.bankroll > self.max_exp_liga:
            motivo_veto = (
                f"Exposição na liga={exp_liga/self.bankroll:.2%} > "
                f"limite={self.max_exp_liga:.2%}"
            )

        aprovado = motivo_veto is None

        # Stake final: arredondado para evitar frações ridículas
        stake_final = round(stake_cand, 2) if aprovado else 0.0

        if not aprovado:
            logger.warning("portfolio_veto", extra={"motivo": motivo_veto, "mercado": mercado, "match": match_id})
        else:
            logger.info("portfolio_aprovado", extra={"stake": stake_final, "kelly_marg": round(k_marginal, 4), "rho": rho})

        return KellyMarginalDecisao(
            aprovado=aprovado,
            kelly_individual=round(k_ind, 5),
            kelly_marginal=round(k_marginal, 5),
            stake_recomendado=stake_final,
            rho_portfolio=round(rho, 4),
            exposicao_evento=round(exp_evento, 2),
            exposicao_time=round(exp_time, 2),
            motivo_veto=motivo_veto,
            componentes=componentes,
        )

    def registrar(self, decisao: KellyMarginalDecisao, posicao: PosicaoAberta):
        """Registra aposta aprovada no portfólio."""
        if decisao.aprovado:
            posicao.stake = decisao.stake_recomendado
            self.posicoes.append(posicao)

    def fechar(self, bet_id: str):
        """Remove posição do portfólio (settlou ou foi cancelada)."""
        self.posicoes = [p for p in self.posicoes if p.bet_id != bet_id]

    def snapshot(self) -> dict:
        """Estado atual do portfólio."""
        if not self.posicoes:
            return {
                "n_posicoes": 0,
                "exposicao_total": 0.0,
                "exposicao_pct": 0.0,
            }

        exp_total   = sum(p.stake for p in self.posicoes)
        ganho_max   = sum(p.ganho_potencial for p in self.posicoes)
        ligas       = {}
        eventos     = {}

        for p in self.posicoes:
            ligas[p.liga]        = ligas.get(p.liga, 0) + p.stake
            eventos[p.match_id]  = eventos.get(p.match_id, 0) + p.stake

        return {
            "n_posicoes":        len(self.posicoes),
            "exposicao_total":   round(exp_total, 2),
            "exposicao_pct":     round(exp_total / self.bankroll, 4),
            "ganho_potencial":   round(ganho_max, 2),
            "exposicao_por_liga":  {k: round(v, 2) for k, v in sorted(ligas.items(), key=lambda x: -x[1])},
            "exposicao_por_evento":{k: round(v, 2) for k, v in sorted(eventos.items(), key=lambda x: -x[1])},
        }


# ════════════════════════════════════════════════════════════════════════════
# DEMO
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    BANKROLL = 10_000.0
    mgr = PortfolioRiskManager(
        bankroll=BANKROLL,
        kelly_fracao=0.25,
        max_exposicao_evento_pct=0.06,
        max_exposicao_time_pct=0.08,
        max_correlacao_portfolio=0.55,
    )

    print("=" * 65)
    print("PORTFOLIO RISK MANAGER — Kelly Marginal + Correlação")
    print("=" * 65)

    apostas_candidatas = [
        # Primeira aposta: sem portfólio → kelly cheio
        dict(match_id="m001", liga="Premier League", time_home="Arsenal",
             time_away="Chelsea", mercado="home_win", odd=2.10, p_modelo=0.55,
             bet_id="b001"),
        # Segunda aposta: mesmo jogo, mercado correlacionado → kelly reduzido
        dict(match_id="m001", liga="Premier League", time_home="Arsenal",
             time_away="Chelsea", mercado="over_2.5", odd=1.85, p_modelo=0.62,
             bet_id="b002"),
        # Terceira: mesmos times, mercado diferente → alta correlação, possível veto
        dict(match_id="m001", liga="Premier League", time_home="Arsenal",
             time_away="Chelsea", mercado="asian_handicap", odd=1.95, p_modelo=0.57,
             bet_id="b003"),
        # Quarta: jogo diferente, mesma liga → baixa correlação
        dict(match_id="m002", liga="Premier League", time_home="Man City",
             time_away="Liverpool", mercado="home_win", odd=1.75, p_modelo=0.65,
             bet_id="b004"),
        # Quinta: liga diferente → correlação mínima
        dict(match_id="m003", liga="Bundesliga", time_home="Bayern",
             time_away="Dortmund", mercado="over_2.5", odd=1.80, p_modelo=0.63,
             bet_id="b005"),
        # Sexta: sem edge → Kelly = 0
        dict(match_id="m004", liga="Serie A", time_home="Juventus",
             time_away="Milan", mercado="draw", odd=3.20, p_modelo=0.28,
             bet_id="b006"),
    ]

    for ac in apostas_candidatas:
        print(f"\n{'─'*65}")
        print(f"  Candidata: {ac['bet_id']} | {ac['mercado']} | {ac['match_id']} | {ac['liga']}")

        dec = mgr.avaliar(**ac)

        status = "✓ APROVADO" if dec.aprovado else "✗ VETADO"
        print(f"  {status}")
        print(f"  Kelly individual: {dec.kelly_individual:.4f} → stake bruto R$ {dec.kelly_individual*BANKROLL:.2f}")
        print(f"  ρ_portfolio:      {dec.rho_portfolio:.4f}")
        print(f"  Kelly marginal:   {dec.kelly_marginal:.4f} → stake R$ {dec.stake_recomendado:.2f}")
        print(f"  Exp. evento:      R$ {dec.exposicao_evento:.2f} ({dec.exposicao_evento/BANKROLL:.2%} bankroll)")

        if dec.motivo_veto:
            print(f"  Veto: {dec.motivo_veto}")

        if dec.aprovado:
            pos = PosicaoAberta(
                bet_id=ac["bet_id"], match_id=ac["match_id"],
                liga=ac["liga"], time_home=ac["time_home"], time_away=ac["time_away"],
                mercado=ac["mercado"], odd=ac["odd"], stake=dec.stake_recomendado,
                p_modelo=ac["p_modelo"], kelly_individual=dec.kelly_individual,
            )
            mgr.registrar(dec, pos)

    print(f"\n{'═'*65}")
    print("  SNAPSHOT DO PORTFÓLIO FINAL")
    print("═" * 65)
    snap = mgr.snapshot()
    for k, v in snap.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                pct = f"({vv/BANKROLL:.2%})" if isinstance(vv, float) else ""
                print(f"    {kk:30s}: R$ {vv:.2f} {pct}")
        else:
            print(f"  {k:30s}: {v}")
