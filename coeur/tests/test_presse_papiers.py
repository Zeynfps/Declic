"""Historique du presse-papiers (fausse plateforme, dossier temporaire)."""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from declic.chemins import Chemins
from declic.plateforme.base import Plateforme
from declic.registre import Registre


class PlateformePresse(Plateforme):
    nom = "test"

    def __init__(self):
        self.copies: list[str] = []
        self.colles: list[str] = []
        self.rappel = None

    def copier_texte(self, texte):
        self.copies.append(texte)

    def coller_texte(self, texte):
        self.colles.append(texte)

    def surveiller_presse_papiers(self, rappel):
        self.rappel = rappel


class TestPressePapiers(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        racine = Path(self._dossier.name)
        self.chemins = Chemins(racine / "config", racine / "donnees")
        self.plateforme = PlateformePresse()
        self.registre = Registre(self.plateforme, self.chemins)
        self.pp = next(m for m in self.registre.modules if m.nom == "pp")
        self.pp.horloge = lambda: dt.datetime(2026, 11, 25, 19, 0)

    def tearDown(self):
        self.registre.historique.fermer()
        self._dossier.cleanup()

    def test_historique_dans_l_ordre_et_sans_doublon(self):
        self.registre.demarrer_automatisations()  # branche l'écoute de la plateforme
        for copie in ("premier", "deuxième\nsur deux lignes", "premier", "   ", "troisième"):
            self.plateforme.rappel(copie)
        resultats = [r for r in self.registre.rechercher("pp", 20) if r.module == "pp"]
        self.assertEqual([r.titre for r in resultats], ["troisième", "premier", "deuxième"])
        self.assertEqual({r.section for r in resultats}, {"Presse-papiers"})
        self.assertIn("2 lignes", resultats[2].sous_titre)
        self.assertEqual([r.titre for r in self.registre.rechercher("pp deux", 20) if r.module == "pp"], ["deuxième"])

    def test_coller_et_garder_entre_deux_demarrages(self):
        self.pp.ajouter("adresse@exemple.fr")
        r = self.registre.rechercher("presse-papiers", 5)[0]
        self.assertEqual(self.registre.executer(r.commande, r.argument).message, "Collé")
        self.assertEqual(self.plateforme.colles, ["adresse@exemple.fr"])
        autre = Registre(PlateformePresse(), self.chemins)  # relu depuis le disque
        self.assertEqual(autre.rechercher("pp", 5)[0].titre, "adresse@exemple.fr")
        autre.historique.fermer()

    def test_effacer_et_vide(self):
        self.pp.ajouter("x")
        self.registre.executer("pp.effacer", None)
        self.assertEqual([r.titre for r in self.registre.rechercher("pp", 5) if r.module == "pp"],
                         ["Rien de copié pour l'instant"])
        self.assertFalse(any(r.module == "pp" for r in self.registre.rechercher("ppx", 5)))


if __name__ == "__main__":
    unittest.main()
