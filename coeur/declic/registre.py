"""Le registre : rassemble les commandes de tous les modules, cherche et exécute."""
from __future__ import annotations

import logging
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
        plateforme = self.contexte.plateforme
        if plateforme.prend_en_charge("surveiller"):
            try:
                plateforme.surveiller(lambda evenement, valeur=None: self.declencher(evenement, valeur))
            except Exception:
                journal.exception("Écoute des événements du système impossible")
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
    def rechercher(self, requete: str, limite: int = 20, page: Optional[str] = None) -> list[Resultat]:
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
            if base >= SEUIL:
                resultats.append(self._resultat(commande, base * self.historique.bonus(commande.id)))

        for module in self.modules:
            try:
                for r in module.resultats(requete):
                    cible = commandes.get(r.commande)
                    if cible is None:
                        continue
                    r.confirmer = r.confirmer or cible.confirmer
                    r.module = r.module or cible.module
                    resultats.append(r)
            except Exception:
                journal.exception("Module %s : recherche impossible", module.nom)

        for r in resultats:
            if r.score >= SCORE_SECOURS and cle_favori(r.commande, r.argument) in cles_favoris:
                r.favori = True
                r.score *= 1.15
        resultats.sort(key=lambda r: r.score, reverse=True)
        # Les propositions de dernier recours (recherche web, questions aux IA) restent toujours en bas de liste
        secours = [r for r in resultats if r.score < SCORE_SECOURS]
        return [r for r in resultats if r.score >= SCORE_SECOURS][:max(limite - len(secours), 0)] + secours

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
