"""État des bascules (Bluetooth, Wi-Fi, Ne pas déranger…) pour l'afficher dans la barre : « Activé » ou « Désactivé ».

Certains états sont lents à lire (Wi-Fi et Bluetooth sous Windows : environ une seconde). La recherche ne doit
jamais attendre : on montre le dernier état connu et on le relit en arrière-plan quand il a vieilli. Après une
bascule faite par Déclic, le nouvel état est connu tout de suite.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

journal = logging.getLogger("declic")

FRAICHEUR_S = 10  # au-delà, l'état est relu (en arrière-plan)


class EtatsBascules:
    def __init__(self, plateforme, horloge=time.monotonic, synchrone: bool = False):
        self.plateforme = plateforme
        self.horloge = horloge
        self.synchrone = synchrone  # tests : relire sans fil d'exécution
        self._etats: dict[str, tuple[bool, float]] = {}
        self._en_cours: set[str] = set()
        self._verrou = threading.Lock()

    def lire(self, nom: str) -> Optional[bool]:
        """Dernier état connu (None si encore jamais lu) ; relance une lecture s'il a vieilli."""
        if not self.plateforme.prend_en_charge("etat_bascule"):
            return None
        with self._verrou:
            connu = self._etats.get(nom)
            vieux = connu is None or self.horloge() - connu[1] > FRAICHEUR_S
            lancer = vieux and nom not in self._en_cours
            if lancer:
                self._en_cours.add(nom)
        if lancer:
            if self.synchrone:
                self._relire(nom)
            else:
                threading.Thread(target=self._relire, args=(nom,), daemon=True, name=f"état {nom}").start()
        connu = self._etats.get(nom)
        return connu[0] if connu else None

    def _relire(self, nom: str) -> None:
        try:
            etat = bool(self.plateforme.etat_bascule(nom))
            with self._verrou:
                self._etats[nom] = (etat, self.horloge())
        except Exception as exc:  # réglage absent sur ce PC… : pas d'indicateur
            journal.debug("État de %s illisible : %s", nom, exc)
        finally:
            with self._verrou:
                self._en_cours.discard(nom)

    def noter(self, nom: str, etat: bool) -> None:
        """Après une bascule : le nouvel état est connu sans relire."""
        with self._verrou:
            self._etats[nom] = (bool(etat), self.horloge())

    def prechauffer(self, noms) -> None:
        """Lit tous les états une première fois (au démarrage du service), pour la première ouverture de la barre."""
        for nom in noms:
            self.lire(nom)
