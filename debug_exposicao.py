import sqlite3
from datetime import date

conn = sqlite3.connect('data/edge_protocol.db')
c = conn.cursor()

c.execute("SELECT id, jogo, stake_unidades, status, data FROM sinais WHERE data = ?", (str(date.today()),))
sinais = c.fetchall()
conn.close()

print(f"Sinais de hoje: {len(sinais)}")
for s in sinais:
    print(f"  ID:{s[0]} | {s[1]} | stake:{s[2]} | status:{s[3]} | data:{s[4]}")

total_exposicao = sum(s[2] * 0.01 for s in sinais if s[2] and s[3] == 'pendente')
print(f"\nExposição total: {total_exposicao*100:.1f}%")