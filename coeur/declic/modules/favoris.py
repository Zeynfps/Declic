"""Favoris : des résultats épinglés en haut de la barre vide.

Ils vivent dans ~/.config/declic/favoris.toml, à part de l'historique d'usage :
« Effacer les suggestions » ne les touche donc pas. Un favori peut garder un argument
(« ChatGPT : « … » », « Persée : céramique »), ou n'être qu'une commande (une appli, un réglage).

    [[favori]]
    commande = "liens.persee"
    argument = "céramique sigillée"   # facultatif
    titre = "Persée : « céramique sigillée »"
    icone = "web-browser-symbolic"
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from typing import Optional

from declic import fichiers_toml
from declic.modele import Commande, Creation, CreationRefusee, Element, Reponse
from declic.modules import Module

ENTETE = """# Favoris de Déclic : affichés en haut de la barre vide, dans cet ordre.
# Dans la barre : Ctrl+Maj+F (ou Ctrl+K → « Ajouter aux favoris ») sur un résultat.
# « Effacer les suggestions » ne touche pas à ce fichier.
"""


@dataclass(frozen=True)
class Favori:
    commande: str
    titre: str
    icone: str = ""
    argument: Optional[str] = None

    @property
    def cle(self) -> str:
        return cle_favori(self.commande, self.argument)


def cle_favori(commande: str, argument: Optional[str]) -> str:
    return commande if argument is None else f"{commande}\x1f{argument}"


class Favoris(Module):
    nom = "favoris"

    def __init__(self, contexte):
        super().__init__(contexte)
        self.liste: list[Favori] = []
        self.recharger()

    def recharger(self) -> None:
        self.liste = []
        fichier = self.contexte.chemins.favoris
        if not fichier.exists():
            return
        with fichier.open("rb") as f:
            donnees = tomllib.load(f)
        vus = set()
        for entree in donnees.get("favori", []):
            if not entree.get("commande"):
                continue
            argument = entree.get("argument")
            favori = Favori(str(entree["commande"]), str(entree.get("titre") or entree["commande"]),
                            str(entree.get("icone", "")), None if argument is None else str(argument))
            if favori.cle not in vus:
                vus.add(favori.cle)
                self.liste.append(favori)

    def cles(self) -> set[str]:
        return {f.cle for f in self.liste}

    # --- Ajouter / retirer --------------------------------------------------------------
    def basculer(self, commande: str, argument: Optional[str], titre: str, icone: str = "") -> Reponse:
        cle = cle_favori(commande, argument)
        if cle in self.cles():
            self.retirer(cle)
            return Reponse(message=f"« {titre} » retiré des favoris", fermer=False)
        valeurs = {"commande": commande, "titre": titre, "icone": icone}
        if argument is not None:
            valeurs["argument"] = argument
        fichiers_toml.ajouter_bloc(self.contexte.chemins.favoris, "favori", valeurs, entete=ENTETE)
        self.recharger()
        return Reponse(message=f"« {titre} » ajouté aux favoris", fermer=False)

    def retirer(self, cle: str) -> bool:
        if cle not in self.cles():
            return False
        fichiers_toml.retirer_bloc(
            self.contexte.chemins.favoris, "favori",
            lambda e: cle_favori(str(e.get("commande", "")),
                                 None if e.get("argument") is None else str(e["argument"])) != cle)
        self.recharger()
        return True

    def _basculer(self, contexte, argument):
        # Argument : JSON {"commande", "argument" (ou null), "titre", "icone"}, envoyé par la barre
        try:
            d = json.loads(argument or "")
            commande = str(d["commande"])
        except (ValueError, KeyError, TypeError):
            return Reponse.erreur("Favori illisible.")
        if commande.startswith("favoris."):
            return Reponse.erreur("Ce résultat ne peut pas être mis en favori.")
        arg = d.get("argument")
        return self.basculer(commande, None if arg is None else str(arg), str(d.get("titre") or commande),
                             str(d.get("icone") or ""))

    def commandes(self) -> list[Commande]:
        return [Commande("favoris.basculer", "Ajouter ou retirer un favori", self._basculer,
                         argument="favori", cachee=True)]

    # --- « Mes ajouts » : voir et retirer les favoris -------------------------------------
    def creations(self) -> list[Creation]:
        return [Creation(
            type="favori", titre="Favori", titre_pluriel="Favoris", icone="starred-symbolic",
            description="En haut de la barre vide ; ajoutés avec Ctrl+Maj+F sur un résultat.",
            champs=(), creer=self._creer, lister=self._lister, supprimer=self._supprimer, ajoutable=False,
        )]

    def _creer(self, _valeurs):
        raise CreationRefusee("Un favori s'ajoute depuis la recherche : Ctrl+Maj+F sur un résultat.")

    def _lister(self) -> list[Element]:
        return [Element(cle=f.cle, titre=f.titre, sous_titre=f.commande)
                for f in self.liste]

    def _supprimer(self, cle: str) -> Reponse:
        titre = next((f.titre for f in self.liste if f.cle == cle), None)
        if titre is None or not self.retirer(cle):
            raise CreationRefusee("Ce favori n'existe plus.")
        return Reponse(message=f"« {titre} » retiré des favoris", fermer=False)
