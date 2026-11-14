"""Ligne de commande : lancer le service, ou chercher / exécuter sans interface.

    python3 -m declic serveur            lance l'API locale (utilisée par la barre)
    python3 -m declic chercher "15% de 240"
    python3 -m declic lancer systeme.theme-sombre
    python3 -m declic commandes          liste toutes les commandes disponibles
"""
from __future__ import annotations

import argparse
import logging
import sys

from declic import __version__, chemins
from declic.plateforme import detecter
from declic.registre import Registre


def _registre() -> Registre:
    return Registre(detecter(), chemins.par_defaut())


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="declic", description="Barre de commande et automatisations.")
    analyseur.add_argument("--version", action="version", version=f"Déclic {__version__}")
    analyseur.add_argument("-v", "--verbeux", action="store_true", help="journal détaillé")
    sous = analyseur.add_subparsers(dest="action", required=True)

    p_serveur = sous.add_parser("serveur", help="lancer l'API locale")
    p_serveur.add_argument("--port", type=int, default=None)

    p_chercher = sous.add_parser("chercher", help="chercher des commandes")
    p_chercher.add_argument("requete", nargs="?", default="")
    p_chercher.add_argument("-n", "--limite", type=int, default=10)

    p_lancer = sous.add_parser("lancer", help="exécuter une commande")
    p_lancer.add_argument("commande")
    p_lancer.add_argument("argument", nargs="?")
    p_lancer.add_argument("-o", "--oui", action="store_true", help="ne pas demander confirmation")

    sous.add_parser("commandes", help="lister toutes les commandes disponibles")
    sous.add_parser("regles", help="vérifier les automatisations (regles.toml)")

    args = analyseur.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbeux else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    registre = _registre()

    if args.action == "serveur":
        from declic.serveur import PORT_PAR_DEFAUT, creer_serveur

        serveur = creer_serveur(registre, args.port or PORT_PAR_DEFAUT)
        registre.demarrer_automatisations()
        print(f"Déclic {__version__} écoute sur http://127.0.0.1:{serveur.server_address[1]} "
              f"({registre.contexte.plateforme.nom})", flush=True)
        try:
            serveur.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            serveur.server_close()
        return 0

    if args.action == "chercher":
        for r in registre.rechercher(args.requete, args.limite):
            extra = f" [{r.argument}]" if r.argument else (f" <{r.attend_argument}>" if r.attend_argument else "")
            print(f"{r.score:6.1f}  {r.commande:<36} {r.titre}{extra}")
        return 0

    if args.action == "commandes":
        toutes = registre.commandes()
        for c in sorted(toutes.values(), key=lambda c: c.id):
            if not c.cachee:
                print(f"{c.id:<40} {c.titre}" + (" (confirmation)" if c.confirmer else ""))
        print(f"\n{sum(not c.cachee for c in toutes.values())} commandes", file=sys.stderr)
        return 0

    if args.action == "regles":
        auto = registre.automatisations
        print(auto.rapport() if auto else "Module d'automatisation absent")
        return 1 if auto and (auto.erreurs or auto.verifier_actions()) else 0

    if args.action == "lancer":
        commande = registre.commandes().get(args.commande)
        if commande and commande.confirmer and not args.oui:
            if input(f"{commande.titre} : confirmer ? [o/N] ").strip().casefold() not in ("o", "oui", "y"):
                print("Annulé.")
                return 1
        reponse = registre.executer(args.commande, args.argument)
        print(("✔ " if reponse.statut == "ok" else "✘ ") + reponse.message)
        if reponse.texte:
            print(reponse.texte)
        return 0 if reponse.statut == "ok" else 1

    return 2
