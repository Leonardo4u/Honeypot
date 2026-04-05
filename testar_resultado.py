from dotenv import load_dotenv

load_dotenv()

from data.verificar_resultados import buscar_resultado_jogo

print("Testando busca de resultado...\n")

jogos = [
    ("Aston Villa", "Lille"),
    ("AS Roma", "Bologna"),
    ("Porto", "VfB Stuttgart"),
    ("FC Midtjylland", "Nottingham Forest"),
    ("Grmio", "Vitoria"),
]

for casa, fora in jogos:
    resultado = buscar_resultado_jogo(casa, fora)
    if resultado:
        print(f"{casa} vs {fora}: {resultado}")
    else:
        print(f"{casa} vs {fora}: não encontrado")