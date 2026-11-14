"""Historique d'utilisation (SQLite) : fréquence et récence, pour classer les résultats."""
from __future__ import annotations

import math
import sqlite3
import threading
import time
from pathlib import Path


class Historique:
    def __init__(self, chemin: Path | str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(chemin), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS usage (cle TEXT PRIMARY KEY, nombre INTEGER NOT NULL, dernier REAL NOT NULL)"
        )
        self._db.commit()

    def noter(self, cle: str, quand: float | None = None) -> None:
        quand = time.time() if quand is None else quand
        with self._lock:
            self._db.execute(
                "INSERT INTO usage(cle, nombre, dernier) VALUES (?, 1, ?) "
                "ON CONFLICT(cle) DO UPDATE SET nombre = nombre + 1, dernier = excluded.dernier",
                (cle, quand),
            )
            self._db.commit()

    def bonus(self, cle: str, maintenant: float | None = None) -> float:
        """Multiplicateur ≥ 1 : plus la commande est utilisée, et récemment, plus il est grand."""
        with self._lock:
            ligne = self._db.execute("SELECT nombre, dernier FROM usage WHERE cle = ?", (cle,)).fetchone()
        if not ligne:
            return 1.0
        nombre, dernier = ligne
        maintenant = time.time() if maintenant is None else maintenant
        jours = max(0.0, (maintenant - dernier) / 86400)
        recence = 0.3 * math.exp(-jours / 7)  # s'efface en une à deux semaines
        return 1.0 + 0.25 * math.log1p(nombre) + recence

    def effacer(self) -> None:
        """Oublie tout l'usage : la barre vide ne propose plus de suggestions."""
        with self._lock:
            self._db.execute("DELETE FROM usage")
            self._db.commit()

    def fermer(self) -> None:
        with self._lock:
            self._db.close()
