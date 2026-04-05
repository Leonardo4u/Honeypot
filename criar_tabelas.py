# BUG-03 FIX: importar e chamar criar_banco() como primeiro passo
# garante que tabelas sinais, job_execucoes e todas as dependentes
# sejam criadas antes dos passos subsequentes.
from data.database import criar_banco, bootstrap_completo
from data.kelly_banca import criar_tabela_banca
from data.clv_brier import criar_tabelas_validacao

bootstrap_completo()
criar_tabela_banca()
criar_tabelas_validacao()
print("Todas as tabelas criadas!")
