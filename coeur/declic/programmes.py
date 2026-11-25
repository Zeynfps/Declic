"""Programmes ouverts : lesquels viennent de s'ouvrir ou de se fermer, et lesquels sont des jeux.

La plateforme donne la liste des programmes (nom → chemin) ; on la compare d'un relevé à l'autre et on en
tire des événements pour les automatisations :
  application.ouverte / application.fermee   (valeur = nom du programme, ex. « Discord »)
  jeu.lance / jeu.ferme                       (valeur = nom du jeu) : « lancé » quand un premier jeu s'ouvre,
                                              « fermé » quand plus aucun jeu ne tourne ; ainsi un jeu qui passe
                                              par plusieurs programmes (lanceur, puis jeu) ne compte qu'une fois.
"""
from __future__ import annotations

import re

# Dossiers où les boutiques installent les jeux (chemins en minuscules, séparateurs « / »)
DOSSIERS_JEUX = (
    "/steamapps/common/",            # Steam (et Proton sous Linux)
    "/epic games/",                  # Epic Games Store
    "/riot games/",                  # League of Legends, Valorant…
    "/gog galaxy/games/", "/gog games/",
    "/xboxgames/",                   # Xbox / Game Pass sur PC
    "/ea games/",
    "/ubisoft game launcher/games/",
    "/games/heroic/",                # Heroic (Linux)
)
# Programmes rangés avec les jeux mais qui n'en sont pas
NON_JEUX = re.compile(r"client|crash|launcher|helper|update|service|overlay|setup|install|redist|unins|"
                      r"anticheat|battleye|vanguard|report|bootstrap", re.IGNORECASE)


def est_un_jeu(nom: str, chemin: str) -> bool:
    if not chemin or NON_JEUX.search(nom):
        return False
    c = chemin.replace("\\", "/").lower()
    if any(d in c for d in DOSSIERS_JEUX):
        return True
    return c.startswith("/home/") and "/games/" in c  # Lutris, Heroic : ~/Games/… par défaut


class SuiviProgrammes:
    """Compare les relevés successifs et renvoie les événements correspondants."""

    def __init__(self):
        self.precedents: dict[str, str] | None = None
        self.jeux: dict[str, str] = {}  # jeux en cours : nom → chemin

    def comparer(self, actuels: dict[str, str]) -> list[tuple[str, str]]:
        if self.precedents is None:  # premier relevé : ce qui tourne déjà n'est pas « ouvert » maintenant
            self.precedents = dict(actuels)
            self.jeux = {n: c for n, c in actuels.items() if est_un_jeu(n, c)}
            return []
        evenements = []
        for nom in sorted(actuels.keys() - self.precedents.keys()):
            evenements.append(("application.ouverte", nom))
        for nom in sorted(self.precedents.keys() - actuels.keys()):
            evenements.append(("application.fermee", nom))
        jeux = {n: c for n, c in actuels.items() if est_un_jeu(n, c)}
        if jeux and not self.jeux:
            evenements.append(("jeu.lance", sorted(jeux)[0]))
        elif self.jeux and not jeux:
            evenements.append(("jeu.ferme", sorted(self.jeux)[0]))
        self.precedents, self.jeux = dict(actuels), jeux
        return evenements

    @property
    def jeu_en_cours(self) -> bool:
        return bool(self.jeux)
