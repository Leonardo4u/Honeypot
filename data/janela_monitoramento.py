import sqlite3
import requests
import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"

LIGAS_COPA = [
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_uefa_europa_conference_league"
]

LIGAS_FIM_DE_SEMANA = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_brazil_campeonato"
]

CLASSICOS = [
    "real madrid", "barcelona", "manchester city", "manchester united",
    "liverpool", "chelsea", "arsenal", "juventus", "milan", "inter",
    "bayern munich", "borussia dortmund", "paris saint germain",
    "flamengo", "palmeiras", "corinthians"
]

def criar_tabela_janela():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jogos_monitorados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jogo TEXT NOT NULL,
            liga_key TEXT,
            horario_jogo TEXT,
            modo TEXT DEFAULT 'observacao',
            janela_horas INTEGER DEFAULT 12,
            odd_abertura_pinnacle REAL,
            odd_abertura_media REAL,
            timestamp_abertura TEXT,
            movimento_6h REAL,
            notificado INTEGER DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def detectar_janela(liga_key, home, away, n_bookmakers=0):
    if liga_key in LIGAS_COPA:
        return 48

    home_lower = home.lower()
    away_lower = away.lower()
    for classico in CLASSICOS:
        if classico in home_lower or classico in away_lower:
            return 72

    if n_bookmakers >= 20:
        return 48

    return 12

def buscar_jogos_janela_expandida(liga_key, horas=72):
    if not API_KEY:
        return []

    url = f"{BASE_URL}/sports/{liga_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }

    jogos_encontrados = []

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return []

        agora = datetime.now(timezone.utc)
        limite = agora + timedelta(hours=horas)

        for jogo in response.json():
            horario_str = jogo.get("commence_time", "")
            try:
                horario = datetime.strptime(horario_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if not (agora <= horario <= limite):
                    continue

                home = jogo["home_team"]
                away = jogo["away_team"]
                n_bm = len(jogo.get("bookmakers", []))
                janela = detectar_janela(liga_key, home, away, n_bm)
                horas_para_jogo = (horario - agora).total_seconds() / 3600
                modo = "observacao" if horas_para_jogo > 12 else "ativo"

                odd_pinnacle = None
                odds_lista = []

                for bm in jogo.get("bookmakers", []):
                    for market in bm.get("markets", []):
                        if market["key"] == "h2h":
                            for o in market["outcomes"]:
                                if o["name"] == home:
                                    odds_lista.append(o["price"])
                                    if bm["key"] == "pinnacle":
                                        odd_pinnacle = o["price"]

                odd_media = round(sum(odds_lista) / len(odds_lista), 3) if odds_lista else 0

                jogos_encontrados.append({
                    "jogo": f"{home} vs {away}",
                    "home_team": home,
                    "away_team": away,
                    "liga_key": liga_key,
                    "horario": horario_str,
                    "horas_para_jogo": round(horas_para_jogo, 1),
                    "janela_horas": janela,
                    "modo": modo,
                    "odd_pinnacle": odd_pinnacle,
                    "odd_media": odd_media,
                    "n_bookmakers": n_bm
                })

            except Exception:
                continue

    except Exception as e:
        print(f"Erro ao buscar {liga_key}: {e}")

    return jogos_encontrados

def registrar_jogo_monitorado(jogo_dados):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id FROM jogos_monitorados WHERE jogo = ? AND horario_jogo = ?",
              (jogo_dados["jogo"], jogo_dados["horario"]))
    existente = c.fetchone()

    if existente:
        conn.close()
        return existente[0]

    c.execute('''
        INSERT INTO jogos_monitorados
        (jogo, liga_key, horario_jogo, modo, janela_horas,
         odd_abertura_pinnacle, odd_abertura_media, timestamp_abertura)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        jogo_dados["jogo"],
        jogo_dados["liga_key"],
        jogo_dados["horario"],
        jogo_dados["modo"],
        jogo_dados["janela_horas"],
        jogo_dados.get("odd_pinnacle"),
        jogo_dados.get("odd_media"),
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    jogo_id = c.lastrowid
    conn.close()
    return jogo_id

def atualizar_modo_jogos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    agora = datetime.now(timezone.utc)
    limite_ativo = (agora + timedelta(hours=12)).isoformat()

    c.execute('''
        UPDATE jogos_monitorados
        SET modo = 'ativo'
        WHERE modo = 'observacao'
        AND horario_jogo <= ?
    ''', (limite_ativo,))

    atualizados = c.rowcount
    conn.commit()
    conn.close()

    if atualizados > 0:
        print(f"{atualizados} jogos entraram em modo ATIVO")

    return atualizados

def buscar_jogos_ativos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    agora = datetime.now(timezone.utc)

    c.execute('''
        SELECT jogo, liga_key, horario_jogo, odd_abertura_pinnacle,
               odd_abertura_media, movimento_6h, janela_horas
        FROM jogos_monitorados
        WHERE modo = 'ativo'
        AND horario_jogo >= ?
        ORDER BY horario_jogo ASC
    ''', (agora.isoformat(),))

    rows = c.fetchall()
    conn.close()
    return rows

def buscar_jogos_observacao():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    agora = datetime.now(timezone.utc).isoformat()
    c.execute('''
        SELECT jogo, liga_key, horario_jogo, odd_abertura_pinnacle,
               notificado, janela_horas
        FROM jogos_monitorados
        WHERE modo = 'observacao'
        AND horario_jogo >= ?
        ORDER BY horario_jogo ASC
    ''', (agora,))

    rows = c.fetchall()
    conn.close()
    return rows

def gerar_alerta_abertura(jogo_dados):
    horas = jogo_dados["horas_para_jogo"]
    janela = jogo_dados["janela_horas"]
    odd_p = jogo_dados.get("odd_pinnacle", "N/A")
    odd_m = jogo_dados.get("odd_media", "N/A")

    if janela == 72:
        tipo = " CLSSICO"
    elif janela == 48:
        tipo = " COPA/EUROPA"
    else:
        tipo = " LIGA"

    msg = (
        f"👁️ MODO OBSERVAÇÃO ATIVO\n\n"
        f"{tipo}\n"
        f"⚽ {jogo_dados['jogo']}\n"
        f"⏱️ Faltam {horas:.0f}h para o jogo\n\n"
        f"📊 Odds de abertura:\n"
        f"  Pinnacle: {odd_p}\n"
        f"  Média mercado: {odd_m}\n\n"
        f"🔍 Monitorando por {janela}h\n"
        f"⚡ Sinal gerado quando entrar na janela ativa (12h)\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )
    return msg

def marcar_notificado(jogo):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jogos_monitorados SET notificado = 1 WHERE jogo = ?", (jogo,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    criar_tabela_janela()
    print("=== TESTE JANELA EXPANDIDA ===\n")

    todas_ligas = LIGAS_COPA + LIGAS_FIM_DE_SEMANA
    total = 0

    for liga_key in todas_ligas:
        jogos = buscar_jogos_janela_expandida(liga_key, horas=72)
        for j in jogos:
            print(f"{j['jogo']}")
            print(f"  Liga: {j['liga_key']} | Faltam: {j['horas_para_jogo']}h")
            print(f"  Janela: {j['janela_horas']}h | Modo: {j['modo']}")
            print(f"  Odd Pinnacle: {j['odd_pinnacle']} | Bookmakers: {j['n_bookmakers']}")
            print()
            total += 1

    print(f"Total: {total} jogos encontrados nas próximas 72h")