"""Ce qu'une commande reçoit pour travailler : la plateforme et les chemins."""
from __future__ import annotations

from dataclasses import dataclass

from declic.chemins import Chemins
from declic.plateforme.base import Plateforme


@dataclass
class Contexte:
    plateforme: Plateforme
    chemins: Chemins
