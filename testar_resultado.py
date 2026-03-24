import sys
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, 'data')
sys.path.insert(0, 'model')

from verificar_resultados import buscar_resultado_jogo

print("Testando busca de resultado...\n")

jogos = [
    ("Aston Villa", "Lille"),
    ("AS Roma", "Bologna"),
    ("Porto", "VfB Stuttgart"),
    ("FC Midtjylland", "Nottingham Forest"),
    ("Grêmio", "Vitoria"),
]

for casa, fora in jogos:
    resultado = buscar_resultado_jogo(casa, fora)
    if resultado:
        print(f"{casa} vs {fora}: {resultado}")
    else:
        print(f"{casa} vs {fora}: não encontrado")