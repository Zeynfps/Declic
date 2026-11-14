"""Emplacements des fichiers de Déclic, selon le système.

Linux   : ~/.config/declic (réglages) et ~/.local/share/declic (données)
Windows : %APPDATA%\\Declic (réglages) et %LOCALAPPDATA%\\Declic (données)

Les variables DECLIC_CONFIG et DECLIC_DONNEES remplacent ces dossiers (utile pour les tests).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Chemins:
    config: Path
    donnees: Path

    @property
    def scripts(self) -> Path:
        return self.config / "scripts"

    @property
    def liens(self) -> Path:
        return self.config / "liens.toml"

    @property
    def snippets(self) -> Path:
        return self.config / "snippets.toml"

    @property
    def favoris(self) -> Path:
        return self.config / "favoris.toml"

    @property
    def regles(self) -> Path:
        return self.config / "regles.toml"

    @property
    def historique(self) -> Path:
        return self.donnees / "historique.sqlite3"

    @property
    def jeton(self) -> Path:
        return self.donnees / "jeton"

    @property
    def serveur(self) -> Path:
        """Fichier lu par les interfaces pour trouver le service (port + jeton)."""
        return self.donnees / "serveur.json"

    def creer(self) -> "Chemins":
        for dossier in (self.config, self.donnees, self.scripts):
            dossier.mkdir(parents=True, exist_ok=True)
        return self


def par_defaut() -> Chemins:
    config = os.environ.get("DECLIC_CONFIG")
    donnees = os.environ.get("DECLIC_DONNEES")
    if sys.platform == "win32":
        base_config = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Declic"
        base_donnees = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Declic"
    else:
        base_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "declic"
        base_donnees = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "declic"
    return Chemins(Path(config) if config else base_config, Path(donnees) if donnees else base_donnees)
