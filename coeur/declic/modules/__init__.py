"""Les modules de Déclic.

Un module fournit :
  - des commandes fixes (`commandes()`), retrouvées par la recherche floue du registre ;
  - éventuellement des résultats calculés à partir de la requête (`resultats()`),
    par exemple « = 36 » quand on tape « 15% de 240 ».
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from declic.modele import Commande, Creation, Resultat

if TYPE_CHECKING:
    from declic.contexte import Contexte


class Module:
    nom = "module"

    def __init__(self, contexte: "Contexte"):
        self.contexte = contexte

    def commandes(self) -> list[Commande]:
        return []

    def resultats(self, requete: str) -> list[Resultat]:
        return []

    def recharger(self) -> None:
        """Relire les fichiers de configuration du module."""

    def creations(self) -> list[Creation]:
        """Ce que l'utilisateur peut ajouter à ce module depuis la barre (bouton +)."""
        return []

    def pour_selection(self, selection: str, requete: str) -> list[Resultat]:
        """Actions sur le texte sélectionné dans une autre application (raccourci dédié de la barre)."""
        return []

    def suggestions(self, page: str | None, requete: str) -> list[Resultat]:
        """Résultats liés à la page affichée dans le navigateur au moment d'ouvrir la barre."""
        return []


def tous_les_modules(contexte: "Contexte") -> list[Module]:
    from declic.modules import (applications, assistant, automatisations, calcul, favoris, fichiers, ia, identifiants, interne, liens,
                                presse_papiers, scripts, snippets, son, systeme)

    return [
        interne.Interne(contexte),
        applications.Applications(contexte),
        calcul.Calcul(contexte),
        liens.Liens(contexte),
        ia.IA(contexte),
        assistant.Assistant(contexte),
        snippets.Snippets(contexte),
        systeme.Systeme(contexte),
        son.Son(contexte),
        scripts.Scripts(contexte),
        identifiants.Identifiants(contexte),
        automatisations.Automatisations(contexte),
        fichiers.Fichiers(contexte),
        presse_papiers.PressePapiers(contexte),
        favoris.Favoris(contexte),
    ]
