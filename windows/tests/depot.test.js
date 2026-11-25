'use strict';
// Bloc-notes et dépôt de fichiers des panneaux (sans Electron : seul « supprimer » en a besoin)
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const depot = require('../depot');

const dossierTemporaire = () => fs.mkdtempSync(path.join(os.tmpdir(), 'declic-depot-'));

test('bloc-notes : vide au départ, puis relu tel quel', () => {
  const config = dossierTemporaire();
  assert.strictEqual(depot.lireNote(config), '');
  depot.ecrireNote(config, 'Acheter du pain\nAppeler Léa');
  assert.strictEqual(depot.lireNote(config), 'Acheter du pain\nAppeler Léa');
});

test('dépôt : copie (l\'original reste), noms libres, plus récent en premier', () => {
  const config = dossierTemporaire();
  const source = path.join(dossierTemporaire(), 'rapport.pdf');
  fs.writeFileSync(source, 'contenu');
  assert.deepStrictEqual(depot.ajouter(config, [source]), ['rapport.pdf']);
  assert.deepStrictEqual(depot.ajouter(config, [source, path.join(config, 'absent.txt')]), ['rapport (2).pdf']);
  assert.ok(fs.existsSync(source));
  const noms = depot.lister(config).map((f) => f.nom).sort();
  assert.deepStrictEqual(noms, ['rapport (2).pdf', 'rapport.pdf']);
  // un fichier déjà dans le dépôt n'est pas recopié
  assert.deepStrictEqual(depot.ajouter(config, [path.join(depot.dossier(config), 'rapport.pdf')]), []);
});

test('dépôt : un nom ne peut pas sortir du dossier', () => {
  const config = dossierTemporaire();
  assert.strictEqual(depot.chemin(config, '..\\..\\Windows\\win.ini'), path.join(depot.dossier(config), 'win.ini'));
  assert.throws(() => depot.chemin(config, '..'));
});
