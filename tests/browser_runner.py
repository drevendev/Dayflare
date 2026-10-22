"""Portable Chromium startup for real DOM-only browser regression scripts.

Locally use an installed system Chromium; on hosted CI use the Chromium
revision installed by Playwright. No production browser endpoint is contacted.
"""
from __future__ import annotations

import os
from pathlib import Path


def launch_chromium(playwright):
    override = os.environ.get('DAYFLARE_CHROMIUM_BIN')
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(f'DAYFLARE_CHROMIUM_BIN does not exist: {override}')
        return playwright.chromium.launch(headless=True, executable_path=str(path), args=['--no-sandbox'])
    system = Path('/usr/bin/chromium')
    if system.is_file():
        return playwright.chromium.launch(headless=True, executable_path=str(system), args=['--no-sandbox'])
    return playwright.chromium.launch(headless=True, args=['--no-sandbox'])
