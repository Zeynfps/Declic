"""Poser une question à une IA (ChatGPT, Claude, Gemini) : la barre ouvre le site avec la question.

On tape le mot-clé suivi de la question : « gpt pourquoi la sigillée est rouge ? »,
« claude résume la stratigraphie de Bibracte ». Toute recherche propose aussi, en bas de liste,
de poser la question telle quelle à chacune des IA.

La question part toute seule : une fois la page de l'IA affichée, l'extension appuie sur Entrée
à la place de l'utilisateur (seulement si le navigateur est au premier plan sur cette page-là).

Gemini n'a pas d'adresse officielle pour pré-remplir une question (« ?q= » marche aujourd'hui
mais n'est pas documenté) : la question est donc aussi copiée, pour pouvoir la coller au besoin.
"""
from __future__ import annotations

from declic.modele import Commande, Reponse, Resultat
from declic.modules import Module
from declic.modules.liens import Lien
from declic.plateforme.base import NonPrisEnCharge
from declic import texte

ICONE = "user-available-symbolic"
DELAI_ENVOI_S = 25  # temps laissé au navigateur pour afficher la page de l'IA


class IA(Module):
    nom = "ia"

    # (lien, copier la question par sécurité, mots-clés en plus)
    IAS = (
        (Lien("ChatGPT", "gpt", "https://chatgpt.com/?q={requete}"), False, ("chatgpt", "openai")),
        (Lien("Claude", "claude", "https://claude.ai/new?q={requete}"), False, ("anthropic",)),
        (Lien("Gemini", "gemini", "https://gemini.google.com/app?q={requete}"), True, ("bard", "google")),
    )

    def commandes(self) -> list[Commande]:
        return [Commande(
            id=f"ia.{lien.mot_cle}", titre=f"Demander à {lien.nom}",
            description=f"Mot-clé : « {lien.mot_cle} »", icone=ICONE,
            mots_cles=(lien.mot_cle, lien.nom, "ia", "question", *autres), argument="question", requiert="ouvrir",
            action=self._action(lien, copier),
        ) for lien, copier, autres in self.IAS]

    def _action(self, lien: Lien, copier: bool):
        def action(contexte, question):
            question = (question or "").strip()
            if not question:
                contexte.plateforme.ouvrir(lien.accueil)
                return Reponse(message=f"{lien.nom} ouvert")
            message = f"Question envoyée à {lien.nom}"
            if copier and contexte.plateforme.prend_en_charge("copier_texte"):
                contexte.plateforme.copier_texte(question)
                message += " (aussi copiée)"
            adresse = lien.pour(question)
            contexte.plateforme.ouvrir(adresse)
            if contexte.plateforme.prend_en_charge("valider_page"):
                try:
                    contexte.plateforme.valider_page(adresse, DELAI_ENVOI_S)
                except NonPrisEnCharge:
                    pass  # extension absente : la question reste pré-remplie, il suffit d'appuyer sur Entrée
            return Reponse(message=message)
        return action

    def resultats(self, requete: str) -> list[Resultat]:
        requete = requete.strip()
        if not requete:
            return []
        mot, _, reste = requete.partition(" ")
        reste = reste.strip()
        for lien, _copier, autres in self.IAS:
            cles = {texte.normaliser(c) for c in (lien.mot_cle, lien.nom, *autres)}
            if reste and texte.normaliser(mot) in cles:
                return [Resultat(
                    commande=f"ia.{lien.mot_cle}", titre=f"{lien.nom} : « {reste} »",
                    sous_titre="Ouvre le navigateur et envoie la question", icone=ICONE, score=99.0, argument=reste)]
        resultats = []
        for i, (lien, _copier, _autres) in enumerate(self.IAS):
            # En bas de liste, juste au-dessus de la recherche web : poser la question telle quelle
            resultats.append(Resultat(
                commande=f"ia.{lien.mot_cle}", titre=f"Demander à {lien.nom} : « {requete} »",
                sous_titre=f"ou tapez « {lien.mot_cle} » puis la question", icone=ICONE,
                score=1.5 - i * 0.1, argument=requete))
        return resultats
