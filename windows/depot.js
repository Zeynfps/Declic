'use strict';
// Bloc-notes et dépôt de fichiers des panneaux de la barre, rangés dans %APPDATA%\Declic :
//   note.txt          le bloc-notes (enregistré à chaque frappe, après une courte pause)
//   depot\            les fichiers glissés sur le dépôt (copiés : l'original reste où il était)

const fs = require('fs');
const path = require('path');

const dossier = (config) => path.join(config, 'depot');

// Un nom de fichier du dépôt, jamais un chemin (pas de « ..\ » pour sortir du dossier)
function chemin(config, nom) {
  const propre = path.basename(String(nom));
  if (!propre || propre === '.' || propre === '..') throw new Error('nom de fichier invalide');
  return path.join(dossier(config), propre);
}

function lireNote(config) {
  try {
    return fs.readFileSync(path.join(config, 'note.txt'), 'utf8');
  } catch {
    return '';
  }
}

function ecrireNote(config, texte) {
  fs.mkdirSync(config, { recursive: true });
  fs.writeFileSync(path.join(config, 'note.txt'), texte.slice(0, 200_000), 'utf8');
  return true;
}

function lister(config) {
  try {
    return fs.readdirSync(dossier(config), { withFileTypes: true })
      .map((e) => {
        const complet = path.join(dossier(config), e.name);
        const infos = fs.statSync(complet);
        return { nom: e.name, chemin: complet, dossier: e.isDirectory(), taille: infos.size, date: infos.mtimeMs };
      })
      .sort((a, b) => b.date - a.date);
  } catch {
    return [];
  }
}

// Nom libre dans le dépôt : « rapport.pdf », puis « rapport (2).pdf »…
function nomLibre(config, nom) {
  const { name, ext } = path.parse(nom);
  let candidat = nom;
  for (let i = 2; fs.existsSync(path.join(dossier(config), candidat)); i++) candidat = `${name} (${i})${ext}`;
  return candidat;
}

function ajouter(config, chemins) {
  fs.mkdirSync(dossier(config), { recursive: true });
  const ajoutes = [];
  for (const source of chemins) {
    if (!source || !fs.existsSync(source)) continue;
    if (path.dirname(path.resolve(source)) === path.resolve(dossier(config))) continue; // déjà dans le dépôt
    const nom = nomLibre(config, path.basename(source));
    fs.cpSync(source, path.join(dossier(config), nom), { recursive: true });
    ajoutes.push(nom);
  }
  return ajoutes;
}

// Retiré du dépôt : envoyé à la corbeille (récupérable), pas effacé
async function supprimer(config, nom) {
  const { shell } = require('electron');
  await shell.trashItem(chemin(config, nom));
  return true;
}

module.exports = { dossier, chemin, lireNote, ecrireNote, lister, ajouter, supprimer };
