'use strict';
// Ce que la page de la barre peut demander au processus principal. Le jeton de l'API n'y passe jamais.
const { contextBridge, ipcRenderer, webUtils } = require('electron');

const appeler = async (canal, ...args) => {
  const r = await ipcRenderer.invoke(canal, ...args);
  if (!r.ok) throw new Error(r.erreur);
  return r.valeur;
};

contextBridge.exposeInMainWorld('declic', {
  api: {
    rechercher: (requete, limite, page) => appeler('api:rechercher', requete, limite, page),
    rechercherSelection: (requete, selection, limite) => appeler('api:rechercher-selection', requete, selection, limite),
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
  changerRaccourci: (type, raccourci) => appeler('barre:changer-raccourci', type, raccourci),
  suspendreRaccourcis: (suspendre) => appeler('barre:suspendre-raccourcis', suspendre),
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
  surSelection: (fn) => ipcRenderer.on('barre:selection', (_e, texte, refus) => fn(texte, refus)),
  surRaccourciCapte: (fn) => ipcRenderer.on('barre:raccourci-capte', (_e, raccourci) => fn(raccourci)),
  surPosition: (fn) => ipcRenderer.on('barre:position', (_e, position) => fn(position)),
  panneaux: {
    lireNote: () => appeler('panneau:note-lire'),
    ecrireNote: (texte) => appeler('panneau:note-ecrire', texte),
    listerDepot: () => appeler('panneau:depot-lister'),
    // chemins des fichiers glissés sur le dépôt (seul le preload peut les lire)
    deposer: (fichiers) => appeler('panneau:depot-ajouter', [...fichiers].map((f) => webUtils.getPathForFile(f)).filter(Boolean)),
    supprimerDepot: (nom) => appeler('panneau:depot-supprimer', nom),
    ouvrirDepot: (nom) => appeler('panneau:depot-ouvrir', nom),
    dossierDepot: () => appeler('panneau:depot-dossier'),
    glisserDepot: (nom) => ipcRenderer.send('panneau:depot-glisser', nom),
    signalerEpingles: (nombre, formes) => appeler('panneau:epingles', nombre, formes),
    surDepotSorti: (fn) => ipcRenderer.on('panneau:depot-sorti', (_e, nom) => fn(nom)),
    surDepotChange: (fn) => ipcRenderer.on('panneau:depot-change', () => fn()),
    capterSouris: (capter) => appeler('panneau:souris', capter),
    prendreFocus: () => appeler('panneau:focus'),
  },
});
