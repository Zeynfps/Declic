'use strict';
// Règles d'apparence de la barre Windows (sans Electron : fenetres.js ne fait que des calculs).
const test = require('node:test');
const assert = require('node:assert');
const fenetres = require('../fenetres');

test('apparence : flou et assombrissement autour, teinte de la barre', () => {
  const a = fenetres.apparence({ flouRayon: 50, assombrissement: 20, opaciteBarre: 40, assombrirBarre: 0 });
  assert.deepStrictEqual([a.flou, a.voile, a.teinte, a.base, a.fondUtile], [30, 0.2, 0.4, '28, 28, 31', true]);
  // Verre de la barre : toujours un peu dépoli, même sans flou autour
  assert.strictEqual(fenetres.apparence({ flouRayon: 0 }).flouVerre, 8);
});

test('« Assombrir la barre » va du graphite au noir', () => {
  assert.strictEqual(fenetres.apparence({ assombrirBarre: 50 }).base, '14, 14, 16');
  assert.strictEqual(fenetres.apparence({ assombrirBarre: 100 }).base, '0, 0, 0');
});

test("sans flou ni assombrissement, pas de fenêtre d'arrière-plan", () => {
  assert.strictEqual(fenetres.apparence({ flouRayon: 0, assombrissement: 0, opaciteBarre: 75 }).fondUtile, false);
});

test('réglages bornés comme sous GNOME', () => {
  assert.deepStrictEqual(fenetres.normaliser({ flouRayon: 250, assombrissement: -5, opaciteBarre: 2, assombrirBarre: 300 }),
    { flouRayon: 100, assombrissement: 0, opaciteBarre: 10, assombrirBarre: 100 });
  assert.deepStrictEqual(fenetres.normaliser({}), fenetres.APPARENCE_PAR_DEFAUT);
});

test('formats précédents convertis, opacité remise par défaut', () => {
  assert.deepStrictEqual(fenetres.normaliser({ flouActif: true, opaciteBarre: 100, assombrissement: 0 }),
    { flouRayon: 30, opaciteBarre: 75, assombrissement: 0, assombrirBarre: 40 });
  assert.strictEqual(fenetres.normaliser({ flouActif: false, opaciteBarre: 88 }).flouRayon, 0);
  assert.strictEqual(fenetres.normaliser({ flou: 'fort', opaciteBarre: 55 }).flouRayon, 60);
});

test("fenêtres outil transparentes ; l'arrière-plan ne prend jamais le focus", () => {
  const b = fenetres.optionsBarre('preload.js');
  assert.strictEqual(b.transparent, true);
  assert.strictEqual(b.type, 'toolbar');
  assert.strictEqual(fenetres.optionsFond('p').focusable, false);
});

test("barre centrée, au cinquième de la hauteur, avec la marge de l'ombre", () => {
  const p = fenetres.positionBarre({ workArea: { x: 0, y: 0, width: 2560, height: 1400 } });
  assert.deepStrictEqual(p, { x: 905 - fenetres.MARGE, y: 280 - fenetres.MARGE,
    width: fenetres.LARGEUR_BARRE + 2 * fenetres.MARGE, height: fenetres.HAUTEUR_BARRE + 2 * fenetres.MARGE });
});
