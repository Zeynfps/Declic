"""Snippets : textes réutilisables, copiés dans le presse-papiers.

Fichier ~/.config/declic/snippets.toml :

    [[snippet]]
    nom = "Adresse"
    mot_cle = "adr"
    texte = "12 rue des Fouilles, 63000 Clermont-Ferrand"

Variables remplacées au moment de copier : {date}, {heure}, {jour}, {annee}.
"""
from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass

from declic.modele import Champ, Commande, Creation, CreationRefusee, Element, Reponse, Resultat
from declic import fichiers_toml, texte
from declic.modules import Module

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

MODELE = """# Snippets de Déclic : textes à copier rapidement.
# Tapez le mot-clé dans la barre (ex. « adr »), puis Entrée : le texte est copié.
# Variables : {date} {heure} {jour} {annee}

[[snippet]]
nom = "Date du jour"
mot_cle = "date"
texte = "{jour} {date}"
"""


@dataclass(frozen=True)
class Snippet:
    nom: str
    mot_cle: str
    texte: str


def remplir(modele: str, maintenant: dt.datetime | None = None) -> str:
    maintenant = maintenant or dt.datetime.now()
    valeurs = {
        "date": maintenant.strftime("%d/%m/%Y"),
        "heure": maintenant.strftime("%H:%M"),
        "jour": _JOURS[maintenant.weekday()],
        "annee": str(maintenant.year),
    }
    for cle, valeur in valeurs.items():
        modele = modele.replace("{" + cle + "}", valeur)
    return modele


class Snippets(Module):
    nom = "snippets"

    def __init__(self, contexte):
        super().__init__(contexte)
        self.snippets: list[Snippet] = []
        self.recharger()

    def recharger(self) -> None:
        fichier = self.contexte.chemins.snippets
        if not fichier.exists():
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_text(MODELE, encoding="utf-8")
        with fichier.open("rb") as f:
            donnees = tomllib.load(f)
        self.snippets = [
            Snippet(str(s["nom"]), str(s.get("mot_cle", "")), str(s["texte"]))
            for s in donnees.get("snippet", []) if "nom" in s and "texte" in s
        ]

    @staticmethod
    def _id(s: Snippet) -> str:
        return f"snippets.{texte.normaliser(s.mot_cle or s.nom).replace(' ', '-')}"

    def creations(self) -> list[Creation]:
        return [Creation(
            type="snippet", titre="Snippet", icone="edit-paste-symbolic",
            description="Un texte à copier en tapant son nom ou son mot-clé.",
            champs=(
                Champ("nom", "Nom", exemple="Adresse du labo"),
                Champ("mot_cle", "Mot-clé", exemple="labo", obligatoire=False,
                      aide="Facultatif : un mot court pour le retrouver tout de suite."),
                Champ("texte", "Texte", exemple="12 rue des Fouilles, 63000 Clermont-Ferrand", multiligne=True,
                      aide="Variables : {date} {heure} {jour} {annee}. Maj+Entrée pour aller à la ligne."),
            ),
            creer=self._creer, titre_pluriel="Snippets",
            lister=self._lister, supprimer=self._supprimer,
        )]

    def _lister(self) -> list[Element]:
        return [Element(cle=self._id(s), titre=s.nom,
                        sous_titre=(f"{s.mot_cle} · " if s.mot_cle else "") + s.texte.replace("\n", " ⏎ ")[:70],
                        remplir=s.mot_cle or s.nom)
                for s in self.snippets]

    def _supprimer(self, cle: str) -> Reponse:
        snippet = next((s for s in self.snippets if self._id(s) == cle), None)
        if snippet is None:
            raise CreationRefusee("Ce snippet n'existe plus.")
        retires = fichiers_toml.retirer_bloc(
            self.contexte.chemins.snippets, "snippet",
            lambda e: self._id(Snippet(str(e.get("nom", "")), str(e.get("mot_cle", "")), "")) != cle)
        self.recharger()
        if not retires:
            raise CreationRefusee("Ce snippet n'a pas été trouvé dans snippets.toml.")
        return Reponse(message=f"Snippet « {snippet.nom} » supprimé", fermer=False)

    def _creer(self, valeurs: dict) -> Reponse:
        nom = valeurs.get("nom", "").strip()
        mot_cle = valeurs.get("mot_cle", "").strip()
        contenu = valeurs.get("texte", "").strip("\n")
        if not nom:
            raise CreationRefusee("Donnez un nom au snippet.", "nom")
        if any(c.isspace() for c in mot_cle):
            raise CreationRefusee("Le mot-clé doit être un seul mot, sans espace.", "mot_cle")
        if not contenu.strip():
            raise CreationRefusee("Écrivez le texte du snippet.", "texte")
        nouveau = Snippet(nom, mot_cle, contenu)
        existant = next((s for s in self.snippets if self._id(s) == self._id(nouveau)), None)
        if existant:
            champ = "mot_cle" if mot_cle else "nom"
            raise CreationRefusee(f"« {existant.nom} » utilise déjà ce {'mot-clé' if mot_cle else 'nom'}.", champ)
        entree = {"nom": nom, "texte": contenu}
        if mot_cle:
            entree = {"nom": nom, "mot_cle": mot_cle, "texte": contenu}
        fichiers_toml.ajouter_bloc(self.contexte.chemins.snippets, "snippet", entree, entete=MODELE)
        self.recharger()
        return Reponse(message=f"Snippet « {nom} » ajouté", fermer=False, remplir=mot_cle or nom)

    def _copier(self, snippet: Snippet):
        def action(contexte, _argument):
            contexte.plateforme.copier_texte(remplir(snippet.texte))
            return Reponse(message=f"« {snippet.nom} » copié : collez avec Ctrl+V")
        return action

    def _editer(self, contexte, _argument):
        contexte.plateforme.ouvrir(str(contexte.chemins.snippets))
        return Reponse(message="Fichier des snippets ouvert")

    def commandes(self) -> list[Commande]:
        commandes = [Commande(
            id="snippets.modifier", titre="Modifier les snippets", description="Ouvre snippets.toml",
            icone="document-edit-symbolic", mots_cles=("snippet", "texte"), action=self._editer, requiert="ouvrir",
        )]
        for s in self.snippets:
            commandes.append(Commande(
                id=f"snippets.{texte.normaliser(s.mot_cle or s.nom).replace(' ', '-')}",
                titre=s.nom, description=remplir(s.texte)[:80], icone="edit-paste-symbolic",
                mots_cles=tuple(x for x in (s.mot_cle, "snippet") if x), action=self._copier(s),
                requiert="copier_texte",
            ))
        return commandes

    def resultats(self, requete: str) -> list[Resultat]:
        q = texte.normaliser(requete)
        return [
            Resultat(commande=f"snippets.{texte.normaliser(s.mot_cle or s.nom).replace(' ', '-')}",
                     titre=s.nom, sous_titre=remplir(s.texte)[:80], icone="edit-paste-symbolic", score=99.0)
            for s in self.snippets if s.mot_cle and q == texte.normaliser(s.mot_cle)
        ]
