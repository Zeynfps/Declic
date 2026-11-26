'use strict';
// Icônes de la barre Windows : les noms d'icônes du service (thème GNOME, « …-symbolic ») sont traduits
// en petits dessins SVG au trait, dessinés pour Déclic (24 × 24, couleur du texte).
// Un chemin de fichier (raccourci .lnk, document) est remplacé par l'icône que Windows lui donne.

const TRAITS = {
  punaise: '<path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/><path d="M12 14v7"/>',
  manette: '<path d="M7.5 8h9a4.5 4.5 0 014.4 3.6l.9 4.6a2.4 2.4 0 01-4.3 1.9L16 16H8l-1.5 2.1a2.4 2.4 0 01-4.3-1.9l.9-4.6A4.5 4.5 0 017.5 8z"/><path d="M8 11v3M6.5 12.5h3M15.5 12h.01M17.5 13.5h.01"/>',
  recherche: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
  application: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M9 12h6M12 9v6"/>',
  calcul: '<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8 7h8M8.5 12h.01M12 12h.01M15.5 12h.01M8.5 16h.01M12 16h.01M15.5 16h.01"/>',
  avion: '<path d="M10.5 3.5c0-1 3-1 3 0V9l7 4v2l-7-2v4.5l2.5 2V21L12 20l-4 1v-1.5l2.5-2V13l-7 2v-2l7-4z"/>',
  son: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 010 6M18 6.5a7.5 7.5 0 010 11"/>',
  sonBas: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 010 6"/>',
  muet: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
  bluetooth: '<path d="M7 7.5l10 9-5 4.5V3l5 4.5-10 9"/>',
  erreur: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
  cle: '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2.5 2.5M18.5 4.5L21 7"/>',
  alerte: '<path d="M12 4l9 16H3z"/><path d="M12 10v4.5M12 17.5h.01"/>',
  luminosite: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
  crayon: '<path d="M4 20l1-4.5L15.5 5a2 2 0 013 3L8 18.5z"/><path d="M13.5 7l3.5 3.5"/>',
  enregistrer: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
  effacer: '<path d="M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13"/><path d="M10.5 11v5M13.5 11v5"/>',
  copier: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2"/>',
  coller: '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5V3.5h6V5"/><path d="M9 11h6M9 15h4"/>',
  annuler: '<path d="M9 7L4.5 11.5 9 16"/><path d="M5 11.5h9a5 5 0 010 10h-3"/>',
  ok: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  reglages: '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
  dossier: '<path d="M3 6.5A1.5 1.5 0 014.5 5H9l2 2.5h8.5A1.5 1.5 0 0121 9v9a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18z"/>',
  dossierOuvert: '<path d="M3 18V6.5A1.5 1.5 0 014.5 5H9l2 2.5h7A1.5 1.5 0 0119.5 9v1.5"/><path d="M3 18l2.5-7.5h16L19 18z"/>',
  suivant: '<path d="M9 5l7 7-7 7"/>',
  precedent: '<path d="M15 5l-7 7 7 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  lecture: '<path d="M8 5l11 7-11 7z"/>',
  pisteSuivante: '<path d="M5 6l9 6-9 6z"/><path d="M18 6v12"/>',
  pistePrecedente: '<path d="M19 6l-9 6 9 6z"/><path d="M6 6v12"/>',
  microCoupe: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0011.3 4.4M12 17.5V21M4 4l16 16"/>',
  wifi: '<path d="M2.5 9a14 14 0 0119 0M5.5 12.5a9.5 9.5 0 0113 0M8.5 16a5 5 0 017 0"/><path d="M12 19.5h.01"/>',
  lune: '<path d="M19 14.5A7.5 7.5 0 119.5 5a6 6 0 009.5 9.5z"/>',
  etoile: '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
  sansNotif: '<path d="M6 16V11a6 6 0 019.5-4.9M18 10.5V16l1.5 2h-12M10 20a2 2 0 004 0M4 4l16 16"/>',
  eclair: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
  feuille: '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14z"/><path d="M5 19l7-7"/>',
  equilibre: '<path d="M12 4v16M6 20h12M5 8h14"/><path d="M5 8l-2.5 5a2.5 2.5 0 005 0zM19 8l-2.5 5a2.5 2.5 0 005 0z"/>',
  cadenas: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 018 0v3"/>',
  sortie: '<path d="M14 4H6a1 1 0 00-1 1v14a1 1 0 001 1h8"/><path d="M11 12h10M17.5 8.5L21 12l-3.5 3.5"/>',
  redemarrer: '<path d="M20 12a8 8 0 11-2.3-5.6"/><path d="M20 4.5v4h-4"/>',
  arret: '<path d="M12 3v8"/><path d="M7 6.5a7.5 7.5 0 1010 0"/>',
  document: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  disponible: '<path d="M4 6.5A2.5 2.5 0 016.5 4h11A2.5 2.5 0 0120 6.5v8a2.5 2.5 0 01-2.5 2.5H10l-4.5 3.5V17A2.5 2.5 0 014 14.5z"/><path d="M12 7.5l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/>',
  corbeille: '<path d="M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13"/>',
  terminal: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10l3 2.5L7 15M12.5 15H17"/>',
  liste: '<path d="M9 7h11M9 12h11M9 17h11M4.5 7h.01M4.5 12h.01M4.5 17h.01"/>',
  rafraichir: '<path d="M19.5 9A8 8 0 006 6.5L4 8.5M4.5 15a8 8 0 0013.5 2.5l2-2"/><path d="M4 4v4.5h4.5M20 20v-4.5h-4.5"/>',
  oeil: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  brouillard: '<path d="M4 9h16M6 13h14M4 17h12"/><path d="M7 5.5h10"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.5 5.8 3.5 9s-1 6.3-3.5 9c-2.5-2.7-3.5-5.8-3.5-9S9.5 5.7 12 3z"/>',
  fermer: '<path d="M6 6l12 12M18 6L6 18"/>',
};

// Nom d'icône du service → dessin (le premier motif qui correspond l'emporte)
const CORRESPONDANCES = [
  [/input-gaming/, 'manette'], [/pin/, 'punaise'], [/calculator/, 'calcul'], [/airplane/, 'avion'], [/volume-muted/, 'muet'], [/volume-low/, 'sonBas'],
  [/audio-volume/, 'son'], [/bluetooth/, 'bluetooth'], [/dialog-error/, 'erreur'], [/password/, 'cle'],
  [/dialog-warning/, 'alerte'], [/brightness/, 'luminosite'], [/document-edit/, 'crayon'], [/document-save/, 'enregistrer'],
  [/edit-clear/, 'effacer'], [/edit-copy/, 'copier'], [/edit-paste/, 'coller'], [/edit-undo/, 'annuler'],
  [/edit-find|system-search/, 'recherche'], [/emblem-ok/, 'ok'], [/emblem-system|preferences/, 'reglages'],
  [/folder-open/, 'dossierOuvert'], [/folder/, 'dossier'], [/go-next/, 'suivant'], [/go-previous/, 'precedent'],
  [/help-about/, 'info'], [/list-add/, 'plus'], [/skip-backward/, 'pistePrecedente'], [/skip-forward/, 'pisteSuivante'],
  [/media-playback/, 'lecture'], [/microphone/, 'microCoupe'], [/network-wireless/, 'wifi'],
  [/night/, 'lune'], [/starred/, 'etoile'], [/notifications-disabled/, 'sansNotif'],
  [/power-saver/, 'feuille'], [/power-profile-performance/, 'eclair'], [/power-profile/, 'equilibre'],
  [/lock-screen/, 'cadenas'], [/log-out/, 'sortie'], [/reboot/, 'redemarrer'], [/shutdown/, 'arret'],
  [/text-x|x-office|document|image|audio-x|video-x|package/, 'document'], [/user-available/, 'disponible'],
  [/trash/, 'corbeille'], [/terminal/, 'terminal'], [/view-list/, 'liste'], [/view-refresh/, 'rafraichir'],
  [/view-reveal/, 'oeil'], [/fog/, 'brouillard'], [/web-browser/, 'globe'], [/window-close/, 'fermer'],
  [/system-run|executable/, 'application'],
];

function dessinPour(nom) {
  const n = String(nom ?? '');
  const trouve = CORRESPONDANCES.find(([motif]) => motif.test(n));
  return TRAITS[trouve ? trouve[1] : 'application'];
}

const ESPACE_SVG = 'http://www.w3.org/2000/svg';

// Élément <svg> pour un nom d'icône (taille en pixels)
function icone(nom, taille = 20, classe = 'icone') {
  const svg = document.createElementNS(ESPACE_SVG, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(taille));
  svg.setAttribute('height', String(taille));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.7');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('class', classe);
  svg.setAttribute('aria-hidden', 'true');
  // Dessins fixes, écrits ci-dessus : aucun contenu venu du service n'est interprété ici
  const gabarit = new DOMParser().parseFromString(`<svg xmlns="${ESPACE_SVG}">${dessinPour(nom)}</svg>`, 'image/svg+xml');
  for (const enfant of [...gabarit.documentElement.childNodes]) svg.append(document.importNode(enfant, true));
  return svg;
}

// Chemin Windows absolu (C:\… ou \\serveur\…) : l'icône vient du système
const estChemin = (texte) => /^([a-zA-Z]:\\|\\\\)/.test(String(texte ?? ''));

const cacheIcones = new Map();

// Icône d'un résultat : celle du fichier ou de l'application si Windows la connaît, sinon un dessin
function iconeResultat(nom, cheminFichier, taille = 22) {
  const source = estChemin(nom) ? nom : cheminFichier && estChemin(cheminFichier) ? cheminFichier : null;
  const dessin = icone(estChemin(nom) ? 'application-x-executable-symbolic' : nom, taille);
  if (!source) return dessin;
  const boite = document.createElement('span');
  boite.className = 'icone-boite';
  boite.style.width = boite.style.height = `${taille}px`;
  boite.append(dessin);
  const appliquer = (url) => {
    if (!url) return;
    const img = document.createElement('img');
    img.src = url;
    img.width = img.height = taille;
    img.alt = '';
    boite.replaceChildren(img);
  };
  if (cacheIcones.has(source)) {
    appliquer(cacheIcones.get(source));
  } else {
    window.declic.iconeFichier(source).then((url) => { cacheIcones.set(source, url); appliquer(url); }).catch(() => cacheIcones.set(source, null));
  }
  return boite;
}
