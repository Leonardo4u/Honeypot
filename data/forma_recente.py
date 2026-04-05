import sqlite3
import json
import os
try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:
    def _load_dotenv(*_args, **_kwargs) -> bool:
        return bool(False)

_load_dotenv()

FORMA_PATH = os.path.join(os.path.dirname(__file__), "forma_recente.json")
DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")

def calcular_forma_local(time, ultimos=5):
    """
    Calcula forma recente do time usando o banco de dados local.
    Usa os resultados j registrados no sistema.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT jogo, resultado, lucro_unidades
        FROM sinais
        WHERE (jogo LIKE ? OR jogo LIKE ?)
        AND status = 'finalizado'
        ORDER BY criado_em DESC
        LIMIT ?
    ''', (f'{time} vs %', f'% vs {time}', ultimos))
    jogos = c.fetchall()
    conn.close()

    if not jogos:
        return {
            "pontos": 0,
            "forma_percent": 50.0,
            "sequencia": [],
            "jogos": 0,
            "fonte": "local_fallback",
            "fallback": True,
            "source_marker": "fallback_no_local_history"
        }

    pontos = 0
    sequencia = []

    for jogo, resultado, lucro in jogos:
        times = jogo.split(' vs ')
        eh_casa = times[0].strip() == time

        if resultado == 'verde':
            if eh_casa:
                pontos += 3
                sequencia.append('V')
            else:
                pontos += 3
                sequencia.append('V')
        elif resultado == 'vermelho':
            sequencia.append('D')
        else:
            pontos += 1
            sequencia.append('E')

    n = len(jogos)
    forma_percent = round(pontos / (n * 3) * 100, 1) if n > 0 else 50

    return {
        "pontos": pontos,
        "forma_percent": forma_percent,
        "sequencia": sequencia,
        "jogos": n,
        "fonte": "local",
        "fallback": False,
        "source_marker": "local_history"
    }

def calcular_ajuste_forma(time_casa, time_fora):
    """
    Calcula ajuste contextual baseado na forma recente.
    Retorna fator entre -0.08 e +0.08
    """
    forma_casa_dados = calcular_forma_local(time_casa)
    forma_fora_dados = calcular_forma_local(time_fora)

    forma_casa = forma_casa_dados["forma_percent"] if forma_casa_dados else 50
    forma_fora = forma_fora_dados["forma_percent"] if forma_fora_dados else 50

    ajuste_casa = round((forma_casa - 50) / 50 * 0.08, 3)
    ajuste_fora = round((forma_fora - 50) / 50 * 0.08, 3)

    return ajuste_casa, ajuste_fora

def calcular_confianca_dados(time_casa, time_fora):
    contexto = calcular_confianca_contexto(time_casa, time_fora)
    return contexto["confianca"]


def carregar_medias_safe():
    try:
        try:
            from .atualizar_stats import carregar_medias
        except ImportError:
            from data.atualizar_stats import carregar_medias

        return carregar_medias()
    except Exception:
        return {}


def calcular_confianca_contexto(time_casa, time_fora, liga=None, mercado=None):
    try:
        from .database import buscar_historico_time, calcular_confianca_calibrada
        from .quality_prior import calcular_prior_qualidade_mercado_liga
    except ImportError:
        from data.database import buscar_historico_time, calcular_confianca_calibrada
        from quality_prior import calcular_prior_qualidade_mercado_liga

    medias = carregar_medias_safe()

    hc = buscar_historico_time(time_casa)
    hf = buscar_historico_time(time_fora)
    amostra_time = min(len(hc), len(hf))
    peso_time = min(1.0, amostra_time / 20.0) if amostra_time > 0 else 0.0

    base_calibrada = float(calcular_confianca_calibrada(time_casa, time_fora))
    componente_time = (base_calibrada - 50.0) * peso_time

    bonus_cobertura = 0.0
    if time_casa in medias and time_fora in medias:
        bonus_cobertura = 5.0
    elif time_casa in medias or time_fora in medias:
        bonus_cobertura = 2.0

    prior = {
        "qualidade": "sem_sinal",
        "amostra": 0,
        "prior_confianca": -2.0,
        "prior_ranking": -1.0,
        "win_rate": 0.0,
        "roi_pct": 0.0,
        "fonte": "todas",
    }
    if liga and mercado:
        prior = calcular_prior_qualidade_mercado_liga(liga, mercado)

    fallback_proxy_confianca = 0.0
    fallback_proxy_aplicado = False
    if prior.get("qualidade") == "sem_sinal":
        # Proxy conservador para reduzir cautela excessiva em mercados/ligas novas.
        proxy_amostra = min(2.0, amostra_time / 12.0)
        proxy_cobertura = 1.0 if bonus_cobertura >= 5.0 else (0.5 if bonus_cobertura > 0 else 0.0)
        fallback_proxy_confianca = round(proxy_amostra + proxy_cobertura, 4)
        fallback_proxy_aplicado = fallback_proxy_confianca > 0.0

    confianca = (
        50.0
        + componente_time
        + bonus_cobertura
        + float(prior.get("prior_confianca", 0.0))
        + fallback_proxy_confianca
    )
    confianca = max(50.0, min(100.0, confianca))

    return {
        "confianca": int(round(confianca)),
        "origem": "debiased_prior_v1",
        "base_calibrada": round(base_calibrada, 2),
        "peso_amostra_time": round(peso_time, 4),
        "amostra_time": amostra_time,
        "bonus_cobertura": round(bonus_cobertura, 2),
        "qualidade_prior": prior.get("qualidade", "sem_sinal"),
        "amostra_prior": int(prior.get("amostra", 0)),
        "prior_confianca": round(float(prior.get("prior_confianca", 0.0)), 4),
        "prior_ranking": round(float(prior.get("prior_ranking", 0.0)), 4),
        "prior_win_rate": round(float(prior.get("win_rate", 0.0)), 4),
        "prior_roi_pct": round(float(prior.get("roi_pct", 0.0)), 4),
        "fonte_prior": prior.get("fonte", "todas"),
        "fallback_proxy_aplicado": fallback_proxy_aplicado,
        "fallback_proxy_confianca": round(float(fallback_proxy_confianca), 4),
    }

def carregar_forma():
    if not os.path.exists(FORMA_PATH):
        return {}
    with open(FORMA_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)

if __name__ == "__main__":
    print("=== TESTE DE FORMA LOCAL ===\n")
    print("O sistema calcula forma usando o banco de dados local.")
    print("Quanto mais resultados registrados, mais preciso fica.\n")

    from data.atualizar_stats import carregar_medias
    medias = carregar_medias()

    times_teste = ["Arsenal", "Liverpool", "Palmeiras", "Flamengo"]
    for time in times_teste:
        forma = calcular_forma_local(time)
        confianca = calcular_confianca_dados(time, "Liverpool")
        if forma:
            print(f"{time}: {forma['sequencia']} ({forma['forma_percent']}%)")
        else:
            print(f"{time}: sem histórico local ainda (usando padrão 50%)")
        print(f"  Confiança dos dados: {confianca}/100")
        print()