"""Compteur de requêtes d'IA : en-têtes des fournisseurs, compte de Déclic, remise à zéro."""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from declic import ia_quota

UTC = dt.timezone.utc


class TestQuota(unittest.TestCase):
    def test_minuit_pacifique_ete_et_hiver(self):
        hiver = dt.datetime(2026, 11, 25, 20, 0, tzinfo=UTC)  # 12 h à Los Angeles (UTC−8)
        self.assertEqual(ia_quota.prochain_minuit_pacifique(hiver), dt.datetime(2026, 11, 26, 8, 0, tzinfo=UTC))
        ete = dt.datetime(2026, 7, 14, 20, 0, tzinfo=UTC)  # 13 h à Los Angeles (UTC−7)
        self.assertEqual(ia_quota.prochain_minuit_pacifique(ete), dt.datetime(2026, 7, 15, 7, 0, tzinfo=UTC))

    def test_entetes_claude_et_openai(self):
        maintenant = dt.datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
        claude = ia_quota.depuis_entetes({"Anthropic-RateLimit-Requests-Limit": "50", "anthropic-ratelimit-requests-remaining": "49",
                                          "anthropic-ratelimit-requests-reset": "2026-11-25T12:01:00Z"}, maintenant)
        self.assertEqual(claude, {"limite": 50, "restant": 49, "reset": "2026-11-25T12:01:00+00:00"})
        openai = ia_quota.depuis_entetes({"x-ratelimit-limit-requests": "10000", "x-ratelimit-remaining-requests": "9998",
                                          "x-ratelimit-reset-requests": "1m30s"}, maintenant)
        self.assertEqual(openai, {"limite": 10000, "restant": 9998, "reset": "2026-11-25T12:01:30+00:00"})
        self.assertIsNone(ia_quota.depuis_entetes({"content-type": "application/json"}, maintenant))

    def test_compte_de_declic_et_remise_a_zero(self):
        temps = [dt.datetime(2026, 11, 25, 20, 0, tzinfo=UTC)]
        with tempfile.TemporaryDirectory() as dossier:
            q = ia_quota.Quotas(Path(dossier) / "ia-quota.json", horloge=lambda: temps[0])
            q.noter("gemini")
            q.noter("gemini")
            etat = q.etat("gemini", 1000)
            self.assertEqual((etat["utilise"], etat["limite"], etat["source"]), (2, 1000, "declic"))
            self.assertEqual(etat["reset"], dt.datetime(2026, 11, 26, 8, 0, tzinfo=UTC))
            q.apprendre_limite("gemini", 20)  # erreur « quota dépassé » : la limite est retenue
            self.assertEqual(q.etat("gemini")["limite"], 20)
            temps[0] = dt.datetime(2026, 11, 26, 9, 0, tzinfo=UTC)  # après minuit, heure du Pacifique
            etat = q.etat("gemini")
            self.assertEqual((etat["utilise"], etat["limite"]), (0, 20))
            self.assertEqual(etat["reset"], dt.datetime(2026, 11, 27, 8, 0, tzinfo=UTC))

    def test_chiffres_du_fournisseur_en_priorite(self):
        with tempfile.TemporaryDirectory() as dossier:
            q = ia_quota.Quotas(Path(dossier) / "q.json", horloge=lambda: dt.datetime(2026, 11, 25, 12, 0, tzinfo=UTC))
            q.noter("openai", {"x-ratelimit-limit-requests": "120", "x-ratelimit-remaining-requests": "60",
                               "x-ratelimit-reset-requests": "6m"})
            etat = q.etat("openai", 999)
            self.assertEqual((etat["utilise"], etat["limite"], etat["source"]), (60, 120, "fournisseur"))

    def test_limite_dans_le_message_de_gemini(self):
        message = "Quota exceeded for metric: generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash-lite"
        self.assertEqual(ia_quota.limite_dans_erreur(message), 20)
        self.assertIsNone(ia_quota.limite_dans_erreur("autre erreur"))

    def test_resume(self):
        reset = dt.datetime.now(UTC) + dt.timedelta(minutes=30)
        texte = ia_quota.resume({"utilise": 60, "limite": 1200, "reset": reset})
        self.assertTrue(texte.startswith("60 / 1 200 requêtes · remise à zéro"), texte)
        self.assertEqual(ia_quota.resume({"utilise": 1, "limite": None, "reset": None}), "1 requête depuis la remise à zéro")


if __name__ == "__main__":
    unittest.main()
