"""Tests de la plateforme Windows (lancés seulement sous Windows)."""
import sys
import unittest

if sys.platform != "win32":
    raise unittest.SkipTest("plateforme Windows uniquement")

from declic.plateforme.windows import (  # noqa: E402
    PlateformeWindows, eclairage_nocturne_actif, eclairage_nocturne_change, profils_wifi, sans_requete)

# Enregistrements réels de l'éclairage nocturne (Windows 11), désactivé puis activé
NOCTURNE_COUPE = bytes.fromhex(
    "43420100" "0A020100" "2A0695A1C2D606" "2A2B0E13" "43420100" "D00A02C614D780B9D68490D7EE0100" "00000000")
NOCTURNE_ACTIF = bytes.fromhex(
    "43420100" "0A020100" "2A06F9979CD806" "2A2B0E15" "43420100" "1000" "D00A02C614D780B9D68490D7EE0100" "00000000")

SORTIE_NETSH = (
    "\r\nProfils sur l’interface Wi-Fi\u00a0:\r\n\r\n"
    "Profils de stratégies de groupe (lecture seule)\r\n---------------------------------\r\n    <Aucun>\r\n\r\n"
    "Profils utilisateurs\r\n-------------\r\n"
    "    Profil Tous les utilisateurs    \u00a0: eduroam\r\n"
    "    Profil Tous les utilisateurs    \u00a0: Café de la Gare\r\n"
    "    All User Profile     : Maison\r\n"
)


class TestWindows(unittest.TestCase):
    def test_profils_wifi_francais_et_anglais(self):
        self.assertEqual(profils_wifi(SORTIE_NETSH), ["Café de la Gare", "eduroam", "Maison"])

    def test_profils_wifi_sans_wifi(self):
        self.assertEqual(profils_wifi(""), [])

    def test_fonctions_prises_en_charge(self):
        p = PlateformeWindows()
        for methode in ("lister_applications", "copier_texte", "lire_volume", "coffre_lister", "surveiller",
                        "chercher_fichiers", "basculer_theme_sombre", "basculer_wifi", "definir_profil_energie"):
            self.assertTrue(p.prend_en_charge(methode), methode)
        # Les mêmes fonctions que sous Linux
        for methode in ("basculer_eclairage_nocturne", "basculer_ne_pas_deranger", "basculer_mode_avion",
                        "saisir_identifiant", "valider_page", "adresse_page"):
            self.assertTrue(p.prend_en_charge(methode), methode)

    def test_eclairage_nocturne(self):
        self.assertFalse(eclairage_nocturne_actif(NOCTURNE_COUPE))
        self.assertTrue(eclairage_nocturne_actif(NOCTURNE_ACTIF))
        date = 1795000000
        active = eclairage_nocturne_change(NOCTURNE_COUPE, True, date)
        self.assertTrue(eclairage_nocturne_actif(active))
        self.assertEqual(active[18], 0x15)
        self.assertEqual(len(active), len(NOCTURNE_COUPE) + 2)
        # Aller-retour : seul l'horodatage change
        retour = eclairage_nocturne_change(active, False, date)
        self.assertEqual(retour[:10] + retour[15:], NOCTURNE_COUPE[:10] + NOCTURNE_COUPE[15:])
        self.assertEqual(eclairage_nocturne_change(NOCTURNE_ACTIF, True, date)[15:], NOCTURNE_ACTIF[15:])
        with self.assertRaises(Exception):
            eclairage_nocturne_change(b"autre chose", True, date)

    def test_adresse_sans_requete(self):
        self.assertEqual(sans_requete("https://Claude.ai/new?q=bonjour"), "https://claude.ai/new")
        self.assertEqual(sans_requete("https://chatgpt.com/?q=x"), "https://chatgpt.com/")
        self.assertIsNone(sans_requete("github.com/rien"))
        self.assertIsNone(sans_requete(None))

    def test_etats_lisibles(self):
        p = PlateformeWindows()
        self.assertIn(p.sur_secteur(), (True, False, None))
        self.assertIn(p.session_verrouillee(), (True, False, None))


if __name__ == "__main__":
    unittest.main()
