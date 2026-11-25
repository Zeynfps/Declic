# Journal des versions

## À venir

- **Windows** (10 et 11) : barre Electron ouverte par Alt+Espace, identique à celle de GNOME (vues, actions
  Ctrl+K, favoris, ajouts, réglages), icône dans la zone de notification, démarrage avec Windows, installateur
  `windows\installer.ps1`. Autour de la barre, l'écran flouté et assombri ; la barre en verre dépoli (reflet,
  réfraction sur les bords), opacité et teinte réglables. Logos réels des applications (raccourcis, Store,
  Steam). Plateforme Windows du service, avec les mêmes fonctions que sous Linux : applications du menu
  Démarrer et du Store, presse-papiers, notifications, verrouillage, veille, mode d'alimentation, corbeille,
  thème sombre, éclairage nocturne, Ne pas déranger, fichiers cachés, Wi-Fi, Bluetooth, mode avion, volume et
  micro, touches multimédia, recherche de fichiers, Gestionnaire d'identifiants avec remplissage des pages de
  connexion, envoi automatique des questions aux IA, et déclencheurs (verrouillage, secteur/batterie, Wi-Fi).
- Nouveau réglage « Assombrir la barre » (du gris graphite au noir), sous GNOME comme sous Windows.
- Tests : les fichiers de test sont écrits en UTF-8 explicite (sous Windows, l'encodage par défaut n'est pas
  l'UTF-8) ; tests propres à Windows et vérification sous Windows dans l'intégration continue.
- « Identifiant de site » n'est proposé dans « Ajouter » que si la plateforme sait remplir les pages.
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
