"""L'IA dans la barre : réponses affichées dans Déclic, et actions sur le texte sélectionné.

Configuration (bouton + → « Clé d'IA ») : un fournisseur (Claude, ChatGPT, Gemini, DeepSeek, Mistral, OpenRouter,
Groq, Grok, ou Ollama sur le PC), sa clé d'API (gardée dans le trousseau du système, jamais dans un fichier) et
un modèle (choisi automatiquement si on le laisse vide). Plusieurs fournisseurs peuvent être enregistrés ;
« IA : utiliser … » choisit celui qui répond.

Dans la barre :
  - « ia question » (ou « ? question ») : la réponse s'affiche dans la barre ;
  - toute recherche propose aussi « Demander à <IA> ici » en bas de liste ;
  - texte sélectionné (raccourci dédié de la barre) : traduire, reformuler, résumer, corriger, expliquer,
    ou poser une question à son sujet.
Réglages non secrets (fournisseur actif, modèles) : ia.json dans le dossier de configuration.
"""
from __future__ import annotations

import json
import logging

from declic import ia_api, texte
from declic.modele import Champ, Commande, Creation, CreationRefusee, Element, Reponse, Resultat
from declic.modules import Module

journal = logging.getLogger("declic.assistant")

ICONE = "user-available-symbolic"
MOTS_CLES = ("ia", "?", "ai", "assistant")
MAX_SELECTION = 30_000  # caractères envoyés à l'IA

SYSTEME = ("Tu es l'assistant intégré à Déclic, une barre de commande. Réponds en français (sauf demande contraire), "
           "directement, sans formule d'introduction ni de conclusion. Pas de Markdown lourd : du texte simple, "
           "des listes courtes si besoin.")

# Actions sur le texte sélectionné : clé → (titre, icône, consigne)
ACTIONS = {
    "traduire": ("Traduire", "preferences-desktop-locale-symbolic",
                 "Traduis ce texte. S'il est en français, traduis-le en anglais ; sinon, en français. "
                 "Donne seulement la traduction."),
    "corriger": ("Corriger l'orthographe et la grammaire", "tools-check-spelling-symbolic",
                 "Corrige l'orthographe, la grammaire et la ponctuation de ce texte sans en changer le sens ni le ton. "
                 "Donne seulement le texte corrigé."),
    "reformuler": ("Reformuler", "edit-redo-symbolic",
                   "Reformule ce texte pour qu'il soit plus clair et plus fluide, dans la même langue et le même "
                   "registre. Donne seulement le texte reformulé."),
    "resumer": ("Résumer", "view-list-symbolic",
                "Résume ce texte en quelques phrases ou en une courte liste de points, dans sa langue."),
    "expliquer": ("Expliquer", "help-about-symbolic",
                  "Explique simplement ce texte (sens, termes difficiles, contexte), en français."),
    "formel": ("Rendre plus formel", "document-edit-symbolic",
               "Réécris ce texte dans un registre plus formel et professionnel, dans la même langue. "
               "Donne seulement le texte réécrit."),
}


class Assistant(Module):
    nom = "assistant"

    @property
    def fichier(self):
        return self.contexte.chemins.config / "ia.json"

    def _reglages(self) -> dict:
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
            return donnees if isinstance(donnees, dict) else {}
        except (OSError, ValueError):
            return {}

    def _ecrire(self, reglages: dict) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        self.fichier.write_text(json.dumps(reglages, ensure_ascii=False, indent=2), encoding="utf-8")

    def _actif(self) -> tuple[ia_api.Fournisseur, dict] | None:
        reglages = self._reglages()
        configures = reglages.get("fournisseurs", {})
        cle = reglages.get("actif") if reglages.get("actif") in configures else next(iter(configures), None)
        if cle is None or cle not in ia_api.FOURNISSEURS:
            return None
        return ia_api.FOURNISSEURS[cle], configures[cle]

    def _plateforme_secrets(self) -> bool:
        return self.contexte.plateforme.prend_en_charge("secret_lire")

    def demander(self, consigne: str) -> tuple[str, str]:
        """Pose la question à l'IA active. Renvoie (nom de l'IA, réponse)."""
        actif = self._actif()
        if actif is None:
            raise ia_api.ErreurIA("aucune IA configurée : bouton + → « Clé d'IA »")
        fournisseur, reglage = actif
        cle = self.contexte.plateforme.secret_lire(fournisseur.cle) if fournisseur.avec_cle else ""
        if fournisseur.avec_cle and not cle:
            raise ia_api.ErreurIA(f"clé de {fournisseur.nom} introuvable : enregistrez-la à nouveau")
        reponse = ia_api.demander(fournisseur, cle or "", reglage.get("modele", ""), SYSTEME, consigne,
                                  reglage.get("adresse", ""))
        return fournisseur.nom.split(" (")[0], reponse

    # --- Commandes ------------------------------------------------------------------------
    def _repondre(self, consigne_de):
        def action(_contexte, argument):
            argument = (argument or "").strip()
            if not argument:
                return Reponse.erreur("Rien à envoyer à l'IA")
            try:
                nom, reponse = self.demander(consigne_de(argument[:MAX_SELECTION]))
            except ia_api.ErreurIA as exc:
                return Reponse.erreur(f"IA : {exc}")
            return Reponse(message=f"Réponse de {nom}", texte=reponse, fermer=False)
        return action

    def _utiliser(self, cle: str):
        def action(_contexte, _argument):
            reglages = self._reglages()
            reglages["actif"] = cle
            self._ecrire(reglages)
            return Reponse(message=f"L'IA de Déclic est maintenant {ia_api.FOURNISSEURS[cle].nom.split(' (')[0]}")
        return action

    def commandes(self) -> list[Commande]:
        commandes = [Commande(
            "assistant.demander", "Demander à l'IA (réponse dans la barre)",
            self._repondre(lambda question: question), argument="question", icone=ICONE,
            mots_cles=("ia", "question", "assistant", "chat"), requiert="secret_lire")]
        for cle, (titre, icone, consigne) in ACTIONS.items():
            commandes.append(Commande(
                f"assistant.{cle}", titre, self._repondre(lambda t, c=consigne: f"{c}\n\nTexte :\n{t}"),
                argument="texte", icone=icone, cachee=True, requiert="secret_lire"))
        commandes.append(Commande(
            "assistant.question-selection", "Poser une question sur le texte",
            self._repondre(lambda t: t), argument="texte", icone=ICONE, cachee=True, requiert="secret_lire"))
        configures = self._reglages().get("fournisseurs", {})
        if len(configures) > 1:
            for cle in configures:
                if cle in ia_api.FOURNISSEURS:
                    nom = ia_api.FOURNISSEURS[cle].nom.split(" (")[0]
                    commandes.append(Commande(f"assistant.utiliser-{cle}", f"IA : utiliser {nom}", self._utiliser(cle),
                                              icone=ICONE, mots_cles=("ia", "modèle", nom), requiert="secret_lire"))
        return commandes

    # --- Dans la barre -----------------------------------------------------------------------
    @staticmethod
    def _sans_mot_cle(requete: str) -> str | None:
        mot, _, reste = requete.strip().partition(" ")
        return reste.strip() if texte.normaliser(mot) in MOTS_CLES and reste.strip() else None

    def resultats(self, requete: str) -> list[Resultat]:
        requete = requete.strip()
        actif = self._actif() if requete else None
        if actif is None:
            return []
        nom = actif[0].nom.split(" (")[0]
        question = self._sans_mot_cle(requete)
        if question:  # « ia … » : en tête
            return [Resultat(commande="assistant.demander", titre=f"{nom} : « {question} »", argument=question,
                             sous_titre="Réponse dans la barre", icone=ICONE, score=99.0)]
        # sinon, en bas de liste avec les autres propositions de dernier recours
        return [Resultat(commande="assistant.demander", titre=f"Demander à {nom} ici : « {requete} »",
                         argument=requete, sous_titre="Réponse dans la barre", icone=ICONE, score=1.9)]

    def pour_selection(self, selection: str, requete: str) -> list[Resultat]:
        """Actions proposées sur le texte sélectionné ; ce qu'on tape devient une question sur ce texte."""
        if self._actif() is None:
            return [Resultat(commande="creer.fournisseur-ia", titre="Configurer une IA pour agir sur ce texte",
                             sous_titre="Claude, ChatGPT, Gemini, DeepSeek, Mistral, Ollama…", icone="list-add-symbolic",
                             score=99.0, section="Texte sélectionné")]
        extrait = selection[:MAX_SELECTION]
        resultats = []
        q = texte.normaliser(requete.strip())
        if requete.strip():
            resultats.append(Resultat(
                commande="assistant.question-selection", titre=f"Demander : « {requete.strip()} »",
                sous_titre="À propos du texte sélectionné", icone=ICONE, score=99.0, section="Texte sélectionné",
                argument=f"{requete.strip()}\n\nTexte :\n{extrait}"))
        for i, (cle, (titre, icone, _consigne)) in enumerate(ACTIONS.items()):
            if q and q not in texte.normaliser(titre):
                continue
            resultats.append(Resultat(commande=f"assistant.{cle}", titre=titre, icone=icone, argument=extrait,
                                      score=98.0 - i * 0.1, section="Texte sélectionné"))
        return resultats

    # --- Configuration (bouton +) --------------------------------------------------------------
    def creations(self) -> list[Creation]:
        if not self._plateforme_secrets():
            return []
        avec_cle = tuple(f.cle for f in ia_api.FOURNISSEURS.values() if f.avec_cle)
        return [Creation(
            type="fournisseur-ia", titre="Clé d'IA", titre_pluriel="IA configurées", icone=ICONE,
            description="Pour que l'IA réponde dans la barre et agisse sur le texte sélectionné.",
            champs=(
                Champ("fournisseur", "Fournisseur", type="choix",
                      options=tuple((f.cle, f.nom) for f in ia_api.FOURNISSEURS.values())),
                Champ("cle", "Clé d'API", type="secret", si=("fournisseur", avec_cle),
                      aide="Gardée dans le trousseau du système (Gestionnaire d'identifiants sous Windows)."),
                Champ("modele", "Modèle", obligatoire=False, exemple="laisser vide : choisi pour vous",
                      aide="Le nom exact chez le fournisseur ; vide = un bon modèle choisi automatiquement."),
                Champ("adresse", "Adresse d'Ollama", obligatoire=False, exemple="http://127.0.0.1:11434/v1",
                      si=("fournisseur", ("ollama",))),
            ),
            creer=self._creer, lister=self._lister, supprimer=self._supprimer,
        )]

    def _creer(self, valeurs: dict) -> Reponse:
        cle_f = valeurs.get("fournisseur", "")
        fournisseur = ia_api.FOURNISSEURS.get(cle_f)
        if fournisseur is None:
            raise CreationRefusee("Choisissez un fournisseur.", "fournisseur")
        cle = valeurs.get("cle", "").strip() if fournisseur.avec_cle else ""
        if fournisseur.avec_cle and not cle:
            raise CreationRefusee("Collez la clé d'API.", "cle")
        adresse = valeurs.get("adresse", "").strip() if cle_f == "ollama" else ""
        try:  # vérifie la clé et récupère les modèles
            disponibles = ia_api.modeles(fournisseur, cle, adresse)
        except ia_api.ErreurIA as exc:
            raise CreationRefusee(f"{fournisseur.nom} : {exc}", "cle" if fournisseur.avec_cle else "adresse") from None
        modele = valeurs.get("modele", "").strip() or ia_api.choisir_modele(fournisseur, disponibles)
        if not modele:
            raise CreationRefusee("Aucun modèle disponible : indiquez-en un.", "modele")
        if disponibles and modele not in disponibles:
            proches = [m for m in disponibles if texte.normaliser(modele) in texte.normaliser(m)][:5]
            raise CreationRefusee(f"Modèle inconnu chez {fournisseur.nom}"
                                  + (f" ; proches : {', '.join(proches)}" if proches else ""), "modele")
        if fournisseur.avec_cle:
            self.contexte.plateforme.secret_enregistrer(cle_f, cle)
        reglages = self._reglages()
        reglages.setdefault("fournisseurs", {})[cle_f] = {"modele": modele, **({"adresse": adresse} if adresse else {})}
        reglages["actif"] = cle_f
        self._ecrire(reglages)
        return Reponse(message=f"{fournisseur.nom.split(' (')[0]} prêt (modèle {modele})", fermer=False)

    def _lister(self) -> list[Element]:
        reglages = self._reglages()
        actif = self._actif()
        return [Element(cle=cle, titre=ia_api.FOURNISSEURS[cle].nom + (" — utilisée" if actif and actif[0].cle == cle else ""),
                        sous_titre=f"Modèle : {r.get('modele', '?')}")
                for cle, r in reglages.get("fournisseurs", {}).items() if cle in ia_api.FOURNISSEURS]

    def _supprimer(self, cle: str) -> Reponse:
        reglages = self._reglages()
        reglages.get("fournisseurs", {}).pop(cle, None)
        if reglages.get("actif") == cle:
            reglages.pop("actif", None)
        self._ecrire(reglages)
        try:
            self.contexte.plateforme.secret_supprimer(cle)
        except Exception:
            pass
        return Reponse(message="IA retirée", fermer=False)
