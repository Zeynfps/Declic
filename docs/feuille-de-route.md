# Feuille de route de Déclic

## 0.1 : première préversion
Barre GNOME (Super+R), applications, calculatrice et unités, liens de recherche, questions aux IA, favoris,
snippets, actions système, son et musique, scripts, identifiants (trousseau du système), automatisations
déclenchées par le PC (heure, Wi-Fi, verrouillage, alimentation, ouverture de session).

## 0.2 : Windows (sortie le 25 novembre 2026)
- **Windows 10 et 11**, avec les mêmes fonctions et réglages que sous GNOME. Reste à faire : l'éclairage
  nocturne sur les Windows 11 récents (voir `windows-eclairage-nocturne.md`).
- **Recherche de fichiers** par nom (index de GNOME, ou des dossiers personnels sous Windows).
- Envoi automatique des questions aux IA ; réglage « Assombrir la barre ».

## 0.3 : les cinq priorités
1. **Mode jeu et éditeur d'automatisations dans la barre** (voir « Automatisations » plus bas) : quand un jeu se
   lance, Ne pas déranger, son réglé, messageries en silencieux ; tout revient comme avant à sa fermeture.
   **Fait** : Mode jeu, déclencheurs jeu et application, conditions, activer/désactiver, fermer une application.
   Reste : « Tester maintenant » et un journal plus lisible dans la barre.
2. **Historique du presse-papiers** : chercher dans ce qu'on a copié et le recoller, épingler des éléments,
   garder les images, ne jamais enregistrer ce qui vient d'un gestionnaire de mots de passe.
3. **Actions sur le texte sélectionné** : traduire, reformuler, résumer, corriger, chercher, changer la casse.
   Réponse de l'IA affichée **dans la barre** (clé d'API ou modèle local comme Ollama), plus seulement dans le
   navigateur.
4. **Fenêtres** : passer d'une fenêtre à l'autre, fermer une application, ranger en moitiés ou en quarts,
   envoyer sur l'autre écran, dispositions enregistrées (« Mode révision » : PDF à gauche, notes à droite).
5. **Synchronisation des réglages** entre ses PC, Linux et Windows (liens, snippets, favoris, règles), et
   **snippets qui se tapent tout seuls** : `;mail` tapé dans n'importe quelle application devient le texte.

## Automatisations : la suite
- **Déclencheurs** : application lancée ou fermée, casque ou écran branché, batterie sous 20 %, inactivité,
  fichier apparu dans un dossier (ranger les Téléchargements tout seul), lever et coucher du soleil, début d'un
  cours ou d'une réunion (calendrier), appel venu d'ailleurs (Home Assistant, Stream Deck, téléphone).
- **Conditions** : application au premier plan, jeu ou application en plein écran, plage horaire.
- **Actions** : « activer » et « désactiver » en plus des bascules, fermer une application, changer la sortie
  audio, notification avec boutons, demander une valeur à l'utilisateur, variables, « si… sinon ».
- **Éditeur dans la barre** à la place de `regles.toml` : formulaire « Quand / Si / Alors », bouton
  « Tester maintenant », journal lisible.
- **Modèles prêts à l'emploi** : Mode jeu, Mode cours, Fin de journée, Rangement des téléchargements.
- **Suggestions** tirées de l'usage : « Vous coupez le son à chaque ouverture de Teams, en faire une règle ? »

## Dans la barre
- **Système** : choix de la sortie audio (casque, haut-parleurs), connexion des écouteurs Bluetooth,
  luminosité, empêcher la mise en veille, fermer de force une application figée, état de la batterie.
- **Petits outils** : émojis et symboles, pipette à couleurs, capture d'écran avec lecture du texte (OCR),
  devises, fuseaux horaires (« heure à Tokyo »), définitions et traduction, minuteur, rappels
  (« rappelle-moi dans 20 min de… »), notes rapides.
- **Études** : bibliothèque Zotero (chercher, copier la citation), emploi du temps depuis un calendrier .ics
  (« prochain cours »), recherche dans le texte des PDF.
- **Navigateur** : chercher dans les favoris, l'historique et les onglets ouverts.
- Raccourci clavier ou alias pour n'importe quelle commande ; variables `{presse-papiers}` et `{curseur}`
  dans les snippets.

## Design de la barre
- Panneau d'aperçu à droite : contenu d'un fichier, élément du presse-papiers, détail d'un calcul.
- Arguments en étiquettes : `wiki`, puis Tab, et une case « recherche » apparaît dans la barre.
- Visite guidée au premier lancement ; thème clair et couleur d'accent au choix.

## Ensuite
- **Téléphone** : appairage par QR code, puis déclencheurs envoyés par le téléphone sur le réseau local
  (application Android, automatisations Raccourcis sur iPhone) : « quand j'arrive à la maison… ».
- Bureaux virtuels, sessions de concentration.
- Extensions écrites par d'autres, avec un format simple (liste, détail, formulaire).
- Autres bureaux que GNOME (KDE…), et une version Windows installable en un seul fichier.

## Ce qui distingue Déclic
- Le même outil et la même configuration sous **Linux et Windows**.
- **Libre, local et en français**, avec des requêtes naturelles (« 15 % de 240 »).
- **Une barre de commande et un centre d'automatisations au même endroit**, bientôt pilotable depuis le
  téléphone.
