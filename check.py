import csv
rows = list(csv.DictReader(open('data/picks_log.csv')))
settled = [r for r in rows if r.get('outcome') in ('0','1')]
print(f'Settled: {len(settled)}')
print(f'Total: {len(rows)}')
print(f'Pronto para calibracao: {len(settled) >= 30}')