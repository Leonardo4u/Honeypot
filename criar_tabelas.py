import sys
sys.path.insert(0, 'data')
from kelly_banca import criar_tabela_banca
from clv_brier import criar_tabelas_validacao
criar_tabela_banca()
criar_tabelas_validacao()
print("Todas as tabelas criadas!")