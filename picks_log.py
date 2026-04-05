"""Entrypoint CLI para sincronizar picks_log.csv com resultados no SQLite."""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

from model import picks_log as picks_log_module


if __name__ == "__main__":
    raise SystemExit(picks_log_module.main())
