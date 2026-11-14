"""Retrouver un fichier ou un dossier par son nom, avec l'index du système (LocalSearch sous GNOME).

On tape une partie du nom (« rapport fouille ») : les fichiers dont le nom contient tous les mots
apparaissent sous les commandes, les plus récents d'abord à pertinence égale. Entrée ouvre le fichier
avec l'application par défaut ; les actions (Ctrl+K) proposent de l'afficher dans son dossier.
"""
from __future__ import annotations

import os
import time

from declic import texte
from declic.modele import Commande, Reponse, Resultat
from declic.modules import Module
from declic.plateforme.base import NonPrisEnCharge

LONGUEUR_MIN = 3  # en dessous, presque tous les noms correspondent
NB_MAX = 6  # lignes de fichiers affichées au plus
# Dossiers techniques qui noient les vrais documents
IGNORES = {"node_modules", "__pycache__", "site-packages", "dist-packages", ".git", ".cache", ".venv", "venv"}
UN_MOIS = 30 * 24 * 3600


def chemin_court(chemin: str) -> str:
    maison = os.path.expanduser("~")
    if chemin == maison or chemin.startswith(maison + os.sep):
        return "~" + chemin[len(maison):]
    return chemin


class Fichiers(Module):
    nom = "fichiers"

    def commandes(self) -> list[Commande]:
        return [
            Commande(id="fichiers.ouvrir", titre="Ouvrir le fichier", action=self._ouvrir, argument="chemin",
                     icone="text-x-generic-symbolic", requiert="chercher_fichiers", cachee=True),
            Commande(id="fichiers.montrer", titre="Afficher dans le dossier", action=self._montrer, argument="chemin",
                     icone="folder-open-symbolic", requiert="afficher_dans_dossier", cachee=True),
        ]

    def _ouvrir(self, contexte, chemin):
        if not chemin or not os.path.lexists(chemin):
            return Reponse.erreur("Ce fichier n'existe plus")
        contexte.plateforme.ouvrir(chemin)
        return Reponse(message=f"{os.path.basename(chemin)} ouvert")

    def _montrer(self, contexte, chemin):
        if not chemin or not os.path.lexists(chemin):
            return Reponse.erreur("Ce fichier n'existe plus")
        contexte.plateforme.afficher_dans_dossier(chemin)
        return Reponse(message="Dossier ouvert")

    def resultats(self, requete: str) -> list[Resultat]:
        requete = requete.strip()
        mots = texte.mots(texte.normaliser(requete))
        if len("".join(mots)) < LONGUEUR_MIN:
            return []
        plateforme = self.contexte.plateforme
        if not plateforme.prend_en_charge("chercher_fichiers"):
            return []
        try:
            trouves = plateforme.chercher_fichiers(mots)
        except NonPrisEnCharge:
            return []
        maintenant = time.time()
        resultats = []
        for f in trouves:
            if IGNORES.intersection(f.chemin.split(os.sep)):
                continue
            nom_seul = os.path.splitext(f.nom)[0] if not f.dossier else f.nom
            pertinence = max(texte.score(requete, f.nom), texte.score(requete, nom_seul), 40.0)
            recent = max(0.0, 1.0 - (maintenant - f.modifie) / UN_MOIS) if f.modifie else 0.0
            # Pertinence sur 100 ; le registre range ensuite les fichiers entre les applications et les fonctions
            score = 0.9 * pertinence + 10.0 * recent
            resultats.append(Resultat(
                commande="fichiers.ouvrir", titre=f.nom, sous_titre=chemin_court(os.path.dirname(f.chemin)),
                icone=f.icone or ("folder-symbolic" if f.dossier else "text-x-generic-symbolic"),
                score=score, argument=f.chemin, section="Fichiers", module="fichiers"))
        resultats.sort(key=lambda r: r.score, reverse=True)
        return resultats[:NB_MAX]
