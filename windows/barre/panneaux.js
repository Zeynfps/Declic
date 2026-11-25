'use strict';
// Panneaux autour de la barre, comme la Game Bar : presse-papiers et applications épinglées à gauche,
// bloc-notes et dépôt de fichiers à droite. Chacun s'active dans les réglages (section « Panneaux »).
// Ils occupent la place libre de part et d'autre de la barre ; sur un écran trop étroit, ils ne s'affichent pas.

const LARGEUR_BARRE_PX = 750;
const ECART_PX = 24;
const LARGEUR_MAX_PX = 320;
const LARGEUR_MIN_PX = 220;

class Panneaux {
  constructor(barre) {
    this.barre = barre;
    this.gauche = document.getElementById('colonne-gauche');
    this.droite = document.getElementById('colonne-droite');
    this.minuteurNote = 0;
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
    this.gauche.replaceChildren();
    this.droite.replaceChildren();
    if (!this.assezDePlace) return;
    const r = reglages;
    if (r.panneauPressePapiers !== false) this.gauche.append(await this.pressePapiers());
    if (r.panneauApplications !== false) this.gauche.append(await this.applications());
    if (r.panneauNotes !== false) this.droite.append(await this.notes());
    if (r.panneauDepot !== false) this.droite.append(await this.depot());
    this.recaler();
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
    this.gauche.replaceChildren();
    this.droite.replaceChildren();
  }

  cadre(titre, nomIcone, bouton = null) {
    const panneau = el('section', 'panneau');
    const entete = el('div', 'panneau-entete');
    entete.append(icone(nomIcone, 15), el('span', 'panneau-titre', titre));
    if (bouton) entete.append(bouton);
    panneau.append(entete);
    return panneau;
  }

  // --- Presse-papiers : les derniers textes copiés, un clic les recolle ----------------------
  async pressePapiers() {
    const panneau = this.cadre('Presse-papiers', 'edit-paste-symbolic');
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
    const panneau = this.cadre('Applications', 'view-app-grid-symbolic');
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
    const panneau = this.cadre('Bloc-notes', 'document-edit-symbolic');
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
    const panneau = this.cadre('Dépôt', 'folder-symbolic', ouvrirDossier);
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
