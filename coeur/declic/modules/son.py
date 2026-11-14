"""Volume, micro et contrôle de la musique."""
from __future__ import annotations

import re

from declic.modele import Commande, Reponse, Resultat
from declic import texte
from declic.modules import Module

_RE_VOLUME = re.compile(r"^\s*(?:vol|volume|son)\s+(\d{1,3})\s*%?\s*$")


def _volume(pourcent: int):
    def action(contexte, _argument):
        contexte.plateforme.definir_volume(pourcent)
        return Reponse(message=f"Volume : {pourcent} %")
    return action


def _changer(delta: int):
    def action(contexte, _argument):
        contexte.plateforme.changer_volume(delta)
        volume, muet = contexte.plateforme.lire_volume()
        return Reponse(message=f"Volume : {volume} %" + (" (muet)" if muet else ""))
    return action


def _media(commande: str, message: str):
    def action(contexte, _argument):
        lecteur = contexte.plateforme.media(commande)
        return Reponse(message=f"{message} ({lecteur})")
    return action


def _regler(contexte, argument):
    try:
        pourcent = int(str(argument).strip().rstrip("%"))
    except (TypeError, ValueError):
        return Reponse.erreur("Indiquez un volume entre 0 et 100.")
    if not 0 <= pourcent <= 100:
        return Reponse.erreur("Indiquez un volume entre 0 et 100.")
    contexte.plateforme.definir_volume(pourcent)
    return Reponse(message=f"Volume : {pourcent} %")


def _muet(contexte, _argument):
    muet = contexte.plateforme.basculer_muet()
    return Reponse(message="Son coupé" if muet else "Son rétabli")


def _micro(contexte, _argument):
    muet = contexte.plateforme.basculer_micro_muet()
    return Reponse(message="Micro coupé" if muet else "Micro rétabli")


class Son(Module):
    nom = "son"

    def commandes(self) -> list[Commande]:
        C = Commande
        commandes = [
            C("son.regler", "Régler le volume", _regler, argument="pourcentage", requiert="definir_volume",
              icone="audio-volume-medium-symbolic", mots_cles=("volume",)),
            C("son.monter", "Monter le volume", _changer(+10), icone="audio-volume-high-symbolic",
              mots_cles=("volume", "plus fort"), requiert="changer_volume"),
            C("son.baisser", "Baisser le volume", _changer(-10), icone="audio-volume-low-symbolic",
              mots_cles=("volume", "moins fort"), requiert="changer_volume"),
            C("son.muet", "Couper ou rétablir le son", _muet, icone="audio-volume-muted-symbolic",
              mots_cles=("mute", "silence"), requiert="basculer_muet"),
            C("son.micro", "Couper ou rétablir le micro", _micro, icone="microphone-disabled-symbolic",
              mots_cles=("micro", "mute"), requiert="basculer_micro_muet"),
            C("son.lecture-pause", "Lecture / pause", _media("lecture-pause", "Lecture / pause"),
              icone="media-playback-start-symbolic", mots_cles=("play", "pause", "musique"), requiert="media"),
            C("son.suivant", "Piste suivante", _media("suivant", "Piste suivante"),
              icone="media-skip-forward-symbolic", mots_cles=("next", "musique"), requiert="media"),
            C("son.precedent", "Piste précédente", _media("precedent", "Piste précédente"),
              icone="media-skip-backward-symbolic", mots_cles=("previous", "musique"), requiert="media"),
        ]
        for pourcent in (0, 25, 50, 75, 100):
            commandes.append(C(f"son.volume-{pourcent}", f"Volume à {pourcent} %", _volume(pourcent),
                               icone="audio-volume-medium-symbolic", mots_cles=("volume",),
                               requiert="definir_volume"))
        return commandes

    def resultats(self, requete: str) -> list[Resultat]:
        m = _RE_VOLUME.match(texte.normaliser(requete))
        if not m or int(m.group(1)) > 100:
            return []
        return [Resultat(commande="son.regler", titre=f"Volume à {int(m.group(1))} %",
                         icone="audio-volume-medium-symbolic", score=97.0, argument=m.group(1))]
