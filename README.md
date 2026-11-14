# Déclic

**Une barre de commande au clavier et des automatisations pour Linux (GNOME).**

Appuyez sur **Super+R** : une barre s'ouvre au centre de l'écran. Tapez quelques lettres pour lancer une
application, faire un calcul, chercher sur un site, poser une question à une IA, changer un réglage du système
ou lancer une de vos automatisations, sans quitter le clavier.

> **Préversion (alpha).** Fonctionne sur **GNOME 51** (Wayland). Les autres bureaux, Windows et les
> applications pour téléphone ne sont pas encore disponibles.

## Ce que Déclic sait faire

| | |
|---|---|
| **Applications** | Lancer n'importe quelle application installée |
| **Calculatrice** | `15% de 240`, `(3+4)*2`, `100 km en miles`, nombres au format français ; Entrée copie le résultat |
| **Liens de recherche** | Un mot-clé puis la recherche : `wiki Gergovie`, `scholar céramique`, `persee …`, `hal …`, `gallica …` ; ajoutez les vôtres avec le bouton **+** |
| **Questions aux IA** | `gpt …`, `claude …`, `gemini …` ouvrent le navigateur avec la question ; toute recherche propose aussi « Demander à … » |
| **Favoris** | **Ctrl+Maj+F** sur un résultat l'épingle en haut de la barre vide (une appli, un réglage, une recherche, une question) |
| **Snippets** | Textes réutilisables avec variables (`{date}`, `{heure}`, `{jour}`, `{annee}`) |
| **Système** | Verrouiller, mise en veille, thème sombre, éclairage nocturne, Ne pas déranger, Wi-Fi, Bluetooth, mode avion, profil d'énergie, corbeille… |
| **Son et musique** | Volume, muet, micro, lecture/pause, piste suivante (toute application compatible MPRIS) |
| **Scripts** | Vos propres scripts, déposés dans `~/.config/declic/scripts/` |
| **Identifiants** | Remplit un formulaire de connexion avec un compte rangé dans le trousseau du système, après avoir vérifié l'adresse de la page |
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
| Ctrl+, ou le logo en bas à gauche | Réglages (flou, assombrissement, opacité) |
| Échap, Alt+← | Revenir en arrière, puis fermer |

## Installer

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
 Barre (extension GNOME Shell, JavaScript)  ──HTTP local + jeton──▶  Service Déclic (Python)
                                                                       ├─ registre et classement des commandes
                                                                       ├─ modules : applis, calcul, liens, IA…
                                                                       ├─ moteur d'automatisations
                                                                       └─ plateforme : Linux (D-Bus, GSettings…)
```

- `coeur/` : le service en Python. `declic/modules/` contient une partie par fonction, `declic/plateforme/`
  ce qui dépend du système (`linux.py` ; `windows.py` n'est qu'une ébauche non testée).
- `gnome/declic@zeynfps.github.io/` : l'extension GNOME Shell (la barre). Elle n'a aucune logique propre :
  elle affiche ce que le service renvoie.
- `linux/` : installateur et service systemd.
- `docs/` : feuille de route.

L'API écoute seulement sur `127.0.0.1` et demande un jeton, rangé dans `~/.local/share/declic/serveur.json`
(lisible par vous seul).

Essayer le service sans rien installer :

```bash
cd coeur
python3 -m unittest                       # tests
python3 -m declic commandes               # toutes les commandes disponibles
python3 -m declic chercher "15% de 240"   # recherche, comme dans la barre
```

## Feuille de route

Voir [docs/feuille-de-route.md](docs/feuille-de-route.md). Prochaines étapes : historique du presse-papiers,
changement de fenêtre, recherche de fichiers, puis déclencheurs envoyés par le téléphone (Android et iPhone).

## Licence

Déclic est un logiciel libre, distribué sous la licence **GNU GPL version 3 ou ultérieure**
(voir [LICENSE](LICENSE)). Vous pouvez l'utiliser, l'étudier, le modifier et le redistribuer ; les versions
modifiées doivent rester libres sous la même licence.
