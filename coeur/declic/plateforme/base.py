"""Interface commune à toutes les plateformes (Linux, Windows…).

Chaque méthode non redéfinie par une plateforme est considérée comme « non prise en charge » :
les commandes qui en dépendent (champ `requiert`) sont alors masquées automatiquement.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class NonPrisEnCharge(RuntimeError):
    pass


@dataclass
class Application:
    id: str  # identifiant propre à la plateforme (fichier .desktop, raccourci…)
    nom: str
    description: str = ""
    icone: str = ""
    mots_cles: tuple[str, ...] = field(default_factory=tuple)


class Plateforme:
    nom = "inconnue"

    def prend_en_charge(self, methode: str) -> bool:
        implementation = getattr(type(self), methode, None)
        return implementation is not None and implementation is not getattr(Plateforme, methode, None)

    def _absent(self, quoi: str):
        raise NonPrisEnCharge(f"« {quoi} » n'est pas encore disponible sur {self.nom}.")

    # --- Applications et ouverture -------------------------------------------------
    def lister_applications(self) -> list[Application]:
        self._absent("lister les applications")

    def lancer_application(self, app_id: str) -> None:
        self._absent("lancer une application")

    def ouvrir(self, cible: str) -> None:
        """Ouvre une URL ou un chemin avec l'application par défaut."""
        self._absent("ouvrir")

    # --- Presse-papiers et notifications -------------------------------------------
    def copier_texte(self, texte: str) -> None:
        self._absent("copier dans le presse-papiers")

    def notifier(self, titre: str, message: str = "") -> None:
        self._absent("notifier")

    # --- Session et alimentation ---------------------------------------------------
    def verrouiller(self) -> None:
        self._absent("verrouiller")

    def veille(self) -> None:
        self._absent("mettre en veille")

    def redemarrer(self) -> None:
        self._absent("redémarrer")

    def eteindre(self) -> None:
        self._absent("éteindre")

    def deconnecter(self) -> None:
        self._absent("se déconnecter")

    def definir_profil_energie(self, profil: str) -> None:
        """profil : economie | equilibre | performance"""
        self._absent("changer le profil d'énergie")

    # --- Fichiers ------------------------------------------------------------------
    def vider_corbeille(self) -> None:
        self._absent("vider la corbeille")

    def ouvrir_corbeille(self) -> None:
        self._absent("ouvrir la corbeille")

    # --- Bascules (renvoient le nouvel état : True = activé) -----------------------
    def basculer_theme_sombre(self) -> bool:
        self._absent("basculer le thème sombre")

    def basculer_eclairage_nocturne(self) -> bool:
        self._absent("basculer l'éclairage nocturne")

    def basculer_ne_pas_deranger(self) -> bool:
        self._absent("basculer « Ne pas déranger »")

    def basculer_fichiers_caches(self) -> bool:
        self._absent("afficher les fichiers cachés")

    def basculer_wifi(self) -> bool:
        self._absent("basculer le Wi-Fi")

    def basculer_bluetooth(self) -> bool:
        self._absent("basculer le Bluetooth")

    def basculer_mode_avion(self) -> bool:
        self._absent("basculer le mode avion")

    # --- Réseau --------------------------------------------------------------------
    def reseaux_wifi_connus(self) -> list[str]:
        """Noms des Wi-Fi enregistrés sur la machine (pour choisir un déclencheur)."""
        self._absent("lister les Wi-Fi connus")

    # --- Coffre à identifiants (trousseau du système, jamais un fichier en clair) ------
    # Un identifiant = un site (clé) + attributs publics (nom, adresse, identifiant, titre) + mot de passe.
    def coffre_enregistrer(self, site: str, attributs: dict[str, str], mot_de_passe: str) -> None:
        self._absent("enregistrer un mot de passe")

    def coffre_lister(self) -> list[dict[str, str]]:
        """Attributs publics de chaque identifiant (avec la clé « site »), sans les mots de passe."""
        self._absent("lister les identifiants")

    def coffre_supprimer(self, site: str) -> bool:
        self._absent("supprimer un identifiant")

    def saisir_identifiant(self, site: str, delai_s: int) -> None:
        """Demande à l'interface de taper identifiant + mot de passe dans la page de connexion, si
        (et seulement si) la fenêtre active est un navigateur affichant une adresse du site enregistré."""
        self._absent("saisir un identifiant")

    def adresse_page(self, pid: int) -> str | None:
        """Adresse de l'onglet affiché dans la fenêtre active du navigateur de ce processus.
        None si le navigateur ne l'expose pas (accessibilité désactivée)."""
        self._absent("lire l'adresse de la page")

    # --- Événements (déclencheurs des automatisations) -------------------------------
    def surveiller(self, rappel) -> None:
        """Écoute les événements du système et appelle rappel(evenement, valeur) pour chacun.
        Voir declic.modules.automatisations.EVENEMENTS pour les noms."""
        self._absent("surveiller les événements")

    # --- Son et média ----------------------------------------------------------------
    def lire_volume(self) -> tuple[int, bool]:
        """(volume en %, muet)"""
        self._absent("lire le volume")

    def definir_volume(self, pourcent: int) -> None:
        self._absent("régler le volume")

    def changer_volume(self, delta: int) -> None:
        self._absent("changer le volume")

    def basculer_muet(self) -> bool:
        self._absent("couper le son")

    def basculer_micro_muet(self) -> bool:
        self._absent("couper le micro")

    def media(self, commande: str) -> str:
        """commande : lecture-pause | suivant | precedent. Renvoie le nom du lecteur piloté."""
        self._absent("piloter la musique")
