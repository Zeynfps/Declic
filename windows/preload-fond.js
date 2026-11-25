'use strict';
// Arrière-plan de la barre : reçoit l'image de l'écran et les réglages, signale un clic (qui ferme la barre).
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fond', {
  surImage: (fn) => ipcRenderer.on('fond:image', (_e, image) => fn(image)),
  surApparence: (fn) => ipcRenderer.on('fond:apparence', (_e, a) => fn(a)),
  clic: () => ipcRenderer.send('fond:clic'),
});
