import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")

def gerar_dashboard_terminal():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        SELECT clv_percentual, timestamp_entrada
        FROM clv_tracking
        WHERE status = 'fechado' AND clv_percentual IS NOT NULL
        ORDER BY timestamp_entrada ASC
    ''')
    clvs = c.fetchall()

    c.execute('''
        SELECT brier_score, prob_prevista, resultado_real
        FROM brier_tracking
        WHERE brier_score IS NOT NULL
    ''')
    briers = c.fetchall()

    conn.close()

    print("\n" + "="*50)
    print("  DASHBOARD DE VALIDAÇÃO — EDGE PROTOCOL")
    print("="*50)

    if not clvs:
        print("\nCLV: sem dados ainda")
    else:
        valores_clv = [r[0] for r in clvs]
        clv_medio = sum(valores_clv) / len(valores_clv)
        clv_pos = sum(1 for v in valores_clv if v > 0)
        clv_pos_pct = clv_pos / len(valores_clv) * 100

        print(f"\n📊 CLV TRACKING ({len(valores_clv)} apostas)")
        print(f"  CLV Médio:          {clv_medio:+.2f}%")
        print(f"  CLV Positivo:       {clv_pos_pct:.1f}% das apostas")
        print(f"  Melhor CLV:         {max(valores_clv):+.2f}%")
        print(f"  Pior CLV:           {min(valores_clv):+.2f}%")

        if clv_medio > 2:
            print(f"  Status:             ✅ EXCELENTE — batendo mercado sharp")
        elif clv_medio > 0:
            print(f"  Status:             ✅ BOM — acima do mercado")
        else:
            print(f"  Status:             ⚠️  REVISAR — abaixo do mercado sharp")

        print(f"\n  Evolução CLV:")
        acumulado = 0
        for i, (clv, ts) in enumerate(clvs[-10:]):
            acumulado += clv
            barra = "█" * int(abs(clv)) if abs(clv) < 20 else "█" * 20
            sinal = "+" if clv >= 0 else ""
            print(f"  #{i+1:2d} {sinal}{clv:6.2f}%  {barra}")

    if not briers:
        print(f"\nBRIER SCORE: sem dados ainda")
    else:
        scores = [r[0] for r in briers]
        brier_medio = sum(scores) / len(scores)

        print(f"\n🎯 BRIER SCORE ({len(scores)} apostas)")
        print(f"  Score Médio:        {brier_medio:.4f}")

        if brier_medio < 0.20:
            print(f"  Calibração:         ✅ EXCELENTE (< 0.20)")
        elif brier_medio < 0.25:
            print(f"  Calibração:         ✅ BOA (< 0.25)")
        else:
            print(f"  Calibração:         ⚠️  SUPERESTIMANDO (> 0.25)")

        print(f"\n  Reliability Diagram (simplificado):")
        buckets = {}
        for score, prob, resultado in briers:
            bucket = int(prob * 10) * 10
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(resultado)

        print(f"  {'Prob prevista':15} {'Freq real':10} {'Calibrado?':10}")
        for bucket in sorted(buckets.keys()):
            resultados = buckets[bucket]
            freq_real = sum(resultados) / len(resultados) * 100
            diff = abs(bucket - freq_real)
            status = "✅" if diff < 10 else "⚠️"
            print(f"  {bucket:3d}%            {freq_real:6.1f}%     {status}")

    print("\n" + "="*50)

if __name__ == "__main__":
    gerar_dashboard_terminal()