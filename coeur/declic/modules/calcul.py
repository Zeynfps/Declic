"""Calculatrice et conversions d'unités, directement dans la barre.

Exemples : « 2,5 * 4 », « 15% de 240 », « racine(2) », « 2^10 », « 5 km en miles », « 30 c en f ».
L'évaluation passe par l'arbre syntaxique de Python, avec une liste blanche stricte :
aucun code arbitraire ne peut être exécuté.
"""
from __future__ import annotations

import ast
import math
import operator
import re

from declic.modele import Commande, Reponse, Resultat
from declic.modules import Module

_OPERATEURS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNAIRES = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FONCTIONS = {
    "racine": math.sqrt, "sqrt": math.sqrt, "abs": abs, "arrondi": round, "round": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "ln": math.log, "log": math.log10,
    "exp": math.exp, "plancher": math.floor, "floor": math.floor, "plafond": math.ceil, "ceil": math.ceil,
}
_CONSTANTES = {"pi": math.pi, "π": math.pi, "e": math.e}

# Unités : (grandeur, facteur vers l'unité de base)
_UNITES: dict[str, tuple[str, float]] = {}


def _unite(grandeur: str, facteur: float, *noms: str) -> None:
    for nom in noms:
        _UNITES[nom] = (grandeur, facteur)


_unite("longueur", 0.001, "mm", "millimetre", "millimetres")
_unite("longueur", 0.01, "cm", "centimetre", "centimetres")
_unite("longueur", 1.0, "m", "metre", "metres")
_unite("longueur", 1000.0, "km", "kilometre", "kilometres")
_unite("longueur", 0.0254, "in", "pouce", "pouces", "inch", "inches")
_unite("longueur", 0.3048, "ft", "pied", "pieds", "foot", "feet")
_unite("longueur", 0.9144, "yd", "yard", "yards")
_unite("longueur", 1609.344, "mi", "mile", "miles")
_unite("masse", 0.001, "g", "gramme", "grammes")
_unite("masse", 0.000001, "mg", "milligramme", "milligrammes")
_unite("masse", 1.0, "kg", "kilo", "kilos", "kilogramme", "kilogrammes")
_unite("masse", 1000.0, "t", "tonne", "tonnes")
_unite("masse", 0.45359237, "lb", "lbs", "livre", "livres", "pound", "pounds")
_unite("masse", 0.028349523125, "oz", "once", "onces", "ounce", "ounces")
_unite("duree", 1.0, "s", "sec", "seconde", "secondes")
_unite("duree", 60.0, "min", "minute", "minutes")
_unite("duree", 3600.0, "h", "heure", "heures")
_unite("duree", 86400.0, "j", "jour", "jours", "day", "days")
_unite("duree", 604800.0, "semaine", "semaines", "week", "weeks")
_unite("donnees", 1.0, "o", "octet", "octets", "b", "byte", "bytes")
_unite("donnees", 1e3, "ko", "kb")
_unite("donnees", 1e6, "mo", "mb")
_unite("donnees", 1e9, "go", "gb")
_unite("donnees", 1e12, "to", "tb")
_unite("surface", 1.0, "m2", "m²")
_unite("surface", 1e-4, "cm2", "cm²")
_unite("surface", 1e6, "km2", "km²")
_unite("surface", 1e4, "ha", "hectare", "hectares")
_unite("surface", 100.0, "a", "are", "ares")

_TEMPERATURES = {
    "c": "c", "°c": "c", "celsius": "c",
    "f": "f", "°f": "f", "fahrenheit": "f",
    "k": "k", "kelvin": "k",
}

_RE_POURCENT = re.compile(r"^\s*([\d.,]+)\s*%\s*(?:de|of|sur)\s*(.+)$", re.IGNORECASE)
_RE_CONVERSION = re.compile(r"^\s*(-?[\d.,]+)\s*([^\d\s][^\s]*)\s+(?:en|in|to|vers|->)\s+([^\s]+)\s*$", re.IGNORECASE)


class ErreurCalcul(ValueError):
    pass


def _nombre(texte: str) -> float:
    texte = texte.strip().replace(" ", "").replace(" ", "")
    if "," in texte and "." not in texte:
        texte = texte.replace(",", ".")
    return float(texte)


def _evaluer_noeud(noeud):
    if isinstance(noeud, ast.Expression):
        return _evaluer_noeud(noeud.body)
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)) and not isinstance(noeud.value, bool):
        return noeud.value
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in _OPERATEURS:
        gauche, droite = _evaluer_noeud(noeud.left), _evaluer_noeud(noeud.right)
        if isinstance(noeud.op, ast.Pow) and abs(droite) > 1000:
            raise ErreurCalcul("puissance trop grande")
        return _OPERATEURS[type(noeud.op)](gauche, droite)
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _UNAIRES:
        return _UNAIRES[type(noeud.op)](_evaluer_noeud(noeud.operand))
    if isinstance(noeud, ast.Name) and noeud.id in _CONSTANTES:
        return _CONSTANTES[noeud.id]
    if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id in _FONCTIONS
            and not noeud.keywords and len(noeud.args) <= 2):
        return _FONCTIONS[noeud.func.id](*(_evaluer_noeud(a) for a in noeud.args))
    raise ErreurCalcul("expression non autorisée")


def evaluer(expression: str) -> float:
    texte = expression.strip().rstrip("=").strip()
    texte = texte.replace("×", "*").replace("÷", "/").replace("^", "**").replace("−", "-")
    # virgule décimale française : « 2,5 » → « 2.5 » (mais pas le séparateur d'arguments « f(1, 2) »)
    texte = re.sub(r"(?<=\d),(?=\d)", ".", texte)
    texte = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", texte)  # « 1 000 » → « 1000 »
    if len(texte) > 200:
        raise ErreurCalcul("expression trop longue")
    try:
        arbre = ast.parse(texte, mode="eval")
    except SyntaxError as exc:
        raise ErreurCalcul("syntaxe") from exc
    valeur = _evaluer_noeud(arbre)
    if isinstance(valeur, complex) or not math.isfinite(valeur):
        raise ErreurCalcul("résultat non fini")
    return float(valeur)


def convertir(valeur: float, depuis: str, vers: str) -> tuple[float, str]:
    d, v = depuis.casefold(), vers.casefold()
    if d in _TEMPERATURES and v in _TEMPERATURES:
        d, v = _TEMPERATURES[d], _TEMPERATURES[v]
        celsius = {"c": valeur, "f": (valeur - 32) * 5 / 9, "k": valeur - 273.15}[d]
        resultat = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[v]
        return resultat, {"c": "°C", "f": "°F", "k": "K"}[v]
    if d in _UNITES and v in _UNITES:
        (gd, fd), (gv, fv) = _UNITES[d], _UNITES[v]
        if gd != gv:
            raise ErreurCalcul(f"on ne peut pas convertir des {gd} en {gv}")
        return valeur * fd / fv, vers
    raise ErreurCalcul("unité inconnue")


def formater(valeur: float) -> str:
    """Format français : virgule décimale, espaces fines pour les milliers, pas de zéros inutiles."""
    if valeur == int(valeur) and abs(valeur) < 1e15:
        texte = f"{int(valeur):,}".replace(",", " ")
        return texte
    texte = f"{valeur:.10g}"
    if "e" in texte:
        return texte.replace(".", ",")
    entier, _, decimales = texte.partition(".")
    entier = f"{int(entier):,}".replace(",", " ") if entier.lstrip("-").isdigit() else entier
    if texte.startswith("-0"):
        entier = "-0"
    return f"{entier},{decimales}" if decimales else entier


def _ressemble_a_un_calcul(texte: str) -> bool:
    return bool(re.search(r"\d", texte)) and bool(
        re.search(r"[+\-*/×÷^%()]|\b(?:racine|sqrt|sin|cos|tan|ln|log|exp|abs)\b|\s(?:en|in|to)\s", texte)
    )


def calculer(requete: str) -> tuple[float, str] | None:
    """Renvoie (valeur, unité affichée) ou None si la requête n'est pas un calcul."""
    if not _ressemble_a_un_calcul(requete):
        return None
    try:
        m = _RE_POURCENT.match(requete)
        if m:
            return _nombre(m.group(1)) / 100 * evaluer(m.group(2)), ""
        m = _RE_CONVERSION.match(requete)
        if m:
            valeur, unite = convertir(_nombre(m.group(1)), m.group(2), m.group(3))
            return round(valeur, 4), unite  # une conversion n'a pas besoin de 10 décimales
        return evaluer(requete), ""
    except (ErreurCalcul, ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None


class Calcul(Module):
    nom = "calcul"

    def commandes(self) -> list[Commande]:
        return [Commande(
            id="calcul.copier", titre="Copier le résultat", action=self._copier,
            argument="résultat", requiert="copier_texte", cachee=True,
        )]

    def _copier(self, contexte, argument):
        if not argument:
            return Reponse.erreur("Rien à copier.")
        contexte.plateforme.copier_texte(argument)
        return Reponse(message=f"« {argument} » copié")

    def resultats(self, requete: str) -> list[Resultat]:
        calcul = calculer(requete)
        if calcul is None:
            return []
        valeur, unite = calcul
        texte = formater(valeur) + (f" {unite}" if unite else "")
        return [Resultat(
            commande="calcul.copier", titre=f"= {texte}", sous_titre=f"{requete.strip()} · Entrée pour copier",
            icone="accessories-calculator-symbolic", score=95.0, argument=texte,
        )]
