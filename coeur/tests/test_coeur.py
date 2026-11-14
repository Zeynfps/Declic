"""Tests du cœur de Déclic, avec une fausse plateforme (rien n'est modifié sur la machine).

Lancer :  cd coeur && python3 -m unittest -v
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from declic import texte
from declic.chemins import Chemins
from declic.modules import calcul
from declic.modules.snippets import remplir
from declic.plateforme.base import Application, Plateforme
from declic.registre import Registre
from declic.serveur import creer_serveur


class FaussePlateforme(Plateforme):
    """Enregistre les appels au lieu d'agir."""

    nom = "test"

    def __init__(self):
        self.appels: list[tuple] = []
        self.sombre = False

    def lister_applications(self):
        return [Application("org.gnome.Nautilus.desktop", "Fichiers", "Gestionnaire de fichiers",
                            mots_cles=("dossier", "explorer")),
                Application("org.zotero.Zotero.desktop", "Zotero", "Bibliographie")]

    def lancer_application(self, app_id):
        self.appels.append(("lancer", app_id))

    def ouvrir(self, cible):
        self.appels.append(("ouvrir", cible))

    def copier_texte(self, texte_):
        self.appels.append(("copier", texte_))

    def verrouiller(self):
        self.appels.append(("verrouiller",))

    def basculer_theme_sombre(self):
        self.sombre = not self.sombre
        return self.sombre


class PlateformeAvecCoffre(FaussePlateforme):
    """Fausse plateforme avec Wi-Fi connus et un trousseau en mémoire."""

    def __init__(self):
        super().__init__()
        self.coffre: dict[str, tuple[dict, str]] = {}

    def reseaux_wifi_connus(self):
        return ["Freebox", "Wifi-Fac"]

    def coffre_enregistrer(self, site, attributs, mot_de_passe):
        self.coffre[site] = (dict(attributs), mot_de_passe)

    def coffre_lister(self):
        return [{"site": k, **a} for k, (a, _m) in self.coffre.items()]

    def coffre_supprimer(self, site):
        return self.coffre.pop(site, None) is not None

    def saisir_identifiant(self, site, delai_s):
        self.appels.append(("saisir", site))

    page_affichee = None

    def adresse_page(self, pid):
        return self.page_affichee if pid == 4242 else None


class TestTexte(unittest.TestCase):
    def test_accents_et_casse(self):
        self.assertEqual(texte.normaliser("Éclairage NOCTURNE"), "eclairage nocturne")

    def test_ordre_des_scores(self):
        cible = "Vider la corbeille"
        self.assertEqual(texte.score("vider la corbeille", cible), 100)
        self.assertGreater(texte.score("vider", cible), texte.score("corb", cible))  # début > mot
        self.assertGreaterEqual(texte.score("vid corb", cible), 80)  # débuts de mots
        self.assertGreaterEqual(texte.score("vlc", cible), 75)  # initiales
        self.assertGreater(texte.score("vdrcrb", cible), 0)  # lettres dans l'ordre
        self.assertEqual(texte.score("xyz", cible), 0)


class TestCalcul(unittest.TestCase):
    def test_expressions(self):
        self.assertEqual(calcul.calculer("2+2")[0], 4)
        self.assertEqual(calcul.calculer("2,5 * 4")[0], 10)
        self.assertEqual(calcul.calculer("2^10")[0], 1024)
        self.assertAlmostEqual(calcul.calculer("racine(2)")[0], 2 ** 0.5)
        self.assertEqual(calcul.calculer("15% de 240")[0], 36)
        self.assertEqual(calcul.calculer("1 000 + 1")[0], 1001)

    def test_conversions(self):
        valeur, unite = calcul.calculer("5 km en miles")
        self.assertEqual(valeur, 3.1069)
        self.assertEqual(unite, "miles")
        self.assertAlmostEqual(calcul.calculer("100 c en f")[0], 212)
        self.assertAlmostEqual(calcul.calculer("2 ha en m2")[0], 20000)

    def test_refus(self):
        self.assertIsNone(calcul.calculer("bonjour"))
        self.assertIsNone(calcul.calculer("__import__('os').system('ls')"))
        self.assertIsNone(calcul.calculer("2 ** 99999"))
        self.assertIsNone(calcul.calculer("1/0"))
        self.assertIsNone(calcul.calculer("5 kg en km"))

    def test_format_francais(self):
        self.assertEqual(calcul.formater(1234567), "1 234 567")
        self.assertEqual(calcul.formater(2.5), "2,5")
        self.assertEqual(calcul.formater(-0.25), "-0,25")


class TestSnippets(unittest.TestCase):
    def test_variables(self):
        import datetime as dt
        self.assertEqual(remplir("{jour} {date} {heure}", dt.datetime(2026, 11, 14, 9, 5)),
                         "samedi 14/11/2026 09:05")


class BaseRegistre(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        racine = Path(self._dossier.name)
        self.chemins = Chemins(racine / "config", racine / "donnees")
        self.plateforme = FaussePlateforme()
        self.registre = Registre(self.plateforme, self.chemins)

    def tearDown(self):
        self.registre.historique.fermer()
        self._dossier.cleanup()


class TestRegistre(BaseRegistre):
    def test_commandes_non_prises_en_charge_masquees(self):
        ids = self.registre.commandes()
        self.assertIn("systeme.verrouiller", ids)  # implémenté par la fausse plateforme
        self.assertNotIn("systeme.veille", ids)  # pas implémenté → masqué
        self.assertNotIn("son.muet", ids)

    def test_recherche_application(self):
        premier = self.registre.rechercher("zot")[0]
        self.assertEqual(premier.commande, "app.org.zotero.Zotero.desktop")

    def test_recherche_par_mot_cle(self):
        ids = [r.commande for r in self.registre.rechercher("dossier")]
        self.assertIn("app.org.gnome.Nautilus.desktop", ids)

    def test_calcul_en_premier(self):
        premier = self.registre.rechercher("15% de 240")[0]
        self.assertEqual((premier.commande, premier.argument), ("calcul.copier", "36"))
        reponse = self.registre.executer(premier.commande, premier.argument)
        self.assertEqual(reponse.statut, "ok")
        self.assertIn(("copier", "36"), self.plateforme.appels)

    def test_lien_rapide(self):
        premier = self.registre.rechercher("persee céramique sigillée")[0]
        self.assertEqual(premier.commande, "liens.persee")
        self.registre.executer(premier.commande, premier.argument)
        self.assertEqual(self.plateforme.appels[-1],
                         ("ouvrir", "https://www.persee.fr/search?q=c%C3%A9ramique+sigill%C3%A9e"))

    def test_recherche_web_en_dernier_recours(self):
        resultats = self.registre.rechercher("gergovie")
        self.assertEqual(resultats[-1].commande, "liens.g")

    def test_ia_par_mot_cle(self):
        premier = self.registre.rechercher("claude pourquoi la sigillée est rouge ?")[0]
        self.assertEqual((premier.commande, premier.argument), ("ia.claude", "pourquoi la sigillée est rouge ?"))
        self.registre.executer(premier.commande, premier.argument)
        self.assertEqual(self.plateforme.appels[-1],
                         ("ouvrir", "https://claude.ai/new?q=pourquoi+la+sigill%C3%A9e+est+rouge+%3F"))

    def test_ia_gemini_copie_aussi(self):
        premier = self.registre.rechercher("gemini datation carbone 14")[0]
        self.assertEqual(premier.commande, "ia.gemini")
        self.registre.executer(premier.commande, premier.argument)
        self.assertIn(("copier", "datation carbone 14"), self.plateforme.appels)
        self.assertTrue(self.plateforme.appels[-1][1].startswith("https://gemini.google.com/app?q="))

    def test_ia_en_dernier_recours(self):
        commandes = [r.commande for r in self.registre.rechercher("a")]
        self.assertEqual(commandes[-4:], ["ia.gpt", "ia.claude", "ia.gemini", "liens.g"])
        self.assertLessEqual(len(commandes), 20)

    def _favori(self, commande, argument=None, titre="X"):
        return self.registre.executer("favoris.basculer", json.dumps(
            {"commande": commande, "argument": argument, "titre": titre, "icone": ""}))

    def test_favoris_en_haut_et_gardes_par_effacer(self):
        self.assertEqual(self._favori("ia.claude", "résume Bibracte", "Claude : « résume Bibracte »").statut, "ok")
        self._favori("systeme.theme-sombre", titre="Thème sombre")
        for _ in range(3):
            self.registre.executer("systeme.theme-sombre")
        vide = self.registre.rechercher("")
        self.assertEqual([(r.commande, r.argument, r.section) for r in vide[:2]],
                         [("ia.claude", "résume Bibracte", "Favoris"), ("systeme.theme-sombre", None, "Favoris")])
        self.assertEqual([r.commande for r in vide].count("systeme.theme-sombre"), 1)  # pas aussi en suggestion
        self.registre.executer("declic.effacer-suggestions")
        self.assertEqual([r.commande for r in self.registre.rechercher("")],
                         ["ia.claude", "systeme.theme-sombre"])
        self.assertTrue(any(r.favori for r in self.registre.rechercher("theme sombre")))
        # retrait (bascule) et liste dans « Mes ajouts »
        self.assertEqual([e.titre for e in self.registre.elements("favori")],
                         ["Claude : « résume Bibracte »", "Thème sombre"])
        self._favori("systeme.theme-sombre")
        self.assertEqual([r.commande for r in self.registre.rechercher("")], ["ia.claude"])
        self.assertEqual(self.registre.supprimer("favori", "ia.claude\x1frésume Bibracte")["statut"], "ok")
        self.assertEqual(self.registre.rechercher(""), [])
        self.assertNotIn("creer.favori", self.registre.commandes())

    def test_favori_commande_disparue_ignore(self):
        self._favori("app.nexiste-pas", titre="Vieille appli")
        self.assertEqual(self.registre.rechercher(""), [])
        self.assertEqual(self.registre.executer("favoris.basculer", "pas du json").statut, "erreur")

    def test_snippet_par_defaut(self):
        premier = self.registre.rechercher("date")[0]
        self.assertTrue(premier.commande.startswith("snippets."))

    def test_bascule(self):
        reponse = self.registre.executer("systeme.theme-sombre")
        self.assertEqual(reponse.message, "Thème sombre")

    def test_commande_inconnue_et_plateforme_absente(self):
        self.assertEqual(self.registre.executer("nexiste.pas").statut, "erreur")
        self.assertEqual(self.registre.executer("systeme.veille").statut, "erreur")

    def test_historique_fait_remonter(self):
        avant = [r.commande for r in self.registre.rechercher("ouvrir") if r.score >= 2]
        cible = avant[-1]  # la dernière commande fixe (pas la recherche web de dernier recours)
        self.assertGreater(avant.index(cible), 0)
        for _ in range(5):
            self.registre.executer(cible)
        apres = [r.commande for r in self.registre.rechercher("ouvrir") if r.score >= 2]
        self.assertLess(apres.index(cible), avant.index(cible))
        self.assertIn(cible, [r.commande for r in self.registre.rechercher("")])

    def test_effacer_suggestions(self):
        self.registre.executer("declic.a-propos")
        self.assertTrue(self.registre.rechercher(""))
        self.assertEqual(self.registre.executer("declic.effacer-suggestions").statut, "ok")
        self.assertEqual(self.registre.rechercher(""), [])

    def test_confirmation_signalee(self):
        resultats = self.registre.rechercher("corbeille")
        self.assertTrue(all(r.confirmer for r in resultats if r.commande == "systeme.vider-corbeille"))

    def test_script_personnel(self):
        script = self.chemins.scripts / "bonjour.sh"
        script.write_text("#!/bin/sh\n# @declic titre: Dire bonjour\n# @declic argument: nom\necho \"Bonjour $1\"\n")
        self.registre.recharger()
        premier = self.registre.rechercher("dire bonjour")[0]
        self.assertEqual(premier.commande, "script.bonjour")
        self.assertEqual(premier.attend_argument, "nom")
        reponse = self.registre.executer("script.bonjour", "Gergovie")
        self.assertEqual(reponse.message, "Bonjour Gergovie")

    def test_lien_personnel(self):
        self.chemins.liens.write_text('[[lien]]\nnom = "Arkeogis"\nmot_cle = "ark"\n'
                                      'url = "https://arkeogis.org/?q={requete}"\n', encoding="utf-8")
        self.registre.recharger()
        self.assertEqual(self.registre.rechercher("ark bronze")[0].commande, "liens.ark")


class TestCreation(BaseRegistre):
    def _creer(self, type_, **valeurs):
        return self.registre.creer(type_, valeurs)

    def test_lien_avec_mot_temoin(self):
        r = self._creer("lien", nom="Inrap", mot_cle="Inrap",
                        adresse="https://www.inrap.fr/recherche?search_api_fulltext=DECLIC&page=0")
        self.assertEqual(r["statut"], "ok", r)
        self.assertEqual(r["remplir"], "inrap ")
        import tomllib
        donnees = tomllib.loads(self.chemins.liens.read_text())
        self.assertEqual(donnees["lien"][0]["url"], "https://www.inrap.fr/recherche?search_api_fulltext={requete}&page=0")
        # utilisable tout de suite, sans relancer le service
        res = self.registre.rechercher("inrap fibules")
        self.assertEqual(res[0].commande, "liens.inrap")
        self.registre.executer(res[0].commande, res[0].argument)
        self.assertIn(("ouvrir", "https://www.inrap.fr/recherche?search_api_fulltext=fibules&page=0"),
                      self.plateforme.appels)

    def test_lien_refuse(self):
        self.assertEqual(self._creer("lien", nom="", mot_cle="x", adresse="https://a.fr/?q={requete}")["champ"], "nom")
        self.assertEqual(self._creer("lien", nom="A", mot_cle="deux mots", adresse="https://a.fr/?q={requete}")["champ"], "mot_cle")
        r = self._creer("lien", nom="A", mot_cle="a", adresse="https://a.fr/accueil")
        self.assertEqual((r["statut"], r["champ"]), ("erreur", "adresse"))
        self.assertFalse(self.chemins.liens.exists())  # rien n'est écrit si la saisie est refusée
        self.assertEqual(self._creer("lien", nom="A", mot_cle="a", adresse="a.fr/?q={requete}")["statut"], "ok")
        self.assertEqual(self._creer("lien", nom="B", mot_cle="a", adresse="https://b.fr/?q={requete}")["champ"], "mot_cle")

    def test_fichier_existant_conserve_et_caracteres_speciaux(self):
        self.chemins.liens.write_text('# mes liens\n[[lien]]\nnom = "Persée bis"\nmot_cle = "pb"\nurl = "https://p.fr/?q={requete}"\n')
        self.registre.recharger()
        r = self._creer("lien", nom='Le "site" \\ ça', mot_cle="s", adresse="https://s.fr/?q={requete}")
        self.assertEqual(r["statut"], "ok", r)
        contenu = self.chemins.liens.read_text()
        self.assertTrue(contenu.startswith("# mes liens"))
        self.assertIn("pb", self.registre.modules[3].perso)
        self.assertEqual(self.registre.modules[3].perso["s"].nom, 'Le "site" \\ ça')

    def test_snippet(self):
        r = self._creer("snippet", nom="Labo", mot_cle="labo", texte="12 rue des Fouilles\nClermont")
        self.assertEqual(r["statut"], "ok", r)
        res = self.registre.rechercher("labo")
        self.assertEqual(res[0].titre, "Labo")
        self.registre.executer(res[0].commande, None)
        self.assertIn(("copier", "12 rue des Fouilles\nClermont"), self.plateforme.appels)
        self.assertEqual(self._creer("snippet", nom="Autre", mot_cle="labo", texte="x")["champ"], "mot_cle")
        self.assertEqual(self._creer("snippet", nom="Vide", texte="  ")["champ"], "texte")

    def test_lister_et_supprimer_lien(self):
        self.chemins.liens.write_text(
            '# en-tête à garder\n\n[[lien]]\nnom = "A"\nmot_cle = "a"\nurl = "https://a.fr/?q={requete}"\n'
            '# note sur B\n[[lien]]\nnom = "Mon Google"\nmot_cle = "g"  # remplace Google\nurl = "https://g.fr/?q={requete}"\n')
        self.registre.recharger()
        self.assertEqual([e.cle for e in self.registre.elements("lien")], ["a", "g"])
        r = self.registre.supprimer("lien", "g")
        self.assertEqual(r["statut"], "ok", r)
        self.assertIn("Google", r["message"])  # « g » renvoie de nouveau vers Google
        contenu = self.chemins.liens.read_text()
        self.assertIn("# en-tête à garder", contenu)
        self.assertIn('nom = "A"', contenu)
        self.assertNotIn("Mon Google", contenu)
        res = self.registre.rechercher("g test")
        self.assertIn("google.com", res[0].sous_titre)
        self.assertEqual(self.registre.supprimer("lien", "zzz")["statut"], "erreur")

    def test_supprimer_snippet(self):
        self._creer("snippet", nom="Labo", mot_cle="labo", texte="12 rue")
        self._creer("snippet", nom="Signature", texte="Cordialement")
        cles = {e.titre: e.cle for e in self.registre.elements("snippet")}
        self.assertEqual(self.registre.supprimer("snippet", cles["Labo"])["statut"], "ok")
        titres = [e.titre for e in self.registre.elements("snippet")]
        self.assertNotIn("Labo", titres)
        self.assertIn("Signature", titres)
        self.assertIn("Date du jour", titres)  # le modèle d'origine reste

    def test_commande_ajouter(self):
        res = self.registre.rechercher("ajouter lien")
        self.assertEqual(res[0].commande, "creer.lien")
        self.assertEqual(self.registre.executer("creer.lien").ouvrir, "creer:lien")
        self.assertEqual(self._creer("inconnu")["statut"], "erreur")


class TestAutomatisations(BaseRegistre):
    REGLES = """
[[regle]]
nom = "Mode révision"
quand = "manuel"
alors = ["systeme.verrouiller", "notifier:Bon courage", "liens.ouvrir:https://ent.fr"]

[[regle]]
nom = "Matin"
quand = { heure = "08:30", jours = ["semaine"] }
alors = ["liens.ouvrir:https://matin.fr"]

[[regle]]
nom = "Fac"
quand = { evenement = "wifi.connecte", valeur = "Eduroam" }
si = { heure_entre = ["22:00", "06:00"] }
alors = ["liens.ouvrir:https://fac.fr"]

[[regle]]
nom = "Maison"
quand = { telephone = "arrivée", lieu = "maison" }
alors = ["attendre:0", "liens.ouvrir:https://maison.fr", "inconnu.commande"]

[[regle]]
nom = "Éteinte"
quand = "manuel"
actif = false
alors = ["systeme.verrouiller"]

[[regle]]
nom = "Cassée"
quand = { heure = "25:00" }
alors = ["systeme.verrouiller"]

[[regle]]
nom = "Sans actions"
quand = "manuel"
"""

    def setUp(self):
        super().setUp()
        import datetime as dt
        self.maintenant = dt.datetime(2026, 11, 16, 23, 15)  # un lundi soir
        self.plateforme.notifier = lambda titre, message="": self.plateforme.appels.append(("notifier", titre, message))
        self.chemins.regles.write_text(self.REGLES)
        self.auto = self.registre.automatisations
        self.auto.synchrone = True
        self.auto.horloge = lambda: self.maintenant
        self.registre.recharger()

    def ouverts(self):
        return [a[1] for a in self.plateforme.appels if a[0] == "ouvrir"]

    def test_lecture_et_erreurs(self):
        self.assertEqual([r.nom for r in self.auto.regles], ["Mode révision", "Matin", "Fac", "Maison", "Éteinte"])
        self.assertEqual(len(self.auto.erreurs), 2)
        self.assertTrue(any("Cassée" in e and "heure" in e for e in self.auto.erreurs))
        self.assertTrue(any("Sans actions" in e for e in self.auto.erreurs))
        self.assertEqual(self.auto.verifier_actions(), ["« Maison » : action inconnue « inconnu.commande »"])

    def test_manuel_depuis_la_barre(self):
        ids = self.registre.commandes()
        self.assertIn("auto.mode-revision", ids)
        self.assertNotIn("auto.eteinte", ids)  # règle désactivée
        res = self.registre.rechercher("mode revision")
        self.assertEqual(res[0].commande, "auto.mode-revision")
        self.assertEqual(self.registre.executer("auto.mode-revision").statut, "ok")
        self.assertIn(("verrouiller",), self.plateforme.appels)
        self.assertIn(("notifier", "Mode révision", "Bon courage"), self.plateforme.appels)
        self.assertEqual(self.ouverts(), ["https://ent.fr"])
        self.assertTrue(self.auto.journal[-1].reussie)

    def test_horaire(self):
        import datetime as dt
        self.assertEqual(self.auto.tic(dt.datetime(2026, 11, 16, 8, 30, 5)), ["Matin"])
        self.assertEqual(self.auto.tic(dt.datetime(2026, 11, 16, 8, 30, 40)), [])  # une seule fois par minute
        self.assertEqual(self.auto.tic(dt.datetime(2026, 11, 17, 8, 30)), ["Matin"])  # le lendemain
        self.assertEqual(self.auto.tic(dt.datetime(2026, 11, 21, 8, 30)), [])  # samedi
        self.assertEqual(self.ouverts(), ["https://matin.fr"] * 2)

    def test_evenement_valeur_et_plage_passant_minuit(self):
        import datetime as dt
        self.assertEqual(self.registre.declencher("wifi.connecte", "Freebox"), [])  # autre réseau
        self.assertEqual(self.registre.declencher("wifi.connecte", "eduroam"), ["Fac"])  # casse ignorée, 23:15
        self.maintenant = dt.datetime(2026, 11, 17, 12, 0)
        self.assertEqual(self.registre.declencher("wifi.connecte", "eduroam"), [])  # hors plage 22:00–06:00
        self.assertEqual(self.ouverts(), ["https://fac.fr"])

    def test_telephone_et_echec_partiel(self):
        lancees = self.registre.declencher("telephone.arrivee", "Maison")
        self.assertEqual(lancees, ["Maison"])
        execution = self.auto.journal[-1]
        self.assertFalse(execution.reussie)
        self.assertEqual(self.ouverts(), ["https://maison.fr"])  # l'action suivant l'échec a quand même eu lieu
        self.assertTrue(any(a[0] == "notifier" and "échec" in a[1] for a in self.plateforme.appels))
        self.assertIn("ÉCHEC", self.auto.rapport())

    def test_modele_cree(self):
        self.chemins.regles.unlink()
        self.registre.recharger()
        self.assertIn("[[regle]]", self.chemins.regles.read_text())
        self.assertEqual((self.auto.regles, self.auto.erreurs), ([], []))  # exemples commentés


class TestIdentifiantsEtBlocs(BaseRegistre):
    SECRET = "Tr0p-s3cr3t!é"

    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        racine = Path(self._dossier.name)
        self.chemins = Chemins(racine / "config", racine / "donnees")
        self.plateforme = PlateformeAvecCoffre()
        self.registre = Registre(self.plateforme, self.chemins)
        self.registre.automatisations.synchrone = True

    def _ent(self, **autres):
        valeurs = {"nom": "ENT fac", "adresse": "cas.univ.fr/login", "identifiant": "etu.test",
                   "mot_de_passe": self.SECRET, **autres}
        return self.registre.creer("identifiant", valeurs)

    def test_mot_de_passe_jamais_ressorti(self):
        r = self._ent()
        self.assertEqual(r["statut"], "ok", r)
        self.assertEqual(self.plateforme.coffre["ent-fac"][1], self.SECRET)
        self.assertEqual(self.plateforme.coffre["ent-fac"][0]["adresse"], "https://cas.univ.fr/login")
        visibles = json.dumps([r, [e.en_dict() for e in self.registre.elements("identifiant")],
                               [c.en_dict() for c in self.registre.creations()]], ensure_ascii=False)
        self.assertNotIn(self.SECRET, visibles)
        for fichier in Path(self._dossier.name).rglob("*"):
            if fichier.is_file():
                self.assertNotIn(self.SECRET.encode(), fichier.read_bytes(), fichier)

    def test_refus(self):
        self.assertEqual(self._ent(adresse="http://cas.univ.fr")["champ"], "adresse")  # pas de http en clair
        self.assertEqual(self._ent(mot_de_passe="")["champ"], "mot_de_passe")
        self.assertEqual(self._ent()["statut"], "ok")
        self.assertEqual(self._ent()["champ"], "nom")  # déjà enregistré

    def test_connexion_et_suppression(self):
        self._ent()
        res = self.registre.rechercher("se connecter ent")
        self.assertEqual(res[0].commande, "identifiants.ent-fac")
        self.assertEqual(self.registre.executer("identifiants.ent-fac").statut, "ok")
        self.assertEqual(self.plateforme.appels[-2:], [("ouvrir", "https://cas.univ.fr/login"), ("saisir", "ent-fac")])
        self.assertEqual(self.registre.supprimer("identifiant", "ent-fac")["statut"], "ok")
        self.assertEqual(self.plateforme.coffre, {})

    def test_page_autorisee(self):
        from declic.modules.identifiants import page_autorisee
        ok = lambda url: page_autorisee(url, "https://cas.univ.fr/login")[0]
        self.assertTrue(ok("https://cas.univ.fr/login?service=https%3A%2F%2Fent.univ.fr"))
        self.assertTrue(ok("https://auth.cas.univ.fr/x"))  # sous-domaine
        self.assertFalse(ok("http://cas.univ.fr/login"))  # non chiffré
        self.assertFalse(ok("https://cas.univ.fr.arnaque.com/login"))
        self.assertFalse(ok("https://faux-cas.univ.fr/login"))  # autre hôte du même domaine
        self.assertFalse(ok("https://arnaque.com/?u=https://cas.univ.fr/login"))
        self.assertFalse(ok("https://cas.univ.fr@arnaque.com/login"))  # piège « utilisateur@hôte »
        self.assertFalse(ok(None))

    def test_verifier_page_et_remplir_ici(self):
        self._ent()
        self.plateforme.page_affichee = "https://cas.univ.fr/login?service=ent"
        self.assertEqual(self.registre.verifier_page("ent-fac", 4242), {"ok": True, "raison": ""})
        self.assertFalse(self.registre.verifier_page("ent-fac", 999)["ok"])  # adresse illisible → refus
        res = self.registre.rechercher("", 10, page="https://cas.univ.fr/login")
        self.assertEqual((res[0].commande, res[0].argument), ("identifiants.remplir", "ent-fac"))
        self.assertEqual(self.registre.rechercher("rempl", 10, page="https://cas.univ.fr/login")[0].titre,
                         "Remplir ici : ENT fac")
        self.assertFalse(any(r.commande == "identifiants.remplir"
                             for r in self.registre.rechercher("", 10, page="https://moodle.univ.fr/")))
        self.plateforme.page_affichee = "https://cas.univ.fr.arnaque.com/login"
        r = self.registre.verifier_page("ent-fac", 4242)
        self.assertFalse(r["ok"])
        self.assertIn("arnaque", r["raison"])
        self.assertEqual(self.registre.executer("identifiants.remplir", "ent-fac").statut, "ok")
        self.assertEqual(self.plateforme.appels[-1], ("saisir", "ent-fac"))

    def test_formulaire_par_blocs(self):
        self._ent()
        creation = next(c for c in self.registre.creations() if c.type == "automatisation")
        champs = {c.cle: c for c in creation.champs}
        self.assertEqual([v for v, _l in champs["wifi"].options], ["Freebox", "Wifi-Fac"])
        self.assertEqual(champs["wifi"].si, ("declencheur", ("wifi",)))
        self.assertIn(("ent-fac", "ENT fac"), champs["connexion"].options)
        self.assertFalse(champs["wifi"].visible({"declencheur": "manuel"}))

    def test_creer_regle_wifi_puis_declencher(self):
        self._ent()
        r = self.registre.creer("automatisation", {
            "nom": "Arrivée à la fac", "declencheur": "wifi", "wifi": "Wifi-Fac", "jours": "semaine",
            "ouvrir": "moodle.univ.fr", "connexion": "ent-fac", "commandes": "systeme.verrouiller, notifier:Bonne journée"})
        self.assertEqual(r["statut"], "ok", r)
        import tomllib
        bloc = tomllib.loads(self.chemins.regles.read_text())["regle"][0]
        self.assertEqual(bloc["quand"], {"evenement": "wifi.connecte", "valeur": "Wifi-Fac"})
        self.assertEqual(bloc["si"], {"jours": ["semaine"]})
        self.assertEqual(bloc["alors"], ["liens.ouvrir:https://moodle.univ.fr", "identifiants.connexion:ent-fac",
                                         "systeme.verrouiller", "notifier:Bonne journée"])
        import datetime as dt
        self.registre.automatisations.horloge = lambda: dt.datetime(2026, 11, 16, 9, 0)  # lundi
        self.assertEqual(self.registre.declencher("wifi.connecte", "Wifi-Fac"), ["Arrivée à la fac"])
        self.assertIn(("saisir", "ent-fac"), self.plateforme.appels)
        self.assertEqual(self.registre.supprimer("automatisation", "auto.arrivee-a-la-fac")["statut"], "ok")
        self.assertEqual(self.registre.automatisations.regles, [])

    def test_creer_regle_refus(self):
        base = {"nom": "X", "declencheur": "heure", "heure": "8h", "jours": "tous", "ouvrir": "a.fr"}
        self.assertEqual(self.registre.creer("automatisation", base)["statut"], "ok")  # « 8h » → 08:00
        self.assertEqual(self.registre.automatisations.regles[0].quand.heure.hour, 8)
        self.assertEqual(self.registre.creer("automatisation", {**base, "nom": "Y", "heure": "25:00"})["champ"], "heure")
        self.assertEqual(self.registre.creer("automatisation", {**base, "nom": "Z", "ouvrir": ""})["champ"], "ouvrir")
        self.assertEqual(self.registre.creer("automatisation", {**base, "nom": "W", "commandes": "pas.une-commande"})["champ"],
                         "commandes")


class TestServeur(BaseRegistre):
    def setUp(self):
        super().setUp()
        self.serveur = creer_serveur(self.registre, port=0)
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        self.fil.start()
        infos = json.loads(self.chemins.serveur.read_text())
        self.port, self.jeton = infos["port"], infos["jeton"]

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        super().tearDown()

    def _requete(self, chemin, donnees=None, jeton=True):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{chemin}",
                                     data=json.dumps(donnees).encode() if donnees is not None else None)
        if jeton:
            req.add_header("Authorization", f"Bearer {self.jeton}")
        if donnees is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_jeton_obligatoire(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._requete("/v1/sante", jeton=False)
        self.assertEqual(ctx.exception.code, 401)
        ctx.exception.close()

    def test_fichier_serveur_prive(self):
        if os.name == "posix":
            self.assertEqual(self.chemins.serveur.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.chemins.jeton.stat().st_mode & 0o777, 0o600)

    def test_aller_retour(self):
        self.assertTrue(self._requete("/v1/sante")["ok"])
        resultats = self._requete("/v1/recherche?q=2%2B2")["resultats"]
        self.assertEqual(resultats[0]["titre"], "= 4")
        reponse = self._requete("/v1/executer", {"commande": resultats[0]["commande"],
                                                 "argument": resultats[0]["argument"]})
        self.assertEqual(reponse["statut"], "ok")
        self.assertIn(("copier", "4"), self.plateforme.appels)

    def test_declencheur_par_api(self):
        self.chemins.regles.write_text('[[regle]]\nnom = "Maison"\nquand = { telephone = "arrivee", lieu = "maison" }\n'
                                       'alors = ["liens.ouvrir:https://maison.fr"]\n')
        self.registre.recharger()
        self.registre.automatisations.synchrone = True
        r = self._requete("/v1/declencheur", {"evenement": "telephone.arrivee", "valeur": "maison"})
        self.assertEqual(r["regles"], ["Maison"])
        etat = self._requete("/v1/automatisations")
        self.assertEqual(etat["regles"][0]["nom"], "Maison")
        self.assertTrue(etat["journal"][0]["reussie"])
        self.assertIn("wifi.connecte", etat["evenements"])

    def test_creations_par_api(self):
        types = [c["type"] for c in self._requete("/v1/creations")["creations"]]
        self.assertEqual(types, ["lien", "snippet", "automatisation", "favori"])
        r = self._requete("/v1/creer", {"type": "lien", "valeurs": {"nom": "HAL bis", "mot_cle": "hb",
                                                                    "adresse": "https://hal.science/?q=declic"}})
        self.assertEqual((r["statut"], r["champ"]), ("ok", None))
        self.assertEqual([e["cle"] for e in self._requete("/v1/elements?type=lien")["elements"]], ["hb"])
        self.assertEqual(self._requete("/v1/supprimer", {"type": "lien", "cle": "hb"})["statut"], "ok")
        self.assertEqual(self._requete("/v1/elements?type=lien")["elements"], [])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._requete("/v1/creer", {"type": "lien"})
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()


if __name__ == "__main__":
    unittest.main()
