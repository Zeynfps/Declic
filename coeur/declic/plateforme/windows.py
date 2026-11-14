"""Plateforme Windows : ÉBAUCHE, non testée.

Seules quelques fonctions simples sont prévues. Tout le reste est « non pris en charge »,
et les commandes correspondantes sont masquées automatiquement.
À compléter et tester sur une vraie machine Windows.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from declic.plateforme.base import Application, Plateforme


class PlateformeWindows(Plateforme):
    nom = "Windows"

    def lister_applications(self) -> list[Application]:
        # Raccourcis du menu Démarrer (utilisateur et commun)
        dossiers = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]
        applis = {}
        for dossier in dossiers:
            if dossier.is_dir():
                for lnk in dossier.rglob("*.lnk"):
                    applis.setdefault(lnk.stem.casefold(), Application(id=str(lnk), nom=lnk.stem))
        return sorted(applis.values(), key=lambda a: a.nom.casefold())

    def lancer_application(self, app_id: str) -> None:
        os.startfile(app_id)  # type: ignore[attr-defined]

    def ouvrir(self, cible: str) -> None:
        os.startfile(cible)  # type: ignore[attr-defined]

    def copier_texte(self, texte: str) -> None:
        subprocess.run(["clip"], input=texte.encode("utf-16-le"), check=True, timeout=5)

    def verrouiller(self) -> None:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)

    def redemarrer(self) -> None:
        subprocess.run(["shutdown", "/r", "/t", "0"], check=True)

    def eteindre(self) -> None:
        subprocess.run(["shutdown", "/s", "/t", "0"], check=True)

    def deconnecter(self) -> None:
        subprocess.run(["shutdown", "/l"], check=True)
