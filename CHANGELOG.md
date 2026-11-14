# Journal des versions

## À venir

- Recherche de fichiers et de dossiers par nom (index de GNOME), avec « Afficher dans le dossier » et
  « Copier le chemin » dans les actions.
- Résultats rangés par sections : Applications, puis Fichiers, puis Fonctionnalités ; un nom presque
  identique à ce qui est tapé (une ou deux fautes) passe en « Meilleur résultat ».
- Les questions posées à ChatGPT, Claude ou Gemini sont envoyées automatiquement une fois la page ouverte.
- La ligne sous la souris ne vole plus la sélection quand la liste change sous un pointeur immobile.

## 0.1.0 — préversion

Première version publique, pour GNOME 51.

- Barre de commande (Super+R) : recherche floue, actions (Ctrl+K), retour en arrière, réglages d'apparence,
  mémoire de la vue quand on la ferme en cliquant à côté.
- Modules : applications, calculatrice et unités, liens de recherche, questions aux IA (ChatGPT, Claude,
  Gemini), favoris, snippets, actions système, son et musique, scripts, identifiants.
- Ajout et suppression des liens, snippets, identifiants et automatisations depuis la barre.
- Automatisations « quand → si → alors » déclenchées par l'heure, le Wi-Fi, le verrouillage, l'alimentation
  ou l'ouverture de session.
- Service local (API HTTP sur 127.0.0.1 avec jeton) et installateur pour l'utilisateur, sans droits administrateur.
