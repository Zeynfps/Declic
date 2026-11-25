'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('osd', {
  surMessage: (fn) => ipcRenderer.on('osd:message', (_e, message) => fn(message)),
});
