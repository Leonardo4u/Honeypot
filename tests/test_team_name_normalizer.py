import unittest

import pandas as pd

from model.team_name_normalizer import normalize, normalize_df


class TestTeamNameNormalizer(unittest.TestCase):
    def test_known_alias_lookup(self):
        self.assertEqual(normalize("Vasco DA Gama"), "Vasco da Gama")
        self.assertEqual(normalize("Atletico-MG"), "Atletico Mineiro")
        self.assertEqual(normalize("Sao Paulo"), "São Paulo")

    def test_unknown_name_passthrough(self):
        self.assertEqual(normalize("Fortaleza EC"), "Fortaleza EC")
        self.assertEqual(normalize(""), "")

    def test_normalize_df_sample(self):
        df = pd.DataFrame(
            {
                "time_casa": ["Vasco DA Gama", "Sao Paulo"],
                "time_fora": ["Atletico-MG", "Fluminense FC"],
            }
        )
        normalize_df(df, "time_casa")
        normalize_df(df, "time_fora")

        self.assertEqual(df.loc[0, "time_casa"], "Vasco da Gama")
        self.assertEqual(df.loc[1, "time_casa"], "São Paulo")
        self.assertEqual(df.loc[0, "time_fora"], "Atletico Mineiro")
        self.assertEqual(df.loc[1, "time_fora"], "Fluminense")


if __name__ == "__main__":
    unittest.main()
