import os
import unittest
from unittest.mock import MagicMock, patch

from data.ingestion_resilience import request_with_retry
from services import api_error_monitor


class TestApiErrorMonitor(unittest.TestCase):
    def setUp(self):
        api_error_monitor._LAST_SENT_AT.clear()

    @patch("services.api_error_monitor.requests.post")
    @patch.dict(
        os.environ,
        {
            "BOT_TOKEN": "bot-telegram-token-de-teste",
            "EDGE_API_ERROR_TELEGRAM_CHAT": "@leogg07",
            "ODDS_API_KEY": "abcdef1234567890abcdef1234567890",
        },
        clear=False,
    )
    def test_envio_com_sanitizacao_endpoint_e_mensagem(self, post_mock):
        post_mock.return_value = MagicMock(status_code=200, text="ok")

        sent = api_error_monitor.report_api_error(
            error_type="http_error",
            error_message="falha ao chamar endpoint?apiKey=abcdef1234567890abcdef1234567890",
            endpoint="https://api.exemplo.com/v1/resource?apiKey=abcdef1234567890abcdef1234567890",
            status_code=500,
            timestamp="2026-04-05T12:00:00+00:00",
        )

        self.assertTrue(sent)
        self.assertEqual(post_mock.call_count, 1)
        payload = post_mock.call_args.kwargs["json"]
        texto = payload["text"]
        self.assertIn("api.exemplo.com/v1/resource", texto)
        self.assertNotIn("abcdef1234567890abcdef1234567890", texto)

    @patch("services.api_error_monitor.requests.post")
    @patch.dict(
        os.environ,
        {
            "BOT_TOKEN": "bot-telegram-token-de-teste",
            "EDGE_API_ERROR_TELEGRAM_CHAT": "@leogg07",
        },
        clear=False,
    )
    def test_debounce_nao_reenvia_mesmo_erro_antes_60s(self, post_mock):
        post_mock.return_value = MagicMock(status_code=200, text="ok")

        first = api_error_monitor.report_api_error(
            error_type="timeout",
            error_message="tempo esgotado",
            endpoint="provider:odds",
            status_code=None,
            timestamp="2026-04-05T12:00:00+00:00",
        )
        second = api_error_monitor.report_api_error(
            error_type="timeout",
            error_message="tempo esgotado",
            endpoint="provider:odds",
            status_code=None,
            timestamp="2026-04-05T12:00:01+00:00",
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(post_mock.call_count, 1)


class TestIngestionResilienceApiMonitor(unittest.TestCase):
    @patch("data.ingestion_resilience.report_api_error")
    @patch("data.ingestion_resilience.requests.get")
    def test_http_429_dispara_alerta_rate_limit(self, get_mock, report_mock):
        response = MagicMock()
        response.status_code = 429
        get_mock.return_value = response

        result = request_with_retry(
            url="https://api.exemplo.com/odds",
            timeout=1,
            attempts=1,
            source_name="odds_api:soccer_epl",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "http_error")
        report_mock.assert_called_once()
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["error_type"], "rate_limit")
        self.assertEqual(kwargs["endpoint"], "odds_api:soccer_epl")
        self.assertEqual(kwargs["status_code"], 429)

    @patch("data.ingestion_resilience.report_api_error")
    @patch("data.ingestion_resilience.requests.get", side_effect=Exception("boom"))
    def test_excecao_dispara_alerta_exception(self, _get_mock, report_mock):
        result = request_with_retry(
            url="https://api.exemplo.com/odds",
            timeout=1,
            attempts=1,
            source_name="odds_api:soccer_epl",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unknown_error")
        report_mock.assert_called_once()
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["error_type"], "exception")
        self.assertEqual(kwargs["endpoint"], "odds_api:soccer_epl")


if __name__ == "__main__":
    unittest.main(verbosity=2)
