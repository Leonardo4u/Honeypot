@echo off
cd C:\Users\Leo\edge_protocol
python scheduler.py
```

Agora adiciona esse arquivo na inicialização do Windows:

1. Aperta **Windows + R**
2. Digita `shell:startup` e aperta Enter
3. Abre a pasta que aparecer
4. Copia o arquivo `iniciar_bot.bat` para essa pasta

Pronto — toda vez que o Windows iniciar, o scheduler vai abrir automaticamente.

---

## Passo 3 — Testar

Reinicia o computador e verifica se o CMD abre automaticamente com o scheduler rodando.

---

## Resumo do que vai acontecer todo dia
```
08:00 → Analisa jogos e envia os 5 melhores sinais
13:00 → Nova análise (jogos da tarde)
17:00 → Nova análise (jogos noturnos)
23:30 → Resumo do dia enviado nos canais
Segunda 06:00 → Médias de gols atualizadas