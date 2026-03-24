═══════════════════════════════════════════════════════════════
  EDGE PROTOCOL — PLANILHA DE APOSTAS
  README — Integração com o Bot
═══════════════════════════════════════════════════════════════

ARQUIVOS ENTREGUES
──────────────────
  bot_apostas.xlsx     → Planilha principal com 7 abas
  update_excel.py      → Script de atualização automática
  exemplo_dados.json   → 10 apostas de exemplo já inseridas
  README.txt           → Este arquivo

REQUISITOS
──────────
  pip install openpyxl pandas

ABAS DA PLANILHA
────────────────
  1. Dashboard        → Cards de performance + por liga
  2. Sinais Completos → Todas as apostas com histórico completo
  3. Março 2026       → Resumo mensal com performance por liga/tier
  4. Gestão de Banca  → Calculadora Kelly + histórico de banca
  5. CLV & Brier      → Validação do modelo
  6. Steam & SOS      → Monitoramento de sharp money
  7. Monitoramento 72h → Jogos em observação

═══════════════════════════════════════════════════════════════
  INTEGRAÇÃO COM O BOT (scheduler.py)
═══════════════════════════════════════════════════════════════

1. QUANDO SINAL É ENVIADO
─────────────────────────
No scheduler.py, após inserir_sinal(), adicione:

    import subprocess, json

    payload = json.dumps({
        "acao": "nova_aposta",
        "aposta": {
            "id": str(sinal_id),
            "data": datetime.now().strftime("%Y-%m-%d"),
            "hora": datetime.now().strftime("%H:%M"),
            "liga": analise["liga"],
            "jogo": analise["jogo"],
            "mercado": analise["mercado"],
            "tip": "Casa" if analise["mercado"]=="1x2_casa" else "Over 2.5",
            "odd_entrada": analise["odd"],
            "odd_fechamento": None,
            "ev": analise.get("ev_percentual_num", 0),
            "edge_score": analise["edge_score"],
            "tier": kelly["tier"],
            "prob_modelo": analise.get("prob_modelo", 0.55),
            "confianca": confianca,
            "steam": analise.get("steam_bonus", 0),
            "kelly_pct": kelly["kelly_final_pct"],
            "unidades": stake_unidades,
            "resultado": None,
            "retorno": None,
            "banca_apos": None,
            "notas": analise.get("fonte_dados","")
        }
    })
    subprocess.run(["python", "update_excel.py", payload])


2. QUANDO RESULTADO É REGISTRADO
─────────────────────────────────
No scheduler.py, após atualizar_resultado(), adicione:

    estado_banca = atualizar_banca(avaliacao["lucro"])

    payload = json.dumps({
        "acao": "resultado",
        "aposta": {
            "id": str(sinal_id),
            "odd_fechamento": odd_fechamento,  # da Pinnacle via CLV
            "resultado": avaliacao["resultado"].capitalize(),
            "retorno": avaliacao["lucro"],
            "banca_apos": estado_banca["banca_atual"],
            "data": datetime.now().strftime("%Y-%m-%d")
        }
    })
    subprocess.run(["python", "update_excel.py", payload])


3. REFRESH COMPLETO (opcional)
───────────────────────────────
Para regenerar o arquivo do zero com todos os dados do banco:

    python update_excel.py '{"acao":"full_refresh"}'

Ou integrar no resumo diário do scheduler (23h30):

    subprocess.run(["python", "update_excel.py",
                    '{"acao":"full_refresh"}'])


═══════════════════════════════════════════════════════════════
  USO MANUAL
═══════════════════════════════════════════════════════════════

Inserir aposta manualmente:
  python update_excel.py '{"acao":"nova_aposta","aposta":{...}}'

Registrar resultado:
  python update_excel.py '{"acao":"resultado","aposta":{"id":"001","resultado":"Green","retorno":1.92,"banca_apos":1019.20}}'

Regenerar arquivo completo:
  python update_excel.py '{"acao":"full_refresh"}'


═══════════════════════════════════════════════════════════════
  LOGS
═══════════════════════════════════════════════════════════════

Cada execução gera uma linha em update_log.txt:
  [2026-03-19 15:30:22] Nova aposta inserida: #001 — Arsenal vs Chelsea [1x2]
  [2026-03-19 18:02:11] Resultado atualizado: #001 — Green
  [2026-03-19 18:02:11] Histórico banca: dia 2026-03-19 — R$1.019,20


═══════════════════════════════════════════════════════════════
  CALCULADORA KELLY (Aba 4)
═══════════════════════════════════════════════════════════════

Para usar a calculadora interativa:
  1. Abra a aba "Gestão de Banca"
  2. Edite as células AMARELAS (campos de input)
  3. Os resultados calculam automaticamente

Campos editáveis:
  B13 → Probabilidade do modelo (ex: 0.60)
  B14 → Odd disponível (ex: 1.92)
  B15 → Tier (Padrão | Premium | Elite)

═══════════════════════════════════════════════════════════════
  DÚVIDAS
═══════════════════════════════════════════════════════════════

Consulte a documentação do bot ou abra uma conversa com
o Claude para ajustes personalizados.
