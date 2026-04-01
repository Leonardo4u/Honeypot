import unittest

from model.portfolio_risk import PosicaoAberta, PortfolioRiskManager


class TestPortfolioRiskManager(unittest.TestCase):
    def test_accepts_uncorrelated_position(self):
        mgr = PortfolioRiskManager(bankroll=1000.0)
        decisao = mgr.avaliar(
            match_id="m001",
            liga="Premier League",
            time_home="Arsenal",
            time_away="Chelsea",
            mercado="home_win",
            odd=2.10,
            p_modelo=0.58,
        )
        self.assertTrue(decisao.aprovado)
        self.assertGreater(decisao.stake_recomendado, 0.0)
        self.assertEqual(decisao.rho_portfolio, 0.0)

    def test_rejects_when_correlation_threshold_exceeded(self):
        mgr = PortfolioRiskManager(bankroll=1000.0, max_correlacao_portfolio=0.55)
        mgr.posicoes.append(
            PosicaoAberta(
                bet_id="b001",
                match_id="m001",
                liga="Premier League",
                time_home="Arsenal",
                time_away="Chelsea",
                mercado="home_win",
                odd=2.0,
                stake=60.0,
                p_modelo=0.55,
                kelly_individual=0.02,
            )
        )

        decisao = mgr.avaliar(
            match_id="m001",
            liga="Premier League",
            time_home="Arsenal",
            time_away="Chelsea",
            mercado="asian_handicap",
            odd=1.95,
            p_modelo=0.57,
        )
        self.assertFalse(decisao.aprovado)
        self.assertIsNotNone(decisao.motivo_veto)
        self.assertIn("ρ_portfolio", decisao.motivo_veto)

    def test_kelly_is_reduced_under_portfolio_constraints(self):
        mgr = PortfolioRiskManager(bankroll=1000.0)
        mgr.posicoes.append(
            PosicaoAberta(
                bet_id="b010",
                match_id="m010",
                liga="Premier League",
                time_home="Liverpool",
                time_away="Everton",
                mercado="home_win",
                odd=1.80,
                stake=40.0,
                p_modelo=0.60,
                kelly_individual=0.03,
            )
        )

        decisao = mgr.avaliar(
            match_id="m011",
            liga="Premier League",
            time_home="Arsenal",
            time_away="Chelsea",
            mercado="over_2.5",
            odd=1.90,
            p_modelo=0.60,
        )
        self.assertTrue(decisao.aprovado)
        self.assertGreater(decisao.kelly_individual, decisao.kelly_marginal)
        self.assertGreater(decisao.rho_portfolio, 0.0)


if __name__ == "__main__":
    unittest.main()
