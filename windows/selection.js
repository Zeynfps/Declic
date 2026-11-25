'use strict';
// Texte sélectionné dans l'application au premier plan, pour le raccourci « texte sélectionné » de Déclic.
//
// Windows n'offre pas de moyen général de lire une sélection : on fait comme les autres lanceurs, un Ctrl+C
// envoyé à l'application, puis on remet le texte qui était dans le presse-papiers (Electron 45 ne lit plus que le
// texte : une image ou des fichiers copiés juste avant ne sont pas remis).
// Jamais dans un terminal (Ctrl+C y arrête le programme en cours) ni dans un jeu en plein écran.

const path = require('path');
const { clipboard } = require('electron');

// Terminaux : reconnus à leur type de fenêtre (console Windows, Windows Terminal…) ou au nom du programme
const CLASSES_TERMINAUX = /^(ConsoleWindowClass|CASCADIA_HOSTING_WINDOW_CLASS|mintty|PuTTY|VirtualConsoleClass|TMobaXtermForm)$/;
const PROGRAMMES_TERMINAUX = /^(windowsterminal|wt|openconsole|alacritty|wezterm(-gui)?|kitty|hyper|tabby|termius|mobaxterm|warp)$/i;
const QUNS_D3D_PLEIN_ECRAN = 3;
const VK = { CONTROL: 0x11, MENU: 0x12, SHIFT: 0x10, LWIN: 0x5b, RWIN: 0x5c, C: 0x43 };
const HAUT = 0x0002;

let api = null;

function charger() {
  if (api !== null) return api;
  try {
    const koffi = require('koffi');
    const user32 = koffi.load('user32.dll');
    const kernel32 = koffi.load('kernel32.dll');
    const shell32 = koffi.load('shell32.dll');
    api = {
      GetForegroundWindow: user32.func('intptr_t __stdcall GetForegroundWindow()'),
      GetClassNameW: user32.func('int __stdcall GetClassNameW(intptr_t hwnd, _Out_ uint16 *nom, int taille)'),
      GetWindowThreadProcessId: user32.func('uint32 __stdcall GetWindowThreadProcessId(intptr_t hwnd, _Out_ uint32 *pid)'),
      keybd_event: user32.func('void __stdcall keybd_event(uint8 vk, uint8 scan, uint32 flags, uintptr_t extra)'),
      GetClipboardSequenceNumber: user32.func('uint32 __stdcall GetClipboardSequenceNumber()'),
      OpenProcess: kernel32.func('intptr_t __stdcall OpenProcess(uint32 acces, bool heriter, uint32 pid)'),
      QueryFullProcessImageNameW: kernel32.func('bool __stdcall QueryFullProcessImageNameW(intptr_t h, uint32 flags, _Out_ uint16 *nom, _Inout_ uint32 *taille)'),
      CloseHandle: kernel32.func('bool __stdcall CloseHandle(intptr_t h)'),
      SHQueryUserNotificationState: shell32.func('int32 __stdcall SHQueryUserNotificationState(_Out_ int32 *etat)'),
    };
  } catch {
    api = false;
  }
  return api;
}

// Nom de l'exécutable au premier plan (sans « .exe »), ou ''
function programmeAuPremierPlan(a) {
  const fenetre = a.GetForegroundWindow();
  if (!fenetre) return '';
  const pid = [0];
  a.GetWindowThreadProcessId(fenetre, pid);
  const poignee = a.OpenProcess(0x1000, false, pid[0]); // PROCESS_QUERY_LIMITED_INFORMATION
  if (!poignee) return '';
  try {
    const tampon = new Uint16Array(1024);
    const taille = [tampon.length];
    if (!a.QueryFullProcessImageNameW(poignee, 0, tampon, taille)) return '';
    const chemin = String.fromCharCode(...tampon.subarray(0, taille[0]));
    return path.basename(chemin).replace(/\.exe$/i, '');
  } finally {
    a.CloseHandle(poignee);
  }
}

function classeAuPremierPlan(a) {
  const fenetre = a.GetForegroundWindow();
  if (!fenetre) return '';
  const tampon = new Uint16Array(256);
  const n = a.GetClassNameW(fenetre, tampon, tampon.length);
  return String.fromCharCode(...tampon.subarray(0, n));
}

function enJeuPleinEcran(a) {
  const etat = [0];
  return a.SHQueryUserNotificationState(etat) === 0 && etat[0] === QUNS_D3D_PLEIN_ECRAN;
}

const attendre = (ms) => new Promise((r) => setTimeout(r, ms));

// Renvoie {texte} (texte sélectionné, '' si rien), ou {refus: raison} quand on ne doit pas copier
async function lireSelection() {
  const a = charger();
  if (!a) return { refus: 'indisponible' };
  const programme = programmeAuPremierPlan(a);
  if (CLASSES_TERMINAUX.test(classeAuPremierPlan(a)) || PROGRAMMES_TERMINAUX.test(programme)) {
    return { refus: `terminal (${programme})` };
  }
  if (enJeuPleinEcran(a)) return { refus: 'jeu en plein écran' };

  const avant = await clipboard.readText(); // le presse-papiers d'Electron 45 est asynchrone
  const sequence = a.GetClipboardSequenceNumber();
  // Les touches du raccourci (Alt, Maj, Win…) sont encore enfoncées : on les relâche, sinon l'application
  // recevrait Ctrl+Alt+C au lieu de Ctrl+C
  for (const touche of [VK.MENU, VK.SHIFT, VK.LWIN, VK.RWIN]) a.keybd_event(touche, 0, HAUT, 0);
  a.keybd_event(VK.CONTROL, 0, 0, 0);
  a.keybd_event(VK.C, 0, 0, 0);
  a.keybd_event(VK.C, 0, HAUT, 0);
  a.keybd_event(VK.CONTROL, 0, HAUT, 0);

  let change = false;
  for (let i = 0; i < 25 && !change; i++) { // 500 ms au plus
    await attendre(20);
    change = a.GetClipboardSequenceNumber() !== sequence;
  }
  if (!change) return { texte: '' }; // rien de sélectionné (ou l'application ne copie pas)
  await attendre(30); // certaines applications écrivent plusieurs formats à la suite
  const texte = await clipboard.readText();

  // Le presse-papiers redevient ce qu'il était
  if (avant) await clipboard.writeText(avant);
  else await clipboard.clear();
  return { texte };
}

module.exports = { lireSelection };
