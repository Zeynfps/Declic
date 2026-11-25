# Journal des versions

## À venir

- **L'IA dans la barre**, avec la clé de votre choix (bouton + → « Clé d'IA ») : Claude, ChatGPT, Gemini, DeepSeek,
  Mistral, OpenRouter, Groq, Grok, ou Ollama sur le PC (gratuit). Clés gardées dans le trousseau du système.
  « ia question » répond dans la barre ; toute recherche propose aussi « Demander à … ici ».
- **Texte sélectionné** (Windows, Alt+Maj+Espace) : traduire, corriger, reformuler, résumer, expliquer, rendre plus
  formel, ou poser une question sur le texte ; Ctrl+Entrée remplace la sélection par la réponse. Jamais dans un
  terminal ni un jeu en plein écran ; le presse-papiers est remis comme avant.
- **Panneaux autour de la barre** (Windows), comme la Game Bar : presse-papiers, applications épinglées, bloc-notes
  enregistré tout seul, dépôt de fichiers (glisser-déposer, dans un sens comme dans l'autre). Chacun se masque dans
  les réglages.
- Les deux raccourcis (ouvrir Déclic, texte sélectionné) se changent dans les réglages, au clavier.
- Les bascules (Bluetooth, Wi-Fi, Ne pas déranger, mode avion, thème sombre…) affichent leur état dans la
  barre : « Activé » ou « Désactivé », avec un petit interrupteur.

## 0.3.0 — Mode jeu et presse-papiers (25 novembre 2026)

- **Historique du presse-papiers** : `pp` dans la barre liste les 200 derniers textes copiés (`pp mot` filtre) ;
  Entrée recolle directement dans l'application d'où l'on vient (Windows ; sous GNOME, le texte est copié et
  Ctrl+V suffit). Les textes marqués comme secrets par les gestionnaires de mots de passe ne sont pas gardés.
  « Effacer l'historique du presse-papiers » le vide.
- **Mode jeu** (bouton + → Mode jeu) : au lancement d'un jeu, Ne pas déranger, mode performance, volume,
  applications à fermer ; tout revient comme avant à la fermeture du jeu. Jeux reconnus d'après leur dossier
  (Steam et Proton, Epic, Riot, GOG, Xbox, EA, Ubisoft, Lutris, Heroic), lanceurs et anti-triche exclus.
- Automatisations : nouveaux déclencheurs « jeu lancé / fermé » et « application ouverte / fermée » ;
  conditions « si telle application est ouverte » et « si un jeu tourne » ; actions « activer » et
  « désactiver » (Ne pas déranger, Wi-Fi, Bluetooth, mode avion, thème sombre…) qui ne basculent pas deux fois,
  et « fermer une application ». Le formulaire de la barre propose « remettre comme avant » à la fermeture.
- Installation simplifiée : un `.exe` pour Windows (Python compris), une commande pour Linux ; fichiers
  fabriqués par GitHub à chaque version.

## 0.2.0 — Windows (25 novembre 2026)

- **Windows** (10 et 11) : barre Electron ouverte par Alt+Espace, identique à celle de GNOME (vues, actions
  Ctrl+K, favoris, ajouts, réglages), icône dans la zone de notification, démarrage avec Windows, installateur
  `windows\installer.ps1`. Autour de la barre, l'écran flouté et assombri ; la barre en verre dépoli (reflet,
  réfraction sur les bords), opacité et teinte réglables. Logos réels des applications (raccourcis, Store,
  Steam). Plateforme Windows du service, avec les mêmes fonctions que sous Linux : applications du menu
  Démarrer et du Store, presse-papiers, notifications, verrouillage, veille, mode d'alimentation, corbeille,
  thème sombre, éclairage nocturne, Ne pas déranger, fichiers cachés, Wi-Fi, Bluetooth, mode avion, volume et
  micro, touches multimédia, recherche de fichiers, Gestionnaire d'identifiants avec remplissage des pages de
  connexion, envoi automatique des questions aux IA, et déclencheurs (verrouillage, secteur/batterie, Wi-Fi).
  Pas encore au point : l'éclairage nocturne, sans effet sur les Windows 11 récents
  (voir `docs/windows-eclairage-nocturne.md`).
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
