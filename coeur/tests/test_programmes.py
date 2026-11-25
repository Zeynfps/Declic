"""Programmes ouverts, jeux et Mode jeu (sans système réel : une fausse plateforme)."""
from __future__ import annotations

import datetime as dt
import tempfile
import tomllib
import unittest
from pathlib import Path

from declic.chemins import Chemins
from declic.plateforme.base import Plateforme
from declic.programmes import SuiviProgrammes, est_un_jeu
from declic.registre import Registre

STEAM = r"C:\Program Files (x86)\Steam\steamapps\common\Hades\Hades.exe"


class PlateformeJeux(Plateforme):
    """Programmes ouverts modifiables, « Ne pas déranger » et profil d'énergie en mémoire."""

    nom = "test"

    def __init__(self):
        self.ouverts: dict[str, str] = {"explorer": r"C:\Windows\explorer.exe"}
        self.dnd = False
        self.profil = "equilibre"
        self.bascules = 0
        self.fermes: list[str] = []

    def processus(self):
        return dict(self.ouverts)

    def fermer_application(self, nom):
        self.fermes.append(nom)
        return int(self.ouverts.pop(nom, None) is not None)

    def basculer_ne_pas_deranger(self):
        self.dnd = not self.dnd
        self.bascules += 1
        return self.dnd

    def etat_bascule(self, nom):
        assert nom == "ne_pas_deranger"
        return self.dnd

    def definir_profil_energie(self, profil):
        self.profil = profil

    def notifier(self, titre, message=""):
        pass


class TestJeux(unittest.TestCase):
    def test_reconnaitre_un_jeu(self):
        self.assertTrue(est_un_jeu("Hades", STEAM))
        self.assertTrue(est_un_jeu("League of Legends", r"C:\Riot Games\League of Legends\Game\League of Legends.exe"))
        self.assertTrue(est_un_jeu("Celeste", "/home/a/.local/share/Steam/steamapps/common/Celeste/Celeste.exe"))
        self.assertTrue(est_un_jeu("hollow", "/home/a/Games/hollow/hollow"))
        # lanceurs, clients et anti-triche rangés avec les jeux : pas des jeux
        self.assertFalse(est_un_jeu("Riot Client", r"C:\Riot Games\Riot Client\RiotClientElectron\Riot Client.exe"))
        self.assertFalse(est_un_jeu("LeagueClient", r"C:\Riot Games\League of Legends\LeagueClient.exe"))
        self.assertFalse(est_un_jeu("EpicGamesLauncher", r"C:\Program Files\Epic Games\Launcher\EpicGamesLauncher.exe"))
        self.assertFalse(est_un_jeu("steam", r"C:\Program Files (x86)\Steam\steam.exe"))
        self.assertFalse(est_un_jeu("Discord", r"C:\Users\a\AppData\Local\Discord\Discord.exe"))

    def test_suivi_ouvertures_et_jeux(self):
        suivi = SuiviProgrammes()
        self.assertEqual(suivi.comparer({"explorer": "x"}), [])  # premier relevé : rien de « nouveau »
        self.assertEqual(suivi.comparer({"explorer": "x", "Discord": "d"}), [("application.ouverte", "Discord")])
        # un jeu en deux programmes (lanceur interne, puis jeu) : un seul « jeu.lance »
        jeu = {"explorer": "x", "Discord": "d", "Hades": STEAM}
        self.assertEqual(suivi.comparer(jeu), [("application.ouverte", "Hades"), ("jeu.lance", "Hades")])
        deux = {**jeu, "HadesHelper2": STEAM.replace("Hades.exe", "Hades2.exe")}
        self.assertEqual(suivi.comparer(deux), [("application.ouverte", "HadesHelper2")])
        self.assertTrue(suivi.jeu_en_cours)
        self.assertEqual(suivi.comparer({"explorer": "x"}),
                         [("application.fermee", "Discord"), ("application.fermee", "Hades"),
                          ("application.fermee", "HadesHelper2"), ("jeu.ferme", "Hades")])
        self.assertFalse(suivi.jeu_en_cours)


class TestModeJeu(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        racine = Path(self._dossier.name)
        self.chemins = Chemins(racine / "config", racine / "donnees")
        self.plateforme = PlateformeJeux()
        self.registre = Registre(self.plateforme, self.chemins)
        self.auto = self.registre.automatisations
        self.auto.synchrone = True
        self.auto.horloge = lambda: dt.datetime(2026, 11, 25, 21, 0)

    def tearDown(self):
        self.registre.historique.fermer()
        self._dossier.cleanup()

    def test_activer_desactiver_sans_double_bascule(self):
        self.assertEqual(self.registre.executer("systeme.ne-pas-deranger-activer", None).statut, "ok")
        self.assertEqual(self.registre.executer("systeme.ne-pas-deranger-activer", None).statut, "ok")
        self.assertTrue(self.plateforme.dnd)
        self.assertEqual(self.plateforme.bascules, 1)  # déjà activé : pas rebasculé
        self.registre.executer("systeme.ne-pas-deranger-desactiver", None)
        self.assertFalse(self.plateforme.dnd)

    def test_mode_jeu_complet(self):
        self.auto.releve_programmes()  # premier relevé
        r = self.registre.creer("mode-jeu", {"ne_pas_deranger": "oui", "energie": "performance", "volume": "",
                                             "fermer": "OneDrive.exe, "})
        self.assertEqual(r["statut"], "ok", r)
        blocs = tomllib.loads(self.chemins.regles.read_text(encoding="utf-8"))["regle"]
        self.assertEqual([b["nom"] for b in blocs], ["Mode jeu", "Mode jeu (fin)"])
        self.assertEqual(blocs[0]["alors"], ["systeme.ne-pas-deranger-activer", "systeme.energie-performance",
                                             "systeme.fermer-application:OneDrive"])

        self.plateforme.ouverts["OneDrive"] = r"C:\OneDrive\OneDrive.exe"
        self.plateforme.ouverts["Hades"] = STEAM
        self.auto.releve_programmes()
        self.assertTrue(self.plateforme.dnd)
        self.assertEqual(self.plateforme.profil, "performance")
        self.assertEqual(self.plateforme.fermes, ["OneDrive"])

        del self.plateforme.ouverts["Hades"]
        self.auto.releve_programmes()
        self.assertFalse(self.plateforme.dnd)
        self.assertEqual(self.plateforme.profil, "equilibre")

        # recréer remplace ; supprimer retire les deux règles
        self.assertEqual(self.registre.creer("mode-jeu", {"ne_pas_deranger": "oui", "energie": "non"})["statut"], "ok")
        self.assertEqual(len(self.auto.regles), 2)
        self.assertEqual(self.registre.supprimer("mode-jeu", "auto.mode-jeu")["statut"], "ok")
        self.assertEqual(self.auto.regles, [])

    def test_regle_application_avec_inverse_et_condition(self):
        r = self.registre.creer("automatisation", {
            "nom": "Réunion", "declencheur": "application", "application": "Teams.exe", "fin": "inverse",
            "jours": "tous", "commandes": "systeme.ne-pas-deranger-activer"})
        self.assertEqual(r["statut"], "ok", r)
        noms = [regle.nom for regle in self.auto.regles]
        self.assertEqual(noms, ["Réunion", "Réunion (fin)"])
        self.assertEqual(self.auto.regles[1].quand.evenement, "application.fermee")
        self.assertEqual(self.registre.declencher("application.ouverte", "teams"), ["Réunion"])
        self.assertTrue(self.plateforme.dnd)
        self.assertEqual(self.registre.declencher("application.fermee", "Teams"), ["Réunion (fin)"])
        self.assertFalse(self.plateforme.dnd)

    def test_condition_application_ouverte(self):
        self.chemins.regles.write_text(
            '[[regle]]\nnom = "Discord"\nquand = "manuel"\nsi = { application = "discord", jeu_en_cours = false }\n'
            'alors = ["systeme.ne-pas-deranger-activer"]\n', encoding="utf-8")
        self.auto.recharger()
        regle = self.auto.regles[0]
        maintenant = self.auto.horloge()
        self.assertFalse(regle.si.remplies(maintenant, self.auto.programmes))  # Discord fermé
        self.plateforme.ouverts["Discord"] = "d"
        self.auto.releve_programmes()
        self.assertTrue(regle.si.remplies(maintenant, self.auto.programmes))
        self.plateforme.ouverts["Hades"] = STEAM
        self.auto.releve_programmes()
        self.assertFalse(regle.si.remplies(maintenant, self.auto.programmes))  # un jeu tourne


if __name__ == "__main__":
    unittest.main()
