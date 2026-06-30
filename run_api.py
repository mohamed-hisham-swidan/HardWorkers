"""Launcher for the FastAPI backend server."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from config.settings import AppConfig


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = AppConfig()
    host = config.api.host
    port = config.api.port
    reload_enabled = config.api.reload

    log = logging.getLogger("run_api")
    log.info("Starting API server on %s:%s", host, port)

    uvicorn.run(
        "api.main:create_app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level="info",
        factory=True,
    )


if __name__ == "__main__":
    main()
