import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from data.coletar_odds import coletar_odds
from model.analisar_jogo import analisar_jogo
import traceback

jogos = coletar_odds()
print(f"Jogos coletados: {len(jogos)}")

for jogo in jogos[:3]:
    print(f"\nAnalisando: {jogo.get('home_team','?')} vs {jogo.get('away_team','?')}")
    try:
        resultado = analisar_jogo(jogo)
        print(f"  -> OK")
    except Exception as e:
        print(f"  -> ERRO: {e}")
        traceback.print_exc()