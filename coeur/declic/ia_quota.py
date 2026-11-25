"""Où en est-on de ses requêtes d'IA : « 12 / 1 000 aujourd'hui, remise à zéro à 09:00 ».

Deux sources, la plus sûre d'abord :
  - le fournisseur, quand il l'indique dans les en-têtes de chaque réponse (Claude, OpenAI, Groq, Mistral,
    OpenRouter, xAI…) : limite, restant, et date de remise à zéro ;
  - sinon (Gemini, DeepSeek, Ollama…), le compte de Déclic : les requêtes envoyées depuis la dernière remise à
    zéro du fournisseur (Gemini : minuit, heure du Pacifique), et la limite indiquée par l'utilisateur ou apprise
    d'une erreur « quota dépassé ».
Les comptes sont rangés dans le dossier de données (ia-quota.json) ; aucune clé n'y figure.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

UTC = dt.timezone.utc


# --- Heure du Pacifique, sans base de fuseaux (le Python livré avec Déclic n'en a pas) ---------
def _dimanche(annee: int, mois: int, rang: int) -> dt.date:
    """Le n-ième dimanche du mois (rang 1 = premier)."""
    premier = dt.date(annee, mois, 1)
    return premier + dt.timedelta(days=(6 - premier.weekday()) % 7 + 7 * (rang - 1))


def decalage_pacifique(instant: dt.datetime) -> dt.timedelta:
    """UTC−7 l'été (du 2e dimanche de mars au 1er dimanche de novembre, à 2 h locales), UTC−8 l'hiver."""
    annee = instant.astimezone(UTC).year
    debut = dt.datetime.combine(_dimanche(annee, 3, 2), dt.time(10), UTC)  # 2 h PST = 10 h UTC
    fin = dt.datetime.combine(_dimanche(annee, 11, 1), dt.time(9), UTC)  # 2 h PDT = 9 h UTC
    return dt.timedelta(hours=-7 if debut <= instant.astimezone(UTC) < fin else -8)


def prochain_minuit_pacifique(maintenant: dt.datetime) -> dt.datetime:
    decalage = decalage_pacifique(maintenant)
    local = maintenant.astimezone(UTC) + decalage
    minuit = dt.datetime.combine(local.date() + dt.timedelta(days=1), dt.time(0))
    return (minuit - decalage).replace(tzinfo=UTC)


# --- Lecture des en-têtes des fournisseurs ---------------------------------------------------
def _duree(texte: str) -> dt.timedelta | None:
    """« 1h2m3.5s », « 6m0s », « 20ms », « 59 » (secondes) → durée."""
    texte = texte.strip()
    if re.fullmatch(r"\d+(\.\d+)?", texte):
        return dt.timedelta(seconds=float(texte))
    total, trouve = 0.0, False
    for nombre, unite in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", texte):
        trouve = True
        total += float(nombre) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unite]
    return dt.timedelta(seconds=total) if trouve else None


def depuis_entetes(entetes: dict, maintenant: dt.datetime) -> dict | None:
    """{"limite", "restant", "reset"} d'après les en-têtes, ou None s'il n'y en a pas."""
    e = {k.lower(): v for k, v in entetes.items()}
    if "anthropic-ratelimit-requests-limit" in e:
        limite, restant = e.get("anthropic-ratelimit-requests-limit"), e.get("anthropic-ratelimit-requests-remaining")
        reset = e.get("anthropic-ratelimit-requests-reset")
        quand = dt.datetime.fromisoformat(reset.replace("Z", "+00:00")) if reset else None
    elif "x-ratelimit-limit-requests" in e:
        limite, restant = e.get("x-ratelimit-limit-requests"), e.get("x-ratelimit-remaining-requests")
        duree = _duree(e.get("x-ratelimit-reset-requests", "") or "")
        quand = maintenant + duree if duree is not None else None
    else:
        return None
    try:
        return {"limite": int(float(limite)), "restant": int(float(restant)),
                "reset": quand.astimezone(UTC).isoformat(timespec="seconds") if quand else None}
    except (TypeError, ValueError):
        return None


def limite_dans_erreur(message: str) -> int | None:
    """Gemini, quota dépassé : « … limit: 1000, model: … » → 1000."""
    trouve = re.search(r"limit:\s*(\d+)", message or "")
    return int(trouve.group(1)) if trouve else None


# --- Le compte de Déclic ---------------------------------------------------------------------
class Quotas:
    def __init__(self, fichier: Path, horloge=lambda: dt.datetime.now(UTC)):
        self.fichier = fichier
        self.horloge = horloge

    def _lire(self) -> dict:
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
            return donnees if isinstance(donnees, dict) else {}
        except (OSError, ValueError):
            return {}

    def _ecrire(self, donnees: dict) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        self.fichier.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")

    def _periode(self, fournisseur: str, entree: dict) -> dict:
        """Remet le compte à zéro si la date de remise à zéro est passée."""
        maintenant = self.horloge()
        reset = entree.get("reset")
        if reset and dt.datetime.fromisoformat(reset) <= maintenant:
            entree = {k: v for k, v in entree.items() if k in ("limite_apprise",)}
        if not entree.get("reset") and fournisseur == "gemini":
            entree["reset"] = prochain_minuit_pacifique(maintenant).isoformat(timespec="seconds")
        return entree

    def noter(self, fournisseur: str, entetes: dict | None = None) -> dict:
        """Une requête vient de partir (et d'aboutir)."""
        donnees = self._lire()
        entree = self._periode(fournisseur, donnees.get(fournisseur, {}))
        entree["requetes"] = entree.get("requetes", 0) + 1
        venu = depuis_entetes(entetes or {}, self.horloge())
        if venu:
            entree["fournisseur"] = venu
            if venu["reset"]:
                entree["reset"] = venu["reset"]
        donnees[fournisseur] = entree
        self._ecrire(donnees)
        return entree

    def apprendre_limite(self, fournisseur: str, limite: int) -> None:
        donnees = self._lire()
        entree = self._periode(fournisseur, donnees.get(fournisseur, {}))
        entree["limite_apprise"] = limite
        donnees[fournisseur] = entree
        self._ecrire(donnees)

    def etat(self, fournisseur: str, limite_reglee: int | None = None) -> dict:
        """{"utilise", "limite" (ou None), "reset" (datetime ou None), "source"}."""
        entree = self._periode(fournisseur, self._lire().get(fournisseur, {}))
        venu = entree.get("fournisseur")
        reset = entree.get("reset")
        reset = dt.datetime.fromisoformat(reset) if reset else None
        if venu:
            return {"utilise": venu["limite"] - venu["restant"], "limite": venu["limite"], "reset": reset,
                    "source": "fournisseur"}
        return {"utilise": entree.get("requetes", 0), "limite": limite_reglee or entree.get("limite_apprise"),
                "reset": reset, "source": "declic"}


def resume(etat: dict, maintenant: dt.datetime | None = None) -> str:
    """« 12 / 1 000 requêtes · remise à zéro à 09:00 » (heure locale du PC)."""
    utilise, limite = etat["utilise"], etat["limite"]
    texte = f"{utilise} / {limite:,} requêtes".replace(",", " ") if limite else \
        f"{utilise} requête{'s' if utilise > 1 else ''} depuis la remise à zéro"
    reset = etat.get("reset")
    if reset:
        local = reset.astimezone()
        aujourdhui = (maintenant or dt.datetime.now(UTC)).astimezone().date()
        quand = f"{local:%H:%M}" if local.date() == aujourdhui else \
            f"demain {local:%H:%M}" if local.date() == aujourdhui + dt.timedelta(days=1) else f"le {local:%d/%m à %H:%M}"
        texte += f" · remise à zéro {'à ' if local.date() == aujourdhui else ''}{quand}"
    return texte
