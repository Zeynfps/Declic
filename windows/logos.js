'use strict';
// Logos des applications et des fichiers, pour la barre (processus principal d'Electron).
const { app, nativeImage, shell } = require('electron');
const fs = require('fs');
const path = require('path');

// Logo d'une application ou d'un fichier, en image (data:) de 32 pixels.
//   - image (.png, .ico…) : lue telle quelle (logos du Store, icônes des jeux Steam) ;
//   - raccourci .lnk : on suit le raccourci jusqu'au programme (Windows ne donne sinon que l'icône
//     générique des raccourcis : page blanche et flèche) ;
//   - programme ou document : l'icône que Windows lui associe.
const IMAGES = new Set(['.png', '.jpg', '.jpeg', '.ico', '.bmp']);

async function iconeFichier(chemin, profondeur = 0) {
  if (typeof chemin !== 'string' || !path.isAbsolute(chemin) || !fs.existsSync(chemin)) return null;
  const extension = path.extname(chemin).toLowerCase();
  let image = null;
  if (IMAGES.has(extension)) {
    image = nativeImage.createFromPath(chemin);
  } else if (extension === '.lnk' && profondeur < 2) {
    let lien = null;
    try { lien = shell.readShortcutLink(chemin); } catch { lien = null; }
    const source = [lien?.icon, lien?.target].find((c) => c && path.isAbsolute(c) && fs.existsSync(c));
    if (source) return iconeFichier(source, profondeur + 1);
  }
  if (!image || image.isEmpty()) image = await app.getFileIcon(chemin, { size: 'large' });
  if (image.isEmpty()) return null;
  const { width } = image.getSize();
  return (width > 32 ? image.resize({ width: 32, height: 32, quality: 'best' }) : image).toDataURL();
}

module.exports = { iconeFichier };
