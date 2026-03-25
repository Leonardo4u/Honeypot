import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TEST_MODULES = [
    "tests.test_filtros_gate",
    "tests.test_scheduler_runtime_gates",
    "tests.test_scheduler_dry_run",
    "tests.test_scheduler_provider_health",
    "tests.test_settlement_fixture_resolution",
    "tests.test_scheduler_settlement_integrity",
    "tests.test_scheduler_guardrails",
    "tests.test_confidence_quality_prior",
    "tests.test_scheduler_quality_prior_ranking",
    "tests.test_quality_telemetry_weekly",
    "tests.test_database_integration",
]


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(TEST_MODULES)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
