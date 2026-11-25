'use strict';
// Prépare le Python qui sera livré avec l'installateur Windows : la distribution « embarquable » officielle de
// python.org (environ 10 Mo, sans installation), dans build/python. Ainsi, Déclic s'installe sans que
// l'utilisateur ait Python sur son PC.
//
//   node outils/preparer-python.js        (lancé par « npm run construire »)
//
// Le fichier python3XX._pth est réécrit pour que Python trouve le service Déclic, livré à côté dans
// resources/coeur (chemin relatif au dossier de python.exe).

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const VERSION = process.env.DECLIC_PYTHON || '3.13.17';
const RACINE = path.join(__dirname, '..');
const CACHE = path.join(RACINE, 'build', 'cache');
const CIBLE = path.join(RACINE, 'build', 'python');
const NOM = `python-${VERSION}-embed-amd64.zip`;
const ADRESSE = `https://www.python.org/ftp/python/${VERSION}/${NOM}`;

async function telecharger() {
  const fichier = path.join(CACHE, NOM);
  if (fs.existsSync(fichier)) return fichier;
  fs.mkdirSync(CACHE, { recursive: true });
  console.log(`Téléchargement de ${ADRESSE}`);
  const reponse = await fetch(ADRESSE);
  if (!reponse.ok) throw new Error(`python.org a répondu ${reponse.status} pour ${ADRESSE}`);
  fs.writeFileSync(`${fichier}.part`, Buffer.from(await reponse.arrayBuffer()));
  fs.renameSync(`${fichier}.part`, fichier);
  return fichier;
}

async function main() {
  const archive = await telecharger();
  fs.rmSync(CIBLE, { recursive: true, force: true });
  fs.mkdirSync(CIBLE, { recursive: true });
  // tar de Windows (bsdtar) sait ouvrir les .zip
  execFileSync(path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe'), ['-xf', archive, '-C', CIBLE]);
  const pth = fs.readdirSync(CIBLE).find((f) => /^python3\d+\._pth$/.test(f));
  if (!pth) throw new Error('fichier ._pth introuvable dans la distribution de Python');
  const zip = pth.replace('._pth', '.zip');
  fs.writeFileSync(path.join(CIBLE, pth), [zip, '.', '..\\coeur', ''].join('\r\n'));
  // Vérification : Python démarre et trouve ce dont le service a besoin
  const sortie = execFileSync(path.join(CIBLE, 'python.exe'), ['-c',
    'import sys, sqlite3, ctypes, winreg, tomllib, unicodedata; print(sys.version.split()[0])'], { encoding: 'utf8' });
  console.log(`Python ${sortie.trim()} prêt dans ${CIBLE}`);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
