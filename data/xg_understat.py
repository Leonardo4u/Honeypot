import json
import os
import time

XG_PATH = os.path.join(os.path.dirname(__file__), "xg_dados.json")

LIGAS_UNDERSTAT = {
    "soccer_epl": "EPL",
    "soccer_spain_la_liga": "La_liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_italy_serie_a": "Serie_A",
    "soccer_france_ligue_one": "Ligue_1",
}


def _media_ponderada_temporal(valores, decay_base=0.9):
    """
    Media ponderada com decaimento exponencial por recencia.
    Espera lista em ordem cronologica (mais antigo -> mais recente).
    """
    if not valores:
        return 1.2

    total_peso = 0.0
    soma = 0.0
    n = len(valores)
    for idx, valor in enumerate(valores):
        expoente = (n - 1) - idx
        peso = decay_base ** expoente
        soma += float(valor) * peso
        total_peso += peso

    if total_peso <= 0:
        return round(sum(valores) / len(valores), 3)

    return round(soma / total_peso, 3)

def buscar_xg_liga(liga_key, temporada=2024):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    liga_nome = LIGAS_UNDERSTAT.get(liga_key)
    if not liga_nome:
        return {}

    url = f"https://understat.com/league/{liga_nome}/{temporada}"

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.get(url)
        time.sleep(3)

        dados = driver.execute_script("""
            try {
                return teamsData;
            } catch(e) {
                return null;
            }
        """)

        driver.quit()

        if not dados:
            print(f"Dados não encontrados para {liga_nome}")
            return {}

        xg_times = {}
        for team_id, team_data in dados.items():
            nome = team_data.get("title", "")
            historico = team_data.get("history", [])

            if not historico or not nome:
                continue

            xg_marcado_casa = []
            xg_marcado_fora = []
            xg_sofrido_casa = []
            xg_sofrido_fora = []

            for jogo in historico:
                eh_casa = jogo.get("h_a") == "h"
                xg = float(jogo.get("xG", 0) or 0)
                xga = float(jogo.get("xGA", 0) or 0)

                if eh_casa:
                    xg_marcado_casa.append(xg)
                    xg_sofrido_casa.append(xga)
                else:
                    xg_marcado_fora.append(xg)
                    xg_sofrido_fora.append(xga)

            xg_times[nome] = {
                "xg_marcado_casa": _media_ponderada_temporal(xg_marcado_casa),
                "xg_marcado_fora": _media_ponderada_temporal(xg_marcado_fora),
                "xg_sofrido_casa": _media_ponderada_temporal(xg_sofrido_casa),
                "xg_sofrido_fora": _media_ponderada_temporal(xg_sofrido_fora),
                "jogos_casa": len(xg_marcado_casa),
                "jogos_fora": len(xg_marcado_fora)
            }

        print(f"{len(xg_times)} times carregados de {liga_nome}")
        return xg_times

    except Exception as e:
        print(f"Erro: {e}")
        try:
            driver.quit()
        except Exception:
            pass
        return {}

def atualizar_xg_todas_ligas():
    print("=== ATUALIZANDO xG (UNDERSTAT) ===\n")
    todos_xg = {}

    for liga_key in LIGAS_UNDERSTAT:
        print(f"Buscando {liga_key}...")
        xg = buscar_xg_liga(liga_key)
        todos_xg.update(xg)
        print()

    if todos_xg:
        with open(XG_PATH, "w", encoding="utf-8") as f:
            json.dump(todos_xg, f, ensure_ascii=False, indent=2)
        print(f"Total: {len(todos_xg)} times salvos em xg_dados.json")
    else:
        print("Nenhum dado encontrado.")

    return todos_xg

def carregar_xg():
    if not os.path.exists(XG_PATH):
        return {}
    with open(XG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def calcular_media_gols_com_xg(time_casa, time_fora):
    from atualizar_stats import carregar_medias
    medias = carregar_medias()
    xg = carregar_xg()

    dados_casa = xg.get(time_casa, {})
    dados_fora = xg.get(time_fora, {})

    if dados_casa and dados_fora:
        xg_ataque_casa = dados_casa.get("xg_marcado_casa", 0)
        xg_defesa_fora = dados_fora.get("xg_sofrido_fora", 0)
        media_gols_casa = round((xg_ataque_casa + xg_defesa_fora) / 2, 2)

        xg_ataque_fora = dados_fora.get("xg_marcado_fora", 0)
        xg_defesa_casa = dados_casa.get("xg_sofrido_casa", 0)
        media_gols_fora = round((xg_ataque_fora + xg_defesa_casa) / 2, 2)

        return media_gols_casa, media_gols_fora, "xG"
    else:
        ataque_casa = medias.get(time_casa, {}).get("casa", 1.5)
        defesa_fora = medias.get(time_fora, {}).get("gols_sofridos_fora", 1.3)
        media_gols_casa = round((ataque_casa + defesa_fora) / 2, 2)

        ataque_fora = medias.get(time_fora, {}).get("fora", 1.1)
        defesa_casa = medias.get(time_casa, {}).get("gols_sofridos_casa", 1.2)
        media_gols_fora = round((ataque_fora + defesa_casa) / 2, 2)

        return media_gols_casa, media_gols_fora, "médias"

if __name__ == "__main__":
    print("Testando EPL primeiro...\n")
    xg = buscar_xg_liga("soccer_epl")

    if xg:
        print("\n--- PRIMEIROS 3 TIMES ---")
        for nome, dados in list(xg.items())[:3]:
            print(f"\n{nome}:")
            print(f"  xG marcado casa: {dados['xg_marcado_casa']}")
            print(f"  xG sofrido fora: {dados['xg_sofrido_fora']}")
    else:
        print("Falhou. Verifique se o Chrome está instalado.")