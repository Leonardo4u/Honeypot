import unittest
import os
import json
import tempfile
from unittest.mock import patch

from model.signal_policy_v2 import (
    EVMinimoPolicy,
    SteamGatePolicy,
    gate_ev_steam,
    policy_v2_blocks,
    log_policy_v2_rejection,
)


class TestSignalPolicyV2(unittest.TestCase):
    def test_ev_gate_behavior_rejects_below_minimum(self):
        policy = EVMinimoPolicy(execucao_automatizada=False)
        decisao = policy.avaliar(
            mercado="draw",
            ev_calculado=0.02,
            book="pinnacle",
            minutos_ate_jogo=180,
            volume_estimado=100000,
        )
        self.assertFalse(decisao.aprovado)
        self.assertGreater(decisao.ev_minimo, decisao.ev_calculado)

    def test_steam_signal_acceptance_and_rejection(self):
        steam = SteamGatePolicy(limiar_steam_score=0.01, limiar_bloqueio=0.008)

        favor = steam.avaliar(
            odd_abertura=1.90,
            odd_atual=1.84,
            book="pinnacle",
            minutos_ate_jogo=180,
            nossa_direcao="down",
        )
        self.assertTrue(favor.aprovado)
        self.assertFalse(favor.rejeitado_por_steam)

        contra = steam.avaliar(
            odd_abertura=1.90,
            odd_atual=2.02,
            book="pinnacle",
            minutos_ate_jogo=180,
            nossa_direcao="down",
        )
        self.assertFalse(contra.aprovado)
        self.assertTrue(contra.rejeitado_por_steam)

    def test_shadow_mode_runs_but_does_not_block(self):
        ev_policy = EVMinimoPolicy(execucao_automatizada=False)
        steam_policy = SteamGatePolicy(limiar_steam_score=0.02, limiar_bloqueio=0.01)
        decisao = gate_ev_steam(
            mercado="home_win",
            ev_calculado=0.10,
            odd_abertura=2.00,
            odd_atual=2.14,
            book="pinnacle",
            minutos_ate_jogo=120,
            nossa_direcao="down",
            ev_policy=ev_policy,
            steam_policy=steam_policy,
            volume_estimado=100000,
        )

        self.assertFalse(decisao.aprovado)
        self.assertFalse(policy_v2_blocks(decisao, shadow_mode=True))
        self.assertTrue(policy_v2_blocks(decisao, shadow_mode=False))

    def test_policy_v2_rejection_logs_are_separated(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = os.path.join(td, "data")
            os.makedirs(data_dir, exist_ok=True)
            with patch.dict(os.environ, {"BOT_DATA_DIR": data_dir}, clear=False):
                log_policy_v2_rejection(
                    shadow_mode=True,
                    prediction_id="pred-1",
                    league="Premier League",
                    market="1x2_casa",
                    team_home="Arsenal",
                    team_away="Chelsea",
                    odds=2.0,
                    ev=0.05,
                    edge_score=82,
                    reject_reason="steam",
                    odds_reference=1.9,
                )
                log_policy_v2_rejection(
                    shadow_mode=False,
                    prediction_id="pred-2",
                    league="Premier League",
                    market="1x2_casa",
                    team_home="Arsenal",
                    team_away="Chelsea",
                    odds=2.0,
                    ev=0.05,
                    edge_score=82,
                    reject_reason="steam",
                    odds_reference=1.9,
                )

            shadow_path = os.path.join(td, "logs", "policy_v2_shadow.log")
            reject_path = os.path.join(td, "logs", "policy_v2_reject.log")
            self.assertTrue(os.path.exists(shadow_path))
            self.assertTrue(os.path.exists(reject_path))

            with open(shadow_path, "r", encoding="utf-8") as f:
                shadow_obj = json.loads(f.readline())
            with open(reject_path, "r", encoding="utf-8") as f:
                reject_obj = json.loads(f.readline())

            self.assertTrue(shadow_obj["would_have_blocked"])
            self.assertFalse(reject_obj["would_have_blocked"])


if __name__ == "__main__":
    unittest.main()
