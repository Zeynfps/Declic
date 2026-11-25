'use strict';
// Arrière-plan : l'écran flouté, à sa taille exacte.
// Un simple « filter: blur() » en CSS fait pâlir les bords ; on les cachait en agrandissant l'image, ce qui
// donnait un petit zoom dès que le flou passait au-dessus de 0. Ici, l'image est d'abord prolongée sur ses
// bords (en étirant sa dernière ligne de pixels), puis floutée sur un canevas : les bords restent nets de
// couleur et l'image ne bouge pas.
const ecran = document.getElementById('ecran');
const racine = document.documentElement.style;
const FLOU_MAX = 60; // en pixels CSS (flouRayon 100 × 0,6)

let prolongee = null; // image + bordure prolongée
let marge = 0;
let flou = 0;
let dessinPrevu = false;

function prolonger(image) {
  const l = image.naturalWidth;
  const h = image.naturalHeight;
  const echelle = l / window.innerWidth; // l'image est plus petite que l'écran (capture réduite)
  marge = Math.ceil(FLOU_MAX * echelle * 3) + 2;
  const m = marge;
  const c = document.createElement('canvas');
  c.width = l + 2 * m;
  c.height = h + 2 * m;
  const g = c.getContext('2d');
  g.drawImage(image, m, m);
  g.drawImage(image, 0, 0, l, 1, m, 0, l, m); // haut
  g.drawImage(image, 0, h - 1, l, 1, m, m + h, l, m); // bas
  g.drawImage(image, 0, 0, 1, h, 0, m, m, h); // gauche
  g.drawImage(image, l - 1, 0, 1, h, m + l, m, m, h); // droite
  g.drawImage(image, 0, 0, 1, 1, 0, 0, m, m); // coins
  g.drawImage(image, l - 1, 0, 1, 1, m + l, 0, m, m);
  g.drawImage(image, 0, h - 1, 1, 1, 0, m + h, m, m);
  g.drawImage(image, l - 1, h - 1, 1, 1, m + l, m + h, m, m);
  ecran.width = l;
  ecran.height = h;
  return c;
}

function dessiner() {
  dessinPrevu = false;
  if (!prolongee) return;
  const g = ecran.getContext('2d');
  const rayon = flou * (ecran.width / window.innerWidth);
  g.filter = rayon > 0 ? `blur(${rayon}px)` : 'none';
  g.drawImage(prolongee, -marge, -marge);
}

const redessiner = () => {
  if (!dessinPrevu) {
    dessinPrevu = true;
    requestAnimationFrame(dessiner);
  }
};

window.fond.surImage((donnees) => {
  if (!donnees) {
    prolongee = null;
    ecran.hidden = true;
    ecran.width = ecran.height = 0; // l'image de l'écran ne reste pas en mémoire
    return;
  }
  const image = new Image();
  image.onload = () => {
    prolongee = prolonger(image);
    dessiner();
    ecran.hidden = false;
  };
  image.src = donnees;
});
window.fond.surApparence((a) => {
  flou = a.flou;
  racine.setProperty('--voile', String(a.voile));
  ecran.style.visibility = flou > 0 ? 'visible' : 'hidden';
  redessiner();
});
document.addEventListener('mousedown', () => window.fond.clic());
