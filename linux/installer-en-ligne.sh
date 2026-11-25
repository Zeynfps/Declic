#!/bin/bash
# Installe (ou met à jour) Déclic pour Linux (GNOME) en une seule commande :
#
#   curl -fsSL https://raw.githubusercontent.com/Zeynfps/Declic/main/linux/installer-en-ligne.sh | bash
#
# Télécharge la dernière version Linux publiée sur GitHub, la range dans ~/.local/share/declic/app, puis lance
# linux/installer.sh (service systemd utilisateur + extension GNOME Shell). Rien n'est installé hors de votre
# dossier personnel, pas besoin de sudo. Désinstaller : ~/.local/share/declic/app/linux/installer.sh --desinstaller
set -euo pipefail

DEPOT="Zeynfps/Declic"
DOSSIER="${XDG_DATA_HOME:-$HOME/.local/share}/declic/app"

for outil in curl tar python3; do
    command -v "$outil" >/dev/null || { echo "✘ « $outil » est nécessaire : installez-le puis relancez."; exit 1; }
done

# PyGObject : présent sur presque tous les GNOME, sinon on donne la commande exacte
if ! python3 -c "import gi" 2>/dev/null; then
    echo "✘ PyGObject manque. Installez-le puis relancez cette commande :"
    if command -v dnf >/dev/null; then echo "    sudo dnf install python3-gobject wl-clipboard"
    elif command -v apt >/dev/null; then echo "    sudo apt install python3-gi wl-clipboard"
    elif command -v pacman >/dev/null; then echo "    sudo pacman -S python-gobject wl-clipboard"
    else echo "    (paquet « python3-gobject » ou « python3-gi » de votre distribution)"; fi
    exit 1
fi

echo "→ Recherche de la dernière version"
adresse=$(curl -fsSL "https://api.github.com/repos/$DEPOT/releases" | python3 -c '
import json, sys
for version in json.load(sys.stdin):
    if version["tag_name"].endswith("-linux") and not version.get("draft"):
        for fichier in version["assets"]:
            if fichier["name"].endswith(".tar.gz"):
                print(version["tag_name"], fichier["browser_download_url"])
                sys.exit()
sys.exit("aucune version Linux publiée")')
version=${adresse%% *}
echo "→ Téléchargement de Déclic ${version%-linux}"
temporaire=$(mktemp -d)
trap 'rm -rf "$temporaire"' EXIT
curl -fsSL "${adresse#* }" -o "$temporaire/declic.tar.gz"

mkdir -p "$temporaire/app"
tar -xzf "$temporaire/declic.tar.gz" -C "$temporaire/app" --strip-components=1
mkdir -p "$(dirname "$DOSSIER")"
rm -rf "$DOSSIER"
mv "$temporaire/app" "$DOSSIER"

exec "$DOSSIER/linux/installer.sh"
