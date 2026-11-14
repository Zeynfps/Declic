"""Choix de la plateforme selon le système."""
from __future__ import annotations

import sys

from declic.plateforme.base import Plateforme


def detecter() -> Plateforme:
    if sys.platform.startswith("linux"):
        from declic.plateforme.linux import PlateformeLinux

        return PlateformeLinux()
    if sys.platform == "win32":
        from declic.plateforme.windows import PlateformeWindows

        return PlateformeWindows()
    return Plateforme()
