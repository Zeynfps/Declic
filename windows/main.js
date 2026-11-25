'use strict';
// Déclic pour Windows : la barre de commande (Electron) et le lancement du service Déclic (Python).
//
//   - Alt+Espace (modifiable) ouvre la barre au centre de l'écran, avec autour l'écran flouté et assombri
//     (fenêtre d'arrière-plan, voir fenetres.js) ; un clic à côté la ferme.
//   - Le service (python -m declic serveur) est lancé au besoin et relancé s'il s'arrête.
//   - Le jeton de l'API locale reste dans ce processus : la page de la barre ne le voit jamais.
//   - Icône dans la zone de notification : ouvrir, réglages, démarrer avec Windows, quitter.

const { app, BrowserWindow, globalShortcut, ipcMain, Menu, Tray, nativeImage, screen, clipboard, shell } = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const fenetres = require('./fenetres');
const { capturer } = require('./capture');
const { iconeFichier } = require('./logos');
const { processusAuPremierPlan } = require('./premier-plan');

const RACCOURCI_PAR_DEFAUT = 'Alt+Space';
const DELAI_DEMARRAGE_MS = 8000;
const DOSSIER_DONNEES = path.join(process.env.LOCALAPPDATA || app.getPath('userData'), 'Declic');
const DOSSIER_CONFIG = path.join(process.env.APPDATA || app.getPath('userData'), 'Declic');
const FICHIER_SERVEUR = path.join(DOSSIER_DONNEES, 'serveur.json');
const FICHIER_REGLAGES = path.join(DOSSIER_CONFIG, 'barre.json');
const FICHIER_JOURNAL = path.join(DOSSIER_DONNEES, 'service.log');
const DOSSIER_COEUR = process.env.DECLIC_COEUR || path.join(__dirname, '..', 'coeur');

// Réglages de la barre, comme sous GNOME : flou et assombrissement de l'arrière-plan, opacité de la barre
// (bornes et valeurs par défaut : fenetres.js)
const APPARENCE_PAR_DEFAUT = fenetres.APPARENCE_PAR_DEFAUT;
const REGLAGES_PAR_DEFAUT = {
  raccourci: RACCOURCI_PAR_DEFAUT,
  nombreResultats: 8,
  ...APPARENCE_PAR_DEFAUT,
  python: '',
};

let fenetre = null;
let osd = null;
let zoneNotif = null;
let service = null;
let demarrage = null;
let ouverte = false;
let raccourciActif = null;

// ---------- Réglages ----------

function lireReglages() {
  try {
    return fenetres.normaliser({ ...REGLAGES_PAR_DEFAUT, ...JSON.parse(fs.readFileSync(FICHIER_REGLAGES, 'utf8')) });
  } catch {
    return fenetres.normaliser({ ...REGLAGES_PAR_DEFAUT });
  }
}

function ecrireReglages(modifs) {
  const reglages = fenetres.normaliser({ ...lireReglages(), ...modifs });
  fs.mkdirSync(DOSSIER_CONFIG, { recursive: true });
  fs.writeFileSync(FICHIER_REGLAGES, JSON.stringify(reglages, null, 2));
  return reglages;
}

// ---------- Service Déclic (Python) ----------

function lireServeur() {
  try {
    const infos = JSON.parse(fs.readFileSync(FICHIER_SERVEUR, 'utf8'));
    if (Number.isInteger(infos.port) && typeof infos.jeton === 'string') return infos;
  } catch {
    // pas encore de service
  }
  return null;
}

// Python installé pour l'utilisateur (python.org, winget), sinon le lanceur « py », sinon « python ».
// Le faux « python » du Microsoft Store (dossier WindowsApps) est ignoré : il ouvre le Store.
function trouverPython() {
  const choisi = lireReglages().python;
  if (choisi && fs.existsSync(choisi)) return { commande: choisi, args: [] };
  const racine = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python');
  try {
    const versions = fs.readdirSync(racine)
      .filter((d) => /^Python3\d+$/i.test(d))
      .sort((a, b) => Number(b.slice(7)) - Number(a.slice(7)));
    for (const v of versions) {
      const exe = path.join(racine, v, 'python.exe');
      if (fs.existsSync(exe)) return { commande: exe, args: [] };
    }
  } catch {
    // aucun Python installé pour l'utilisateur
  }
  for (const essai of [{ commande: 'py', args: ['-3'] }, { commande: 'python', args: [] }]) {
    const r = spawnSync(essai.commande, [...essai.args, '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', windowsHide: true });
    if (r.status === 0 && !/WindowsApps/i.test(r.stdout)) return essai;
  }
  return null;
}

function demarrerService() {
  if (service) return true;
  const python = trouverPython();
  if (!python) return false;
  fs.mkdirSync(DOSSIER_DONNEES, { recursive: true });
  const journal = fs.openSync(FICHIER_JOURNAL, 'a');
  service = spawn(python.commande, [...python.args, '-m', 'declic', 'serveur'], {
    cwd: DOSSIER_COEUR,
    env: { ...process.env, PYTHONPATH: DOSSIER_COEUR, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    stdio: ['ignore', journal, journal],
    windowsHide: true,
  });
  service.on('exit', () => { service = null; });
  return true;
}

async function sante(infos) {
  try {
    const r = await fetch(`http://127.0.0.1:${infos.port}/v1/sante`, {
      headers: { Authorization: `Bearer ${infos.jeton}` }, signal: AbortSignal.timeout(1500),
    });
    return r.ok;
  } catch {
    return false;
  }
}

// Attend que le service réponde (en le lançant si besoin). Une seule attente à la fois.
function serviceDisponible() {
  if (demarrage) return demarrage;
  demarrage = (async () => {
    const infos = lireServeur();
    if (infos && await sante(infos)) return infos;
    if (!demarrerService()) {
      throw new Error("Python 3.11 ou plus récent est introuvable. Installez-le (winget install Python.Python.3.13) puis relancez Déclic.");
    }
    const limite = Date.now() + DELAI_DEMARRAGE_MS;
    while (Date.now() < limite) {
      await new Promise((r) => setTimeout(r, 250));
      const nouvelles = lireServeur();
      if (nouvelles && await sante(nouvelles)) return nouvelles;
    }
    throw new Error(`le service ne démarre pas (voir ${FICHIER_JOURNAL})`);
  })().finally(() => { demarrage = null; });
  return demarrage;
}

async function requete(methode, chemin, donnees = null) {
  const envoyer = async (infos) => {
    const r = await fetch(`http://127.0.0.1:${infos.port}${chemin}`, {
      method: methode,
      headers: { Authorization: `Bearer ${infos.jeton}`, 'content-type': 'application/json' },
      body: donnees === null ? undefined : JSON.stringify(donnees),
      signal: AbortSignal.timeout(15000),
    });
    const reponse = await r.json();
    if (!r.ok) throw new Error(reponse?.erreur ?? `erreur HTTP ${r.status}`);
    return reponse;
  };
  const infos = lireServeur();
  if (infos) {
    try {
      return await envoyer(infos);
    } catch (e) {
      if (!/fetch failed|ECONNREFUSED|aborted|timeout/i.test(String(e?.message) + String(e?.cause?.code))) throw e;
    }
  }
  return envoyer(await serviceDisponible());
}

// ---------- Fenêtres de la barre et de l'arrière-plan ----------
// Voir fenetres.js. À l'ouverture : on prend une image réduite de l'écran (capture.js, ~40 ms, gardée en
// mémoire seulement), l'arrière-plan l'affiche floutée et assombrie, puis la barre s'ouvre par-dessus.

let fond = null;

function creerFond() {
  fond = new BrowserWindow(fenetres.optionsFond(path.join(__dirname, 'preload-fond.js')));
  fond.setAlwaysOnTop(true, 'screen-saver');
  fond.loadFile(path.join(__dirname, 'barre', 'fond.html'));
  fond.on('closed', () => { fond = null; });
}

// Applique flou, assombrissement et opacité, y compris pendant que la barre est ouverte (réglages en direct)
function appliquerApparence(reglages) {
  const a = fenetres.apparence(reglages);
  fenetre?.webContents.send('barre:apparence', { teinte: a.teinte, base: a.base, reflet: a.reflet, flouVerre: a.flouVerre });
  fond?.webContents.send('fond:apparence', { flou: a.flou, voile: a.voile });
  if (fond && ouverte) {
    if (a.fondUtile && !fond.isVisible()) fond.showInactive();
    if (!a.fondUtile) fond.hide();
  }
}

// Image de l'écran sous la barre (en pixels physiques), en JPEG pour la page de l'arrière-plan
function imageEcran(ecran) {
  const f = ecran.scaleFactor || 1;
  const zone = { x: Math.round(ecran.bounds.x * f), y: Math.round(ecran.bounds.y * f), width: Math.round(ecran.bounds.width * f), height: Math.round(ecran.bounds.height * f) };
  const image = capturer(zone, 0.5);
  if (!image) return null;
  const jpeg = nativeImage.createFromBitmap(image.pixels, { width: image.largeur, height: image.hauteur }).toJPEG(82);
  return `data:image/jpeg;base64,${jpeg.toString('base64')}`;
}

function creerFenetre() {
  fenetre = new BrowserWindow({ ...fenetres.optionsBarre(path.join(__dirname, 'preload.js')), icon: path.join(__dirname, 'icones', 'declic.png') });
  fenetre.setAlwaysOnTop(true, 'screen-saver');
  fenetre.loadFile(path.join(__dirname, 'barre', 'index.html'));
  fenetre.webContents.once('did-finish-load', () => appliquerApparence(lireReglages()));
  // Un clic dans une autre fenêtre ferme la barre, en gardant la vue pour la rouvrir au même endroit
  fenetre.on('blur', () => { if (ouverte) fermer(true); });
  fenetre.on('closed', () => { fenetre = null; });
}

function ouvrir() {
  if (!fenetre) creerFenetre();
  if (!fond) creerFond();
  const ecran = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const reglages = lireReglages();
  const a = fenetres.apparence(reglages);
  // la fenêtre qui avait la main : si c'est un navigateur, sa page sert à proposer « Remplir ici »
  const pidPrecedent = processusAuPremierPlan();
  ouverte = true;
  // 1. l'image de l'écran, prise à chaque ouverture (~40 ms) : ainsi les réglages de flou agissent en
  //    direct, même s'ils étaient à 0 à l'ouverture ; elle sert à l'arrière-plan et au verre de la barre
  const image = imageEcran(ecran);
  const position = fenetres.positionBarre(ecran);
  fond.setBounds(ecran.bounds);
  fond.webContents.send('fond:image', image);
  fenetre.webContents.send('barre:ecran', image && {
    image,
    // où se trouve la barre (sans la marge de l'ombre) par rapport à l'écran, en pixels CSS
    x: position.x - ecran.bounds.x + fenetres.MARGE,
    y: position.y - ecran.bounds.y + fenetres.MARGE,
    largeur: ecran.bounds.width,
    hauteur: ecran.bounds.height,
  });
  appliquerApparence(reglages);
  if (a.fondUtile) fond.showInactive();
  // 2. la barre par-dessus
  fenetre.setBounds(position);
  fenetre.webContents.send('barre:ouverture', reglages);
  fenetre.show();
  fenetre.focus();
  // 3. l'adresse de la page (~0,4 s, après l'ouverture pour ne pas la retarder) ; null si ce n'est pas un navigateur
  if (pidPrecedent && pidPrecedent !== process.pid) {
    requete('GET', `/v1/page-active?pid=${pidPrecedent}`)
      .then((r) => { if (ouverte && r.url) fenetre?.webContents.send('barre:page', r.url); })
      .catch(() => {});
  }
}

function fermer(garder = false) {
  if (!fenetre || !ouverte) return;
  ouverte = false;
  fenetre.webContents.send('barre:fermeture', { garder });
  fenetre.hide();
  fond?.hide();
  // l'image de l'écran ne reste pas en mémoire
  fond?.webContents.send('fond:image', null);
  fenetre.webContents.send('barre:ecran', null);
}

function basculer() {
  if (ouverte) fermer(true);
  else ouvrir();
}

// Petit message au bas de l'écran après une commande qui ferme la barre (comme l'OSD de GNOME)
function afficherOsd(message) {
  if (!message) return;
  const { workArea } = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const largeur = 420;
  const hauteur = 64;
  if (!osd) {
    osd = new BrowserWindow({
      width: largeur, height: hauteur, show: false, frame: false, transparent: true, resizable: false,
      skipTaskbar: true, focusable: false, alwaysOnTop: true, hasShadow: false,
      webPreferences: { preload: path.join(__dirname, 'preload-osd.js'), contextIsolation: true, sandbox: true },
    });
    osd.setAlwaysOnTop(true, 'screen-saver');
    osd.setIgnoreMouseEvents(true);
    osd.loadFile(path.join(__dirname, 'barre', 'osd.html'));
    osd.on('closed', () => { osd = null; });
  }
  osd.setBounds({ x: Math.round(workArea.x + (workArea.width - largeur) / 2), y: workArea.y + workArea.height - hauteur - 60, width: largeur, height: hauteur });
  const montrer = () => { osd.webContents.send('osd:message', String(message)); osd.showInactive(); };
  if (osd.webContents.isLoading()) osd.webContents.once('did-finish-load', montrer);
  else montrer();
  clearTimeout(afficherOsd.minuteur);
  afficherOsd.minuteur = setTimeout(() => osd?.hide(), 1800);
}

// ---------- Démarrage avec Windows ----------

// Lancé depuis les sources (electron.exe + dossier de l'appli), Windows doit relancer les deux :
// sans le dossier, electron.exe ouvrirait sa page par défaut au lieu de Déclic.
const OPTIONS_DEMARRAGE = { path: process.execPath, args: app.isPackaged ? [] : [app.getAppPath()] };

function demarreAvecWindows() {
  return app.getLoginItemSettings(OPTIONS_DEMARRAGE).openAtLogin;
}

function demarrerAvecWindows(actif) {
  app.setLoginItemSettings({ ...OPTIONS_DEMARRAGE, openAtLogin: Boolean(actif) });
}

// ---------- Raccourci global ----------

function enregistrerRaccourci(raccourci) {
  if (raccourciActif) globalShortcut.unregister(raccourciActif);
  raccourciActif = null;
  if (globalShortcut.register(raccourci, basculer)) {
    raccourciActif = raccourci;
    return true;
  }
  return false;
}

// ---------- Zone de notification ----------

function libelleRaccourci(r) {
  return r.replace('Alt', 'Alt').replace('Space', 'Espace').replace('Control', 'Ctrl').replace('Shift', 'Maj').replace('Super', 'Win');
}

function majMenu() {
  if (!zoneNotif) return;
  zoneNotif.setToolTip(`Déclic — ${libelleRaccourci(raccourciActif ?? lireReglages().raccourci)}`);
  zoneNotif.setContextMenu(Menu.buildFromTemplate([
    { label: `Ouvrir Déclic (${libelleRaccourci(raccourciActif ?? lireReglages().raccourci)})`, click: ouvrir },
    { label: 'Réglages', click: () => { ouvrir(); fenetre.webContents.send('barre:reglages'); } },
    { type: 'separator' },
    {
      label: 'Démarrer avec Windows', type: 'checkbox', checked: demarreAvecWindows(),
      click: (element) => { demarrerAvecWindows(element.checked); majMenu(); },
    },
    { label: 'Ouvrir le journal du service', click: () => shell.openPath(FICHIER_JOURNAL) },
    { type: 'separator' },
    { label: 'Quitter Déclic', click: () => app.quit() },
  ]));
}

function creerZoneNotif() {
  const image = nativeImage.createFromPath(path.join(__dirname, 'icones', 'declic.png')).resize({ width: 16, height: 16 });
  zoneNotif = new Tray(image);
  zoneNotif.on('click', basculer);
  majMenu();
}

// ---------- Liaison avec la page de la barre ----------

function gerer(canal, fn) {
  ipcMain.handle(canal, async (_e, ...args) => {
    try {
      return { ok: true, valeur: await fn(...args) };
    } catch (e) {
      return { ok: false, erreur: e.message };
    }
  });
}

gerer('api:rechercher', (requeteTexte, limite, page) => {
  const q = encodeURIComponent(String(requeteTexte ?? ''));
  const p = page ? `&page=${encodeURIComponent(page)}` : '';
  return requete('GET', `/v1/recherche?q=${q}&limite=${Number(limite) || 8}${p}`).then((r) => r.resultats);
});
gerer('api:executer', (commande, argument) => requete('POST', '/v1/executer', { commande: String(commande), argument: argument ?? null }));
gerer('api:creations', () => requete('GET', '/v1/creations').then((r) => r.creations));
gerer('api:creer', (type, valeurs) => requete('POST', '/v1/creer', { type: String(type), valeurs }));
gerer('api:elements', (type) => requete('GET', `/v1/elements?type=${encodeURIComponent(String(type))}`).then((r) => r.elements));
gerer('api:supprimer', (type, cle) => requete('POST', '/v1/supprimer', { type: String(type), cle: String(cle) }));
gerer('barre:reglages', () => lireReglages());
gerer('barre:regler', (modifs) => {
  const permis = ['nombreResultats', ...Object.keys(APPARENCE_PAR_DEFAUT)];
  const propres = Object.fromEntries(Object.entries(modifs ?? {}).filter(([k]) => permis.includes(k)));
  const reglages = ecrireReglages(propres);
  appliquerApparence(reglages);
  return reglages;
});
gerer('barre:reinitialiser', () => {
  const reglages = ecrireReglages(APPARENCE_PAR_DEFAUT);
  appliquerApparence(reglages);
  return reglages;
});
gerer('barre:demarrage-windows', (actif) => {
  if (typeof actif === 'boolean') { demarrerAvecWindows(actif); majMenu(); }
  return demarreAvecWindows();
});
gerer('barre:raccourci', () => ({ raccourci: libelleRaccourci(raccourciActif ?? lireReglages().raccourci), actif: Boolean(raccourciActif) }));
gerer('barre:fermer', (garder) => fermer(Boolean(garder)));
// Un clic sur l'arrière-plan (ou à côté de la barre) la ferme, en gardant la vue
ipcMain.on('fond:clic', () => { if (ouverte) fermer(true); });
gerer('barre:osd', (message) => afficherOsd(message));
gerer('barre:copier', (texte) => clipboard.writeText(String(texte ?? '')));
gerer('barre:icone-fichier', (chemin) => iconeFichier(chemin));


// ---------- Démarrage ----------

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', ouvrir);
  app.whenReady().then(async () => {
    app.setAppUserModelId('Declic');
    creerFenetre();
    creerFond();
    creerZoneNotif();
    if (!enregistrerRaccourci(lireReglages().raccourci)) {
      zoneNotif.displayBalloon({
        title: 'Déclic',
        content: `Le raccourci ${libelleRaccourci(lireReglages().raccourci)} est déjà pris par une autre application. Cliquez sur l'icône de Déclic pour ouvrir la barre.`,
      });
    }
    majMenu();
    serviceDisponible().catch((e) => zoneNotif?.displayBalloon({ title: 'Déclic', content: e.message }));
    if (process.argv.includes('--ouvrir')) ouvrir();
  });
  app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    service?.kill();
  });
  // La barre se cache sans quitter : Déclic reste dans la zone de notification
  app.on('window-all-closed', (e) => e.preventDefault?.());
}

module.exports = { ouvrir, fermer, basculer, requete, lireReglages };
