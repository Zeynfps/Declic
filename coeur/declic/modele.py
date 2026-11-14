"""Les objets de base : commande, résultat de recherche, réponse d'exécution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from declic.contexte import Contexte


@dataclass
class Reponse:
    """Ce que renvoie une commande exécutée."""

    statut: str = "ok"  # ok | erreur
    message: str = ""  # court, affiché en bandeau (HUD)
    texte: str = ""  # contenu plus long à afficher (sortie d'un script…)
    fermer: bool = True  # la barre doit-elle se fermer ?
    remplir: str = ""  # texte à mettre dans la barre de recherche (ex. « inrap » après l'ajout d'un lien)
    ouvrir: str = ""  # vue à ouvrir dans la barre (ex. « creer:lien » pour le formulaire d'ajout)

    @classmethod
    def erreur(cls, message: str) -> "Reponse":
        return cls(statut="erreur", message=message, fermer=False)

    def en_dict(self) -> dict:
        return {"statut": self.statut, "message": self.message, "texte": self.texte, "fermer": self.fermer,
                "remplir": self.remplir, "ouvrir": self.ouvrir}


Action = Callable[["Contexte", Optional[str]], Reponse]


@dataclass
class Commande:
    """Une commande du registre, identifiée par « module.nom »."""

    id: str
    titre: str
    action: Action
    description: str = ""
    icone: str = ""  # nom d'icône du thème (freedesktop), ou chemin
    mots_cles: tuple[str, ...] = ()
    confirmer: bool = False  # demander confirmation avant d'exécuter
    argument: Optional[str] = None  # nom de l'argument attendu (ex. « requête »), None si aucun
    requiert: Optional[str] = None  # capacité de la plateforme nécessaire (nom de méthode)
    cachee: bool = False  # n'apparaît pas dans la recherche (utilisée par les résultats dynamiques)

    @property
    def module(self) -> str:
        return self.id.split(".", 1)[0]


@dataclass
class Resultat:
    """Une ligne proposée dans la barre."""

    commande: str  # id de la commande à exécuter
    titre: str
    sous_titre: str = ""
    icone: str = ""
    score: float = 0.0
    argument: Optional[str] = None  # argument déjà rempli (ex. le résultat d'un calcul)
    confirmer: bool = False
    attend_argument: Optional[str] = None  # la barre doit demander cet argument
    module: str = field(default="")
    section: str = ""  # en-tête sous lequel la barre range la ligne (« Favoris »…) ; vide = choix de la barre
    favori: bool = False
    presque: bool = False  # le texte tapé est (presque) exactement son nom : passe en tête (registre)

    def en_dict(self) -> dict:
        return {
            "commande": self.commande,
            "titre": self.titre,
            "sous_titre": self.sous_titre,
            "icone": self.icone,
            "score": round(self.score, 3),
            "argument": self.argument,
            "confirmer": self.confirmer,
            "attend_argument": self.attend_argument,
            "module": self.module or self.commande.split(".", 1)[0],
            "section": self.section,
            "favori": self.favori,
        }


# --- Création d'éléments depuis la barre (liens, snippets… et ce qui viendra) ---------------
@dataclass(frozen=True)
class Champ:
    """Un champ du formulaire d'ajout."""

    cle: str
    titre: str
    aide: str = ""  # phrase d'aide sous le champ
    exemple: str = ""  # texte grisé dans le champ vide
    obligatoire: bool = True
    multiligne: bool = False
    type: str = "texte"  # texte | secret (masqué, jamais réaffiché) | choix (liste d'options)
    options: tuple[tuple[str, str], ...] = ()  # pour « choix » : (valeur, libellé) ; la 1re est la valeur par défaut
    si: Optional[tuple[str, tuple[str, ...]]] = None  # affiché seulement si le champ X vaut l'une de ces valeurs

    def visible(self, valeurs: dict) -> bool:
        if self.si is None:
            return True
        cle, attendues = self.si
        return valeurs.get(cle, "") in attendues

    def en_dict(self) -> dict:
        return {"cle": self.cle, "titre": self.titre, "aide": self.aide, "exemple": self.exemple,
                "obligatoire": self.obligatoire, "multiligne": self.multiligne, "type": self.type,
                "options": [{"valeur": v, "libelle": l} for v, l in self.options],
                "si": {"champ": self.si[0], "valeurs": list(self.si[1])} if self.si else None}


class CreationRefusee(Exception):
    """Saisie invalide : le message est montré à l'utilisateur, « champ » désigne le champ à corriger."""

    def __init__(self, message: str, champ: Optional[str] = None):
        super().__init__(message)
        self.champ = champ


@dataclass(frozen=True)
class Creation:
    """Un type d'élément qu'un module sait créer. « creer » reçoit les valeurs saisies (dict cle → texte)."""

    type: str
    titre: str
    description: str
    icone: str
    champs: tuple[Champ, ...]
    creer: Callable[[dict], Reponse]
    titre_pluriel: str = ""  # « Liens de recherche », pour la liste des éléments créés
    lister: Optional[Callable[[], list["Element"]]] = None  # éléments déjà créés par l'utilisateur
    supprimer: Optional[Callable[[str], Reponse]] = None  # reçoit Element.cle
    ajoutable: bool = True  # proposé dans « Ajouter » (faux pour les favoris, ajoutés depuis la recherche)

    def en_dict(self) -> dict:
        return {"type": self.type, "titre": self.titre, "titre_pluriel": self.titre_pluriel or self.titre,
                "description": self.description, "icone": self.icone,
                "champs": [c.en_dict() for c in self.champs],
                "gerable": self.lister is not None, "suppression": self.supprimer is not None,
                "ajoutable": self.ajoutable}


@dataclass(frozen=True)
class Element:
    """Un élément créé par l'utilisateur (un lien, un snippet…), tel que la barre l'affiche."""

    cle: str  # identifiant pour la suppression
    titre: str
    sous_titre: str = ""
    remplir: str = ""  # texte mis dans la recherche pour l'utiliser

    def en_dict(self) -> dict:
        return {"cle": self.cle, "titre": self.titre, "sous_titre": self.sous_titre, "remplir": self.remplir}
