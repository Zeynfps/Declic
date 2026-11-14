#!/bin/bash
# Installe Déclic pour l'utilisateur courant (sans sudo) :
#   1. le service (systemd utilisateur) qui fait tourner le cœur Python ;
#   2. l'extension GNOME Shell (la barre, raccourci Super+R).
# Désinstaller : linux/installer.sh --desinstaller
set -euo pipefail
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
COEUR="$RACINE/coeur"
UUID="declic@zeynfps.github.io"
ANCIENS_UUID=("declic@declic.app")  # identifiants des versions précédentes, retirés à l'installation
EXT_SRC="$RACINE/gnome/$UUID"
EXT_DST="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$UUID"
UNITE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/declic.service"

if [[ "${1:-}" == "--desinstaller" ]]; then
    gnome-extensions disable "$UUID" 2>/dev/null || true
    systemctl --user disable --now declic.service 2>/dev/null || true
    rm -f "$UNITE"; systemctl --user daemon-reload
    rm -rf "$EXT_DST"
    echo "Déclic désinstallé (vos réglages dans ~/.config/declic sont conservés)."
    exit 0
fi

echo "→ Vérification des dépendances"
python3 -c "import gi; gi.require_version('Gio', '2.0')" 2>/dev/null \
    || { echo "✘ PyGObject manquant (Fedora : python3-gobject, Debian/Ubuntu : python3-gi)"; exit 1; }
command -v wl-copy >/dev/null || command -v xclip >/dev/null \
    || echo "⚠ wl-clipboard absent : la copie (calculs, snippets) ne marchera pas. Installez le paquet « wl-clipboard »."

echo "→ Tests du cœur"
(cd "$COEUR" && python3 -m unittest -q)

echo "→ Service systemd utilisateur"
mkdir -p "$(dirname "$UNITE")"
sed "s|@COEUR@|$COEUR|g" "$RACINE/linux/declic.service" > "$UNITE"
systemctl --user daemon-reload
systemctl --user enable declic.service
systemctl --user restart declic.service  # recharge le code si le service tournait déjà
sleep 1
systemctl --user --no-pager --lines=0 status declic.service | head -3

echo "→ Extension GNOME Shell"
glib-compile-schemas "$EXT_SRC/schemas"
mkdir -p "$(dirname "$EXT_DST")"
# Anciennes versions sous un autre identifiant : désactivées et retirées (les réglages GSettings restent)
for ancien in "${ANCIENS_UUID[@]}"; do
    dossier="$(dirname "$EXT_DST")/$ancien"
    if [[ -d "$dossier" ]]; then
        gnome-extensions disable "$ancien" 2>/dev/null || true
        rm -rf "$dossier"
        echo "  ancienne extension $ancien retirée"
    fi
done
rm -rf "$EXT_DST"
cp -r "$EXT_SRC" "$EXT_DST"
gnome-extensions enable "$UUID" 2>/dev/null || true
# Sous Wayland, GNOME ne connaît pas encore une nouvelle extension : on l'ajoute nous-mêmes à la liste des
# extensions activées (et on en retire les anciens identifiants), en gardant toutes les autres.
# Elle se chargera à la prochaine connexion.
avant=$(gsettings get org.gnome.shell enabled-extensions)
nouvelle=$(printf '%s' "$avant" | python3 -c '
import ast, sys
texte = sys.stdin.read().strip().removeprefix("@as ")
liste = ast.literal_eval(texte) if texte else []
liste = [x for x in liste if x not in sys.argv[2:]]
if sys.argv[1] not in liste:
    liste.append(sys.argv[1])
print(repr(liste))' "$UUID" "${ANCIENS_UUID[@]}")
if [[ "$nouvelle" != "$avant" ]]; then
    mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/declic"
    printf '%s\n' "$avant" > "${XDG_DATA_HOME:-$HOME/.local/share}/declic/extensions-avant-installation.txt"
    gsettings set org.gnome.shell enabled-extensions "$nouvelle"
fi
cat <<FIN

Déclic est installé.
  • Sous Wayland, GNOME ne charge une nouvelle extension qu'après une reconnexion :
    déconnectez-vous puis reconnectez-vous, puis appuyez sur Super+R.
  • Réglages : ~/.config/declic (liens.toml, snippets.toml, scripts/)
  • Journal du service : journalctl --user -u declic -f
FIN
