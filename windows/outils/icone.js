'use strict';
// Fabrique icones/declic.png (256 × 256) et icones/declic.ico à partir du logo SVG, avec le moteur d'Electron.
// Utilisation : npx electron outils/icone.js
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

app.whenReady().then(async () => {
  const svg = fs.readFileSync(path.join(__dirname, '..', 'icones', 'declic-logo.svg'), 'utf8');
  const fenetre = new BrowserWindow({ width: 256, height: 256, show: false, frame: false, transparent: true, webPreferences: { offscreen: true } });
  const page = `<html><body style="margin:0;background:transparent"><img style="width:256px;height:256px;display:block" src="data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}"></body></html>`;
  await fenetre.loadURL(`data:text/html;base64,${Buffer.from(page).toString('base64')}`);
  await new Promise((r) => setTimeout(r, 300));
  const image = await fenetre.webContents.capturePage({ x: 0, y: 0, width: 256, height: 256 });
  fs.writeFileSync(path.join(__dirname, '..', 'icones', 'declic.png'), image.resize({ width: 256, height: 256 }).toPNG());
  // Icône Windows (.ico) : plusieurs tailles, chacune enregistrée en PNG (accepté depuis Windows Vista)
  const tailles = [16, 24, 32, 48, 64, 256];
  const images = tailles.map((t) => image.resize({ width: t, height: t, quality: 'best' }).toPNG());
  const entete = Buffer.alloc(6 + 16 * tailles.length);
  entete.writeUInt16LE(0, 0);
  entete.writeUInt16LE(1, 2); // icône
  entete.writeUInt16LE(tailles.length, 4);
  let position = entete.length;
  tailles.forEach((t, i) => {
    const o = 6 + 16 * i;
    entete.writeUInt8(t === 256 ? 0 : t, o);
    entete.writeUInt8(t === 256 ? 0 : t, o + 1);
    entete.writeUInt16LE(1, o + 4); // plans
    entete.writeUInt16LE(32, o + 6); // bits par pixel
    entete.writeUInt32LE(images[i].length, o + 8);
    entete.writeUInt32LE(position, o + 12);
    position += images[i].length;
  });
  fs.writeFileSync(path.join(__dirname, '..', 'icones', 'declic.ico'), Buffer.concat([entete, ...images]));
  console.log('icones/declic.png et icones/declic.ico écrits');
  app.quit();
});
