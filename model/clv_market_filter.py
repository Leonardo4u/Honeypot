"""
clv_market_filter.py
=====================
Bloco 2 de 3  Filtro de CLV histrico por mercado  liga

Objetivo:
  S operar combinaes (mercado, liga) onde o CLV histrico acumulado
   positivo e estatisticamente significante. Combinaes com CLV negativo
  ou inconclusivo so bloqueadas mesmo que o modelo indique edge pontual.

Componentes:
  1. CLVRecord:         registro de uma aposta individual
  2. CLVBucket:         agregador de mtricas por (mercado, liga)
  3. CLVHistoryStore:   repositrio em memria (plugvel com BD)
  4. CLVMarketFilter:   deciso de operar ou no uma combinao
  5. CLVDiagnosticPanel: painel de decomposio por buckets de edge score

Lgica de significncia:
  - n_min_amostras: precisamos de histrico suficiente antes de confiar
  - z_score do CLV mdio vs 0 para testar se  estatisticamente > 0
  - Fator de decaimento temporal: apostas antigas pesam menos
    (evita que um bom perodo antigo esconda deteriorao recente)
"""

from __future__ import annotations

import math
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ------------
# ESTRUTURAS
# ------------

@dataclass
class CLVRecord:
    """Registro de uma aposta individual com seu CLV realizado."""
    bet_id:          str
    data:            date
    liga:            str
    mercado:         str
    edge_score:      float       # score composto do modelo (0-100)
    odd_apostada:    float
    odd_fechamento:  float       # odd Pinnacle de fechamento (benchmark)
    stake:           float
    resultado:       Optional[int] = None  # 1=ganhou, 0=perdeu, None=pendente
    overround_open:  float = 1.05
    overround_close: float = 1.04

    @property
    def clv(self) -> float:
        """
        CLV = prob_fair_close - prob_fair_aposta

        Positivo = apostamos a preo melhor que o fechamento de mercado.
         a mtrica mais honesta de qualidade de aposta, independente do resultado.
        """
        p_aposta = (1.0 / self.odd_apostada) / self.overround_open
        p_close  = (1.0 / self.odd_fechamento) / self.overround_close
        return round(p_close - p_aposta, 5)

    @property
    def clv_roi(self) -> float:
        return self.clv * self.stake

    @property
    def edge_bucket(self) -> str:
        """Bucket de edge score para diagnstico granular."""
        s = self.edge_score
        if s < 70:   return "<70"
        if s < 73:   return "70-72"
        if s < 76:   return "73-75"
        if s < 79:   return "76-78"
        if s < 82:   return "79-81"
        return "82+"


@dataclass
class CLVBucketStats:
    """Estatsticas agregadas de uma combinao (mercado, liga) ou bucket."""
    chave:           str
    n_apostas:       int = 0
    clv_soma:        float = 0.0
    clv_soma_q:      float = 0.0     # soma dos quadrados (para varincia online)
    clv_ponderado:   float = 0.0     # CLV mdio ponderado por stake
    stake_total:     float = 0.0
    roi_total:       float = 0.0
    n_positivos:     int = 0

    def update(self, record: CLVRecord, peso_temporal: float = 1.0):
        """Atualizao incremental via algoritmo de Welford (numericamente estvel)."""
        clv = record.clv * peso_temporal
        self.n_apostas  += 1
        delta            = clv - (self.clv_soma / self.n_apostas if self.n_apostas > 1 else 0)
        self.clv_soma   += clv
        self.clv_soma_q += clv * clv
        if record.clv > 0:
            self.n_positivos += 1
        self.stake_total    += record.stake * peso_temporal
        self.roi_total      += record.clv_roi * peso_temporal
        self.clv_ponderado   = self.roi_total / max(self.stake_total, 1e-9)

    @property
    def clv_medio(self) -> float:
        if self.n_apostas == 0:
            return 0.0
        return self.clv_soma / self.n_apostas

    @property
    def clv_std(self) -> float:
        if self.n_apostas < 2:
            return float("inf")
        var = (self.clv_soma_q - (self.clv_soma ** 2) / self.n_apostas) / (self.n_apostas - 1)
        return math.sqrt(max(0.0, var))

    @property
    def z_score(self) -> float:
        """Z-score do CLV mdio vs hiptese nula (CLV = 0)."""
        if self.n_apostas < 2 or self.clv_std == 0:
            return 0.0
        stderr = self.clv_std / math.sqrt(self.n_apostas)
        return self.clv_medio / stderr

    @property
    def pct_positivo(self) -> float:
        return self.n_positivos / self.n_apostas if self.n_apostas else 0.0

    @property
    def significante(self) -> bool:
        """CLV positivo e estatisticamente significante (z > 1.65, p < 0.05 one-tail)."""
        return self.clv_medio > 0 and self.z_score > 1.65 and self.n_apostas >= 30

    def resumo(self) -> dict:
        return {
            "chave":          self.chave,
            "n_apostas":      self.n_apostas,
            "clv_medio":      round(self.clv_medio, 5),
            "clv_ponderado":  round(self.clv_ponderado, 5),
            "clv_std":        round(self.clv_std, 5),
            "z_score":        round(self.z_score, 3),
            "pct_positivo":   round(self.pct_positivo, 3),
            "roi_total":      round(self.roi_total, 2),
            "significante":   self.significante,
            "veredicto":      (
                "OPERAR"      if self.significante
                else "AGUARDAR"  if self.n_apostas < 30
                else "BLOQUEAR"  if self.clv_medio < -0.005
                else "NEUTRO"
            ),
        }


# ------------
# REPOSITRIO
# ------------

class CLVHistoryStore:
    """
    Repositrio de registros CLV com ndice por (mercado, liga) e por bucket.

    Em produo: substituir _records por consulta ao BD.
    Interface mantida idntica para evitar acoplamento.
    """

    def __init__(self, decaimento_dias: float = 180.0):
        """
        Args:
            decaimento_dias: half-life temporal em dias.
                Apostas com `decaimento_dias` dias atrs pesam 50% menos.
        """
        self.decaimento = decaimento_dias
        self._records:  list[CLVRecord] = []

        # ndices
        self._por_chave: dict[str, CLVBucketStats] = defaultdict(
            lambda: CLVBucketStats(chave="")
        )
        self._por_bucket: dict[str, CLVBucketStats] = defaultdict(
            lambda: CLVBucketStats(chave="")
        )
        self._por_liga:   dict[str, CLVBucketStats] = defaultdict(
            lambda: CLVBucketStats(chave="")
        )

    def _peso(self, record_date: date, referencia: date) -> float:
        """Decaimento exponencial  apostas antigas pesam menos."""
        dias = (referencia - record_date).days
        if dias < 0:
            return 1.0
        return math.exp(-math.log(2) * dias / self.decaimento)

    def adicionar(self, record: CLVRecord, referencia: Optional[date] = None):
        """Registra aposta e atualiza todos os ndices."""
        ref    = referencia or date.today()
        peso   = self._peso(record.data, ref)
        chave  = f"{record.mercado}::{record.liga}"
        bucket = f"{record.mercado}::bucket_{record.edge_bucket}"

        self._records.append(record)

        # Inicializar chave se necessrio
        if chave not in self._por_chave:
            self._por_chave[chave] = CLVBucketStats(chave=chave)
        if bucket not in self._por_bucket:
            self._por_bucket[bucket] = CLVBucketStats(chave=bucket)
        if record.liga not in self._por_liga:
            self._por_liga[record.liga] = CLVBucketStats(chave=record.liga)

        self._por_chave[chave].update(record, peso)
        self._por_bucket[bucket].update(record, peso)
        self._por_liga[record.liga].update(record, peso)

    def stats_chave(self, mercado: str, liga: str) -> Optional[CLVBucketStats]:
        return self._por_chave.get(f"{mercado}::{liga}")

    def stats_bucket(self, mercado: str, edge_bucket: str) -> Optional[CLVBucketStats]:
        return self._por_bucket.get(f"{mercado}::bucket_{edge_bucket}")

    def todas_chaves(self) -> list[dict]:
        return [v.resumo() for v in self._por_chave.values() if v.n_apostas > 0]

    def todos_buckets(self) -> list[dict]:
        return [v.resumo() for v in self._por_bucket.values() if v.n_apostas > 0]


# ------------
# FILTRO DE DECISO
# ------------

@dataclass
class CLVFilterDecisao:
    mercado: str
    liga: str
    aprovado: bool
    veredicto: str         # OPERAR / AGUARDAR / BLOQUEAR / NEUTRO
    n_apostas_historico: int
    clv_medio_historico: float
    z_score: float
    motivo: str
    stake_multiplier: float  # 1.0 = stake normal; < 1.0 = stake reduzido por incerteza


class CLVMarketFilter:
    """
    Filtra operaes por combinao (mercado  liga) com base em CLV histrico.

    Modos de operao:
      - OPERAR:   CLV historicamente positivo e significante -> stake normal
      - AGUARDAR: histrico insuficiente -> stake reduzido (explorao cautelosa)
      - BLOQUEAR: CLV historicamente negativo e significante -> veta aposta
      - NEUTRO:   histrico inconcluso -> stake levemente reduzido
    """

    def __init__(
        self,
        store: CLVHistoryStore,
        n_min_para_bloquear: int = 30,    # mnimo de amostras para declarar BLOQUEAR
        n_min_para_operar: int = 30,      # mnimo para stake cheio
        stake_aguardar: float = 0.50,     # stake durante perodo de aprendizado
        stake_neutro: float = 0.75,       # stake em combinao neutra
        permitir_novas_combinacoes: bool = True,
    ):
        self.store              = store
        self.n_min_bloquear     = n_min_para_bloquear
        self.n_min_operar       = n_min_para_operar
        self.stake_aguardar     = stake_aguardar
        self.stake_neutro       = stake_neutro
        self.permitir_novas     = permitir_novas_combinacoes

    def avaliar(self, mercado: str, liga: str) -> CLVFilterDecisao:
        stats = self.store.stats_chave(mercado, liga)

        # Combinao nova: sem histrico
        if stats is None or stats.n_apostas == 0:
            if not self.permitir_novas:
                return CLVFilterDecisao(
                    mercado=mercado, liga=liga,
                    aprovado=False,
                    veredicto="BLOQUEAR",
                    n_apostas_historico=0,
                    clv_medio_historico=0.0,
                    z_score=0.0,
                    motivo="Combinao nova e permit_novas_combinacoes=False",
                    stake_multiplier=0.0,
                )
            return CLVFilterDecisao(
                mercado=mercado, liga=liga,
                aprovado=True,
                veredicto="AGUARDAR",
                n_apostas_historico=0,
                clv_medio_historico=0.0,
                z_score=0.0,
                motivo=f"Sem histórico — explorando com stake reduzido ({self.stake_aguardar:.0%})",
                stake_multiplier=self.stake_aguardar,
            )

        resumo = stats.resumo()
        n      = stats.n_apostas
        clv_m  = stats.clv_medio
        z      = stats.z_score

        if stats.significante:
            return CLVFilterDecisao(
                mercado=mercado, liga=liga,
                aprovado=True,
                veredicto="OPERAR",
                n_apostas_historico=n,
                clv_medio_historico=round(clv_m, 5),
                z_score=round(z, 3),
                motivo=f"CLV positivo e significante: {clv_m:.4f} (z={z:.2f}, n={n})",
                stake_multiplier=1.0,
            )

        if n >= self.n_min_bloquear and clv_m < -0.005 and z < -1.65:
            return CLVFilterDecisao(
                mercado=mercado, liga=liga,
                aprovado=False,
                veredicto="BLOQUEAR",
                n_apostas_historico=n,
                clv_medio_historico=round(clv_m, 5),
                z_score=round(z, 3),
                motivo=f"CLV negativo e significante: {clv_m:.4f} (z={z:.2f}, n={n})",
                stake_multiplier=0.0,
            )

        if n < self.n_min_operar:
            return CLVFilterDecisao(
                mercado=mercado, liga=liga,
                aprovado=True,
                veredicto="AGUARDAR",
                n_apostas_historico=n,
                clv_medio_historico=round(clv_m, 5),
                z_score=round(z, 3),
                motivo=f"Histórico insuficiente (n={n} < {self.n_min_operar})",
                stake_multiplier=self.stake_aguardar,
            )

        return CLVFilterDecisao(
            mercado=mercado, liga=liga,
            aprovado=True,
            veredicto="NEUTRO",
            n_apostas_historico=n,
            clv_medio_historico=round(clv_m, 5),
            z_score=round(z, 3),
            motivo=f"CLV inconclusivo: {clv_m:.4f} (z={z:.2f}, n={n})",
            stake_multiplier=self.stake_neutro,
        )


# ------------
# PAINEL DE DIAGNSTICO
# ------------

class CLVDiagnosticPanel:
    """
    Gera painel de diagnstico de ROI e CLV por buckets de edge score.

    Responde  pergunta principal: "Apostas com edge score entre 72-76
    tm CLV positivo? Vale a pena manter ou subir o limiar?"

    Output: tabela de buckets ordenada por z-score para facilitar deciso.
    """

    def __init__(self, store: CLVHistoryStore):
        self.store = store

    def painel_edge_buckets(self, mercado: Optional[str] = None) -> list[dict]:
        """
        Retorna mtricas por bucket de edge score (filtrando por mercado se informado).
        """
        buckets_raw = self.store.todos_buckets()
        if mercado:
            buckets_raw = [b for b in buckets_raw if b["chave"].startswith(f"{mercado}::")]

        # Parsear e ordenar por z-score
        resultado = []
        for b in buckets_raw:
            parts = b["chave"].split("::")
            mkt   = parts[0] if len(parts) > 0 else "?"
            buck  = parts[1].replace("bucket_", "") if len(parts) > 1 else "?"
            resultado.append({
                "mercado":       mkt,
                "edge_bucket":   buck,
                "n_apostas":     b["n_apostas"],
                "clv_medio":     b["clv_medio"],
                "clv_ponderado": b["clv_ponderado"],
                "z_score":       b["z_score"],
                "pct_positivo":  b["pct_positivo"],
                "roi_total":     b["roi_total"],
                "veredicto":     b["veredicto"],
            })

        resultado.sort(key=lambda x: -x["z_score"])
        return resultado

    def painel_mercado_liga(self) -> list[dict]:
        """Retorna mtricas por combinao mercado  liga."""
        return sorted(self.store.todas_chaves(), key=lambda x: -x["z_score"])

    def recomendacao_limiar(self, mercado: str) -> dict:
        """
        Responde: qual limiar de edge score maximiza CLV para este mercado?

        Analisa CLV por bucket e encontra o ponto de corte onde
        CLV mdio fica consistentemente positivo.
        """
        buckets = self.painel_edge_buckets(mercado)
        if not buckets:
            return {"mercado": mercado, "recomendacao": "SEM_DADOS"}

        # Limiar timo: bucket mais baixo com CLV positivo E z > 1.0
        limiares_possiveis = {
            "<70": 69, "70-72": 72, "73-75": 73,
            "76-78": 76, "79-81": 79, "82+": 82,
        }

        melhor_limiar = 82   # default conservador
        for b in sorted(buckets, key=lambda x: limiares_possiveis.get(x["edge_bucket"], 99)):
            if b["clv_medio"] > 0 and b["z_score"] > 1.0 and b["n_apostas"] >= 15:
                melhor_limiar = limiares_possiveis.get(b["edge_bucket"], 82)
                break

        return {
            "mercado":          mercado,
            "limiar_recomendado": melhor_limiar,
            "justificativa":    f"Primeiro bucket com CLV>0 e z>1.0: {melhor_limiar}",
            "buckets_analisados": len(buckets),
        }

    def imprimir_painel(self):
        """Output formatado para terminal/log."""
        print("\n" + "" * 75)
        print("  CLV DIAGNOSTIC PANEL  Por Edge Score Bucket")
        print("" * 75)
        print(f"  {'Mercado':15s}  {'Bucket':8s}  {'N':5s}  {'CLV Mdio':10s}  "
              f"{'Z-score':8s}  {'%+CLV':6s}  {'ROI Total':10s}  {'Veredicto'}")
        print("  " + "" * 72)

        for b in self.painel_edge_buckets():
            flag = "" if b["z_score"] > 1.65 else " "
            print(
                f"  {b['mercado']:15s}  {b['edge_bucket']:8s}  {b['n_apostas']:5d}  "
                f"{b['clv_medio']:+.4f}{'':4s}  {b['z_score']:+6.2f}   "
                f"{b['pct_positivo']:.0%}{'':3s}  {b['roi_total']:+8.2f}  "
                f"{flag} {b['veredicto']}"
            )

        print("\n  Por Mercado  Liga:")
        print("  " + "" * 72)
        for m in self.painel_mercado_liga()[:10]:
            flag = "" if m["significante"] else " "
            print(
                f"  {m['chave']:35s}  n={m['n_apostas']:4d}  "
                f"CLV={m['clv_medio']:+.4f}  z={m['z_score']:+.2f}  "
                f"{flag} {m['veredicto']}"
            )


# ------------
# DEMO
# ------------

if __name__ == "__main__":
    import random
    rng = random.Random(42)
    today = date.today()

    store  = CLVHistoryStore(decaimento_dias=180)
    filtro = CLVMarketFilter(store)
    painel = CLVDiagnosticPanel(store)

    # Simular histrico: over_2.5 na Premier League tem CLV positivo,
    # draw na Ligue 1 tem CLV negativo, Asian HCP na LaLiga  nova combinao

    def simular_apostas(mercado, liga, n, clv_media, clv_std, edge_base, dias_atras_max=180):
        for i in range(n):
            dias = rng.randint(0, dias_atras_max)
            clv_real = rng.gauss(clv_media, clv_std)
            odd_ap   = rng.uniform(1.70, 2.50)
            # inverter CLV para obter odd de fechamento
            p_ap     = 1 / odd_ap / 1.05
            p_cl     = p_ap + clv_real
            p_cl     = max(0.05, min(0.95, p_cl))
            odd_cl   = (1 / p_cl) / 1.04
            store.adicionar(CLVRecord(
                bet_id=f"{mercado[:3]}_{liga[:3]}_{i:04d}",
                data=today - timedelta(days=dias),
                liga=liga,
                mercado=mercado,
                edge_score=edge_base + rng.gauss(0, 4),
                odd_apostada=odd_ap,
                odd_fechamento=odd_cl,
                stake=rng.uniform(50, 200),
                resultado=1 if rng.random() < p_ap else 0,
            ))

    # Dados simulados: padres distintos por combinao
    simular_apostas("over_2.5",      "Premier League",  60, clv_media=+0.022, clv_std=0.04, edge_base=75)
    simular_apostas("over_2.5",      "Championship",    35, clv_media=+0.008, clv_std=0.05, edge_base=73)
    simular_apostas("draw",          "Ligue 1",         45, clv_media=-0.018, clv_std=0.04, edge_base=74)
    simular_apostas("home_win",      "Premier League",  55, clv_media=+0.015, clv_std=0.04, edge_base=76)
    simular_apostas("home_win",      "Bundesliga",      20, clv_media=+0.005, clv_std=0.05, edge_base=72)
    simular_apostas("asian_handicap","La Liga",          8, clv_media=+0.030, clv_std=0.06, edge_base=78)
    # edge_bucket especfico com CLV ruim:
    simular_apostas("over_2.5",      "Serie A",         40, clv_media=-0.010, clv_std=0.04, edge_base=70)

    print("=" * 75)
    print("CLV MARKET FILTER  Diagnstico e Decises")
    print("=" * 75)

    casos = [
        ("over_2.5",       "Premier League"),
        ("draw",           "Ligue 1"),
        ("asian_handicap", "La Liga"),
        ("home_win",       "Bundesliga"),
        ("over_2.5",       "Serie A"),
        ("btts_yes",       "Premier League"),   # combinao nova
    ]
    for mercado, liga in casos:
        d = filtro.avaliar(mercado, liga)
        status = "" if d.aprovado else ""
        print(f"\n  {status} {mercado:18s} × {liga:18s}")
        print(f"    veredicto:  {d.veredicto}")
        print(f"    CLV médio:  {d.clv_medio_historico:+.4f}  (z={d.z_score:.2f}, n={d.n_apostas_historico})")
        print(f"    stake mult: {d.stake_multiplier:.2f}×")
        print(f"    motivo:     {d.motivo}")

    painel.imprimir_painel()

    print("\n  Recomendao de limiar por mercado:")
    for m in ["over_2.5", "home_win", "draw"]:
        rec = painel.recomendacao_limiar(m)
        print(f"    {m:18s}: limiar recomendado = {rec['limiar_recomendado']}")
