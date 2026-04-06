import sqlite3

conn = sqlite3.connect("data/edge_protocol.db")
c = conn.cursor()

print("=== COLUNAS DA TABELA sinais ===")
c.execute("PRAGMA table_info(sinais)")
for col in c.fetchall():
    print(col)

print("\n=== COLUNAS DA TABELA clv_tracking ===")
c.execute("PRAGMA table_info(clv_tracking)")
for col in c.fetchall():
    print(col)

conn.close()