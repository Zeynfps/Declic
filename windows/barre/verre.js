'use strict';
// Verre de la barre, inspiré du « Liquid Glass » d'Apple (traduit en CSS/SVG pour Windows) :
//   - à l'intérieur de la barre, l'écran qui est derrière, flouté et saturé (verre dépoli) ;
//   - sur les bords, une réfraction : l'image est déviée vers l'intérieur, comme à travers une lentille ;
//   - par-dessus, la teinte de la barre (opacité et noirceur réglables) et un reflet lumineux sur le pourtour.
// L'image de l'écran arrive du processus principal à chaque ouverture, et repart à la fermeture.

const ZONE_LENTILLE = 26; // largeur en pixels de la bordure où l'image est déviée

// Carte de déviation pour feDisplacementMap : rouge = déplacement horizontal, vert = vertical
// (128 = aucun). Près d'un bord, on va chercher l'image un peu plus à l'intérieur.
function carteLentille(largeur, hauteur) {
  const canevas = document.createElement('canvas');
  canevas.width = largeur;
  canevas.height = hauteur;
  const ctx = canevas.getContext('2d');
  const image = ctx.createImageData(largeur, hauteur);
  const force = (d) => {
    const t = Math.max(0, 1 - d / ZONE_LENTILLE);
    return t * t; // plus fort tout contre le bord
  };
  for (let y = 0; y < hauteur; y++) {
    const fy = force(y) - force(hauteur - 1 - y);
    for (let x = 0; x < largeur; x++) {
      const fx = force(x) - force(largeur - 1 - x);
      const i = (y * largeur + x) * 4;
      image.data[i] = Math.round(128 + 127 * fx);
      image.data[i + 1] = Math.round(128 + 127 * fy);
      image.data[i + 2] = 128;
      image.data[i + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  return canevas.toDataURL('image/png');
}

let tailleCarte = '';

function preparerLentille() {
  const verre = document.getElementById('verre');
  const { width, height } = verre.getBoundingClientRect();
  const largeur = Math.round(width);
  const hauteur = Math.round(height);
  if (!largeur || !hauteur || tailleCarte === `${largeur}x${hauteur}`) return;
  tailleCarte = `${largeur}x${hauteur}`;
  const filtre = document.getElementById('lentille');
  const carte = document.getElementById('carte-lentille');
  for (const el of [filtre, carte]) {
    el.setAttribute('width', String(largeur));
    el.setAttribute('height', String(hauteur));
  }
  carte.setAttribute('href', carteLentille(largeur, hauteur));
}

// Réglages d'apparence venus du processus principal
function appliquerVerre({ teinte, base, reflet, flouVerre }) {
  const racine = document.documentElement.style;
  racine.setProperty('--opacite', String(teinte));
  if (base) racine.setProperty('--barre', base);
  if (reflet !== undefined) racine.setProperty('--reflet', String(reflet));
  if (flouVerre !== undefined) racine.setProperty('--flou-verre', `${flouVerre}px`);
}

// Image de l'écran, placée pour que la barre en montre exactement la partie qui est derrière elle
function placerEcran(ecran) {
  const verre = document.getElementById('verre');
  if (!ecran) {
    verre.hidden = true;
    verre.style.backgroundImage = '';
    return;
  }
  preparerLentille();
  verre.style.backgroundImage = `url("${ecran.image}")`;
  verre.style.backgroundSize = `${ecran.largeur}px ${ecran.hauteur}px`;
  verre.style.backgroundPosition = `${-ecran.x - 1}px ${-ecran.y - 1}px`; // 1 px : la bordure de la barre
  verre.hidden = false;
}

window.addEventListener('load', preparerLentille);
