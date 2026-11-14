"""Liens rapides (« quicklinks ») et recherche web.

On tape le mot-clé suivi de la recherche : « scholar céramique sigillée », « wiki Gergovie ».
Liens personnels dans ~/.config/declic/liens.toml :

    [[lien]]
    nom = "Persée"
    mot_cle = "persee"
    url = "https://www.persee.fr/search?q={requete}"
"""
from __future__ import annotations

import re
import tomllib
import urllib.parse
from dataclasses import dataclass

from declic.modele import Champ, Commande, Creation, CreationRefusee, Element, Reponse, Resultat
from declic import fichiers_toml, texte
from declic.modules import Module


@dataclass(frozen=True)
class Lien:
    nom: str
    mot_cle: str
    url: str  # « {requete} » est remplacé par la recherche encodée

    @property
    def accueil(self) -> str:
        p = urllib.parse.urlsplit(self.url.replace("{requete}", ""))
        return f"{p.scheme}://{p.netloc}/"

    def pour(self, requete: str) -> str:
        return self.url.replace("{requete}", urllib.parse.quote_plus(requete.strip()))


LIENS_PAR_DEFAUT = (
    Lien("Google", "g", "https://www.google.com/search?q={requete}"),
    Lien("DuckDuckGo", "ddg", "https://duckduckgo.com/?q={requete}"),
    Lien("Wikipédia", "wiki", "https://fr.wikipedia.org/w/index.php?search={requete}"),
    Lien("Google Scholar", "scholar", "https://scholar.google.com/scholar?q={requete}"),
    Lien("Persée", "persee", "https://www.persee.fr/search?q={requete}"),
    Lien("Cairn", "cairn", "https://shs.cairn.info/resultats_recherche?searchTerm={requete}"),
    Lien("OpenEdition", "openedition", "https://search.openedition.org/results?q={requete}"),
    Lien("HAL", "hal", "https://hal.science/search/index/?q={requete}"),
    Lien("Gallica", "gallica", "https://gallica.bnf.fr/services/engine/search/sru?query=gallica%20all%20%22{requete}%22"),
    Lien("Wiktionnaire", "dico", "https://fr.wiktionary.org/w/index.php?search={requete}"),
    Lien("OpenStreetMap", "carte", "https://www.openstreetmap.org/search?query={requete}"),
)


# Pour ajouter un site sans connaître « {requete} » : on y cherche ce mot, puis on colle l'adresse obtenue.
MOT_TEMOIN = "declic"

ENTETE = """# Liens de recherche personnels de Déclic.
# Dans la barre : le mot-clé puis la recherche (ex. « persee céramique »).
# Dans l'adresse, {requete} est remplacé par ce que vous cherchez.
# Vous pouvez aussi les ajouter depuis la barre : bouton + en haut à droite.
"""


class Liens(Module):
    nom = "liens"

    def __init__(self, contexte):
        super().__init__(contexte)
        self.liens: list[Lien] = []
        self.perso: dict[str, Lien] = {}  # liens du fichier de l'utilisateur, par mot-clé
        self.recharger()

    def recharger(self) -> None:
        liens = {l.mot_cle: l for l in LIENS_PAR_DEFAUT}
        self.perso = {}
        fichier = self.contexte.chemins.liens
        if fichier.exists():
            with fichier.open("rb") as f:
                donnees = tomllib.load(f)
            for entree in donnees.get("lien", []):
                try:
                    lien = Lien(str(entree["nom"]), str(entree["mot_cle"]).casefold(), str(entree["url"]))
                except KeyError:
                    continue
                liens[lien.mot_cle] = lien
                self.perso[lien.mot_cle] = lien
        self.liens = list(liens.values())

    # --- Ajout depuis la barre ------------------------------------------------------------
    def creations(self) -> list[Creation]:
        return [Creation(
            type="lien", titre="Lien de recherche", icone="web-browser-symbolic",
            description="Un site où chercher avec un mot-clé, comme « persee céramique ».",
            champs=(
                Champ("nom", "Nom", exemple="Inrap"),
                Champ("mot_cle", "Mot-clé", exemple="inrap",
                      aide="Un seul mot, à taper avant la recherche."),
                Champ("adresse", "Adresse de recherche",
                      exemple="https://www.inrap.fr/recherche?search_api_fulltext=declic",
                      aide=f"Cherchez « {MOT_TEMOIN} » sur le site, puis collez ici l'adresse de la page de résultats."),
            ),
            creer=self._creer, titre_pluriel="Liens de recherche",
            lister=self._lister, supprimer=self._supprimer,
        )]

    def _lister(self) -> list[Element]:
        return [Element(cle=l.mot_cle, titre=l.nom, sous_titre=f"{l.mot_cle} · {l.url}", remplir=f"{l.mot_cle} ")
                for l in sorted(self.perso.values(), key=lambda l: l.nom.casefold())]

    def _supprimer(self, cle: str) -> Reponse:
        lien = self.perso.get(cle)
        if lien is None:
            raise CreationRefusee(f"Aucun lien perso avec le mot-clé « {cle} ».")
        fichiers_toml.retirer_bloc(self.contexte.chemins.liens, "lien",
                                   lambda e: str(e.get("mot_cle", "")).casefold() != cle)
        self.recharger()
        defaut = next((l.nom for l in LIENS_PAR_DEFAUT if l.mot_cle == cle), None)
        suite = f" ; « {cle} » renvoie de nouveau vers {defaut}" if defaut else ""
        return Reponse(message=f"« {lien.nom} » supprimé{suite}", fermer=False)

    def _creer(self, valeurs: dict) -> Reponse:
        nom = valeurs.get("nom", "").strip()
        mot_cle = valeurs.get("mot_cle", "").strip().casefold()
        adresse = valeurs.get("adresse", "").strip()
        if not nom:
            raise CreationRefusee("Donnez un nom au lien.", "nom")
        if not mot_cle:
            raise CreationRefusee("Choisissez un mot-clé.", "mot_cle")
        if any(c.isspace() for c in mot_cle):
            raise CreationRefusee("Le mot-clé doit être un seul mot, sans espace.", "mot_cle")
        if mot_cle in self.perso:
            raise CreationRefusee(f"Le mot-clé « {mot_cle} » est déjà pris par « {self.perso[mot_cle].nom} ».", "mot_cle")
        if not adresse:
            raise CreationRefusee("Collez l'adresse d'une page de résultats du site.", "adresse")
        if not adresse.startswith(("http://", "https://")):
            if " " in adresse or "." not in adresse:
                raise CreationRefusee("L'adresse doit commencer par https://", "adresse")
            adresse = "https://" + adresse
        if "{requete}" not in adresse:
            temoin = re.compile(re.escape(MOT_TEMOIN), re.IGNORECASE)
            if not temoin.search(adresse):
                raise CreationRefusee(
                    f"Je ne vois pas où placer la recherche : cherchez « {MOT_TEMOIN} » sur le site "
                    "et collez l'adresse de la page de résultats (ou écrivez {requete} à la place du mot cherché).",
                    "adresse")
            adresse = temoin.sub("{requete}", adresse)
        remplace = next((l.nom for l in LIENS_PAR_DEFAUT if l.mot_cle == mot_cle), None)
        fichiers_toml.ajouter_bloc(self.contexte.chemins.liens, "lien",
                                   {"nom": nom, "mot_cle": mot_cle, "url": adresse}, entete=ENTETE)
        self.recharger()
        message = f"« {nom} » ajouté : tapez « {mot_cle} » puis votre recherche"
        if remplace:
            message += f" (remplace {remplace})"
        return Reponse(message=message, fermer=False, remplir=f"{mot_cle} ")

    def _ouvrir(self, contexte, argument):
        if not argument:
            return Reponse.erreur("Adresse manquante.")
        contexte.plateforme.ouvrir(argument)
        return Reponse(message="Ouvert dans le navigateur")

    def commandes(self) -> list[Commande]:
        commandes = [Commande(id="liens.ouvrir", titre="Ouvrir une adresse", action=self._ouvrir,
                              argument="adresse", requiert="ouvrir", cachee=True)]
        for lien in self.liens:
            commandes.append(Commande(
                id=f"liens.{lien.mot_cle}", titre=f"Rechercher sur {lien.nom}",
                description=f"Mot-clé : « {lien.mot_cle} »", icone="web-browser-symbolic",
                mots_cles=(lien.mot_cle, lien.nom), argument="recherche", requiert="ouvrir",
                action=self._action_lien(lien),
            ))
        return commandes

    def _action_lien(self, lien: Lien):
        def action(contexte, argument):
            contexte.plateforme.ouvrir(lien.pour(argument) if argument else lien.accueil)
            return Reponse(message=f"{lien.nom} ouvert")
        return action

    def resultats(self, requete: str) -> list[Resultat]:
        requete = requete.strip()
        if not requete:
            return []
        resultats = []
        mot, _, reste = requete.partition(" ")
        for lien in self.liens:
            if reste.strip() and texte.normaliser(mot) == texte.normaliser(lien.mot_cle):
                resultats.append(Resultat(
                    commande=f"liens.{lien.mot_cle}", titre=f"{lien.nom} : « {reste.strip()} »",
                    sous_titre=lien.pour(reste), icone="web-browser-symbolic", score=98.0, argument=reste.strip(),
                ))
        if requete.startswith(("http://", "https://")) or (
            "." in requete and " " not in requete and not requete[0].isdigit() and "/" in requete
        ):
            adresse = requete if "://" in requete else f"https://{requete}"
            resultats.append(Resultat(commande="liens.ouvrir", titre=f"Ouvrir {adresse}",
                                      icone="web-browser-symbolic", score=97.0, argument=adresse))
        # Toujours possible en dernier recours : chercher sur le web
        resultats.append(Resultat(
            commande="liens.g", titre=f"Rechercher « {requete} » sur le web", sous_titre="Google",
            icone="system-search-symbolic", score=1.0, argument=requete,
        ))
        return resultats
