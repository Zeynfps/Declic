"""Scripts personnels : la façon la plus simple d'ajouter ses propres commandes.

Déposez un script dans ~/.config/declic/scripts/ avec un en-tête comme :

    #!/bin/bash
    # @declic titre: Ouvrir mon mémoire
    # @declic description: Ouvre le dossier du mémoire
    # @declic icone: folder-documents-symbolic
    # @declic argument: recherche        (facultatif : le texte tapé après le titre)

La sortie du script (stdout) est affichée dans la barre.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from declic.modele import Commande, Reponse
from declic import texte
from declic.modules import Module

_ENTETE = re.compile(r"^\s*(?:#|//|--|REM)\s*@declic\s+([a-z_]+)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_DELAI = 30  # secondes


def lire_entete(chemin: Path) -> dict[str, str]:
    infos: dict[str, str] = {}
    try:
        with chemin.open(encoding="utf-8", errors="replace") as f:
            for _, ligne in zip(range(40), f):
                m = _ENTETE.match(ligne)
                if m:
                    infos[m.group(1).casefold()] = m.group(2)
    except OSError:
        pass
    return infos


def commande_pour(chemin: Path) -> list[str]:
    if os.access(chemin, os.X_OK) and sys.platform != "win32":
        return [str(chemin)]
    suffixe = chemin.suffix.casefold()
    if suffixe == ".py":
        return [sys.executable, str(chemin)]
    if suffixe in (".ps1",):
        return ["powershell", "-NoProfile", "-File", str(chemin)]
    if suffixe in (".bat", ".cmd"):
        return ["cmd", "/c", str(chemin)]
    return ["sh", str(chemin)]


class Scripts(Module):
    nom = "script"

    def _executer(self, chemin: Path, titre: str):
        def action(contexte, argument):
            args = commande_pour(chemin) + ([argument] if argument else [])
            try:
                fini = subprocess.run(args, capture_output=True, text=True, timeout=_DELAI, cwd=chemin.parent)
            except subprocess.TimeoutExpired:
                return Reponse.erreur(f"« {titre} » a dépassé {_DELAI} s.")
            sortie = (fini.stdout or "").strip()
            if fini.returncode != 0:
                return Reponse(statut="erreur", message=f"« {titre} » a échoué (code {fini.returncode})",
                               texte=(fini.stderr or sortie).strip()[-4000:], fermer=False)
            premiere = sortie.splitlines()[0] if sortie else f"« {titre} » terminé"
            return Reponse(message=premiere[:120], texte=sortie[-4000:], fermer=not sortie or "\n" not in sortie)
        return action

    def commandes(self) -> list[Commande]:
        dossier = self.contexte.chemins.scripts
        if not dossier.is_dir():
            return []
        commandes = []
        for chemin in sorted(dossier.iterdir()):
            if not chemin.is_file() or chemin.name.startswith("."):
                continue
            infos = lire_entete(chemin)
            if "titre" not in infos:
                continue
            titre = infos["titre"]
            commandes.append(Commande(
                id=f"script.{texte.normaliser(chemin.stem).replace(' ', '-')}", titre=titre,
                description=infos.get("description", f"Script {chemin.name}"),
                icone=infos.get("icone", "utilities-terminal-symbolic"),
                mots_cles=tuple(m.strip() for m in infos.get("mots_cles", "").split(",") if m.strip()),
                argument=infos.get("argument"), action=self._executer(chemin, titre),
            ))
        return commandes
