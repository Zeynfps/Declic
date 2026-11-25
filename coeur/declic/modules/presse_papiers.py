"""Historique du presse-papiers : retrouver ce qu'on a copié et le recoller.

Dans la barre : « pp » (ou « presse-papiers », « clipboard ») liste les derniers textes copiés, du plus récent
au plus ancien ; « pp mot » filtre. Entrée colle le texte dans l'application d'où l'on vient (ou le copie
seulement, si la plateforme ne sait pas coller).

Les textes arrivent de la plateforme (Windows : surveillance du presse-papiers) ou de la barre (GNOME : l'extension
les envoie à l'API). Ce que les gestionnaires de mots de passe marquent comme secret n'est jamais gardé.
Historique rangé dans le dossier de données de l'utilisateur (presse-papiers.json), effaçable depuis la barre.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading

from declic import texte
from declic.modele import Commande, Reponse, Resultat
from declic.modules import Module

journal = logging.getLogger("declic.presse_papiers")

MAX_ELEMENTS = 200
MAX_CARACTERES = 20_000
AFFICHES = 30
MOTS_CLES = ("pp", "presse-papiers", "presse papiers", "pressepapiers", "clipboard", "copies")


def _il_y_a(date: dt.datetime, maintenant: dt.datetime) -> str:
    secondes = max(0, int((maintenant - date).total_seconds()))
    if secondes < 60:
        return "à l'instant"
    if secondes < 3600:
        return f"il y a {secondes // 60} min"
    if secondes < 86400:
        return f"il y a {secondes // 3600} h"
    return f"le {date:%d/%m}"


class PressePapiers(Module):
    nom = "pp"

    def __init__(self, contexte, horloge=dt.datetime.now):
        super().__init__(contexte)
        self.horloge = horloge
        self._verrou = threading.Lock()
        self.elements: list[dict] = []  # {"texte", "date"} du plus récent au plus ancien
        self._lire()

    @property
    def fichier(self):
        return self.contexte.chemins.donnees / "presse-papiers.json"

    def _lire(self) -> None:
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
            self.elements = [e for e in donnees.get("elements", []) if isinstance(e.get("texte"), str)][:MAX_ELEMENTS]
        except (OSError, ValueError, AttributeError):
            self.elements = []

    def _ecrire(self) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            temporaire = self.fichier.with_suffix(".tmp")
            temporaire.write_text(json.dumps({"elements": self.elements}, ensure_ascii=False), encoding="utf-8")
            temporaire.replace(self.fichier)
        except OSError:
            journal.exception("Historique du presse-papiers non enregistré")

    # --- Arrivée d'un texte copié -----------------------------------------------------
    def ajouter(self, contenu: str) -> bool:
        """Garde un texte copié (en tête ; s'il y était déjà, il remonte). Renvoie False s'il est ignoré."""
        if not isinstance(contenu, str) or not contenu.strip() or len(contenu) > MAX_CARACTERES:
            return False
        with self._verrou:
            if self.elements and self.elements[0]["texte"] == contenu:
                return False
            self.elements = [e for e in self.elements if e["texte"] != contenu]
            self.elements.insert(0, {"texte": contenu, "date": self.horloge().isoformat(timespec="seconds")})
            del self.elements[MAX_ELEMENTS:]
            self._ecrire()
        return True

    def demarrer(self) -> None:
        """Dans le service : écoute le presse-papiers si la plateforme le sait (Windows)."""
        plateforme = self.contexte.plateforme
        if plateforme.prend_en_charge("surveiller_presse_papiers"):
            plateforme.surveiller_presse_papiers(self.ajouter)

    # --- Dans la barre ------------------------------------------------------------------
    def resultats(self, requete: str) -> list[Resultat]:
        mot, _, reste = requete.strip().partition(" ")
        if texte.normaliser(mot) not in MOTS_CLES and texte.normaliser(requete.strip()) not in MOTS_CLES:
            return []
        filtre = texte.normaliser(reste.strip()) if texte.normaliser(mot) in MOTS_CLES else ""
        maintenant = self.horloge()
        resultats = []
        for i, element in enumerate(self.elements):
            contenu = element["texte"]
            if filtre and filtre not in texte.normaliser(contenu):
                continue
            lignes = contenu.strip().splitlines()
            titre = lignes[0].strip()[:90] if lignes else contenu[:90]
            details = [_il_y_a(dt.datetime.fromisoformat(element["date"]), maintenant)]
            if len(lignes) > 1:
                details.append(f"{len(lignes)} lignes")
            elif len(contenu) > 90:
                details.append(f"{len(contenu)} caractères")
            resultats.append(Resultat(
                commande="pp.coller", titre=titre, sous_titre=" · ".join(details), icone="edit-paste-symbolic",
                score=95.0 + (AFFICHES - len(resultats)) * 0.1, argument=contenu, section="Presse-papiers", module="pp"))
            if len(resultats) >= AFFICHES:
                break
        if not resultats:
            vide = "Rien ne correspond" if filtre else "Rien de copié pour l'instant"
            resultats.append(Resultat(commande="pp.historique", titre=vide, icone="edit-paste-symbolic",
                                      score=95.0, section="Presse-papiers", module="pp"))
        return resultats

    def _coller(self, contexte, argument):
        if not argument:
            return Reponse.erreur("Rien à coller")
        self.ajouter(argument)  # remonte en tête de l'historique
        plateforme = contexte.plateforme
        if plateforme.prend_en_charge("coller_texte"):
            plateforme.coller_texte(argument)
            return Reponse(message="Collé")
        plateforme.copier_texte(argument)
        return Reponse(message="Copié : Ctrl+V pour coller")

    def _historique(self, _contexte, _argument):
        return Reponse(remplir="pp ", fermer=False)

    def _effacer(self, _contexte, _argument):
        with self._verrou:
            self.elements = []
            self._ecrire()
        return Reponse(message="Historique du presse-papiers effacé", fermer=False)

    def commandes(self) -> list[Commande]:
        return [
            Commande("pp.historique", "Historique du presse-papiers", self._historique, icone="edit-paste-symbolic",
                     description="Ce que vous avez copié : tapez « pp » puis un mot pour filtrer",
                     mots_cles=("clipboard", "copier", "coller", "copies", "historique")),
            Commande("pp.effacer", "Effacer l'historique du presse-papiers", self._effacer, confirmer=True,
                     icone="edit-clear-symbolic", mots_cles=("clipboard", "vider", "oublier")),
            Commande("pp.coller", "Coller depuis l'historique", self._coller, argument="texte", cachee=True,
                     requiert="copier_texte", icone="edit-paste-symbolic"),
        ]
