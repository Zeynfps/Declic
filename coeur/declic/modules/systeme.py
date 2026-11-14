"""Actions système : session, alimentation, corbeille, bascules d'affichage et de réseau."""
from __future__ import annotations

from declic.modele import Commande, Reponse
from declic.modules import Module


def _simple(methode: str, message: str):
    def action(contexte, _argument):
        getattr(contexte.plateforme, methode)()
        return Reponse(message=message)
    return action


def _bascule(methode: str, actif: str, inactif: str):
    def action(contexte, _argument):
        etat = getattr(contexte.plateforme, methode)()
        return Reponse(message=actif if etat else inactif)
    return action


def _profil(profil: str, message: str):
    def action(contexte, _argument):
        contexte.plateforme.definir_profil_energie(profil)
        return Reponse(message=message)
    return action


class Systeme(Module):
    nom = "systeme"

    def commandes(self) -> list[Commande]:
        C = Commande
        return [
            # Session et alimentation
            C("systeme.verrouiller", "Verrouiller l'écran", _simple("verrouiller", "Écran verrouillé"),
              icone="system-lock-screen-symbolic", mots_cles=("lock", "bloquer"), requiert="verrouiller"),
            C("systeme.veille", "Mettre en veille", _simple("veille", "Mise en veille…"),
              icone="weather-clear-night-symbolic", mots_cles=("sleep", "suspendre"), requiert="veille"),
            C("systeme.redemarrer", "Redémarrer", _simple("redemarrer", "Redémarrage…"), confirmer=True,
              icone="system-reboot-symbolic", mots_cles=("restart", "reboot"), requiert="redemarrer"),
            C("systeme.eteindre", "Éteindre", _simple("eteindre", "Extinction…"), confirmer=True,
              icone="system-shutdown-symbolic", mots_cles=("shutdown", "arrêter"), requiert="eteindre"),
            C("systeme.deconnecter", "Se déconnecter", _simple("deconnecter", "Déconnexion…"), confirmer=True,
              icone="system-log-out-symbolic", mots_cles=("logout", "fermer la session"), requiert="deconnecter"),
            C("systeme.energie-economie", "Profil d'énergie : économie", _profil("economie", "Mode économie d'énergie"),
              icone="power-profile-power-saver-symbolic", mots_cles=("batterie", "power saver"),
              requiert="definir_profil_energie"),
            C("systeme.energie-equilibre", "Profil d'énergie : équilibré", _profil("equilibre", "Mode équilibré"),
              icone="power-profile-balanced-symbolic", mots_cles=("balanced",), requiert="definir_profil_energie"),
            C("systeme.energie-performance", "Profil d'énergie : performance",
              _profil("performance", "Mode performance"), icone="power-profile-performance-symbolic",
              mots_cles=("performance",), requiert="definir_profil_energie"),
            # Fichiers
            C("systeme.vider-corbeille", "Vider la corbeille", _simple("vider_corbeille", "Corbeille vidée"),
              confirmer=True, icone="user-trash-full-symbolic", mots_cles=("trash", "poubelle"),
              requiert="vider_corbeille"),
            C("systeme.ouvrir-corbeille", "Ouvrir la corbeille", _simple("ouvrir_corbeille", "Corbeille ouverte"),
              icone="user-trash-symbolic", mots_cles=("trash", "poubelle"), requiert="ouvrir_corbeille"),
            C("systeme.fichiers-caches", "Afficher ou masquer les fichiers cachés",
              _bascule("basculer_fichiers_caches", "Fichiers cachés affichés", "Fichiers cachés masqués"),
              icone="view-reveal-symbolic", mots_cles=("hidden", "points"), requiert="basculer_fichiers_caches"),
            # Affichage et notifications
            C("systeme.theme-sombre", "Basculer le thème sombre",
              _bascule("basculer_theme_sombre", "Thème sombre", "Thème clair"),
              icone="weather-clear-night-symbolic", mots_cles=("dark mode", "clair", "apparence"),
              requiert="basculer_theme_sombre"),
            C("systeme.eclairage-nocturne", "Basculer l'éclairage nocturne",
              _bascule("basculer_eclairage_nocturne", "Éclairage nocturne activé", "Éclairage nocturne désactivé"),
              icone="night-light-symbolic", mots_cles=("night light", "lumière bleue"),
              requiert="basculer_eclairage_nocturne"),
            C("systeme.ne-pas-deranger", "Basculer « Ne pas déranger »",
              _bascule("basculer_ne_pas_deranger", "Ne pas déranger : activé", "Ne pas déranger : désactivé"),
              icone="notifications-disabled-symbolic", mots_cles=("dnd", "notifications", "silence"),
              requiert="basculer_ne_pas_deranger"),
            # Réseau
            C("systeme.wifi", "Basculer le Wi-Fi", _bascule("basculer_wifi", "Wi-Fi activé", "Wi-Fi désactivé"),
              icone="network-wireless-symbolic", mots_cles=("wifi", "internet", "réseau"), requiert="basculer_wifi"),
            C("systeme.bluetooth", "Basculer le Bluetooth",
              _bascule("basculer_bluetooth", "Bluetooth activé", "Bluetooth désactivé"),
              icone="bluetooth-active-symbolic", mots_cles=("bluetooth",), requiert="basculer_bluetooth"),
            C("systeme.mode-avion", "Basculer le mode avion",
              _bascule("basculer_mode_avion", "Mode avion activé", "Mode avion désactivé"),
              icone="airplane-mode-symbolic", mots_cles=("airplane", "avion"), requiert="basculer_mode_avion"),
        ]
