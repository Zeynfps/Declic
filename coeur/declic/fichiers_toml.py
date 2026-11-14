"""Ajout d'entrées dans les fichiers TOML de l'utilisateur, sans toucher au reste du fichier.

La bibliothèque standard sait lire le TOML (tomllib) mais pas l'écrire : on ajoute un bloc
« [[table]] » à la fin du texte existant (commentaires conservés), on vérifie que le tout se relit,
puis on remplace le fichier d'un coup (pas de fichier à moitié écrit en cas de panne).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from pathlib import Path


def chaine(valeur: str) -> str:
    """Chaîne TOML de base. Les échappements de JSON (\\" \\\\ \\n \\t \\uXXXX) sont aussi ceux du TOML."""
    return json.dumps(valeur, ensure_ascii=False)


def valeur(v) -> str:
    """Valeur TOML : texte, booléen, nombre, liste ou petit tableau en ligne."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return chaine(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(valeur(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {valeur(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"type non pris en charge : {type(v).__name__}")


def ajouter_bloc(fichier: Path, table: str, valeurs: dict, entete: str = "") -> None:
    texte = fichier.read_text(encoding="utf-8") if fichier.exists() else entete
    if texte and not texte.endswith("\n"):
        texte += "\n"
    bloc = f"\n[[{table}]]\n" + "".join(f"{cle} = {valeur(v)}\n" for cle, v in valeurs.items())
    _ecrire(fichier, texte + bloc)


_ENTETE_TABLE = re.compile(r"^\s*\[")


def retirer_bloc(fichier: Path, table: str, garder) -> int:
    """Retire les blocs « [[table]] » dont l'entrée lue (dict) donne garder(entree) == False.

    Le reste du texte (commentaires, autres tables) est conservé tel quel. Renvoie le nombre de blocs retirés.
    """
    texte = fichier.read_text(encoding="utf-8")
    entete_cible = re.compile(rf"^\s*\[\[\s*{re.escape(table)}\s*\]\]\s*(#.*)?$")
    # Découpe en morceaux : chaque ligne d'en-tête de table commence un nouveau morceau
    morceaux: list[list[str]] = [[]]
    for ligne in texte.splitlines(keepends=True):
        if _ENTETE_TABLE.match(ligne):
            morceaux.append([])
        morceaux[-1].append(ligne)
    conserves, retires = [], 0
    for morceau in morceaux:
        if morceau and entete_cible.match(morceau[0]):
            entree = tomllib.loads("".join(morceau))[table][0]
            if not garder(entree):
                retires += 1
                continue
        conserves.append("".join(morceau))
    if retires:
        _ecrire(fichier, "".join(conserves))
    return retires


def _ecrire(fichier: Path, contenu: str) -> None:
    tomllib.loads(contenu)  # lève une erreur plutôt que d'écrire un fichier illisible
    fichier.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(dir=fichier.parent, prefix=f".{fichier.name}.")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            f.write(contenu)
        os.replace(temporaire, fichier)
    except BaseException:
        Path(temporaire).unlink(missing_ok=True)
        raise
