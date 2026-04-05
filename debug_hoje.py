from data.coletar_odds import buscar_jogos_com_odds, formatar_jogos
from model.analisar_jogo import analisar_jogo
from data.atualizar_stats import carregar_medias
from data.xg_understat import calcular_media_gols_com_xg
from model.filtros import aplicar_triple_gate

dados = buscar_jogos_com_odds('soccer_brazil_campeonato')
jogos = formatar_jogos(dados)

for jogo in jogos:
    home = jogo['home_team']
    away = jogo['away_team']
    media_casa, media_fora, fonte = calcular_media_gols_com_xg(home, away)

    for mercado, odd_key in [("1x2_casa", "casa"), ("over_2.5", "over_2.5")]:
        odd = jogo['odds'].get(odd_key, 0)
        if odd == 0:
            continue

        analise = analisar_jogo({
            "liga": jogo['liga'],
            "jogo": jogo['jogo'],
            "horario": jogo['horario'],
            "media_gols_casa": media_casa,
            "media_gols_fora": media_fora,
            "mercado": mercado,
            "odd": odd,
            "ajuste_lesoes": 0.0,
            "ajuste_motivacao": 0.0,
            "ajuste_fadiga": 0.0,
            "confianca_dados": 70,
            "estabilidade_odd": 80,
            "contexto_jogo": 70,
            "banca": 1000
        })

        filtro = aplicar_triple_gate({
            "ev": analise.get("ev", 0),
            "odd": odd,
            "escalacao_confirmada": True,
            "variacao_odd": 0.0
        })

        print(f"{jogo['jogo']} | {mercado}")
        print(f"  Odd: {odd} | EV: {analise.get('ev_percentual','N/A')} | Score: {analise.get('edge_score',0)}")
        print(f"  Decisão: {analise['decisao']} | Filtro: {'PASSOU' if filtro['aprovado'] else 'BLOQUEADO  ' + filtro['motivo']}")
        print()
