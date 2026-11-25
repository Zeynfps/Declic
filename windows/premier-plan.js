'use strict';
// Processus de la fenêtre au premier plan, relevé juste avant d'ouvrir la barre : si c'est un navigateur,
// le service lit l'adresse de sa page pour proposer « Remplir ici » (identifiants du site affiché).

let user32 = null;

function charger() {
  if (user32 !== null) return user32;
  try {
    const koffi = require('koffi');
    const dll = koffi.load('user32.dll');
    user32 = {
      GetForegroundWindow: dll.func('intptr_t __stdcall GetForegroundWindow()'),
      GetWindowThreadProcessId: dll.func('uint32 __stdcall GetWindowThreadProcessId(intptr_t hwnd, _Out_ uint32 *pid)'),
    };
  } catch {
    user32 = false;
  }
  return user32;
}

// Identifiant du processus au premier plan, ou 0
function processusAuPremierPlan() {
  const u = charger();
  if (!u) return 0;
  const fenetre = u.GetForegroundWindow();
  if (!fenetre) return 0;
  const pid = [0];
  u.GetWindowThreadProcessId(fenetre, pid);
  return pid[0] || 0;
}

module.exports = { processusAuPremierPlan };
