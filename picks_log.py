"""Entrypoint CLI para sincronizar picks_log.csv com resultados no SQLite."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ROOT, "model")
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

from model import picks_log as picks_log_module


if __name__ == "__main__":
    raise SystemExit(picks_log_module.main())
