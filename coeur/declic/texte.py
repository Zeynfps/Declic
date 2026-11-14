"""Normalisation du texte et correspondance approximative (« fuzzy »).

Le score va de 0 (aucune correspondance) à 100 (identique).
Les accents et la casse sont ignorés : « ecl » trouve « Éclairage ».
"""
from __future__ import annotations

import re
import unicodedata

_MOTS = re.compile(r"[a-z0-9]+")


def normaliser(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte.casefold())
    return "".join(c for c in decompose if not unicodedata.combining(c)).strip()


def mots(texte: str) -> list[str]:
    return _MOTS.findall(normaliser(texte))


def _sous_sequence(requete: str, cible: str) -> float:
    """Toutes les lettres de la requête apparaissent dans l'ordre. Bonus si elles se suivent."""
    i = 0
    suites = 0
    precedent = -2
    for j, c in enumerate(cible):
        if i < len(requete) and c == requete[i]:
            if j == precedent + 1:
                suites += 1
            precedent = j
            i += 1
    if i < len(requete):
        return 0.0
    return 25.0 + 15.0 * suites / max(1, len(requete) - 1)


def score(requete: str, cible: str) -> float:
    q = normaliser(requete)
    c = normaliser(cible)
    if not q or not c:
        return 0.0
    if q == c:
        return 100.0
    if c.startswith(q):
        return 90.0 - min(10.0, (len(c) - len(q)) * 0.2)
    mots_cible = mots(c)
    mots_requete = mots(q)
    # chaque mot de la requête commence un mot de la cible : « vid corb » → « Vider la corbeille »
    if mots_requete and all(any(m.startswith(r) for m in mots_cible) for r in mots_requete):
        return 80.0
    # initiales : « vlc » → « Vider La Corbeille »
    initiales = "".join(m[0] for m in mots_cible)
    if len(q) >= 2 and " " not in q and initiales.startswith(q):
        return 75.0
    if q in c:
        return 50.0  # au milieu d'un mot : moins pertinent qu'un début de mot
    return _sous_sequence(q.replace(" ", ""), c.replace(" ", ""))


def meilleur_score(requete: str, cibles) -> float:
    return max((score(requete, c) for c in cibles if c), default=0.0)
