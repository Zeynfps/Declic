"""Le registre : rassemble les commandes de tous les modules, cherche et exécute."""
from __future__ import annotations

import logging
import os
import threading
from typing import Iterable, Optional

from declic import texte
from declic.chemins import Chemins
from declic.contexte import Contexte
from declic.historique import Historique
from declic.modele import Commande, Creation, CreationRefusee, Element, Reponse, Resultat
from declic.modules import Module, tous_les_modules
from declic.modules.automatisations import Automatisations
from declic.modules.favoris import Favoris, cle_favori
from declic.modules.interne import Interne
from declic.plateforme.base import NonPrisEnCharge, Plateforme

# Commandes qu'on ne note pas dans l'historique (sinon « effacer » se suggérerait lui-même)
SANS_HISTORIQUE = {"declic.effacer-suggestions", "favoris.basculer"}

journal = logging.getLogger("declic")

SCORE_SECOURS = 2.0  # en dessous : proposition de dernier recours (recherche web, IA)
SEUIL = 40.0  # score minimal pour apparaître (sur 100) : écarte les correspondances trop lâches
NIVEAU = 1000.0  # écart entre deux niveaux de la hiérarchie (applications > fichiers > fonctions)
SEUIL_APPLI = 50.0  # une appli trouvée seulement par quelques lettres éparses descend parmi les fonctions
SCORE_DIRECT = 95.0  # résultats de mots-clés explicites (« persee … », « gpt … », calcul) : toujours en tête
SECTIONS = {1: "Fonctionnalités", 2: "Fichiers", 3: "Applications"}
# Modules qui gardent leur propre section, en tête quand on les appelle par leur mot-clé (« pp »)
SECTIONS_PROPRES = {"pp": "Presse-papiers"}


class Registre:
    def __init__(self, plateforme: Plateforme, chemins: Chemins, modules: Optional[Iterable[Module]] = None):
        self.contexte = Contexte(plateforme=plateforme, chemins=chemins.creer())
        self.historique = Historique(chemins.historique)
        self.modules = list(modules) if modules is not None else tous_les_modules(self.contexte)
        for module in self.modules:
            if isinstance(module, (Interne, Automatisations)):
                module.registre = self
        self._verrou = threading.Lock()

    # --- Commandes ------------------------------------------------------------------
    def _disponible(self, commande: Commande) -> bool:
        return commande.requiert is None or self.contexte.plateforme.prend_en_charge(commande.requiert)

    def commandes(self) -> dict[str, Commande]:
        toutes: dict[str, Commande] = {}
        for module in self.modules:
            try:
                for commande in module.commandes():
                    if self._disponible(commande):
                        toutes.setdefault(commande.id, commande)
            except Exception:  # un module en panne ne doit pas casser la barre
                journal.exception("Module %s : impossible de lister les commandes", module.nom)
        # « Ajouter : Lien de recherche »… : ouvre le formulaire d'ajout dans la barre
        for creation in self.creations():
            if not creation.ajoutable:
                continue
            toutes.setdefault(f"creer.{creation.type}", Commande(
                id=f"creer.{creation.type}", titre=f"Ajouter : {creation.titre}", description=creation.description,
                icone="list-add-symbolic", mots_cles=("ajouter", "créer", "nouveau", creation.titre),
                action=lambda _c, _a, t=creation.type: Reponse(ouvrir=f"creer:{t}", fermer=False),
            ))
        return toutes

    # --- Automatisations ------------------------------------------------------------------
    @property
    def automatisations(self) -> Optional[Automatisations]:
        return next((m for m in self.modules if isinstance(m, Automatisations)), None)

    def declencher(self, evenement: str, valeur: Optional[str] = None, source: str = "") -> list[str]:
        """Un événement est arrivé (système, téléphone…) : lance les règles qui l'attendent."""
        auto = self.automatisations
        return auto.declencher(evenement, valeur, source) if auto else []

    def verifier_page(self, site: str, pid: int) -> dict:
        module = next((m for m in self.modules if m.nom == "identifiants"), None)
        return module.verifier(site, pid) if module else {"ok": False, "raison": "module absent"}

    def demarrer_automatisations(self) -> None:
        """Horloge des règles + écoute des événements de la plateforme (dans le service seulement)."""
        auto = self.automatisations
        if auto is None:
            return
        auto.demarrer()
        for module in self.modules:  # modules qui écoutent quelque chose dans le service (presse-papiers…)
            if hasattr(module, "demarrer") and module is not auto:
                try:
                    module.demarrer()
                except Exception:
                    journal.exception("Module %s : démarrage impossible", module.nom)
        plateforme = self.contexte.plateforme
        if plateforme.prend_en_charge("surveiller"):
            try:
                plateforme.surveiller(lambda evenement, valeur=None: self.declencher(evenement, valeur))
            except Exception:
                journal.exception("Écoute des événements du système impossible")
        self.contexte.etats.prechauffer({c.bascule for c in self.commandes().values() if c.bascule})
        self.declencher("declic.demarrage", source="démarrage")

    # --- Création d'éléments ------------------------------------------------------------
    def creations(self) -> list[Creation]:
        liste: list[Creation] = []
        for module in self.modules:
            try:
                liste.extend(module.creations())
            except Exception:
                journal.exception("Module %s : impossible de lister les créations", module.nom)
        return liste

    def creer(self, type_: str, valeurs: dict[str, str]) -> dict:
        creation = next((c for c in self.creations() if c.type == type_), None)
        if creation is None:
            return {**Reponse.erreur(f"On ne sait pas créer « {type_} »").en_dict(), "champ": None}
        try:
            with self._verrou:
                reponse = creation.creer(valeurs)
        except CreationRefusee as exc:
            return {**Reponse.erreur(str(exc)).en_dict(), "champ": exc.champ}
        except Exception as exc:
            journal.exception("Création %s impossible", type_)
            return {**Reponse.erreur(f"Enregistrement impossible : {exc}").en_dict(), "champ": None}
        return {**reponse.en_dict(), "champ": None}

    def elements(self, type_: str) -> list[Element]:
        creation = next((c for c in self.creations() if c.type == type_), None)
        if creation is None or creation.lister is None:
            return []
        with self._verrou:
            return creation.lister()

    def supprimer(self, type_: str, cle: str) -> dict:
        creation = next((c for c in self.creations() if c.type == type_), None)
        if creation is None or creation.supprimer is None:
            return Reponse.erreur(f"On ne sait pas supprimer « {type_} »").en_dict()
        try:
            with self._verrou:
                return creation.supprimer(cle).en_dict()
        except CreationRefusee as exc:
            return Reponse.erreur(str(exc)).en_dict()
        except Exception as exc:
            journal.exception("Suppression %s/%s impossible", type_, cle)
            return Reponse.erreur(f"Suppression impossible : {exc}").en_dict()

    def recharger(self) -> None:
        with self._verrou:
            for module in self.modules:
                try:
                    module.recharger()
                except Exception:
                    journal.exception("Module %s : rechargement impossible", module.nom)

    # --- Recherche --------------------------------------------------------------------
    def rechercher(self, requete: str, limite: int = 20, page: Optional[str] = None,
                   selection: Optional[str] = None) -> list[Resultat]:
        if selection and selection.strip():
            return self.agir_sur_selection(selection, requete, limite)
        resultats = self._rechercher(requete, limite, page)
        commandes = self.commandes()
        for r in resultats:  # Bluetooth, Wi-Fi… : activé ou désactivé, pour l'indicateur de la barre
            commande = commandes.get(r.commande)
            if commande is not None and commande.bascule and r.argument is None:
                r.etat = self.contexte.etats.lire(commande.bascule)
        return resultats

    def agir_sur_selection(self, selection: str, requete: str, limite: int = 20) -> list[Resultat]:
        """Texte sélectionné ailleurs : les actions des modules (IA…), puis la recherche web sur ce texte."""
        commandes = self.commandes()
        resultats: list[Resultat] = []
        for module in self.modules:
            try:
                resultats.extend(r for r in module.pour_selection(selection, requete) if r.commande in commandes)
            except Exception:
                journal.exception("Module %s : actions sur la sélection impossibles", module.nom)
        if "liens.g" in commandes and not requete.strip():
            resultats.append(Resultat(commande="liens.g", titre="Rechercher sur le web", argument=selection.strip()[:300],
                                      icone="web-browser-symbolic", score=1.0, section="Texte sélectionné",
                                      module="liens"))
        for r in resultats:
            r.module = r.module or r.commande.split(".", 1)[0]
            r.confirmer = r.confirmer or commandes[r.commande].confirmer
        resultats.sort(key=lambda r: r.score, reverse=True)
        return resultats[:limite]

    def _rechercher(self, requete: str, limite: int = 20, page: Optional[str] = None) -> list[Resultat]:
        requete = requete.strip()
        commandes = self.commandes()
        resultats: list[Resultat] = []
        if page:
            for module in self.modules:
                try:
                    resultats.extend(module.suggestions(page, requete))
                except Exception:
                    journal.exception("Module %s : suggestions impossibles", module.nom)

        favoris = self._favoris
        cles_favoris = favoris.cles() if favoris else set()
        if not requete:
            # Barre vide : les favoris (dans leur ordre), puis les commandes les plus utilisées
            suggestions = []
            for commande in commandes.values():
                if commande.cachee or commande.id in cles_favoris:
                    continue
                bonus = self.historique.bonus(commande.id)
                if bonus > 1.0:
                    suggestions.append(self._resultat(commande, 50.0 * bonus))
            suggestions.sort(key=lambda r: r.score, reverse=True)
            return (resultats + self._resultats_favoris(commandes) + suggestions)[:limite]

        for commande in commandes.values():
            if commande.cachee:
                continue
            base = max(
                texte.score(requete, commande.titre),
                0.9 * texte.meilleur_score(requete, commande.mots_cles),
            )
            presque = texte.presque_identique(requete, (commande.titre,)) or \
                texte.compacter(requete) in {texte.compacter(m) for m in commande.mots_cles if m}
            if base >= SEUIL or presque:
                r = self._resultat(commande, max(base, 90.0 if presque else 0.0) * self.historique.bonus(commande.id))
                r.presque = presque
                resultats.append(r)

        for module in self.modules:
            try:
                for r in module.resultats(requete):
                    cible = commandes.get(r.commande)
                    if cible is None:
                        continue
                    r.confirmer = r.confirmer or cible.confirmer
                    r.module = r.module or cible.module
                    if r.module == "fichiers":
                        r.presque = texte.presque_identique(requete, (r.titre, os.path.splitext(r.titre)[0]))
                    resultats.append(r)
            except Exception:
                journal.exception("Module %s : recherche impossible", module.nom)

        for r in resultats:
            if r.score >= SCORE_SECOURS and cle_favori(r.commande, r.argument) in cles_favoris:
                r.favori = True
                r.score *= 1.15
            if r.score >= SCORE_SECOURS:
                self._ranger(r)
        resultats.sort(key=lambda r: r.score, reverse=True)
        # Un module appelé par son mot-clé (« pp … ») prend toute la liste
        for module in self.modules:
            if getattr(module, "exclusif", None) and module.exclusif(requete):
                return [r for r in resultats if r.module == module.nom][:limite]
        # Les propositions de dernier recours (recherche web, questions aux IA) restent toujours en bas de liste
        secours = [r for r in resultats if r.score < SCORE_SECOURS]
        return [r for r in resultats if r.score >= SCORE_SECOURS][:max(limite - len(secours), 0)] + secours

    @staticmethod
    def _ranger(r: Resultat) -> None:
        """Hiérarchie de la recherche : applications, puis fichiers, puis fonctions.

        Le score de pertinence (0–100, ×bonus d'usage) devient un score à l'intérieur de son niveau.
        Elle saute quand le texte tapé est (presque) exactement le nom : la ligne passe tout en haut,
        et les mots-clés explicites (« persee … », « gpt … », calcul, « vol 30 »…) y sont aussi.
        """
        pertinence = min(r.score, NIVEAU - 1)
        if r.module == "app":
            niveau, rang = (3, 3) if pertinence >= SEUIL_APPLI else (1, 3)
        elif r.module == "fichiers":
            niveau, rang = 2, 2
        else:
            niveau, rang = 1, 1
            if pertinence >= SCORE_DIRECT and not r.presque:  # mot-clé explicite, calcul…
                r.presque = True
        if r.presque:
            niveau = 4
            r.section = "Calculatrice" if r.module == "calcul" else "Meilleur résultat"
            pertinence += rang  # à égalité parfaite : application, puis fichier, puis fonction
        else:
            r.section = SECTIONS[niveau]
        r.section = SECTIONS_PROPRES.get(r.module, r.section)
        r.score = niveau * NIVEAU + pertinence

    @property
    def _favoris(self) -> Optional[Favoris]:
        return next((m for m in self.modules if isinstance(m, Favoris)), None)

    def _resultats_favoris(self, commandes: dict[str, Commande]) -> list[Resultat]:
        favoris = self._favoris
        if favoris is None:
            return []
        liste = []
        for i, favori in enumerate(favoris.liste):
            commande = commandes.get(favori.commande)
            if commande is None:  # appli désinstallée, lien supprimé… : on le garde dans le fichier, sans l'afficher
                continue
            score = 1000.0 - i
            if favori.argument is None:
                r = self._resultat(commande, score)
            else:
                r = Resultat(commande=commande.id, titre=favori.titre, sous_titre=commande.titre,
                             icone=favori.icone or commande.icone, score=score, argument=favori.argument,
                             confirmer=commande.confirmer, module=commande.module)
            r.section, r.favori = "Favoris", True
            liste.append(r)
        return liste

    @staticmethod
    def _resultat(commande: Commande, score: float) -> Resultat:
        return Resultat(
            commande=commande.id, titre=commande.titre, sous_titre=commande.description, icone=commande.icone,
            score=score, confirmer=commande.confirmer, attend_argument=commande.argument, module=commande.module,
        )

    # --- Exécution --------------------------------------------------------------------
    def executer(self, commande_id: str, argument: Optional[str] = None) -> Reponse:
        commande = self.commandes().get(commande_id)
        if commande is None:
            return Reponse.erreur(f"Commande inconnue : {commande_id}")
        try:
            reponse = commande.action(self.contexte, argument)
        except NonPrisEnCharge as exc:
            return Reponse.erreur(str(exc))
        except Exception as exc:
            journal.exception("Échec de %s", commande_id)
            return Reponse.erreur(f"« {commande.titre} » a échoué : {exc}")
        if reponse.statut == "ok" and commande_id not in SANS_HISTORIQUE:
            self.historique.noter(commande_id)
        return reponse
