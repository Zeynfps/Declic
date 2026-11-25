"""API locale de Déclic : HTTP + JSON, sur 127.0.0.1 uniquement, protégée par un jeton.

Utilisée par la barre (extension GNOME, plus tard l'interface Windows) et, plus tard, par le téléphone.

    GET  /v1/sante                          → {"ok": true, "version": …, "plateforme": …}
    GET  /v1/recherche?q=texte&limite=20    → {"resultats": [...]}
    POST /v1/executer {"commande": id, "argument": …}  → {"statut", "message", "texte", "fermer"}
    POST /v1/recharger                      → {"ok": true}
    GET  /v1/creations                      → {"creations": [{type, titre, description, icone, champs}]}
    POST /v1/creer {"type": …, "valeurs": {cle: texte}} → réponse + {"champ": champ à corriger ou null}
    POST /v1/declencheur {"evenement": "telephone.arrivee", "valeur": "maison"} → {"regles": [noms lancés]}
    GET  /v1/automatisations                → {"regles", "erreurs", "journal", "evenements"}
    POST /v1/recherche-selection {"selection", "requete"} → actions sur le texte sélectionné (IA…)
    POST /v1/presse-papiers  {"texte"}       → {"garde": bool} (texte copié, envoyé par la barre GNOME)
    GET  /v1/page-active?pid=N              → {"url": adresse de l'onglet affiché, ou null}
    GET  /v1/verifier-page?site=X&pid=N     → {"ok": bool, "raison": …} (avant de taper un identifiant)
    GET  /v1/elements?type=lien             → {"elements": [{cle, titre, sous_titre, remplir}]}
    POST /v1/supprimer {"type": …, "cle": …} → réponse

En-tête obligatoire : Authorization: Bearer <jeton>
Le port et le jeton sont écrits dans <données>/serveur.json (lisible par l'utilisateur seul).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from declic import __version__
from declic.registre import Registre

journal = logging.getLogger("declic.serveur")
PORT_PAR_DEFAUT = 47823
TAILLE_MAX = 64 * 1024


def _ecrire_prive(chemin, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descripteur, "w", encoding="utf-8") as f:
        f.write(contenu)
    os.chmod(chemin, 0o600)


def lire_ou_creer_jeton(chemin) -> str:
    if chemin.exists():
        jeton = chemin.read_text(encoding="utf-8").strip()
        if len(jeton) >= 32:
            return jeton
    jeton = secrets.token_urlsafe(32)
    _ecrire_prive(chemin, jeton)
    return jeton


def creer_serveur(registre: Registre, port: int = PORT_PAR_DEFAUT) -> ThreadingHTTPServer:
    chemins = registre.contexte.chemins
    jeton = lire_ou_creer_jeton(chemins.jeton)

    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = f"Declic/{__version__}"

        def log_message(self, format, *args):  # noqa: A002 - signature imposée
            journal.debug("%s - %s", self.address_string(), format % args)

        def _envoyer(self, code: int, donnees: dict) -> None:
            corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corps)

        def _autorise(self) -> bool:
            entete = self.headers.get("Authorization", "")
            fourni = entete.removeprefix("Bearer ").strip()
            if fourni and hmac.compare_digest(fourni.encode(), jeton.encode()):
                return True
            self._envoyer(401, {"erreur": "jeton manquant ou invalide"})
            return False

        def _corps_json(self) -> dict | None:
            taille = int(self.headers.get("Content-Length") or 0)
            if taille > TAILLE_MAX:
                self._envoyer(413, {"erreur": "requête trop grande"})
                return None
            try:
                donnees = json.loads(self.rfile.read(taille) or b"{}")
            except json.JSONDecodeError:
                self._envoyer(400, {"erreur": "JSON invalide"})
                return None
            if not isinstance(donnees, dict):
                self._envoyer(400, {"erreur": "objet JSON attendu"})
                return None
            return donnees

        def do_GET(self):  # noqa: N802
            if not self._autorise():
                return
            url = urlsplit(self.path)
            if url.path == "/v1/sante":
                self._envoyer(200, {"ok": True, "version": __version__, "plateforme": registre.contexte.plateforme.nom})
            elif url.path == "/v1/recherche":
                params = parse_qs(url.query)
                requete = params.get("q", [""])[0]
                try:
                    limite = max(1, min(100, int(params.get("limite", ["20"])[0])))
                except ValueError:
                    limite = 20
                page = params.get("page", [""])[0] or None
                resultats = registre.rechercher(requete, limite, page)
                self._envoyer(200, {"resultats": [r.en_dict() for r in resultats]})
            elif url.path in ("/v1/page-active", "/v1/verifier-page"):
                params = parse_qs(url.query)
                try:
                    pid = int(params.get("pid", ["0"])[0])
                except ValueError:
                    pid = 0
                if pid <= 0:
                    self._envoyer(400, {"erreur": "« pid » attendu"})
                elif url.path == "/v1/page-active":
                    try:
                        adresse = registre.contexte.plateforme.adresse_page(pid)
                    except Exception:
                        adresse = None
                    self._envoyer(200, {"url": adresse})
                else:
                    self._envoyer(200, registre.verifier_page(params.get("site", [""])[0], pid))
            elif url.path == "/v1/automatisations":
                auto = registre.automatisations
                if auto is None:
                    self._envoyer(404, {"erreur": "automatisations absentes"})
                    return
                from declic.modules.automatisations import EVENEMENTS
                self._envoyer(200, {
                    "regles": [{"id": r.id, "nom": r.nom, "quand": r.quand.resume(), "actif": r.actif,
                                "actions": [str(a) for a in r.actions]} for r in auto.regles],
                    "erreurs": auto.erreurs + auto.verifier_actions(),
                    "journal": [e.en_dict() for e in list(auto.journal)[::-1]],
                    "evenements": EVENEMENTS,
                })
            elif url.path == "/v1/elements":
                type_ = parse_qs(url.query).get("type", [""])[0]
                self._envoyer(200, {"elements": [e.en_dict() for e in registre.elements(type_)]})
            elif url.path == "/v1/creations":
                self._envoyer(200, {"creations": [c.en_dict() for c in registre.creations()]})
            else:
                self._envoyer(404, {"erreur": "chemin inconnu"})

        def do_POST(self):  # noqa: N802
            if not self._autorise():
                return
            url = urlsplit(self.path)
            if url.path == "/v1/executer":
                donnees = self._corps_json()
                if donnees is None:
                    return
                commande = donnees.get("commande")
                if not isinstance(commande, str):
                    self._envoyer(400, {"erreur": "« commande » manquante"})
                    return
                argument = donnees.get("argument")
                argument = str(argument) if argument is not None else None
                self._envoyer(200, registre.executer(commande, argument).en_dict())
            elif url.path == "/v1/creer":
                donnees = self._corps_json()
                if donnees is None:
                    return
                type_, valeurs = donnees.get("type"), donnees.get("valeurs")
                if not isinstance(type_, str) or not isinstance(valeurs, dict):
                    self._envoyer(400, {"erreur": "« type » et « valeurs » attendus"})
                    return
                valeurs = {str(k): str(v) for k, v in valeurs.items() if isinstance(v, (str, int, float))}
                self._envoyer(200, registre.creer(type_, valeurs))
            elif url.path == "/v1/declencheur":
                donnees = self._corps_json()
                if donnees is None:
                    return
                evenement, valeur = donnees.get("evenement"), donnees.get("valeur")
                if not isinstance(evenement, str) or not evenement.strip():
                    self._envoyer(400, {"erreur": "« evenement » manquant"})
                    return
                valeur = str(valeur) if valeur is not None else None
                self._envoyer(200, {"regles": registre.declencher(evenement.strip(), valeur, source=f"api:{evenement}")})
            elif url.path == "/v1/supprimer":
                donnees = self._corps_json()
                if donnees is None:
                    return
                type_, cle = donnees.get("type"), donnees.get("cle")
                if not isinstance(type_, str) or not isinstance(cle, str):
                    self._envoyer(400, {"erreur": "« type » et « cle » attendus"})
                    return
                self._envoyer(200, registre.supprimer(type_, cle))
            elif url.path == "/v1/recherche-selection":
                donnees = self._corps_json()
                if donnees is None:
                    return
                selection, requete = donnees.get("selection"), donnees.get("requete", "")
                if not isinstance(selection, str) or not isinstance(requete, str):
                    self._envoyer(400, {"erreur": "« selection » et « requete » attendus"})
                    return
                try:
                    limite = max(1, min(100, int(donnees.get("limite", 20))))
                except (TypeError, ValueError):
                    limite = 20
                resultats = registre.rechercher(requete, limite, selection=selection)
                self._envoyer(200, {"resultats": [r.en_dict() for r in resultats]})
            elif url.path == "/v1/presse-papiers":
                donnees = self._corps_json()
                if donnees is None:
                    return
                contenu = donnees.get("texte")
                if not isinstance(contenu, str):
                    self._envoyer(400, {"erreur": "« texte » attendu"})
                    return
                module = next((m for m in registre.modules if m.nom == "pp"), None)
                self._envoyer(200, {"garde": bool(module and module.ajouter(contenu))})
            elif url.path == "/v1/recharger":
                registre.recharger()
                self._envoyer(200, {"ok": True})
            else:
                self._envoyer(404, {"erreur": "chemin inconnu"})

    serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestionnaire)
    serveur.daemon_threads = True
    _ecrire_prive(chemins.serveur, json.dumps({"port": serveur.server_address[1], "jeton": jeton}))
    return serveur
