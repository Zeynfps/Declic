'use strict';
// Fenêtres de Déclic pour Windows et réglages d'apparence, partagés par main.js et les tests.
//
// Comme sous GNOME :
//   - l'arrière-plan : une fenêtre qui couvre l'écran et montre ce qu'il y avait derrière, flouté et assombri
//     (deux réglages à curseur) ; elle ne prend jamais le focus, et un clic dessus ferme la barre ;
//   - la barre : une fenêtre transparente au centre ; « Opacité de la barre » règle sa teinte, donc ce qu'on
//     voit à travers elle (l'arrière-plan flouté). Coins arrondis et ombre sont dessinés par la page ;
//   - toutes deux sont des fenêtres « outil » : ni dans la barre des tâches, ni dans Alt+Tab.

const LARGEUR_BARRE = 750;
const HAUTEUR_BARRE = 466; // en-tête 58 + corps 360 + pied 46 + bordures
const MARGE = 32; // place autour de la barre pour son ombre (la fenêtre est un peu plus grande que la barre)

// Réglages d'apparence : nom → [minimum, maximum, valeur par défaut]
const BORNES = {
  flouRayon: [0, 100, 30], // force du flou de l'arrière-plan (comme « Intensité du flou » sous GNOME)
  assombrissement: [0, 80, 15], // en %
  opaciteBarre: [10, 100, 75], // en % : teinte de la barre ; plus bas = on voit davantage à travers
  assombrirBarre: [0, 100, 40], // en % : couleur de la barre, du graphite (0) au noir (100)
};

const fenetreOutil = (preload) => ({
  show: false,
  frame: false,
  type: 'toolbar',
  transparent: true,
  backgroundColor: '#00000000',
  hasShadow: false,
  resizable: false,
  movable: false,
  minimizable: false,
  maximizable: false,
  fullscreenable: false,
  skipTaskbar: true,
  alwaysOnTop: true,
  webPreferences: { preload, contextIsolation: true, nodeIntegration: false, sandbox: true },
});

function optionsBarre(preload) {
  return { ...fenetreOutil(preload), width: LARGEUR_BARRE + 2 * MARGE, height: HAUTEUR_BARRE + 2 * MARGE, useContentSize: true, title: 'Déclic' };
}

function optionsFond(preload) {
  return { ...fenetreOutil(preload), focusable: false, title: 'Déclic — arrière-plan' };
}

// Barre centrée horizontalement, au cinquième de la hauteur de l'écran (comme sous GNOME)
function positionBarre(ecran) {
  const { x, y, width, height } = ecran.workArea;
  return {
    x: Math.round(x + (width - LARGEUR_BARRE) / 2) - MARGE,
    y: Math.round(y + height * 0.2) - MARGE,
    width: LARGEUR_BARRE + 2 * MARGE,
    height: HAUTEUR_BARRE + 2 * MARGE,
  };
}

const borner = (cle, valeur) => {
  const [min, max, defaut] = BORNES[cle];
  const n = Math.round(Number(valeur));
  return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : defaut;
};

// Réglages lus sur le disque → réglages valides. Convertit les formats des versions précédentes
// (« flouActif » vrai/faux, puis « flou » aucun/léger/fort), dont l'opacité n'avait pas le même sens.
function normaliser(reglages) {
  const r = { ...reglages };
  const ancien = 'flouActif' in r || typeof r.flou === 'string';
  if (ancien) {
    if (!('flouRayon' in r)) r.flouRayon = r.flouActif === false || r.flou === 'aucun' ? 0 : r.flou === 'fort' ? 60 : BORNES.flouRayon[2];
    r.opaciteBarre = BORNES.opaciteBarre[2];
    delete r.flouActif;
    delete r.flou;
  }
  for (const cle of Object.keys(BORNES)) r[cle] = borner(cle, r[cle] ?? BORNES[cle][2]);
  return r;
}

const APPARENCE_PAR_DEFAUT = Object.fromEntries(Object.entries(BORNES).map(([cle, [, , defaut]]) => [cle, defaut]));

// Ce qu'il faut afficher : flou en pixels CSS, voile sombre, teinte de la barre
function apparence(reglages) {
  const r = normaliser(reglages);
  // Couleur de la barre : du graphite de GNOME (28, 28, 31) au noir, selon « Assombrir la barre »
  const clair = 1 - r.assombrirBarre / 100;
  const base = [28, 28, 31].map((c) => Math.round(c * clair)).join(', ');
  return {
    flou: r.flouRayon * 0.6,
    voile: r.assombrissement / 100,
    teinte: r.opaciteBarre / 100,
    base,
    reflet: 0.09 * clair + 0.03, // reflet en haut de la barre, plus discret quand elle est sombre
    // Verre de la barre : l'écran flouté aussi à l'intérieur, au moins un peu (effet dépoli)
    flouVerre: Math.max(8, r.flouRayon * 0.6),
    fondUtile: r.flouRayon > 0 || r.assombrissement > 0,
  };
}

module.exports = { optionsBarre, optionsFond, positionBarre, normaliser, apparence, BORNES, APPARENCE_PAR_DEFAUT, LARGEUR_BARRE, HAUTEUR_BARRE, MARGE };
