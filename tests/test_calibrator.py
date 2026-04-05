import os
import tempfile
import unittest

from model.calibrator import BucketCalibrator


class TestBucketCalibrator(unittest.TestCase):
    def test_identity_passthrough_quando_nao_fitado(self):
        cal = BucketCalibrator()
        self.assertFalse(cal.is_fitted)
        self.assertAlmostEqual(cal.predict(0.73), 0.73, places=6)

    def test_laplace_em_bucket_vazio(self):
        cal = BucketCalibrator(n_buckets=10, k=20)
        cal.fit([0.95], [1])

        vazio = cal.buckets[0]
        self.assertEqual(vazio["n"], 0)
        # Laplace puro de bucket vazio é (0+1)/(0+2)=0.5
        self.assertAlmostEqual(vazio["laplace_rate"], 0.5, places=6)

    def test_shrinkage_com_n_pequeno(self):
        cal = BucketCalibrator(n_buckets=10, k=20)
        # Base rate global = 0.5
        preds = [0.84, 0.10]
        outs = [1, 0]
        cal.fit(preds, outs)

        idx = cal._bucket_index(0.84)
        b = cal.buckets[idx]

        # n=1 => laplace=2/3, shrink puxa para base_rate=0.5
        self.assertEqual(b["n"], 1)
        self.assertGreater(b["laplace_rate"], b["calibrated_rate"])
        self.assertGreater(b["calibrated_rate"], cal.base_rate)

    def test_save_load_roundtrip(self):
        cal = BucketCalibrator(n_buckets=10, k=20)
        cal.fit([0.2, 0.8, 0.9], [0, 1, 1])

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "calibracao_prob.json")
            cal.save(path)
            loaded = BucketCalibrator.load(path)

        self.assertTrue(loaded.is_fitted)
        self.assertEqual(loaded.n_buckets, cal.n_buckets)
        self.assertAlmostEqual(loaded.base_rate, cal.base_rate, places=6)
        self.assertEqual(len(loaded.buckets), len(cal.buckets))
        self.assertAlmostEqual(loaded.predict(0.83), cal.predict(0.83), places=6)


if __name__ == "__main__":
    unittest.main()
