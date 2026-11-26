'use strict';
// Fichier tiré hors du dépôt : il en sort (déplacé, pas copié), mais seulement s'il est sûr qu'il est arrivé.
// Le glisser d'Electron (webContents.startDrag) ne dit pas ce que la cible a fait du fichier ; on regarde donc où
// il a été lâché :
//  - dans un dossier de l'Explorateur ou sur le bureau : on vérifie que le fichier y est, puis il quitte le dépôt ;
//  - dans une application qui prend les fichiers (Discord, navigateur…) : il quitte le dépôt après un délai
//    (corbeille : récupérable) ;
//  - ailleurs (annulé, refusé, dans le vide, sur Déclic) : il reste.

const { app } = require('electron');
const { execFile } = require('child_process');

// --- Fonctions de Windows ---
let api = null;

function charger() {
  if (api !== null) return api;
  try {
    const koffi = require('koffi');
    const user32 = koffi.load('user32.dll');
    koffi.struct('DECLIC_POINT_GLISSER', { x: 'int32', y: 'int32' });
    api = {
      GetAsyncKeyState: user32.func('int16 __stdcall GetAsyncKeyState(int vk)'),
      GetCursorPos: user32.func('bool __stdcall GetCursorPos(_Out_ DECLIC_POINT_GLISSER *point)'),
      WindowFromPoint: user32.func('intptr_t __stdcall WindowFromPoint(DECLIC_POINT_GLISSER point)'),
      GetParent: user32.func('intptr_t __stdcall GetParent(intptr_t hwnd)'),
      GetAncestor: user32.func('intptr_t __stdcall GetAncestor(intptr_t hwnd, uint32 drapeau)'),
      GetPropW: user32.func('intptr_t __stdcall GetPropW(intptr_t hwnd, const char16_t *nom)'),
      GetWindowLongPtrW: user32.func('intptr_t __stdcall GetWindowLongPtrW(intptr_t hwnd, int index)'),
      GetClassNameW: user32.func('int __stdcall GetClassNameW(intptr_t hwnd, _Out_ uint16_t *nom, int taille)'),
      GetWindowThreadProcessId: user32.func('uint32 __stdcall GetWindowThreadProcessId(intptr_t hwnd, _Out_ uint32 *pid)'),
    };
  } catch {
    api = false;
  }
  return api;
}

const VK_LBUTTON = 0x01;
const VK_ESCAPE = 0x1b;
const GA_ROOT = 2;
const GWL_EXSTYLE = -20;
const WS_EX_ACCEPTFILES = 0x10;

// Le bouton gauche est-il tenu ? (sinon pas de glisser : la souris est déjà relâchée)
function boutonTenu() {
  const a = charger();
  return a ? (a.GetAsyncKeyState(VK_LBUTTON) & 0x8000) !== 0 : true;
}

// Échap a-t-il été pressé depuis le dernier appel ? (il annule un glisser)
function echapPresse() {
  const a = charger();
  return a ? (a.GetAsyncKeyState(VK_ESCAPE) & 0x8001) !== 0 : false;
}

function classe(a, hwnd) {
  const tampon = new Uint16Array(128);
  const n = a.GetClassNameW(hwnd, tampon, 128);
  return String.fromCharCode(...tampon.subarray(0, Math.max(0, n)));
}

// Où le pointeur est-il ? { racine, classe, declic, prendFichiers } (racine : la fenêtre principale)
function sousLePointeur() {
  const a = charger();
  if (!a) return null;
  const point = {};
  if (!a.GetCursorPos(point)) return null;
  const hwnd = a.WindowFromPoint(point);
  if (!hwnd) return null;
  const pid = [0];
  a.GetWindowThreadProcessId(hwnd, pid);
  let prendFichiers = false;
  for (let h = hwnd, i = 0; h && i < 32 && !prendFichiers; i++, h = a.GetParent(h)) {
    // RegisterDragDrop pose cette propriété sur la fenêtre ; WS_EX_ACCEPTFILES est l'ancienne manière
    prendFichiers = Boolean(a.GetPropW(h, 'OleDropTargetInterface'))
      || (Number(a.GetWindowLongPtrW(h, GWL_EXSTYLE)) & WS_EX_ACCEPTFILES) !== 0;
  }
  const racine = a.GetAncestor(hwnd, GA_ROOT) || hwnd;
  return { racine: Number(racine), classe: classe(a, racine), declic: pid[0] === process.pid, prendFichiers };
}

// Dossier affiché par une fenêtre de l'Explorateur (ou le bureau) ; null si ce n'est pas un dossier
function dossierDeLaFenetre(cible) {
  if (cible.classe === 'Progman' || cible.classe === 'WorkerW') return Promise.resolve(app.getPath('desktop'));
  if (cible.classe !== 'CabinetWClass') return Promise.resolve(null);
  const script = `$ErrorActionPreference='SilentlyContinue'; foreach ($w in (New-Object -ComObject Shell.Application).Windows()) { if ([int64]$w.HWND -eq ${cible.racine}) { [Console]::OutputEncoding=[Text.Encoding]::UTF8; $w.Document.Folder.Self.Path; break } }`;
  return new Promise((resoudre) => {
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { windowsHide: true, timeout: 15_000, encoding: 'utf8' },
      (erreur, sortie) => resoudre(erreur ? null : (String(sortie).trim().split(/\r?\n/)[0] || null)));
  });
}

module.exports = { boutonTenu, echapPresse, sousLePointeur, dossierDeLaFenetre };
