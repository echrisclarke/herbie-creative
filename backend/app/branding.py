"""Shared Herbie Creative terminal branding."""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import PROJECT_ROOT

# Block-letter wordmark (same art as install hero, without install caption).
CLI_HERO = r"""
  ##     ## ######## ########  ########  #### ########
  ##     ## ##       ##     ## ##     ##  ##  ##
  ##     ## ##       ##     ## ##     ##  ##  ##
  ######### ######   ########  ########   ##  ######
  ##     ## ##       ##   ##   ##     ##  ##  ##
  ##     ## ##       ##    ##  ##     ##  ##  ##
  ##     ## ######## ##     ## ########  #### ########
     ..     ........ ........  ........  .... ........

   ######  ########  ########    ###    ######## #### ##     ## ########
  ##    ## ##     ## ##         ## ##      ##     ##  ##     ## ##
  ##       ##     ## ##        ##   ##     ##     ##  ##     ## ##
  ##       ########  ######   ##     ##    ##     ##  ##     ## ######
  ##       ##   ##   ##       #########    ##     ##   ##   ##  ##
  ##    ## ##    ##  ##       ##     ##    ##     ##    ## ##   ##
  #######  ##     ## ######## ##     ##    ##    ####    ###    ########
     .....  ........ ........ ........     ....  ....  .......  ........
""".lstrip("\n")


def load_cli_hero() -> str:
    """Prefer scripts/cli_hero.txt when present; otherwise use the built-in wordmark."""
    candidates = (
        PROJECT_ROOT / "scripts" / "cli_hero.txt",
        PROJECT_ROOT / "scripts" / "install_hero.txt",
    )
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        # Drop install-only caption lines from install_hero.txt
        while lines and (
            not lines[0].strip()
            or "first launch" in lines[0].lower()
            or "installing packages" in lines[0].lower()
        ):
            lines.pop(0)
        body = "\n".join(lines).rstrip() + "\n"
        if "##" in body:
            return body
    return CLI_HERO


def print_cli_hero(*, stream=None, subtitle: str | None = None) -> None:
    out = stream or sys.stdout
    hero = load_cli_hero()
    out.write("\n")
    out.write(hero)
    if subtitle:
        out.write(f"  {subtitle}\n")
    out.write("\n")
    out.flush()
