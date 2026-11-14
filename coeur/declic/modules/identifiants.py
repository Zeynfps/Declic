"""Identifiants de sites : se connecter à une page (ENT, Moodle…) sans retaper son mot de passe.

Sécurité :
  - le mot de passe va directement dans le trousseau du système (GNOME : Secret Service, chiffré et
    déverrouillé avec la session). Déclic ne l'écrit dans aucun fichier et ne le relit jamais ;
  - pour se connecter, le service ouvre la page puis demande à l'interface (extension GNOME) de taper
    l'identifiant et le mot de passe. C'est l'extension qui lit le mot de passe dans le trousseau, et
    seulement si l'onglet affiché est en https sur le site enregistré (vérifié par son adresse, juste avant
    l'identifiant puis juste avant le mot de passe) ;
  - jamais de passage par le presse-papiers (les historiques de presse-papiers le garderaient en clair).
"""
from __future__ import annotations

import re
import urllib.parse

from declic import texte
from declic.modele import Champ, Commande, Creation, CreationRefusee, Element, Reponse, Resultat
from declic.modules import Module
from declic.plateforme.base import NonPrisEnCharge

DELAI_SAISIE_S = 20  # temps laissé à la page pour s'ouvrir avant d'abandonner
DELAI_REMPLIR_S = 8  # « Remplir ici » : la page est déjà ouverte


def hote(adresse: str) -> str:
    return (urllib.parse.urlsplit(adresse).hostname or "").lower().rstrip(".")


def page_autorisee(url: str | None, adresse_enregistree: str) -> tuple[bool, str]:
    """La page affichée appartient-elle au site enregistré ? (https, même hôte ou sous-domaine de celui-ci)"""
    if not url:
        return False, "adresse de la page illisible (accessibilité de Firefox désactivée ?)"
    morceaux = urllib.parse.urlsplit(url)
    if morceaux.scheme != "https":
        return False, f"page non chiffrée ({morceaux.scheme or 'adresse inconnue'})"
    attendu, reel = hote(adresse_enregistree), (morceaux.hostname or "").lower().rstrip(".")
    if not attendu or not (reel == attendu or reel.endswith("." + attendu)):
        return False, f"la page est sur « {reel} », pas sur « {attendu} »"
    return True, ""


def cle_site(nom: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texte.normaliser(nom)).strip("-") or "site"


class Identifiants(Module):
    nom = "identifiants"

    def _liste(self) -> list[dict]:
        try:
            return self.contexte.plateforme.coffre_lister()
        except NonPrisEnCharge:
            return []

    # --- Dans la barre -------------------------------------------------------------------
    def commandes(self) -> list[Commande]:
        if not self.contexte.plateforme.prend_en_charge("coffre_lister"):
            return []
        commandes = [Commande("identifiants.connexion", "Se connecter à un site", self._connexion,
                              argument="site", cachee=True, requiert="saisir_identifiant"),
                     Commande("identifiants.remplir", "Remplir l'identifiant ici", self._remplir,
                              argument="site", cachee=True, requiert="saisir_identifiant")]
        for site in self._liste():
            commandes.append(Commande(
                f"identifiants.{site['site']}", f"Se connecter : {site['nom']}",
                lambda contexte, _a, s=site["site"]: self._connexion(contexte, s),
                description=f"{site['identifiant']} · {site['adresse']}", icone="dialog-password-symbolic",
                mots_cles=("connexion", "identifiant", "login", site["nom"]), requiert="saisir_identifiant",
            ))
        return commandes

    def _site(self, cle):
        return next((s for s in self._liste() if s["site"] == (cle or "").strip()), None)

    def _connexion(self, contexte, site_cle):
        site = self._site(site_cle)
        if site is None:
            return Reponse.erreur(f"Aucun identifiant enregistré pour « {site_cle} »")
        contexte.plateforme.ouvrir(site["adresse"])
        contexte.plateforme.saisir_identifiant(site["site"], DELAI_SAISIE_S)
        return Reponse(message=f"{site['nom']} : connexion dès que la page est affichée")

    def _remplir(self, contexte, site_cle):
        site = self._site(site_cle)
        if site is None:
            return Reponse.erreur(f"Aucun identifiant enregistré pour « {site_cle} »")
        contexte.plateforme.saisir_identifiant(site["site"], DELAI_REMPLIR_S)
        return Reponse(message="")  # la barre se ferme, l'extension tape dans la page revenue au premier plan

    def verifier(self, site_cle: str, pid: int) -> dict:
        """Appelé par l'interface juste avant de taper : l'onglet affiché est-il bien sur le site ?"""
        site = self._site(site_cle)
        if site is None:
            return {"ok": False, "raison": "identifiant inconnu"}
        try:
            url = self.contexte.plateforme.adresse_page(pid)
        except Exception as exc:
            return {"ok": False, "raison": f"adresse de la page illisible ({exc})"}
        ok, raison = page_autorisee(url, site["adresse"])
        return {"ok": ok, "raison": raison}

    def suggestions(self, page: str | None, requete: str) -> list[Resultat]:
        """« Remplir ici » pour les identifiants du site affiché dans le navigateur."""
        if not page:
            return []
        q = texte.normaliser(requete)
        resultats = []
        for site in self._liste():
            if not page_autorisee(page, site["adresse"])[0]:
                continue
            if q and not any(q in texte.normaliser(x) for x in ("remplir connexion se connecter", site["nom"])):
                continue
            resultats.append(Resultat(
                commande="identifiants.remplir", titre=f"Remplir ici : {site['nom']}", argument=site["site"],
                sous_titre=f"{site['identifiant']} · {hote(site['adresse'])}", icone="dialog-password-symbolic",
                score=120.0, module="identifiants"))
        return resultats

    # --- Ajout, liste, suppression ------------------------------------------------------------
    def creations(self) -> list[Creation]:
        if not self.contexte.plateforme.prend_en_charge("coffre_enregistrer"):
            return []
        return [Creation(
            type="identifiant", titre="Identifiant de site", titre_pluriel="Identifiants de sites",
            icone="dialog-password-symbolic",
            description="Pour vous connecter à une page en un geste. Le mot de passe est rangé dans le trousseau "
                        "chiffré de GNOME, jamais dans un fichier.",
            champs=(
                Champ("nom", "Nom", exemple="ENT de la fac"),
                Champ("adresse", "Page de connexion", exemple="https://cas.univ.fr/login",
                      aide="Copiez l'adresse de la page où l'on tape l'identifiant. Déclic ne remplira que sur ce "
                           "site (et ses sous-domaines), en https."),
                Champ("identifiant", "Identifiant", exemple="prenom.nom"),
                Champ("mot_de_passe", "Mot de passe", type="secret",
                      aide="Envoyé directement au trousseau GNOME. Il ne sera plus jamais affiché."),
            ),
            creer=self._creer, lister=self._lister, supprimer=self._supprimer,
        )]

    def _creer(self, valeurs: dict) -> Reponse:
        nom = valeurs.get("nom", "").strip()
        adresse = valeurs.get("adresse", "").strip()
        identifiant = valeurs.get("identifiant", "").strip()
        mot_de_passe = valeurs.get("mot_de_passe", "")
        if not nom:
            raise CreationRefusee("Donnez un nom.", "nom")
        if not adresse.startswith(("https://", "http://")):
            if " " in adresse or "." not in adresse:
                raise CreationRefusee("L'adresse doit commencer par https://", "adresse")
            adresse = "https://" + adresse
        if adresse.startswith("http://"):
            raise CreationRefusee("Par sécurité, seulement des pages en https:// (connexion chiffrée).", "adresse")
        if not identifiant:
            raise CreationRefusee("Indiquez l'identifiant.", "identifiant")
        if not mot_de_passe:
            raise CreationRefusee("Indiquez le mot de passe.", "mot_de_passe")
        cle = cle_site(nom)
        if any(s["site"] == cle for s in self._liste()):
            raise CreationRefusee(f"« {nom} » existe déjà : supprimez-le d'abord pour le remplacer.", "nom")
        self.contexte.plateforme.coffre_enregistrer(
            cle, {"nom": nom, "adresse": adresse, "identifiant": identifiant, "titre": ""}, mot_de_passe)
        return Reponse(message=f"« {nom} » enregistré dans le trousseau", fermer=False, remplir=nom)

    def _lister(self) -> list[Element]:
        return [Element(cle=s["site"], titre=s["nom"],
                        sous_titre=f"{s['identifiant']} · {hote(s['adresse'])}", remplir=s["nom"])
                for s in sorted(self._liste(), key=lambda s: s["nom"].casefold())]

    def _supprimer(self, cle: str) -> Reponse:
        site = next((s for s in self._liste() if s["site"] == cle), None)
        if site is None or not self.contexte.plateforme.coffre_supprimer(cle):
            raise CreationRefusee("Cet identifiant n'existe plus.")
        return Reponse(message=f"« {site['nom']} » retiré du trousseau", fermer=False)
