'use strict';
// Image de l'écran, réduite, prise juste avant d'ouvrir la barre : elle sert de fond flouté et assombri
// autour de la barre (comme sous GNOME). Copie directe de Windows (GDI, StretchBlt), bien plus rapide que
// la capture d'Electron (environ 350 ms). L'image reste en mémoire : elle n'est jamais enregistrée.

let gdi = null;

function charger() {
  if (gdi !== null) return gdi;
  try {
    const koffi = require('koffi');
    const user32 = koffi.load('user32.dll');
    const gdi32 = koffi.load('gdi32.dll');
    const Entete = koffi.struct('DECLIC_BITMAPINFOHEADER', {
      biSize: 'uint32', biWidth: 'int32', biHeight: 'int32', biPlanes: 'uint16', biBitCount: 'uint16',
      biCompression: 'uint32', biSizeImage: 'uint32', biXPelsPerMeter: 'int32', biYPelsPerMeter: 'int32',
      biClrUsed: 'uint32', biClrImportant: 'uint32',
    });
    const Info = koffi.struct('DECLIC_BITMAPINFO', { bmiHeader: Entete, bmiColors: koffi.array('uint32', 1) });
    gdi = {
      koffi, Info,
      GetDC: user32.func('intptr_t __stdcall GetDC(intptr_t hwnd)'),
      ReleaseDC: user32.func('int __stdcall ReleaseDC(intptr_t hwnd, intptr_t hdc)'),
      CreateCompatibleDC: gdi32.func('intptr_t __stdcall CreateCompatibleDC(intptr_t hdc)'),
      CreateCompatibleBitmap: gdi32.func('intptr_t __stdcall CreateCompatibleBitmap(intptr_t hdc, int w, int h)'),
      SelectObject: gdi32.func('intptr_t __stdcall SelectObject(intptr_t hdc, intptr_t obj)'),
      SetStretchBltMode: gdi32.func('int __stdcall SetStretchBltMode(intptr_t hdc, int mode)'),
      StretchBlt: gdi32.func('bool __stdcall StretchBlt(intptr_t dst, int x, int y, int w, int h, intptr_t src, int xs, int ys, int ws, int hs, uint32 rop)'),
      GetDIBits: gdi32.func('int __stdcall GetDIBits(intptr_t hdc, intptr_t bmp, uint32 debut, uint32 lignes, _Out_ void *bits, DECLIC_BITMAPINFO *info, uint32 usage)'),
      DeleteObject: gdi32.func('bool __stdcall DeleteObject(intptr_t obj)'),
      DeleteDC: gdi32.func('bool __stdcall DeleteDC(intptr_t hdc)'),
    };
  } catch {
    gdi = false;
  }
  return gdi;
}

const HALFTONE = 4;
const SRCCOPY_CAPTUREBLT = (0x00cc0020 | 0x40000000) >>> 0;

// Zone de l'écran en pixels physiques → image réduite { largeur, hauteur, pixels (BGRA) }, ou null.
function capturer({ x, y, width, height }, echelle = 0.5) {
  const g = charger();
  if (!g) return null;
  const largeur = Math.max(1, Math.round(width * echelle));
  const hauteur = Math.max(1, Math.round(height * echelle));
  const ecran = g.GetDC(0);
  if (!ecran) return null;
  const memoire = g.CreateCompatibleDC(ecran);
  const image = g.CreateCompatibleBitmap(ecran, largeur, hauteur);
  const ancien = g.SelectObject(memoire, image);
  try {
    g.SetStretchBltMode(memoire, HALFTONE);
    if (!g.StretchBlt(memoire, 0, 0, largeur, hauteur, ecran, x, y, width, height, SRCCOPY_CAPTUREBLT)) return null;
    const pixels = Buffer.alloc(largeur * hauteur * 4);
    const info = {
      bmiHeader: { biSize: 40, biWidth: largeur, biHeight: -hauteur, biPlanes: 1, biBitCount: 32, biCompression: 0,
        biSizeImage: 0, biXPelsPerMeter: 0, biYPelsPerMeter: 0, biClrUsed: 0, biClrImportant: 0 },
      bmiColors: [0],
    };
    g.SelectObject(memoire, ancien); // GetDIBits demande une image qui n'est plus sélectionnée
    if (!g.GetDIBits(memoire, image, 0, hauteur, pixels, info, 0)) return null;
    for (let i = 3; i < pixels.length; i += 4) pixels[i] = 255; // GDI laisse l'opacité à 0
    return { largeur, hauteur, pixels };
  } finally {
    g.DeleteObject(image);
    g.DeleteDC(memoire);
    g.ReleaseDC(0, ecran);
  }
}

module.exports = { capturer, disponible: () => Boolean(charger()) };
