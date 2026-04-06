import re

content = open('calibrate.py', encoding='utf-8').read()

match = re.search(r'.{120}int\(row\["outcome"\]\).{120}', content, flags=re.DOTALL)
if match:
    print('Trecho encontrado:', match.group())
else:
    print('Trecho com int(row["outcome"]) nao encontrado')
