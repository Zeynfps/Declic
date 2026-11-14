"""Lancer les applications installées."""
from __future__ import annotations

import time

from declic.modele import Commande, Reponse
from declic.modules import Module
from declic.plateforme.base import NonPrisEnCharge

_DUREE_CACHE = 60  # secondes


class Applications(Module):
    nom = "app"

    def __init__(self, contexte):
        super().__init__(contexte)
        self._cache: list[Commande] = []
        self._date = 0.0

    def recharger(self) -> None:
        self._date = 0.0

    def _lancer(self, app_id: str, nom: str):
        def action(contexte, _argument):
            contexte.plateforme.lancer_application(app_id)
            return Reponse(message=f"{nom} lancé")
        return action

    def commandes(self) -> list[Commande]:
        if time.monotonic() - self._date < _DUREE_CACHE and self._date:
            return self._cache
        plateforme = self.contexte.plateforme
        if not plateforme.prend_en_charge("lister_applications"):
            return []
        try:
            applis = plateforme.lister_applications()
        except NonPrisEnCharge:
            return []
        self._cache = [
            Commande(
                id=f"app.{a.id}", titre=a.nom, description=a.description or "Application",
                icone=a.icone or "application-x-executable-symbolic", mots_cles=a.mots_cles,
                action=self._lancer(a.id, a.nom), requiert="lancer_application",
            )
            for a in applis if a.id and a.nom
        ]
        self._date = time.monotonic()
        return self._cache
