# Déclic

**Une barre de commande au clavier et des automatisations pour Linux (GNOME) et Windows.**

Appuyez sur **Super+R** (Linux) ou **Alt+Espace** (Windows) : une barre s'ouvre au centre de l'écran. Tapez
quelques lettres pour lancer une application, faire un calcul, chercher sur un site, poser une question à une
IA, changer un réglage du système ou lancer une de vos automatisations, sans quitter le clavier.

> **Préversion (alpha).** Fonctionne sur **GNOME 51** (Wayland) et, **nouveau**, sur **Windows 10 et 11**,
> avec les mêmes fonctions et les mêmes réglages. Les autres bureaux et les applications pour téléphone ne sont
> pas encore disponibles.

## Ce que Déclic sait faire

| | |
|---|---|
| **Applications** | Lancer n'importe quelle application installée |
| **Fichiers** | Taper une partie du nom (`rapport fouille`) pour ouvrir un fichier ou un dossier, ou l'afficher dans son dossier (Ctrl+K) ; utilise l'index de GNOME, ou sous Windows celui de vos dossiers personnels |
| **Calculatrice** | `15% de 240`, `(3+4)*2`, `100 km en miles`, nombres au format français ; Entrée copie le résultat |
| **Liens de recherche** | Un mot-clé puis la recherche : `wiki Gergovie`, `scholar céramique`, `persee …`, `hal …`, `gallica …` ; ajoutez les vôtres avec le bouton **+** |
| **Questions aux IA** | `gpt …`, `claude …`, `gemini …` ouvrent le navigateur et envoient la question ; toute recherche propose aussi « Demander à … » |
| **Favoris** | **Ctrl+Maj+F** sur un résultat l'épingle en haut de la barre vide (une appli, un réglage, une recherche, une question) |
| **Snippets** | Textes réutilisables avec variables (`{date}`, `{heure}`, `{jour}`, `{annee}`) |
| **Système** | Verrouiller, mise en veille, thème sombre, éclairage nocturne, Ne pas déranger, Wi-Fi, Bluetooth, mode avion, profil d'énergie, corbeille… |
| **Son et musique** | Volume, muet, micro, lecture/pause, piste suivante (toute application compatible MPRIS, ou sous Windows qui répond aux touches multimédia) |
| **Scripts** | Vos propres scripts, déposés dans `~/.config/declic/scripts/` |
| **Identifiants** | Remplit un formulaire de connexion avec un compte rangé dans le trousseau du système (Gestionnaire d'identifiants sous Windows), après avoir vérifié l'adresse de la page |
| **Automatisations** | Règles « quand → si → alors » : à une heure donnée, en se connectant à un Wi-Fi, au déverrouillage, en branchant le chargeur… |

La barre retient où vous en étiez : si vous la fermez en cliquant à côté ou avec Super+R, elle se rouvre au
même endroit. Échap la remet à zéro.

### Raccourcis de la barre

| Touche | Action |
|---|---|
| Entrée | Action principale |
| Ctrl+Entrée | Action secondaire |
| Ctrl+K | Toutes les actions du résultat |
| Ctrl+Maj+F | Ajouter aux favoris / retirer |
| Ctrl+N ou **+** | Ajouter un lien, un snippet, une automatisation… |
| Ctrl+, ou le logo en bas à gauche | Réglages (flou et assombrissement de l'arrière-plan, opacité et teinte de la barre) |
| Échap, Alt+← | Revenir en arrière, puis fermer |

## Installer sous Linux

Prérequis : GNOME Shell 51, Python ≥ 3.11, PyGObject (`python3-gobject` sur Fedora, `python3-gi` sur
Debian/Ubuntu) et `wl-clipboard`.

```bash
git clone https://github.com/Zeynfps/Declic.git
cd Declic
linux/installer.sh
```

L'installateur lance les tests, installe un service systemd utilisateur et l'extension GNOME Shell. Sous
Wayland, **déconnectez-vous puis reconnectez-vous** pour que GNOME charge l'extension, puis appuyez sur Super+R.

Désinstaller : `linux/installer.sh --desinstaller` (vos réglages dans `~/.config/declic` sont conservés).

## Installer sous Windows

Prérequis : Windows 10 ou 11, [Python](https://www.python.org) ≥ 3.11 et [Node.js](https://nodejs.org) ≥ 20.
L'installateur propose d'installer Python avec winget s'il manque.

```powershell
git clone https://github.com/Zeynfps/Declic.git
cd Declic
powershell -ExecutionPolicy Bypass -File windows\installer.ps1
```

L'installateur lance les tests, installe la barre (Electron), crée le raccourci « Déclic » du menu Démarrer et
démarre Déclic. Appuyez ensuite sur **Alt+Espace**. L'icône de Déclic, dans la zone de notification, propose
« Démarrer avec Windows », les réglages et « Quitter ».

Désinstaller : `powershell -ExecutionPolicy Bypass -File windows\installer.ps1 -Desinstaller`
(vos réglages dans `%APPDATA%\Declic` sont conservés).

La barre Windows fonctionne comme celle de GNOME : mêmes vues, mêmes raccourcis, mêmes commandes et mêmes
réglages. Autour de la barre, l'écran est flouté et assombri (deux curseurs) ; la barre elle-même est en verre
dépoli, avec une opacité et une teinte réglables (« Assombrir la barre »). Toutes les fonctions du tableau
ci-dessus sont disponibles, y compris Ne pas déranger, le mode avion, le remplissage des identifiants et l'envoi
automatique des questions aux IA (Firefox, Chrome, Edge, Brave, Opera, Vivaldi). Seule exception pour
l'instant : l'éclairage nocturne ne s'applique pas encore à l'écran sur les Windows 11 récents
(voir [docs/windows-eclairage-nocturne.md](docs/windows-eclairage-nocturne.md)). La
recherche de fichiers utilise un index des dossiers personnels (Bureau, Documents, Téléchargements, Images,
Musique, Vidéos, OneDrive) tenu par Déclic.

Sous Windows, les fichiers de réglages sont dans `%APPDATA%\Declic` (au lieu de `~/.config/declic`) et
le raccourci se change dans `%APPDATA%\Declic\barre.json` (« raccourci », par exemple `"Control+Space"`).

## Personnaliser

Tout se fait depuis la barre (bouton **+**, et Réglages → « Mes liens, snippets… »), ou dans des fichiers
texte faciles à modifier :

| Fichier | Contenu |
|---|---|
| `~/.config/declic/liens.toml` | Liens de recherche : `[[lien]]` nom, mot_cle, url avec `{requete}` |
| `~/.config/declic/snippets.toml` | Snippets : `[[snippet]]` nom, mot_cle, texte |
| `~/.config/declic/favoris.toml` | Favoris, dans l'ordre d'affichage |
| `~/.config/declic/regles.toml` | Automatisations |
| `~/.config/declic/scripts/` | Scripts, avec un en-tête `# @declic titre: …` |

Les mots de passe ne sont jamais écrits dans ces fichiers : ils restent dans le trousseau du système
(Secret Service).

### Automatisations

Une règle = **quand** (déclencheur) + **si** (conditions, facultatif) + **alors** (actions). Les actions sont
les commandes de la barre, plus `attendre:5` et `notifier:texte`.

```toml
[[regle]]
nom   = "Mode révision"
quand = "manuel"                      # « Lancer : Mode révision » dans la barre
alors = ["systeme.ne-pas-deranger", "son.volume-25", "notifier:Bon courage !"]

[[regle]]
nom   = "Arrivée à la fac"
quand = { evenement = "wifi.connecte", valeur = "eduroam" }
si    = { jours = ["semaine"] }
alors = ["liens.ouvrir:https://moodle.exemple.fr", "son.volume-0"]
```

Déclencheurs : `"manuel"`, `{ heure = "08:30", jours = [...] }`, `{ evenement = ... }`
(`session.verrouillee`, `session.deverrouillee`, `alimentation.secteur`, `alimentation.batterie`,
`wifi.connecte`, `wifi.deconnecte`, `reseau.connecte`, `declic.demarrage`).
Vérifier ses règles : `python3 -m declic regles`, ou dans la barre, Réglages → « Mes automatisations ».

## Comment c'est construit

```
 Barre (extension GNOME Shell,   ──HTTP local + jeton──▶  Service Déclic (Python)
  ou Electron sous Windows)                                ├─ registre et classement des commandes
                                                           ├─ modules : applis, calcul, liens, IA…
                                                           ├─ moteur d'automatisations
                                                           └─ plateforme : Linux (D-Bus, GSettings…)
                                                                           ou Windows (API Win32, COM, registre)
```

- `coeur/` : le service en Python. `declic/modules/` contient une partie par fonction, `declic/plateforme/`
  ce qui dépend du système (`linux.py`, `windows.py`).
- `gnome/declic@zeynfps.github.io/` : l'extension GNOME Shell (la barre). Elle n'a aucune logique propre :
  elle affiche ce que le service renvoie.
- `windows/` : la barre pour Windows (Electron), qui lance aussi le service, et son installateur.
- `linux/` : installateur et service systemd.
- `docs/` : feuille de route.

L'API écoute seulement sur `127.0.0.1` et demande un jeton, rangé dans `~/.local/share/declic/serveur.json`
(`%LOCALAPPDATA%\Declic\serveur.json` sous Windows), lisible par vous seul.

Essayer le service sans rien installer :

```bash
cd coeur
python3 -m unittest                       # tests
python3 -m declic commandes               # toutes les commandes disponibles
python3 -m declic chercher "15% de 240"   # recherche, comme dans la barre
```

## Feuille de route

Voir [docs/feuille-de-route.md](docs/feuille-de-route.md). Prochaines étapes : historique du presse-papiers,
changement de fenêtre, puis déclencheurs envoyés par le téléphone (Android et iPhone).

## Licence

Déclic est un logiciel libre, distribué sous la licence **GNU GPL version 3 ou ultérieure**
(voir [LICENSE](LICENSE)). Vous pouvez l'utiliser, l'étudier, le modifier et le redistribuer ; les versions
modifiées doivent rester libres sous la même licence.
