"""Automatisations : « quand » (déclencheur) + « si » (conditions) + « alors » (actions).

Les actions sont des commandes de Déclic (celles de la barre), écrites « module.commande » ou
« module.commande:argument », plus deux actions propres aux règles : « attendre:5 » (secondes) et
« notifier:texte ».

Fichier ~/.config/declic/regles.toml (voir MODELE ci-dessous pour des exemples commentés).

Déclencheurs :
  quand = "manuel"                                  → commande « Lancer : <nom> » dans la barre
  quand = { heure = "08:30", jours = ["lun", "ven"] } → chaque jour indiqué (tous les jours sans « jours »)
  quand = { evenement = "session.deverrouillee" }   → événement du système (liste dans EVENEMENTS)
  quand = { evenement = "wifi.connecte", valeur = "eduroam" }
  quand = { telephone = "arrivee", lieu = "maison" } → envoyé par le téléphone (événement « telephone.arrivee »)
Conditions (facultatives) :
  si = { heure_entre = ["17:00", "23:00"], jours = ["sam", "dim"] }
"""
from __future__ import annotations

import collections
import datetime as dt
import logging
import re
import threading
import time
import tomllib
from dataclasses import dataclass, field
from typing import Callable, Optional

from declic import fichiers_toml, texte
from declic.modele import Champ, Commande, Creation, CreationRefusee, Element, Reponse
from declic.modules import Module
from declic.plateforme.base import NonPrisEnCharge

journal = logging.getLogger("declic.automatisations")

JOURS = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
_JOURS_LONGS = {"lundi": "lun", "mardi": "mar", "mercredi": "mer", "jeudi": "jeu", "vendredi": "ven",
                "samedi": "sam", "dimanche": "dim"}

# Événements émis par le service (la plateforme, le démarrage) ; le téléphone et l'API peuvent en envoyer d'autres.
EVENEMENTS = {
    "declic.demarrage": "Démarrage de Déclic (ouverture de session)",
    "session.verrouillee": "Écran verrouillé",
    "session.deverrouillee": "Écran déverrouillé",
    "alimentation.secteur": "Ordinateur branché sur secteur",
    "alimentation.batterie": "Ordinateur passé sur batterie",
    "reseau.connecte": "Connexion à un réseau (valeur = nom de la connexion)",
    "wifi.connecte": "Connexion à un Wi-Fi (valeur = nom du réseau)",
    "wifi.deconnecte": "Déconnexion du Wi-Fi (valeur = nom du réseau quitté)",
    "telephone.arrivee": "Le téléphone arrive à un lieu (valeur = nom du lieu)",
    "telephone.depart": "Le téléphone quitte un lieu (valeur = nom du lieu)",
}

ATTENTE_MAX_S = 600
MAX_ACTIONS = 50

MODELE = """# Automatisations de Déclic : « quand » quelque chose arrive, « si » les conditions sont remplies,
# « alors » Déclic lance les actions dans l'ordre.
#
# Actions : les commandes de la barre (liste complète : python3 -m declic commandes), par exemple
#   "son.volume-25", "systeme.ne-pas-deranger", "app.org.zotero.Zotero.desktop",
#   "liens.ouvrir:https://ent.univ.fr", "liens.persee:céramique sigillée"
# et deux actions propres aux règles : "attendre:5" (secondes) et "notifier:Votre message".
#
# Déclencheurs :
#   quand = "manuel"                                     (commande « Lancer : … » dans la barre)
#   quand = { heure = "08:30", jours = ["lun", "mar", "mer", "jeu", "ven"] }
#   quand = { evenement = "session.deverrouillee" }      (aussi : session.verrouillee, declic.demarrage,
#                                                          alimentation.secteur, alimentation.batterie,
#                                                          wifi.connecte, wifi.deconnecte, reseau.connecte)
#   quand = { evenement = "wifi.connecte", valeur = "eduroam" }
#   quand = { telephone = "arrivee", lieu = "maison" }   (envoyé par le téléphone, bientôt)
#
# Conditions (facultatives) :
#   si = { heure_entre = ["17:00", "23:00"], jours = ["sam", "dim"] }
#
# Pour désactiver une règle sans l'effacer : actif = false
# Après une modification : « Recharger la configuration de Déclic » dans la barre.

# --- Exemples (enlevez les # pour les essayer) -------------------------------------------

# [[regle]]
# nom = "Mode révision"
# quand = "manuel"
# alors = ["systeme.ne-pas-deranger", "son.volume-25", "notifier:Bon courage !"]

# [[regle]]
# nom = "Arrivée à la fac"
# quand = { evenement = "wifi.connecte", valeur = "eduroam" }
# si = { jours = ["lun", "mar", "mer", "jeu", "ven"] }
# alors = ["son.volume-0", "liens.ouvrir:https://ent.univ.fr"]
"""


class RegleInvalide(ValueError):
    pass


# --- Description d'une règle ------------------------------------------------------------
def _heure(valeur, ou: str) -> dt.time:
    if not isinstance(valeur, str) or not re.fullmatch(r"\d{1,2}:\d{2}", valeur.strip()):
        raise RegleInvalide(f"{ou} : heure attendue au format HH:MM (reçu {valeur!r})")
    h, m = (int(x) for x in valeur.strip().split(":"))
    if h > 23 or m > 59:
        raise RegleInvalide(f"{ou} : heure impossible ({valeur})")
    return dt.time(h, m)


def _jours(valeur, ou: str) -> frozenset[int]:
    if valeur is None:
        return frozenset(range(7))
    if isinstance(valeur, str):
        valeur = [valeur]
    if not isinstance(valeur, list) or not valeur:
        raise RegleInvalide(f"{ou} : liste de jours attendue, par exemple [\"lun\", \"mar\"]")
    jours = set()
    for jour in valeur:
        j = texte.normaliser(str(jour))
        j = _JOURS_LONGS.get(j, j)
        if j in ("semaine",):
            jours.update(range(5))
        elif j in ("week-end", "weekend"):
            jours.update((5, 6))
        elif j in JOURS:
            jours.add(JOURS.index(j))
        else:
            raise RegleInvalide(f"{ou} : jour inconnu « {jour} » (lun, mar, mer, jeu, ven, sam, dim, semaine, week-end)")
    return frozenset(jours)


@dataclass(frozen=True)
class Declencheur:
    type: str  # manuel | heure | evenement
    heure: Optional[dt.time] = None
    jours: frozenset[int] = frozenset(range(7))
    evenement: str = ""
    valeur: Optional[str] = None  # None : n'importe quelle valeur

    @classmethod
    def lire(cls, quand) -> "Declencheur":
        if quand == "manuel" or quand == {"manuel": True}:
            return cls("manuel")
        if not isinstance(quand, dict):
            raise RegleInvalide("« quand » doit être \"manuel\" ou un tableau { … }")
        if "heure" in quand:
            return cls("heure", heure=_heure(quand["heure"], "quand.heure"), jours=_jours(quand.get("jours"), "quand.jours"))
        if "telephone" in quand:
            valeur = quand.get("lieu", quand.get("valeur"))
            return cls("evenement", evenement=f"telephone.{texte.normaliser(str(quand['telephone']))}",
                       valeur=None if valeur is None else str(valeur))
        if "evenement" in quand:
            nom = str(quand["evenement"]).strip()
            if not re.fullmatch(r"[a-z0-9_-]+(\.[a-z0-9_-]+)+", nom):
                raise RegleInvalide(f"quand.evenement : nom invalide « {nom} » (ex. « session.deverrouillee »)")
            valeur = quand.get("valeur")
            return cls("evenement", evenement=nom, valeur=None if valeur is None else str(valeur))
        raise RegleInvalide("« quand » : il faut « manuel », « heure », « evenement » ou « telephone »")

    def correspond(self, evenement: str, valeur: Optional[str]) -> bool:
        if self.type != "evenement" or evenement != self.evenement:
            return False
        return self.valeur is None or (valeur is not None and texte.normaliser(valeur) == texte.normaliser(self.valeur))

    def resume(self) -> str:
        if self.type == "manuel":
            return "à la demande"
        if self.type == "heure":
            jours = "tous les jours" if len(self.jours) == 7 else ", ".join(JOURS[j] for j in sorted(self.jours))
            return f"à {self.heure:%H:%M} ({jours})"
        suite = f" « {self.valeur} »" if self.valeur else ""
        return f"quand {EVENEMENTS.get(self.evenement, self.evenement).split(' (')[0].lower()}{suite}"


@dataclass(frozen=True)
class Conditions:
    heure_entre: Optional[tuple[dt.time, dt.time]] = None
    jours: frozenset[int] = frozenset(range(7))

    @classmethod
    def lire(cls, si) -> "Conditions":
        if si is None:
            return cls()
        if not isinstance(si, dict):
            raise RegleInvalide("« si » doit être un tableau { … }")
        inconnues = set(si) - {"heure_entre", "jours"}
        if inconnues:
            raise RegleInvalide(f"« si » : condition inconnue {', '.join(sorted(inconnues))} (heure_entre, jours)")
        plage = None
        if "heure_entre" in si:
            valeur = si["heure_entre"]
            if not isinstance(valeur, list) or len(valeur) != 2:
                raise RegleInvalide("si.heure_entre : deux heures attendues, par exemple [\"17:00\", \"23:00\"]")
            plage = (_heure(valeur[0], "si.heure_entre"), _heure(valeur[1], "si.heure_entre"))
        return cls(heure_entre=plage, jours=_jours(si.get("jours"), "si.jours"))

    def remplies(self, maintenant: dt.datetime) -> bool:
        if maintenant.weekday() not in self.jours:
            return False
        if self.heure_entre:
            debut, fin = self.heure_entre
            h = maintenant.time().replace(second=0, microsecond=0)
            # une plage peut passer minuit : ["22:00", "06:00"]
            if not (debut <= h <= fin if debut <= fin else (h >= debut or h <= fin)):
                return False
        return True


@dataclass(frozen=True)
class Action:
    commande: str  # id de commande, ou « attendre » / « notifier »
    argument: Optional[str] = None

    @classmethod
    def lire(cls, texte_action) -> "Action":
        if not isinstance(texte_action, str) or not texte_action.strip():
            raise RegleInvalide("« alors » : chaque action est un texte, par exemple \"son.volume-25\"")
        commande, separateur, argument = texte_action.strip().partition(":")
        commande = commande.strip()
        if commande == "attendre":
            try:
                secondes = float(argument)
            except ValueError:
                raise RegleInvalide(f"« {texte_action} » : nombre de secondes attendu (ex. attendre:5)") from None
            if not 0 <= secondes <= ATTENTE_MAX_S:
                raise RegleInvalide(f"« {texte_action} » : entre 0 et {ATTENTE_MAX_S} secondes")
        return cls(commande, argument if separateur else None)

    def __str__(self) -> str:
        return self.commande + (f":{self.argument}" if self.argument is not None else "")


@dataclass(frozen=True)
class Regle:
    nom: str
    quand: Declencheur
    actions: tuple[Action, ...]
    si: Conditions = field(default_factory=Conditions)
    actif: bool = True

    @property
    def id(self) -> str:
        return "auto." + (re.sub(r"[^a-z0-9]+", "-", texte.normaliser(self.nom)).strip("-") or "regle")

    @classmethod
    def lire(cls, donnees: dict) -> "Regle":
        nom = str(donnees.get("nom", "")).strip()
        if not nom:
            raise RegleInvalide("règle sans « nom »")
        try:
            if "quand" not in donnees:
                raise RegleInvalide("il manque « quand »")
            alors = donnees.get("alors")
            if isinstance(alors, str):
                alors = [alors]
            if not isinstance(alors, list) or not alors:
                raise RegleInvalide("il manque « alors » (la liste des actions)")
            if len(alors) > MAX_ACTIONS:
                raise RegleInvalide(f"trop d'actions (maximum {MAX_ACTIONS})")
            return cls(nom=nom, quand=Declencheur.lire(donnees["quand"]), si=Conditions.lire(donnees.get("si")),
                       actions=tuple(Action.lire(a) for a in alors), actif=bool(donnees.get("actif", True)))
        except RegleInvalide as exc:
            raise RegleInvalide(f"« {nom} » : {exc}") from None


# --- Journal ------------------------------------------------------------------------------
@dataclass
class Execution:
    regle: str
    source: str  # barre, heure, evenement:…, telephone…
    debut: dt.datetime
    etapes: list[tuple[str, str, str]] = field(default_factory=list)  # (action, statut, message)
    fin: Optional[dt.datetime] = None

    @property
    def reussie(self) -> bool:
        return all(statut == "ok" for _a, statut, _m in self.etapes)

    def en_dict(self) -> dict:
        return {"regle": self.regle, "source": self.source, "debut": self.debut.isoformat(timespec="seconds"),
                "fin": self.fin.isoformat(timespec="seconds") if self.fin else None, "reussie": self.reussie,
                "etapes": [{"action": a, "statut": s, "message": m} for a, s, m in self.etapes]}


# --- Le module : règles + moteur ------------------------------------------------------------
class Automatisations(Module):
    nom = "auto"

    def __init__(self, contexte, horloge: Callable[[], dt.datetime] = dt.datetime.now, synchrone: bool = False):
        super().__init__(contexte)
        self.registre = None  # renseigné par le registre
        self.horloge = horloge
        self.synchrone = synchrone  # tests : exécuter sans fil d'exécution
        self.regles: list[Regle] = []
        self.erreurs: list[str] = []
        self.journal: collections.deque[Execution] = collections.deque(maxlen=100)
        self._verrou = threading.Lock()
        self._deja: set[tuple[str, str]] = set()  # (règle, minute) : déclenchements horaires déjà faits
        self._arret = threading.Event()
        self._fil: Optional[threading.Thread] = None
        self.recharger()

    # --- Lecture du fichier -------------------------------------------------------------
    def recharger(self) -> None:
        fichier = self.contexte.chemins.regles
        if not fichier.exists():
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_text(MODELE, encoding="utf-8")
        regles, erreurs = [], []
        try:
            with fichier.open("rb") as f:
                donnees = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            donnees = {}
            erreurs.append(f"regles.toml illisible : {exc}")
        noms = set()
        for brute in donnees.get("regle", []):
            try:
                regle = Regle.lire(brute)
            except RegleInvalide as exc:
                erreurs.append(str(exc))
                continue
            if regle.id in noms:
                erreurs.append(f"« {regle.nom} » : une autre règle porte déjà ce nom")
                continue
            noms.add(regle.id)
            regles.append(regle)
        self.regles, self.erreurs = regles, erreurs
        for e in erreurs:
            journal.warning("Règle ignorée : %s", e)

    def verifier_actions(self) -> list[str]:
        """Actions qui ne correspondent à aucune commande connue (signalées, la règle reste active)."""
        if self.registre is None:
            return []
        connues = self.registre.commandes()
        return [f"« {r.nom} » : action inconnue « {a} »" for r in self.regles for a in r.actions
                if a.commande not in ("attendre", "notifier") and a.commande not in connues]

    # --- Déclenchement -------------------------------------------------------------------
    def declencher(self, evenement: str, valeur: Optional[str] = None, source: str = "") -> list[str]:
        """Lance les règles actives qui attendent cet événement. Renvoie leurs noms."""
        maintenant = self.horloge()
        lancees = []
        for regle in list(self.regles):
            if regle.actif and regle.quand.correspond(evenement, valeur) and regle.si.remplies(maintenant):
                self.lancer(regle, source or f"evenement:{evenement}")
                lancees.append(regle.nom)
        if lancees:
            journal.info("%s%s → %s", evenement, f" ({valeur})" if valeur else "", ", ".join(lancees))
        return lancees

    def tic(self, maintenant: Optional[dt.datetime] = None) -> list[str]:
        """Vérifie les règles horaires (appelé régulièrement). Chaque règle part au plus une fois par minute."""
        maintenant = maintenant or self.horloge()
        minute = maintenant.strftime("%Y-%m-%d %H:%M")
        self._deja = {d for d in self._deja if d[1] == minute}
        lancees = []
        for regle in list(self.regles):
            q = regle.quand
            if (regle.actif and q.type == "heure" and (regle.id, minute) not in self._deja
                    and (maintenant.hour, maintenant.minute) == (q.heure.hour, q.heure.minute)
                    and maintenant.weekday() in q.jours and regle.si.remplies(maintenant)):
                self._deja.add((regle.id, minute))
                self.lancer(regle, "heure")
                lancees.append(regle.nom)
        return lancees

    def lancer(self, regle: Regle, source: str) -> Execution:
        execution = Execution(regle.nom, source, self.horloge())
        with self._verrou:
            self.journal.append(execution)
        if self.synchrone:
            self._executer(regle, execution)
        else:
            threading.Thread(target=self._executer, args=(regle, execution), daemon=True,
                             name=f"regle {regle.nom}").start()
        return execution

    def _executer(self, regle: Regle, execution: Execution) -> None:
        plateforme = self.contexte.plateforme
        for action in regle.actions:
            if self._arret.is_set():
                execution.etapes.append((str(action), "erreur", "Déclic s'arrête"))
                break
            try:
                if action.commande == "attendre":
                    self._arret.wait(float(action.argument))
                    execution.etapes.append((str(action), "ok", ""))
                elif action.commande == "notifier":
                    plateforme.notifier(regle.nom, action.argument or "")
                    execution.etapes.append((str(action), "ok", ""))
                elif self.registre is None:
                    execution.etapes.append((str(action), "erreur", "registre absent"))
                else:
                    reponse = self.registre.executer(action.commande, action.argument)
                    execution.etapes.append((str(action), reponse.statut, reponse.message))
            except Exception as exc:  # une action en échec n'arrête pas les suivantes
                journal.exception("Règle « %s » : action %s", regle.nom, action)
                execution.etapes.append((str(action), "erreur", str(exc)))
        execution.fin = self.horloge()
        if not execution.reussie and execution.source != "barre":
            erreurs = [f"{a} : {m}" for a, s, m in execution.etapes if s != "ok"]
            try:
                plateforme.notifier(f"Automatisation « {regle.nom} » : échec", "\n".join(erreurs)[:300])
            except Exception:
                pass

    # --- Horloge en arrière-plan ------------------------------------------------------------
    def demarrer(self) -> None:
        if self._fil is not None:
            return
        self._arret.clear()

        def boucle():
            while not self._arret.is_set():
                try:
                    self.tic()
                except Exception:
                    journal.exception("Vérification horaire impossible")
                # se caler peu après le début de chaque minute
                self._arret.wait(60.5 - time.time() % 60 if time.time() % 60 > 1 else 15)

        self._fil = threading.Thread(target=boucle, daemon=True, name="horloge des règles")
        self._fil.start()

    def arreter(self) -> None:
        self._arret.set()
        self._fil = None

    # --- Création par blocs depuis la barre (bouton +) ------------------------------------
    DECLENCHEURS = (
        ("manuel", "À la demande (depuis la barre)"),
        ("wifi", "En me connectant à un Wi-Fi"),
        ("heure", "À une heure précise"),
        ("deverrouillage", "Quand je déverrouille l'écran"),
        ("secteur", "Quand je branche le chargeur"),
        ("batterie", "Quand je débranche le chargeur"),
        ("demarrage", "À l'ouverture de session"),
    )
    _EVENEMENT = {"deverrouillage": "session.deverrouillee", "secteur": "alimentation.secteur",
                  "batterie": "alimentation.batterie", "demarrage": "declic.demarrage"}

    def creations(self) -> list[Creation]:
        plateforme = self.contexte.plateforme
        try:
            wifis = plateforme.reseaux_wifi_connus()
        except (NonPrisEnCharge, Exception):  # pas de NetworkManager… : saisie libre impossible, liste vide
            wifis = []
        try:
            sites = plateforme.coffre_lister() if plateforme.prend_en_charge("coffre_lister") else []
        except Exception:
            sites = []
        declencheurs = tuple(d for d in self.DECLENCHEURS if d[0] != "wifi" or wifis)
        champs = [
            Champ("nom", "Nom", exemple="Arrivée à la fac"),
            Champ("declencheur", "Quand", type="choix", options=declencheurs),
            Champ("wifi", "Wi-Fi", type="choix", options=tuple((w, w) for w in wifis), si=("declencheur", ("wifi",)),
                  aide="Les réseaux enregistrés sur cet ordinateur."),
            Champ("heure", "Heure", exemple="08:30", si=("declencheur", ("heure",))),
            Champ("jours", "Quels jours", type="choix",
                  options=(("tous", "Tous les jours"), ("semaine", "En semaine (lun → ven)"), ("week-end", "Le week-end"))),
            Champ("ouvrir", "Ouvrir une page", exemple="https://moodle.univ.fr", obligatoire=False),
        ]
        if sites:
            champs.append(Champ("connexion", "Se connecter avec", type="choix", obligatoire=False,
                                options=(("", "(personne)"),) + tuple((s["site"], s["nom"]) for s in sites),
                                aide="Un identifiant enregistré (bouton + → Identifiant de site)."))
        champs.append(Champ("commandes", "Autres actions", obligatoire=False,
                            exemple="son.volume-25, systeme.ne-pas-deranger",
                            aide="Commandes de Déclic séparées par des virgules (liste : python3 -m declic commandes)."))
        return [Creation(
            type="automatisation", titre="Automatisation", titre_pluriel="Automatisations",
            icone="media-playback-start-symbolic",
            description="Quand quelque chose arrive (un Wi-Fi, une heure…), Déclic fait les actions pour vous.",
            champs=tuple(champs), creer=self._creer, lister=self._lister, supprimer=self._supprimer,
        )]

    def _creer(self, valeurs: dict) -> Reponse:
        nom = valeurs.get("nom", "").strip()
        if not nom:
            raise CreationRefusee("Donnez un nom à l'automatisation.", "nom")
        type_ = valeurs.get("declencheur", "manuel")
        jours = valeurs.get("jours", "tous")
        if type_ == "manuel":
            quand = "manuel"
        elif type_ == "wifi":
            wifi = valeurs.get("wifi", "").strip()
            if not wifi:
                raise CreationRefusee("Choisissez le Wi-Fi.", "wifi")
            quand = {"evenement": "wifi.connecte", "valeur": wifi}
        elif type_ == "heure":
            m = re.fullmatch(r"\s*(\d{1,2})\s*[h:]?\s*(\d{2})?\s*", valeurs.get("heure", "").lower())
            heure = f"{int(m.group(1)):02d}:{m.group(2) or '00'}" if m else ""
            try:
                _heure(heure, "heure")
            except RegleInvalide:
                raise CreationRefusee("Heure attendue comme 08:30 ou 8h30.", "heure") from None
            quand = {"heure": heure}
            if jours != "tous":
                quand["jours"] = [jours]
        elif type_ in self._EVENEMENT:
            quand = {"evenement": self._EVENEMENT[type_]}
        else:
            raise CreationRefusee("Déclencheur inconnu.", "declencheur")

        alors = []
        ouvrir = valeurs.get("ouvrir", "").strip()
        if ouvrir:
            if not ouvrir.startswith(("http://", "https://")):
                ouvrir = "https://" + ouvrir
            alors.append(f"liens.ouvrir:{ouvrir}")
        if valeurs.get("connexion", "").strip():
            alors.append(f"identifiants.connexion:{valeurs['connexion'].strip()}")
        connues = self.registre.commandes() if self.registre else {}
        for brute in valeurs.get("commandes", "").replace("\n", ",").split(","):
            brute = brute.strip()
            if not brute:
                continue
            try:
                action = Action.lire(brute)
            except RegleInvalide as exc:
                raise CreationRefusee(str(exc), "commandes") from None
            if action.commande not in ("attendre", "notifier") and connues and action.commande not in connues:
                raise CreationRefusee(f"Commande inconnue : « {action.commande} »", "commandes")
            alors.append(str(action))
        if not alors:
            raise CreationRefusee("Ajoutez au moins une action : une page, une connexion ou une commande.", "ouvrir")

        bloc = {"nom": nom, "quand": quand}
        if jours != "tous" and type_ != "heure":
            bloc["si"] = {"jours": [jours]}
        bloc["alors"] = alors
        regle = Regle.lire(bloc)  # même validation que le fichier
        if any(r.id == regle.id for r in self.regles):
            raise CreationRefusee(f"Une automatisation s'appelle déjà « {nom} ».", "nom")
        fichiers_toml.ajouter_bloc(self.contexte.chemins.regles, "regle", bloc, entete=MODELE)
        self.recharger()
        return Reponse(message=f"« {nom} » ajoutée : {regle.quand.resume()}", fermer=False,
                       remplir=nom if type_ == "manuel" else "")

    def _lister(self) -> list[Element]:
        return [Element(cle=r.id, titre=r.nom + ("" if r.actif else " (désactivée)"),
                        sous_titre=f"{r.quand.resume()} → {', '.join(str(a) for a in r.actions)}",
                        remplir=r.nom if r.quand.type == "manuel" else "")
                for r in self.regles]

    def _supprimer(self, cle: str) -> Reponse:
        regle = next((r for r in self.regles if r.id == cle), None)
        if regle is None:
            raise CreationRefusee("Cette automatisation n'existe plus.")

        def garder(entree):
            try:
                return Regle.lire(entree).id != cle
            except RegleInvalide:
                return True

        fichiers_toml.retirer_bloc(self.contexte.chemins.regles, "regle", garder)
        self.recharger()
        return Reponse(message=f"« {regle.nom} » supprimée", fermer=False)

    # --- Dans la barre ----------------------------------------------------------------------
    def _action_regle(self, regle: Regle):
        def action(_contexte, _argument):
            self.lancer(regle, "barre")
            return Reponse(message=f"« {regle.nom} » lancée")
        return action

    def _modifier(self, contexte, _argument):
        contexte.plateforme.ouvrir(str(contexte.chemins.regles))
        return Reponse(message="Fichier des automatisations ouvert")

    def _journal(self, _contexte, _argument):
        return Reponse(message="Automatisations", texte=self.rapport(), fermer=False)

    def rapport(self) -> str:
        lignes = [f"Règles ({len(self.regles)}) :"]
        for r in self.regles:
            etat = "" if r.actif else "  [désactivée]"
            lignes.append(f"  • {r.nom} — {r.quand.resume()}{etat}")
            lignes.append(f"      alors : {', '.join(str(a) for a in r.actions)}")
        if not self.regles:
            lignes.append("  (aucune : « Modifier les automatisations » pour en écrire)")
        problemes = self.erreurs + self.verifier_actions()
        if problemes:
            lignes += ["", "À corriger :"] + [f"  ⚠ {p}" for p in problemes]
        lignes += ["", "Dernières exécutions :"]
        for e in list(self.journal)[-15:][::-1]:
            etat = "en cours" if e.fin is None else ("ok" if e.reussie else "ÉCHEC")
            lignes.append(f"  {e.debut:%d/%m %H:%M:%S}  {e.regle}  ({e.source}) — {etat}")
            for a, s, m in e.etapes:
                if s != "ok":
                    lignes.append(f"      ✘ {a} : {m}")
        if not self.journal:
            lignes.append("  (aucune depuis le démarrage de Déclic)")
        return "\n".join(lignes)

    def commandes(self) -> list[Commande]:
        commandes = [
            Commande("auto.modifier", "Modifier les automatisations", self._modifier, requiert="ouvrir",
                     description="Ouvre regles.toml", icone="document-edit-symbolic",
                     mots_cles=("automatisation", "règle", "regles")),
            Commande("auto.journal", "Automatisations : règles et journal", self._journal,
                     description="Règles chargées, erreurs, dernières exécutions", icone="view-list-symbolic",
                     mots_cles=("automatisation", "règle", "journal", "historique")),
        ]
        for regle in self.regles:
            if regle.actif:
                commandes.append(Commande(
                    regle.id, f"Lancer : {regle.nom}", self._action_regle(regle),
                    description=", ".join(str(a) for a in regle.actions)[:80],
                    icone="media-playback-start-symbolic", mots_cles=("automatisation", regle.nom),
                ))
        return commandes
