'use strict';
// Ce que la page de la barre peut demander au processus principal. Le jeton de l'API n'y passe jamais.
const { contextBridge, ipcRenderer } = require('electron');

const appeler = async (canal, ...args) => {
  const r = await ipcRenderer.invoke(canal, ...args);
  if (!r.ok) throw new Error(r.erreur);
  return r.valeur;
};

contextBridge.exposeInMainWorld('declic', {
  api: {
    rechercher: (requete, limite, page) => appeler('api:rechercher', requete, limite, page),
    executer: (commande, argument) => appeler('api:executer', commande, argument),
    creations: () => appeler('api:creations'),
    creer: (type, valeurs) => appeler('api:creer', type, valeurs),
    elements: (type) => appeler('api:elements', type),
    supprimer: (type, cle) => appeler('api:supprimer', type, cle),
  },
  reglages: () => appeler('barre:reglages'),
  regler: (modifs) => appeler('barre:regler', modifs),
  reinitialiser: () => appeler('barre:reinitialiser'),
  demarrageWindows: (actif) => appeler('barre:demarrage-windows', actif),
  raccourci: () => appeler('barre:raccourci'),
  fermer: (garder) => appeler('barre:fermer', garder),
  osd: (message) => appeler('barre:osd', message),
  copier: (texte) => appeler('barre:copier', texte),
  iconeFichier: (chemin) => appeler('barre:icone-fichier', chemin),
  surOuverture: (fn) => ipcRenderer.on('barre:ouverture', (_e, reglages) => fn(reglages)),
  surFermeture: (fn) => ipcRenderer.on('barre:fermeture', (_e, infos) => fn(infos)),
  surReglages: (fn) => ipcRenderer.on('barre:reglages', () => fn()),
  surApparence: (fn) => ipcRenderer.on('barre:apparence', (_e, a) => fn(a)),
  surEcran: (fn) => ipcRenderer.on('barre:ecran', (_e, ecran) => fn(ecran)),
  surPage: (fn) => ipcRenderer.on('barre:page', (_e, url) => fn(url)),
});
