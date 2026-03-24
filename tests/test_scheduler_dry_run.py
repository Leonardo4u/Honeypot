import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import scheduler


class TestSchedulerDryRun(unittest.TestCase):
    def test_executar_dry_run_once_finaliza_com_sucesso(self):
        with patch("scheduler.processar_jogos", new=AsyncMock(return_value=None)) as mocked_processar:
            rc = scheduler.executar_dry_run_once()

        self.assertEqual(rc, 0)
        mocked_processar.assert_awaited_once_with(dry_run=True)

    def test_dry_run_nao_instancia_telegram_bot(self):
        with patch("scheduler.buscar_jogos_com_odds", return_value=[]), \
             patch("scheduler.formatar_jogos", return_value=[]), \
             patch("scheduler.Bot") as mocked_bot:
            asyncio.run(scheduler.processar_jogos(dry_run=True))

        mocked_bot.assert_not_called()

    def test_dry_run_emite_log_cycle_totals(self):
        with patch("scheduler.buscar_jogos_com_odds", return_value=[]), \
             patch("scheduler.formatar_jogos", return_value=[]), \
             patch("scheduler.log_event") as mocked_log:
            asyncio.run(scheduler.processar_jogos(dry_run=True))

        chamadas = [c.args for c in mocked_log.call_args_list]
        self.assertTrue(any(args[0] == "scheduler" and args[1] == "cycle_totals" for args in chamadas))


if __name__ == "__main__":
    unittest.main()
