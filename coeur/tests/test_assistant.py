"""IA dans la barre : configuration, actions sur la sélection (sans appel réseau : ia_api est remplacé)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from declic import ia_api
from declic.chemins import Chemins
from declic.plateforme.base import Plateforme
from declic.registre import Registre


class PlateformeSecrets(Plateforme):
    nom = "test"

    def __init__(self):
        self.secrets = {}

    def secret_enregistrer(self, nom, valeur):
        self.secrets[nom] = valeur

    def secret_lire(self, nom):
        return self.secrets.get(nom)

    def secret_supprimer(self, nom):
        self.secrets.pop(nom, None)

    def ouvrir(self, cible):
        pass


class TestAssistant(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        racine = Path(self._dossier.name)
        self.chemins = Chemins(racine / "config", racine / "donnees")
        self.plateforme = PlateformeSecrets()
        self.registre = Registre(self.plateforme, self.chemins)

    def tearDown(self):
        self.registre.historique.fermer()
        self._dossier.cleanup()

    def _configurer(self, fournisseur="deepseek", modele=""):
        with mock.patch.object(ia_api, "modeles", return_value=["deepseek-chat", "deepseek-reasoner"]):
            return self.registre.creer("fournisseur-ia", {"fournisseur": fournisseur, "cle": "sk-test", "modele": modele})

    def test_sans_ia_on_propose_de_configurer(self):
        resultats = self.registre.rechercher("", 8, selection="Bonjour tout le monde")
        self.assertEqual(resultats[0].commande, "creer.fournisseur-ia")

    def test_configuration_cle_secrete_et_modele_choisi(self):
        r = self._configurer()
        self.assertEqual(r["statut"], "ok", r)
        self.assertEqual(self.plateforme.secrets, {"deepseek": "sk-test"})
        reglages = json.loads((self.chemins.config / "ia.json").read_text(encoding="utf-8"))
        self.assertEqual(reglages, {"fournisseurs": {"deepseek": {"modele": "deepseek-chat"}}, "actif": "deepseek"})
        self.assertNotIn("sk-test", json.dumps(reglages))  # la clé n'est jamais dans le fichier
        self.assertEqual(self._configurer(modele="gpt-9")["champ"], "modele")  # modèle inconnu chez DeepSeek

    def test_actions_sur_la_selection(self):
        self._configurer()
        actions = self.registre.rechercher("", 20, selection="Je suis allé a la plage")
        commandes = [r.commande for r in actions]
        self.assertEqual(commandes[:3], ["assistant.traduire", "assistant.corriger", "assistant.reformuler"])
        self.assertEqual(commandes[-1], "liens.g")
        self.assertEqual({r.section for r in actions}, {"Texte sélectionné"})
        # ce qu'on tape devient une question sur le texte
        question = self.registre.rechercher("c'est quel temps ?", 20, selection="Je suis allé a la plage")[0]
        self.assertEqual(question.commande, "assistant.question-selection")
        self.assertIn("Je suis allé a la plage", question.argument)

        with mock.patch.object(ia_api, "demander", return_value="Je suis allé à la plage.") as appel:
            reponse = self.registre.executer("assistant.corriger", "Je suis allé a la plage")
        self.assertEqual((reponse.texte, reponse.fermer), ("Je suis allé à la plage.", False))
        fournisseur, cle, modele, _systeme, consigne = appel.call_args.args[:5]
        self.assertEqual((fournisseur.cle, cle, modele), ("deepseek", "sk-test", "deepseek-chat"))
        self.assertIn("Corrige", consigne)

    def test_question_dans_la_barre_et_erreur_lisible(self):
        self._configurer()
        premier = self.registre.rechercher("ia combien font 2+2", 8)[0]
        self.assertEqual((premier.commande, premier.argument), ("assistant.demander", "combien font 2+2"))
        with mock.patch.object(ia_api, "demander", side_effect=ia_api.ErreurIA("clé refusée (401)")):
            reponse = self.registre.executer("assistant.demander", "bonjour")
        self.assertEqual(reponse.statut, "erreur")
        self.assertIn("clé refusée", reponse.message)

    def test_choix_du_modele_par_defaut(self):
        claude = ia_api.FOURNISSEURS["claude"]
        self.assertEqual(ia_api.choisir_modele(claude, ["claude-opus-5-5", "claude-haiku-5-5"]), "claude-opus-5-5")
        gemini = ia_api.FOURNISSEURS["gemini"]
        disponibles = ["text-embedding-004", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash-lite",
                       "gemini-3.10-flash-lite", "gemini-3.1-flash-lite-preview", "gemini-3.8-flash-lite-tts"]
        self.assertEqual(ia_api.choisir_modele(gemini, disponibles), "gemini-3.10-flash-lite")
        self.assertEqual(ia_api.choisir_modele(gemini, ["gemini-2.5-pro", "gemini-2.5-flash"]), "gemini-2.5-flash")

    def test_modele_retire_remplace_tout_seul(self):
        self._configurer()
        retire = ia_api.ErreurIA("modèle retiré", "deepseek-v9")
        with mock.patch.object(ia_api, "demander", side_effect=[retire, "Bonjour"]) as appel:
            reponse = self.registre.executer("assistant.demander", "dis bonjour")
        self.assertEqual(reponse.texte, "Bonjour")
        self.assertEqual(appel.call_args.args[2], "deepseek-v9")
        reglages = json.loads((self.chemins.config / "ia.json").read_text(encoding="utf-8"))
        self.assertEqual(reglages["fournisseurs"]["deepseek"]["modele"], "deepseek-v9")

    def test_messages_d_erreur_lisibles(self):
        gemini = '[{"error": {"code": 404, "message": "This model models/gemini-2.5-flash is no longer available. Please update your code to use models/gemini-3.8-flash for the latest."}}]'
        self.assertIn("no longer available", ia_api._message_erreur(gemini))
        self.assertEqual(ia_api._message_erreur('{"error": {"message": "invalid x-api-key"}}'), "invalid x-api-key")
        self.assertEqual(ia_api._message_erreur("pas du json"), "pas du json")


if __name__ == "__main__":
    unittest.main()
