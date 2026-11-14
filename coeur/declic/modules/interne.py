"""Commandes de Déclic lui-même."""
from __future__ import annotations

from declic import __version__
from declic.modele import Commande, Reponse
from declic.modules import Module


class Interne(Module):
    nom = "declic"

    def __init__(self, contexte, registre=None):
        super().__init__(contexte)
        self.registre = registre  # renseigné par le registre

    def _recharger(self, contexte, _argument):
        if self.registre is not None:
            self.registre.recharger()
        return Reponse(message="Configuration rechargée")

    def _config(self, contexte, _argument):
        contexte.plateforme.ouvrir(str(contexte.chemins.config))
        return Reponse(message="Dossier de configuration ouvert")

    def _scripts(self, contexte, _argument):
        contexte.chemins.scripts.mkdir(parents=True, exist_ok=True)
        contexte.plateforme.ouvrir(str(contexte.chemins.scripts))
        return Reponse(message="Dossier des scripts ouvert")

    def _effacer_suggestions(self, contexte, _argument):
        if self.registre is not None:
            self.registre.historique.effacer()
        return Reponse(message="Suggestions effacées", fermer=False)

    def _a_propos(self, contexte, _argument):
        return Reponse(message=f"Déclic {__version__} sur {contexte.plateforme.nom}", fermer=False)

    def commandes(self) -> list[Commande]:
        return [
            Commande("declic.recharger", "Recharger la configuration de Déclic", self._recharger,
                     icone="view-refresh-symbolic", mots_cles=("declic", "reload")),
            Commande("declic.config", "Ouvrir les réglages de Déclic", self._config, requiert="ouvrir",
                     icone="preferences-system-symbolic", mots_cles=("declic", "configuration")),
            Commande("declic.scripts", "Ouvrir le dossier des scripts", self._scripts, requiert="ouvrir",
                     icone="folder-symbolic", mots_cles=("declic", "script")),
            Commande("declic.effacer-suggestions", "Effacer les suggestions", self._effacer_suggestions,
                     description="Oublie les commandes récentes et fréquentes",
                     icone="edit-clear-all-symbolic", mots_cles=("declic", "historique", "clear", "nettoyer")),
            Commande("declic.a-propos", "À propos de Déclic", self._a_propos,
                     icone="help-about-symbolic", mots_cles=("declic", "version")),
        ]
