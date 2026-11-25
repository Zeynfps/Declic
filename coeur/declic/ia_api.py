"""Appels aux IA, sans bibliothèque à installer (urllib) : Déclic livre son propre Python, sans paquets.

Deux formats suffisent :
  - Claude (Anthropic) : l'API Messages (POST /v1/messages, en-têtes x-api-key et anthropic-version) ;
  - tous les autres : le format « compatible OpenAI » (POST …/chat/completions, en-tête Authorization: Bearer),
    proposé par OpenAI, Gemini, DeepSeek, Mistral, OpenRouter, Groq, xAI et Ollama (local).
La liste des modèles vient de chaque fournisseur (GET …/models) : pas de noms de modèles écrits en dur qui
vieilliraient, sauf un choix par défaut pour Claude.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

VERSION_ANTHROPIC = "2026-10-21"
DELAI_S = 120


@dataclass(frozen=True)
class Fournisseur:
    cle: str  # identifiant interne (« claude », « openai »…)
    nom: str
    format: str  # « anthropic » ou « openai »
    adresse: str  # racine de l'API
    avec_cle: bool = True
    prefere: tuple[str, ...] = ()  # mots cherchés dans les noms de modèles pour choisir le modèle par défaut
    modele_defaut: str = ""


FOURNISSEURS = {f.cle: f for f in (
    # Claude Opus 5.5, réglé sur un effort « low » : rapide pour des tâches courtes (traduire, corriger…)
    Fournisseur("claude", "Claude (Anthropic)", "anthropic", "https://api.anthropic.com/v1",
                modele_defaut="claude-opus-5-5"),
    Fournisseur("openai", "ChatGPT (OpenAI)", "openai", "https://api.openai.com/v1", prefere=("gpt-5", "gpt-4.1", "gpt-4o")),
    Fournisseur("gemini", "Gemini (Google)", "openai", "https://generativelanguage.googleapis.com/v1beta/openai",
                prefere=("gemini-2.5-flash", "gemini-flash", "gemini")),
    Fournisseur("deepseek", "DeepSeek", "openai", "https://api.deepseek.com", prefere=("deepseek-chat",)),
    Fournisseur("mistral", "Mistral", "openai", "https://api.mistral.ai/v1", prefere=("mistral-large", "mistral-medium")),
    Fournisseur("openrouter", "OpenRouter (tous les modèles)", "openai", "https://openrouter.ai/api/v1",
                prefere=("anthropic/claude", "openai/gpt")),
    Fournisseur("groq", "Groq", "openai", "https://api.groq.com/openai/v1", prefere=("llama-3.3", "llama")),
    Fournisseur("xai", "Grok (xAI)", "openai", "https://api.x.ai/v1", prefere=("grok",)),
    Fournisseur("ollama", "Ollama (sur ce PC, gratuit)", "openai", "http://127.0.0.1:11434/v1", avec_cle=False),
)}


class ErreurIA(Exception):
    pass


def _requete(methode: str, adresse: str, entetes: dict, corps: dict | None = None) -> dict:
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(adresse, data=donnees, method=methode,
                                     headers={"content-type": "application/json", "user-agent": "Declic", **entetes})
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_S) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            erreur = json.loads(detail)
            message = (erreur.get("error") or {}).get("message") if isinstance(erreur.get("error"), dict) \
                else erreur.get("error") or erreur.get("message")
        except ValueError:
            message = detail[:200]
        if exc.code in (401, 403):
            raise ErreurIA(f"clé refusée ({exc.code}) : {message or 'vérifiez la clé'}") from None
        if exc.code == 429:
            raise ErreurIA("trop de demandes ou crédit épuisé chez le fournisseur (429)") from None
        raise ErreurIA(f"erreur {exc.code} : {message or detail[:200]}") from None
    except urllib.error.URLError as exc:
        raise ErreurIA(f"impossible de joindre le service ({exc.reason})") from None
    except TimeoutError:
        raise ErreurIA("le service n'a pas répondu à temps") from None


def _entetes(fournisseur: Fournisseur, cle: str) -> dict:
    if fournisseur.format == "anthropic":
        return {"x-api-key": cle, "anthropic-version": VERSION_ANTHROPIC}
    return {"authorization": f"Bearer {cle}"} if cle else {}


def modeles(fournisseur: Fournisseur, cle: str, adresse: str = "") -> list[str]:
    """Modèles proposés par le fournisseur avec cette clé (sert aussi à vérifier la clé)."""
    racine = (adresse or fournisseur.adresse).rstrip("/")
    reponse = _requete("GET", f"{racine}/models", _entetes(fournisseur, cle))
    noms = [m.get("id", "") for m in reponse.get("data", []) if isinstance(m, dict)]
    return [n.removeprefix("models/") for n in noms if n]


def choisir_modele(fournisseur: Fournisseur, disponibles: list[str]) -> str:
    if fournisseur.modele_defaut and (not disponibles or fournisseur.modele_defaut in disponibles):
        return fournisseur.modele_defaut
    for mot in fournisseur.prefere:
        trouves = [m for m in disponibles if mot in m.lower() and "embed" not in m.lower() and "audio" not in m.lower()]
        if trouves:
            return sorted(trouves, key=len)[0]
    return disponibles[0] if disponibles else ""


def demander(fournisseur: Fournisseur, cle: str, modele: str, systeme: str, question: str, adresse: str = "") -> str:
    """Une question, une réponse (texte)."""
    racine = (adresse or fournisseur.adresse).rstrip("/")
    if fournisseur.format == "anthropic":
        corps = {"model": modele, "max_tokens": 16000, "system": systeme,
                 "messages": [{"role": "user", "content": question}]}
        if modele.startswith(("claude-opus", "claude-sonnet", "claude-haiku", "claude-fable")):
            corps["output_config"] = {"effort": "low"}  # tâches courtes : réponse rapide
        reponse = _requete("POST", f"{racine}/messages", _entetes(fournisseur, cle), corps)
        if reponse.get("stop_reason") == "refusal":
            raise ErreurIA("l'IA a refusé de répondre à cette demande")
        morceaux = [b.get("text", "") for b in reponse.get("content", []) if b.get("type") == "text"]
    else:
        corps = {"model": modele, "messages": [{"role": "system", "content": systeme},
                                               {"role": "user", "content": question}]}
        reponse = _requete("POST", f"{racine}/chat/completions", _entetes(fournisseur, cle), corps)
        morceaux = [(c.get("message") or {}).get("content") or "" for c in reponse.get("choices", [])[:1]]
    texte = "".join(morceaux).strip()
    if not texte:
        raise ErreurIA("réponse vide")
    return texte
