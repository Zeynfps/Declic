"""Ce qu'une commande reçoit pour travailler : la plateforme et les chemins."""
from __future__ import annotations

from dataclasses import dataclass, field

from declic.chemins import Chemins
from declic.etats import EtatsBascules
from declic.plateforme.base import Plateforme


@dataclass
class Contexte:
    plateforme: Plateforme
    chemins: Chemins
    etats: EtatsBascules = field(default=None)  # état des bascules, pour l'indicateur de la barre

    def __post_init__(self):
        if self.etats is None:
            self.etats = EtatsBascules(self.plateforme)
