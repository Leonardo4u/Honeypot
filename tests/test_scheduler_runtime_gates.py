import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from model.runtime_gate_context import (
    inferir_escalacao_confirmada,
    calcular_variacao_odd_gate,
    calcular_sinais_hoje_gate,
)
from data import steam_monitor


class TestGateContextBuilder(unittest.TestCase):
    def test_inferir_escalacao_usa_flag_explicita(self):
        jogo = {"lineup_confirmed": True}
        confirmado, origem = inferir_escalacao_confirmada(jogo)

        self.assertTrue(confirmado)
        self.assertEqual(origem, "feed:lineup_confirmed")

    def test_inferir_escalacao_bloqueia_quando_kickoff_proximo_sem_feed(self):
        now_utc = datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc)
        jogo = {
            "horario": (now_utc + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        confirmado, origem = inferir_escalacao_confirmada(jogo, agora_utc=now_utc)

        self.assertFalse(confirmado)
        self.assertEqual(origem, "fallback:kickoff_close")

    def test_inferir_escalacao_libera_janela_pre_lineup(self):
        now_utc = datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc)
        jogo = {
            "horario": (now_utc + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        confirmado, origem = inferir_escalacao_confirmada(jogo, agora_utc=now_utc)

        self.assertTrue(confirmado)
        self.assertEqual(origem, "fallback:pre_lineup_window")

    def test_calcular_variacao_odd_gate_usa_magnitude_quando_disponivel(self):
        variacao = calcular_variacao_odd_gate({"magnitude": -9.5})
        self.assertEqual(variacao, -9.5)

    def test_calcular_variacao_odd_gate_fallback_zero(self):
        variacao = calcular_variacao_odd_gate(None)
        self.assertEqual(variacao, 0.0)


class TestDailyLimitGate(unittest.TestCase):
    def test_calcular_sinais_hoje_gate_reflete_contagem_real(self):
        sinais_gate = calcular_sinais_hoje_gate(3, 2)
        self.assertEqual(sinais_gate, 5)

    def test_calcular_sinais_hoje_gate_nao_permite_negativo(self):
        sinais_gate = calcular_sinais_hoje_gate(-1, -5)
        self.assertEqual(sinais_gate, 0)


class TestSteamWindowGate(unittest.TestCase):
    def test_steam_nao_confirma_quando_abertura_muito_recente(self):
        abertura_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        abertura = (2.0, 2.0, 2.0, 2.0, '{"pinnacle":2.0,"betfair":2.0}', abertura_ts)
        dados_atuais = {
            "odd_pinnacle": 1.8,
            "odd_media": 1.8,
            "casas": {"pinnacle": 1.8, "betfair": 1.8},
        }

        with patch("data.steam_monitor.buscar_snapshot_abertura", return_value=abertura), patch(
            "data.steam_monitor.buscar_snapshots_recentes", return_value=[]
        ):
            steam = steam_monitor.calcular_steam("A vs B", "1x2_casa", dados_atuais)

        self.assertIsNotNone(steam)
        self.assertFalse(steam["steam_confirmado"])

    def test_steam_confirma_apos_janela_minima(self):
        abertura_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        abertura = (2.0, 2.0, 2.0, 2.0, '{"pinnacle":2.0,"betfair":2.0}', abertura_ts)
        dados_atuais = {
            "odd_pinnacle": 1.8,
            "odd_media": 1.8,
            "casas": {"pinnacle": 1.8, "betfair": 1.8},
        }

        with patch("data.steam_monitor.buscar_snapshot_abertura", return_value=abertura), patch(
            "data.steam_monitor.buscar_snapshots_recentes", return_value=[]
        ):
            steam = steam_monitor.calcular_steam("A vs B", "1x2_casa", dados_atuais)

        self.assertIsNotNone(steam)
        self.assertTrue(steam["steam_confirmado"])


if __name__ == "__main__":
    unittest.main()
