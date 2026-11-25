"""Indicateur « activé / désactivé » des bascules dans la barre."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from declic.chemins import Chemins
from declic.etats import EtatsBascules
from declic.plateforme.base import Plateforme
from declic.registre import Registre


class PlateformeBascules(Plateforme):
    nom = "test"

    def __init__(self):
        self.bluetooth = True
        self.lectures = 0

    def basculer_bluetooth(self):
        self.bluetooth = not self.bluetooth
        return self.bluetooth

    def etat_bascule(self, nom):
        self.lectures += 1
        if nom != "bluetooth":
            raise KeyError(nom)
        return self.bluetooth


class TestEtats(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        racine = Path(self._dossier.name)
        self.plateforme = PlateformeBascules()
        self.registre = Registre(self.plateforme, Chemins(racine / "config", racine / "donnees"))
        self.temps = [0.0]
        self.registre.contexte.etats = EtatsBascules(self.plateforme, horloge=lambda: self.temps[0], synchrone=True)

    def tearDown(self):
        self.registre.historique.fermer()
        self._dossier.cleanup()

    def _etat(self, requete="bluetooth"):
        r = next(r for r in self.registre.rechercher(requete, 8) if r.commande == "systeme.bluetooth")
        return r.etat, r.en_dict()["etat"]

    def test_etat_affiche_puis_mis_a_jour_apres_bascule(self):
        self.assertEqual(self._etat(), (True, True))
        self.registre.executer("systeme.bluetooth", None)
        lectures = self.plateforme.lectures
        self.assertEqual(self._etat(), (False, False))  # connu par la bascule, sans relire
        self.assertEqual(self.plateforme.lectures, lectures)

    def test_relu_quand_il_a_vieilli(self):
        self._etat()
        self.plateforme.bluetooth = False  # changé ailleurs (réglages de Windows…)
        self.assertEqual(self._etat()[0], True)  # encore frais : dernier état connu
        self.temps[0] += 60
        self.assertEqual(self._etat()[0], False)

    def test_pas_d_etat_pour_les_autres_commandes(self):
        autres = [r for r in self.registre.rechercher("bluetooth", 8) if r.commande != "systeme.bluetooth"]
        self.assertTrue(all(r.etat is None for r in autres))


if __name__ == "__main__":
    unittest.main()
