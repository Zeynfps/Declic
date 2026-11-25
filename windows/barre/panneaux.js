'use strict';
// Panneaux autour de la barre, comme la Game Bar : presse-papiers, applications épinglées et IA à gauche,
// bloc-notes et dépôt de fichiers à droite. Chacun s'active dans les réglages (section « Panneaux »).
// Ils occupent la place libre de part et d'autre de la barre ; sur un écran trop étroit, ils ne s'affichent pas.
//
// Comme la Game Bar et l'overlay de Steam, on les déplace en les tirant par leur titre et on les redimensionne
// par leur coin. Ils s'aimantent entre eux, à la barre et aux bords de l'écran ; des panneaux collés forment un
// groupe qui se déplace d'un bloc (Alt en tirant : le panneau se détache). La disposition est gardée.

const AIMANT_PX = 18; // distance à laquelle un bord accroche un autre bord
const COLLE_PX = 3; // deux panneaux plus proches que ça sont « assemblés"

const LARGEUR_BARRE_PX = 750;
const ECART_PX = 24;
const LARGEUR_MAX_PX = 320;
const LARGEUR_MIN_PX = 220;

class Panneaux {
  constructor(barre) {
    this.barre = barre;
    this.gauche = document.getElementById('colonne-gauche');
    this.droite = document.getElementById('colonne-droite');
    this.libres = document.getElementById('panneaux-libres');
    this.minuteurNote = 0;
    this.minuteurDisposition = 0;
    // Sans ceci, un fichier lâché à côté du dépôt ouvrirait une page à la place de Déclic
    for (const type of ['dragover', 'drop']) document.addEventListener(type, (e) => e.preventDefault());
  }

  // Place les colonnes autour de la barre (position de la barre dans la fenêtre plein écran)
  placer(position) {
    const largeur = Math.min(LARGEUR_MAX_PX, position.x - 2 * ECART_PX);
    const racine = document.documentElement.style;
    racine.setProperty('--barre-x', `${position.x}px`);
    racine.setProperty('--barre-y', `${position.y}px`);
    racine.setProperty('--colonne-l', `${Math.max(largeur, 0)}px`);
    this.assezDePlace = largeur >= LARGEUR_MIN_PX;
  }

  async afficher(reglages) {
    this.vider();
    if (!this.assezDePlace) return;
    const r = reglages;
    this.disposition = { ...(r.panneauxDisposition || {}) };
    if (r.panneauPressePapiers !== false) this.gauche.append(await this.pressePapiers());
    if (r.panneauApplications !== false) this.gauche.append(await this.applications());
    if (r.panneauIA !== false) this.gauche.append(await this.ia());
    if (r.panneauNotes !== false) this.droite.append(await this.notes());
    if (r.panneauDepot !== false) this.droite.append(await this.depot());
    // Panneaux déjà déplacés : à leur place enregistrée
    for (const panneau of this.tous()) {
      const place = this.disposition[panneau.dataset.id];
      if (place) this.liberer(panneau, place);
    }
    this.recaler();
  }

  vider() {
    this.gauche.replaceChildren();
    this.droite.replaceChildren();
    this.libres.replaceChildren();
  }

  tous() {
    return [...document.querySelectorAll('.panneau')];
  }

  // Sort un panneau de sa colonne : il est placé librement sur l'écran
  liberer(panneau, place) {
    if (panneau.parentElement !== this.libres) {
      const r = panneau.getBoundingClientRect();
      place = place ?? { x: r.left, y: r.top, l: r.width };
      this.libres.append(panneau);
    }
    const maxX = window.innerWidth - 120;
    const maxY = window.innerHeight - 60;
    panneau.style.left = `${Math.max(0, Math.min(maxX, place.x))}px`;
    panneau.style.top = `${Math.max(0, Math.min(maxY, place.y))}px`;
    if (place.l) panneau.style.width = `${place.l}px`;
    if (place.h) panneau.style.height = `${place.h}px`;
  }

  // Déplacement par le titre, avec aimantation et groupes
  rendreMobile(panneau) {
    const entete = panneau.querySelector('.panneau-entete');
    entete.addEventListener('mousedown', (e) => {
      if (e.button !== 0 || e.target.closest('button')) return;
      e.preventDefault();
      const groupe = e.altKey ? [panneau] : this.groupe(panneau);
      for (const p of groupe) this.liberer(p);
      const depart = groupe.map((p) => ({ p, x: p.offsetLeft, y: p.offsetTop }));
      const sx = e.clientX;
      const sy = e.clientY;
      panneau.classList.add('deplace');
      const bouger = (m) => {
        let dx = m.clientX - sx;
        let dy = m.clientY - sy;
        // aimantation : le panneau tiré s'accroche aux bords voisins (le groupe suit)
        const ref = depart.find((d) => d.p === panneau);
        const [ax, ay] = this.aimanter(panneau, ref.x + dx, ref.y + dy, groupe);
        dx = ax - ref.x;
        dy = ay - ref.y;
        for (const d of depart) this.liberer(d.p, { x: d.x + dx, y: d.y + dy });
        this.recaler();
      };
      const lacher = () => {
        document.removeEventListener('mousemove', bouger);
        document.removeEventListener('mouseup', lacher);
        panneau.classList.remove('deplace');
        this.enregistrerDisposition();
      };
      document.addEventListener('mousemove', bouger);
      document.addEventListener('mouseup', lacher);
    });
    // Redimensionnement par le coin (CSS « resize ») : la taille est gardée
    new ResizeObserver(() => {
      if (panneau.parentElement === this.libres && panneau.style.height) this.enregistrerDisposition();
    }).observe(panneau);
    panneau.addEventListener('mousedown', (e) => {
      const r = panneau.getBoundingClientRect();
      if (e.clientX > r.right - 18 && e.clientY > r.bottom - 18) { // le coin de redimensionnement
        this.liberer(panneau);
        panneau.style.height = `${r.height}px`;
      }
    });
  }

  // Les panneaux libres collés à celui-ci, de proche en proche
  groupe(panneau) {
    const libres = [...this.libres.children];
    if (!libres.includes(panneau)) return [panneau];
    const colles = (a, b) => {
      const r = a.getBoundingClientRect();
      const s = b.getBoundingClientRect();
      const recouvreX = r.left < s.right + COLLE_PX && s.left < r.right + COLLE_PX;
      const recouvreY = r.top < s.bottom + COLLE_PX && s.top < r.bottom + COLLE_PX;
      return recouvreX && recouvreY;
    };
    const groupe = [panneau];
    for (let i = 0; i < groupe.length; i++) {
      for (const autre of libres) if (!groupe.includes(autre) && colles(groupe[i], autre)) groupe.push(autre);
    }
    return groupe;
  }

  // Position aimantée : bords des autres panneaux, de la barre et de l'écran
  aimanter(panneau, x, y, groupe) {
    const l = panneau.offsetWidth;
    const h = panneau.offsetHeight;
    const cibles = [...this.tous().filter((p) => !groupe.includes(p)), document.getElementById('barre')]
      .map((p) => p.getBoundingClientRect());
    cibles.push({ left: 0, right: window.innerWidth, top: 0, bottom: window.innerHeight, ecran: true });
    let meilleurX = null;
    let meilleurY = null;
    const proposer = (actuel, candidat, meilleur) => {
      const d = Math.abs(actuel - candidat);
      return d <= AIMANT_PX && (!meilleur || d < meilleur.d) ? { v: candidat, d } : meilleur;
    };
    for (const c of cibles) {
      const ecart = c.ecran ? 12 : 10; // petit espace entre panneaux, comme sur Steam
      // côte à côte, ou alignés sur le même bord
      for (const cx of c.ecran ? [c.left + ecart, c.right - ecart - l] : [c.right + ecart, c.left - ecart - l, c.left, c.right - l]) {
        meilleurX = proposer(x, cx, meilleurX);
      }
      for (const cy of c.ecran ? [c.top + ecart, c.bottom - ecart - h] : [c.bottom + ecart, c.top - ecart - h, c.top, c.bottom - h]) {
        meilleurY = proposer(y, cy, meilleurY);
      }
    }
    return [meilleurX ? meilleurX.v : x, meilleurY ? meilleurY.v : y];
  }

  enregistrerDisposition() {
    for (const p of this.libres.children) {
      this.disposition[p.dataset.id] = {
        x: p.offsetLeft, y: p.offsetTop, l: p.offsetWidth, ...(p.style.height ? { h: p.offsetHeight } : {}),
      };
    }
    clearTimeout(this.minuteurDisposition);
    this.minuteurDisposition = setTimeout(() => this.barre.regler({ panneauxDisposition: this.disposition }), 300);
  }

  // Verre des panneaux : chacun montre la partie de l'écran qui est derrière lui (comme la barre)
  recaler() {
    requestAnimationFrame(() => {
      for (const panneau of document.querySelectorAll('.panneau')) {
        const r = panneau.getBoundingClientRect();
        panneau.style.setProperty('--px', `${-r.left}px`);
        panneau.style.setProperty('--py', `${-r.top}px`);
      }
    });
  }

  masquer() {
    clearTimeout(this.minuteurNote);
    this.enregistrerNote(); // ce qui vient d'être tapé n'est jamais perdu
    this.vider();
  }

  cadre(id, titre, nomIcone, bouton = null) {
    const panneau = el('section', 'panneau');
    panneau.dataset.id = id;
    const entete = el('div', 'panneau-entete');
    entete.title = 'Tirer pour déplacer (Alt : seul, sans le groupe)';
    entete.append(icone(nomIcone, 15), el('span', 'panneau-titre', titre));
    if (bouton) entete.append(bouton);
    panneau.append(entete);
    this.rendreMobile(panneau);
    return panneau;
  }

  // --- IA : où en sont les requêtes, et quand le compteur repart à zéro ------------------------
  async ia() {
    const panneau = this.cadre('ia', 'IA', 'user-available-symbolic');
    const reponse = await window.declic.api.executer('assistant.quota', null).catch(() => null);
    const lignes = (reponse?.texte || 'Aucune IA configurée : bouton + → « Clé d\'IA ».').split('\n');
    for (const ligne of lignes) {
      panneau.append(el('div', ligne.startsWith('  ') ? 'panneau-ligne-detail panneau-ia-detail' : 'panneau-ia-titre', ligne.trim()));
    }
    return panneau;
  }

  // --- Presse-papiers : les derniers textes copiés, un clic les recolle ----------------------
  async pressePapiers() {
    const panneau = this.cadre('pp', 'Presse-papiers', 'edit-paste-symbolic');
    const resultats = await window.declic.api.rechercher('pp', 6, null).catch(() => []);
    const elements = resultats.filter((r) => r.commande === 'pp.coller');
    if (!elements.length) panneau.append(el('div', 'panneau-vide', 'Ce que vous copiez apparaîtra ici.'));
    for (const r of elements) {
      const ligne = el('button', 'panneau-ligne');
      ligne.title = 'Recoller là où vous étiez';
      ligne.append(el('span', 'panneau-ligne-titre', r.titre), el('span', 'panneau-ligne-detail', r.sous_titre));
      ligne.addEventListener('click', () => this.barre.executer(r, r.argument));
      panneau.append(ligne);
    }
    return panneau;
  }

  // --- Applications épinglées : les favoris (Ctrl+Maj+F), sinon les plus utilisées -----------
  async applications() {
    const panneau = this.cadre('applications', 'Applications', 'view-app-grid-symbolic');
    const resultats = await window.declic.api.rechercher('', 30, null).catch(() => []);
    const applis = resultats.filter((r) => r.module === 'app' && r.favori);
    const liste = (applis.length ? applis : resultats.filter((r) => r.module === 'app')).slice(0, 8);
    if (!liste.length) {
      panneau.append(el('div', 'panneau-vide', 'Épinglez une application avec Ctrl+Maj+F dans la barre.'));
      return panneau;
    }
    const grille = el('div', 'panneau-grille');
    for (const r of liste) {
      const bouton = el('button', 'panneau-appli');
      bouton.title = r.titre;
      bouton.append(iconeResultat(r.icone, null, 30), el('span', 'panneau-appli-nom', r.titre));
      bouton.addEventListener('click', () => this.barre.executer(r, null));
      grille.append(bouton);
    }
    panneau.append(grille);
    return panneau;
  }

  // --- Bloc-notes : enregistré tout seul ----------------------------------------------------
  async notes() {
    const panneau = this.cadre('notes', 'Bloc-notes', 'document-edit-symbolic');
    const zone = el('textarea', 'panneau-note');
    zone.placeholder = 'Une idée, une liste, un numéro…';
    zone.spellcheck = true;
    zone.value = await window.declic.panneaux.lireNote().catch(() => '');
    zone.addEventListener('input', () => {
      clearTimeout(this.minuteurNote);
      this.minuteurNote = setTimeout(() => this.enregistrerNote(), 400);
    });
    this.zoneNote = zone;
    panneau.append(zone);
    return panneau;
  }

  enregistrerNote() {
    if (this.zoneNote) window.declic.panneaux.ecrireNote(this.zoneNote.value).catch(() => {});
  }

  // --- Dépôt de fichiers : on y glisse des fichiers, on les reprend en les glissant ailleurs --
  async depot() {
    const ouvrirDossier = el('button', 'panneau-bouton');
    ouvrirDossier.title = 'Ouvrir le dossier du dépôt';
    ouvrirDossier.append(icone('folder-open-symbolic', 14));
    ouvrirDossier.addEventListener('click', () => window.declic.panneaux.dossierDepot());
    const panneau = this.cadre('depot', 'Dépôt', 'folder-symbolic', ouvrirDossier);
    const zone = el('div', 'panneau-depot');
    panneau.append(zone);
    const remplir = async () => {
      const fichiers = await window.declic.panneaux.listerDepot().catch(() => []);
      zone.replaceChildren();
      if (!fichiers.length) zone.append(el('div', 'panneau-vide', 'Glissez des fichiers ici pour les garder sous la main.'));
      for (const f of fichiers) zone.append(this.ligneFichier(f, remplir));
      this.recaler(); // la hauteur du dépôt a pu changer
    };
    zone.addEventListener('dragenter', (e) => { e.preventDefault(); zone.classList.add('survol'); });
    zone.addEventListener('dragleave', (e) => { if (!zone.contains(e.relatedTarget)) zone.classList.remove('survol'); });
    zone.addEventListener('drop', async (e) => {
      e.preventDefault();
      zone.classList.remove('survol');
      if (!e.dataTransfer?.files?.length) return;
      try {
        const ajoutes = await window.declic.panneaux.deposer(e.dataTransfer.files);
        this.barre.toast(ajoutes.length ? `${ajoutes.length} fichier${ajoutes.length > 1 ? 's' : ''} gardé${ajoutes.length > 1 ? 's' : ''} dans le dépôt` : 'Déjà dans le dépôt');
      } catch (err) {
        this.barre.toast(`Dépôt impossible : ${err.message}`, 'erreur');
      }
      await remplir();
    });
    await remplir();
    return panneau;
  }

  ligneFichier(f, remplir) {
    const ligne = el('div', 'panneau-fichier');
    ligne.draggable = true;
    ligne.title = `${f.nom}\nGlisser pour le déposer ailleurs, double-clic pour l'ouvrir`;
    const image = el('img', 'panneau-fichier-icone');
    image.alt = '';
    if (f.icone) image.src = f.icone;
    const retirer = el('button', 'panneau-bouton');
    retirer.title = 'Retirer du dépôt (va dans la corbeille)';
    retirer.append(icone('window-close-symbolic', 12));
    retirer.addEventListener('click', async (e) => {
      e.stopPropagation();
      await window.declic.panneaux.supprimerDepot(f.nom).catch((err) => this.barre.toast(err.message, 'erreur'));
      await remplir();
    });
    ligne.append(image, el('span', 'panneau-fichier-nom', f.nom), retirer);
    ligne.addEventListener('dragstart', (e) => { e.preventDefault(); window.declic.panneaux.glisserDepot(f.nom); });
    ligne.addEventListener('dblclick', () => window.declic.panneaux.ouvrirDepot(f.nom).catch((err) => this.barre.toast(err.message, 'erreur')));
    return ligne;
  }
}
