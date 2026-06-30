"""Run HardWorkers in web browser mode."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import flet as ft

from app.application import bootstrap

if __name__ == "__main__":
    ft.run(
        main=bootstrap,
        view=ft.AppView.WEB_BROWSER,
        port=8580,
        upload_dir="uploads",
    )
