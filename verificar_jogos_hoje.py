from datetime import datetime, timezone, timedelta

from data.coletar_odds import buscar_jogos_com_odds, formatar_jogos

agora = datetime.now(timezone.utc)
print(f"Agora (UTC): {agora.strftime('%Y-%m-%d %H:%M')}")
print(f"Janela: até {(agora + timedelta(hours=12)).strftime('%Y-%m-%d %H:%M')} UTC\n")

for liga in ["soccer_epl", "soccer_brazil_campeonato", "soccer_uefa_champs_league",
             "soccer_spain_la_liga", "soccer_italy_serie_a",
             "soccer_germany_bundesliga", "soccer_france_ligue_one"]:
    dados = buscar_jogos_com_odds(liga)
    jogos = formatar_jogos(dados)
    print(f"{liga}: {len(jogos)} jogos nas próximas 12h")
    for j in jogos:
        print(f"  → {j['jogo']} | {j['horario']}")
