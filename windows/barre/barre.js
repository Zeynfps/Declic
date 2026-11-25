'use strict';
// La barre de Déclic pour Windows : même fonctionnement que l'extension GNOME (gnome/…/barre.js).
// Toute la logique (recherche, classement, exécution) est dans le service ; la barre ne fait qu'afficher.
//
//   - une pile de vues : la recherche à la racine, puis la saisie d'un argument, un texte à lire,
//     les réglages, « Ajouter », un formulaire, « Mes ajouts »… ; ←, Échap, Alt+← ou Retour arrière
//     (champ vide) reviennent à la vue précédente ;
//   - un pied d'actions : l'action principale (Entrée) et le panneau d'actions (Ctrl+K) ;
//   - Ctrl+Entrée lance l'action secondaire, Ctrl+Maj+F ajoute aux favoris, Ctrl+N ouvre « Ajouter » ;
//   - un clic à côté (ou Alt+Espace) ferme la barre en gardant la vue ; Échap repart de zéro.

const DELAI_FRAPPE_MS = 60;
const DUREE_TOAST_MS = 2500;

const TYPES = {
  app: 'Application', calcul: 'Calcul', liens: 'Lien rapide', ia: 'IA', snippets: 'Snippet', systeme: 'Système',
  son: 'Son', scripts: 'Script', script: 'Script', creer: 'Ajouter', auto: 'Automatisation', identifiants: 'Identifiant',
  voir: 'Voir', declic: 'Déclic', interne: 'Déclic', fichiers: 'Fichier', favoris: 'Favori',
};

const $ = (id) => document.getElementById(id);
const api = window.declic.api;

function el(balise, classe, texte) {
  const e = document.createElement(balise);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

function touche(texte) {
  return el('kbd', '', texte);
}

class Barre {
  constructor() {
    this.ouverte = false;
    this.sequence = 0;
    this.minuteur = 0;
    this.minuteurToast = 0;
    this.resultats = [];
    this.lignes = [];
    this.index = 0;
    this.pile = [];
    this.aConfirmer = null; // clé du résultat en attente de confirmation
    this.actions = null; // panneau d'actions ouvert : {liste, lignes, index}
    this.reglagesLignes = []; // lignes de la vue réglages : {activer, ajuster, maj, titreAction, icone}
    this.champs = [];
    this.etatGarde = null; // vues laissées par un clic à côté ou Alt+Espace, rouvertes telles quelles
    this.reglages = { nombreResultats: 8, flouRayon: 30, assombrissement: 15, opaciteBarre: 75, assombrirBarre: 40 };

    this.entree = $('entree');
    this.liste = $('liste');
    $('retour').append(icone('go-previous-symbolic', 16));
    $('ajout').append(icone('list-add-symbolic', 16));
    $('vide-icone').append(icone('edit-find-symbolic', 40));

    this.entree.addEventListener('input', () => this.texteModifie());
    document.addEventListener('keydown', (e) => this.toucheClavier(e), true);
    $('retour').addEventListener('click', () => this.revenir());
    $('ajout').addEventListener('click', () => this.ouvrirAjout());
    $('logo').addEventListener('click', () => this.ouvrirReglages());
    $('logo').addEventListener('mouseenter', () => { if (!this.minuteurToast) $('pied-texte').textContent = 'Réglages de Déclic   Ctrl+,'; });
    $('logo').addEventListener('mouseleave', () => { if (!this.minuteurToast) $('pied-texte').textContent = 'Déclic'; });
    $('principal').addEventListener('click', () => this.valider());
    $('bouton-actions').addEventListener('click', () => this.basculerActions());
    // Un clic à côté de la barre la ferme, en gardant la vue (la fenêtre est un peu plus grande que la barre)
    document.addEventListener('mousedown', (e) => { if (!$('barre').contains(e.target)) this.fermer(true); });
    // Le focus ne quitte pas la barre (sauf vers un champ de formulaire)
    $('barre').addEventListener('mousedown', (e) => {
      if (!e.target.closest('input, textarea, .champ')) e.preventDefault();
    });

    window.declic.surOuverture((reglages) => this.ouvrir(reglages));
    window.declic.surFermeture(({ garder }) => this.quand_ferme(garder));
    window.declic.surReglages(() => { if (this.ouverte) this.ouvrirReglages(); });
    window.declic.surApparence((a) => appliquerVerre(a));
    window.declic.surEcran((ecran) => placerEcran(ecran));
    // La page du navigateur qui avait la main, pour proposer « Remplir ici » (comme sous GNOME)
    window.declic.surPage((url) => {
      this.page = url;
      if (this.ouverte && this.vue?.type === 'recherche') this.rechercher(this.index);
    });
  }

  get vue() {
    return this.pile[this.pile.length - 1];
  }

  // --- Ouverture et fermeture --------------------------------------------------------
  ouvrir(reglages) {
    this.reglages = { ...this.reglages, ...reglages };
    this.page = null; // arrive juste après, si un navigateur avait la main
    this.ouverte = true;
    this.appliquerApparence();
    const garde = this.etatGarde;
    this.etatGarde = null;
    if (garde) {
      // On reprend là où on en était ; le texte est sélectionné pour pouvoir taper autre chose d'emblée
      this.pile = garde;
      this.afficherVue(true);
      if (!this.entree.readOnly && this.vue.type !== 'formulaire') this.entree.select();
    } else {
      this.pile = [{ type: 'recherche' }];
      this.afficherVue();
      this.rechercher();
    }
    requestAnimationFrame(() => {
      document.body.classList.add('visible');
      if (this.vue.type !== 'formulaire') this.entree.focus();
    });
  }

  // Demandée par la page (Échap, commande exécutée…) : la fenêtre se cache
  fermer(garder = false) {
    if (!this.ouverte) return;
    window.declic.fermer(garder);
  }

  // La fenêtre vient d'être cachée (par la page, un clic ailleurs ou le raccourci)
  quand_ferme(garder) {
    this.etatGarde = garder ? this.etatAGarder() : null;
    this.ouverte = false;
    clearTimeout(this.minuteur);
    clearTimeout(this.minuteurToast);
    this.minuteur = this.minuteurToast = 0;
    this.fermerActions();
    this.aConfirmer = null;
    document.body.classList.remove('visible');
    this.piedParDefaut();
  }

  etatAGarder() {
    const vue = this.vue;
    if (!vue) return null;
    if (vue.type !== 'formulaire') {
      vue.requete = this.entree.value;
      vue.index = this.index;
    }
    if (vue.type === 'elements') vue.filtre = vue.requete;
    if (this.pile.length === 1 && vue.type === 'recherche' && !vue.requete) return null; // barre vide : rien à retrouver
    // Les mots de passe tapés dans un formulaire ne restent pas en mémoire
    for (const v of this.pile) {
      v.creation?.champs?.filter((c) => c.type === 'secret').forEach((c) => delete v.valeurs?.[c.cle]);
    }
    return this.pile;
  }

  // L'apparence elle-même (flou, opacité, assombrissement) est appliquée par le processus principal ;
  // ici on ne met à jour que les lignes de la vue « Réglages ».
  appliquerApparence() {
    this.reglagesLignes.forEach((l) => l.maj());
    if (this.vue?.type === 'reglages') this.majPied();
  }

  // --- Vues (pile de navigation) ------------------------------------------------------
  empiler(vue) {
    this.fermerActions();
    this.vue.requete = this.entree.value;
    this.vue.index = this.index;
    this.pile.push(vue);
    this.afficherVue();
  }

  revenir() {
    if (this.actions) {
      this.fermerActions();
      return;
    }
    if (this.pile.length <= 1) {
      this.fermer();
      return;
    }
    this.pile.pop();
    this.afficherVue(true);
  }

  preparerEntete(puce, indication, editable, texte = '') {
    $('puce').textContent = puce ?? '';
    $('puce').hidden = !puce;
    this.entree.placeholder = indication;
    this.entree.readOnly = !editable;
    this.entree.value = texte;
  }

  afficherVue(restaurer = false) {
    const vue = this.vue;
    this.aConfirmer = null;
    $('retour').hidden = this.pile.length <= 1;
    $('ajout').hidden = !(vue.type === 'recherche' || (vue.type === 'elements' && vue.creation.ajoutable !== false));
    this.champs = [];
    this.reglagesLignes = [];
    if (vue.type === 'recherche') {
      this.preparerEntete(null, 'Rechercher une appli, une commande, un calcul…', true, restaurer ? vue.requete ?? '' : '');
      this.piedParDefaut();
      if (restaurer) this.rechercher(vue.index ?? 0);
    } else if (vue.type === 'argument') {
      this.preparerEntete(vue.resultat.titre, vue.resultat.attend_argument, true, restaurer ? vue.requete ?? '' : '');
      this.afficherArgument();
    } else if (vue.type === 'texte') {
      this.preparerEntete(vue.titre, '', false);
      this.afficherTexte(vue);
    } else if (vue.type === 'reglages') {
      this.preparerEntete('Réglages', '↑ ↓ pour choisir, ← → pour ajuster', false);
      this.afficherReglages();
    } else if (vue.type === 'contenu') {
      this.preparerEntete('Mes ajouts', 'Liens, snippets…', false);
      this.afficherAjout(vue, true);
    } else if (vue.type === 'elements') {
      this.preparerEntete(vue.creation.titre_pluriel, 'Filtrer…   Entrée : utiliser · Ctrl+X : supprimer', true, restaurer ? vue.filtre ?? '' : '');
      this.afficherElements(vue);
    } else if (vue.type === 'ajout') {
      this.preparerEntete('Ajouter', 'Que voulez-vous ajouter ?', false);
      this.afficherAjout(vue);
    } else if (vue.type === 'formulaire') {
      this.preparerEntete(vue.creation.titre, 'Tab : champ suivant · ← → : choisir · Entrée : enregistrer', false);
      this.afficherFormulaire(vue);
      return; // le focus va au champ du formulaire, pas à l'en-tête
    }
    this.entree.focus();
    const fin = this.entree.value.length;
    this.entree.setSelectionRange(fin, fin); // curseur en fin de texte, sans sélection héritée
  }

  texteModifie() {
    if (!this.ouverte || this.entree.readOnly) return;
    this.aConfirmer = null;
    if (this.vue.type === 'argument') {
      this.afficherArgument();
      return;
    }
    if (this.vue.type === 'elements') {
      this.vue.filtre = this.entree.value;
      this.afficherElements(this.vue);
      return;
    }
    if (this.vue.type !== 'recherche') return;
    clearTimeout(this.minuteur);
    this.minuteur = setTimeout(() => { this.minuteur = 0; this.rechercher(); }, DELAI_FRAPPE_MS);
  }

  // --- Recherche --------------------------------------------------------------------
  async rechercher(index = 0) {
    const numero = ++this.sequence;
    const requete = this.entree.value;
    try {
      const resultats = await api.rechercher(requete, this.reglages.nombreResultats, this.page);
      if (numero !== this.sequence || !this.ouverte || this.vue.type !== 'recherche') return;
      this.resultats = resultats;
      this.index = Math.min(index, Math.max(0, resultats.length - 1));
      this.afficherListe(requete);
    } catch (e) {
      if (numero === this.sequence && this.ouverte && this.vue.type === 'recherche') {
        this.resultats = [];
        this.afficherListe(requete);
        this.toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
      }
    }
  }

  viderListe() {
    this.liste.replaceChildren();
    this.lignes = [];
  }

  afficherVide(visible, texte = '') {
    $('vide').hidden = !visible;
    $('vide-texte').textContent = texte;
  }

  afficherListe(requete) {
    this.viderListe();
    let section = null;
    this.resultats.forEach((resultat, i) => {
      const nom = resultat.section || (resultat.module === 'calcul' ? 'Calculatrice' : requete ? 'Résultats' : 'Suggestions');
      if (nom !== section) {
        section = nom;
        this.liste.append(nom === 'Suggestions' ? this.enteteSuggestions() : this.section(nom));
      }
      const ligne = resultat.module === 'calcul' ? this.carteCalcul(resultat, requete) : this.ligne(resultat);
      this.brancherLigne(ligne, i, () => this.valider());
      this.liste.append(ligne);
      this.lignes.push(ligne);
    });
    this.liste.scrollTop = 0;
    this.afficherVide(this.resultats.length === 0, requete ? `Aucun résultat pour « ${requete} »` : 'Rien à proposer pour le moment');
    this.majSelection();
  }

  section(texte) {
    const s = el('div', 'section');
    s.append(el('span', '', texte));
    return s;
  }

  // En-tête « Suggestions » avec un bouton pour les effacer (oublie l'historique d'usage)
  enteteSuggestions() {
    const s = this.section('Suggestions');
    const bouton = el('button', 'effacer', 'Effacer');
    bouton.addEventListener('click', () => this.effacerSuggestions());
    s.append(bouton);
    return s;
  }

  async effacerSuggestions() {
    try {
      const reponse = await api.executer('declic.effacer-suggestions', null);
      if (!this.ouverte) return;
      this.toast(reponse.message || 'Suggestions effacées', reponse.statut === 'ok' ? 'info' : 'erreur');
      if (this.vue.type === 'recherche') this.rechercher();
    } catch (e) {
      this.toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
    }
  }

  // La souris ne change la sélection que si elle bouge vraiment : une liste qui se reconstruit sous
  // un pointeur immobile (ouverture, frappe) ne vole pas la sélection du clavier.
  brancherLigne(ligne, i, activer) {
    ligne.addEventListener('mousemove', () => {
      if (this.index !== i && !this.actions) {
        this.index = i;
        this.aConfirmer = null;
        this.majSelection(false);
      }
    });
    ligne.addEventListener('click', () => {
      this.index = i;
      activer();
    });
  }

  ligne(resultat) {
    const ligne = el('div', 'ligne');
    ligne.setAttribute('role', 'option');
    ligne.append(iconeResultat(resultat.icone, resultat.module === 'fichiers' ? resultat.argument : null, 22));
    ligne.append(el('span', 'titre', resultat.titre));
    if (resultat.sous_titre && resultat.sous_titre !== TYPES[resultat.module]) ligne.append(el('span', 'sous-titre', resultat.sous_titre));
    else ligne.append(el('span', 'espace'));
    const accessoire = el('span', 'accessoire');
    resultat.accessoire = accessoire;
    ligne.append(accessoire);
    this.remplirAccessoire(resultat);
    return ligne;
  }

  remplirAccessoire(resultat) {
    const accessoire = resultat.accessoire;
    if (!accessoire) return;
    accessoire.replaceChildren();
    if (this.aConfirmer === this.cle(resultat)) {
      accessoire.append(el('span', 'alerte', 'Entrée pour confirmer'));
      return;
    }
    if (resultat.attend_argument && resultat.argument === null) {
      accessoire.append(touche('Tab'), el('span', 'type', resultat.attend_argument));
      return;
    }
    if (resultat.favori) accessoire.append(icone('starred-symbolic', 13, 'icone etoile'));
    accessoire.append(el('span', 'type', TYPES[resultat.module] ?? 'Commande'));
  }

  // Les favoris restent en haut de la barre vide ; « Effacer » (les suggestions) ne les touche pas
  peutEtreFavori(resultat) {
    return resultat && resultat.module !== 'calcul'
      && !/^(favoris|creer)\./.test(resultat.commande) && !resultat.commande.startsWith('identifiants.remplir');
  }

  async basculerFavori(resultat) {
    if (!this.peutEtreFavori(resultat)) return;
    try {
      const reponse = await api.executer('favoris.basculer', JSON.stringify({
        commande: resultat.commande, argument: resultat.argument ?? null, titre: resultat.titre, icone: resultat.icone ?? '',
      }));
      if (!this.ouverte) return;
      this.toast(reponse.message || 'Fait', reponse.statut === 'ok' ? 'info' : 'erreur');
      if (this.vue.type === 'recherche') this.rechercher(this.index);
    } catch (e) {
      this.toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
    }
  }

  carteCalcul(resultat, requete) {
    const expression = (resultat.sous_titre || requete).split(' · ')[0];
    const reponse = resultat.argument ?? resultat.titre.replace(/^=\s*/, '');
    const ligne = el('div', 'ligne calcul');
    const moitie = (valeur, legende) => {
      const colonne = el('div', 'calcul-moitie');
      colonne.append(el('span', 'calcul-valeur', valeur), el('span', 'calcul-legende', legende));
      return colonne;
    };
    ligne.append(moitie(expression, 'Calcul'), icone('go-next-symbolic', 20, 'icone calcul-fleche'), moitie(reponse, 'Réponse'));
    return ligne;
  }

  afficherArgument() {
    const vue = this.vue;
    const saisie = this.entree.value.trim();
    this.viderListe();
    this.liste.append(this.section(vue.resultat.titre));
    const ligne = this.ligne({
      ...vue.resultat,
      sous_titre: saisie ? `« ${saisie} »` : `Tapez ${vue.resultat.attend_argument}, puis Entrée`,
      attend_argument: null, argument: '',
    });
    this.brancherLigne(ligne, 0, () => this.valider());
    this.liste.append(ligne);
    this.lignes.push(ligne);
    this.index = 0;
    this.afficherVide(false);
    this.majSelection();
  }

  afficherTexte(vue) {
    this.viderListe();
    this.resultats = [];
    if (vue.message) this.liste.append(this.section(vue.message));
    this.liste.append(el('div', 'texte', vue.texte));
    this.liste.scrollTop = 0;
    this.afficherVide(false);
    this.majPied();
  }

  cle(resultat) {
    return `${resultat.commande}|${resultat.argument ?? ''}`;
  }

  majSelection(defiler = true) {
    this.lignes.forEach((ligne, i) => ligne.classList.toggle('choisie', i === this.index));
    const ligne = this.lignes[this.index];
    if (ligne && defiler) ligne.scrollIntoView({ block: 'nearest' });
    if (ligne && defiler && this.index === 0) this.liste.scrollTop = 0; // l'en-tête de section reste visible
    this.majPied();
  }

  // --- Pied et messages ---------------------------------------------------------------
  piedParDefaut() {
    $('pied-icone').hidden = true;
    $('pied-texte').textContent = 'Déclic';
    $('pied-texte').className = 'pied-texte';
  }

  toast(message, genre = 'info') {
    if (!this.ouverte) return;
    const iconePied = $('pied-icone');
    iconePied.replaceChildren(icone(genre === 'erreur' ? 'dialog-error-symbolic' : genre === 'alerte' ? 'dialog-warning-symbolic' : 'emblem-ok-symbolic', 15));
    iconePied.hidden = false;
    iconePied.className = `pied-icone ${genre === 'info' ? '' : genre}`;
    $('pied-texte').textContent = message;
    $('pied-texte').className = `pied-texte ${genre === 'info' ? '' : genre}`;
    clearTimeout(this.minuteurToast);
    const duree = genre === 'erreur' ? 2 * DUREE_TOAST_MS : DUREE_TOAST_MS; // le temps de lire l'explication
    this.minuteurToast = setTimeout(() => {
      this.minuteurToast = 0;
      if (this.ouverte) this.piedParDefaut();
    }, duree);
  }

  majPied() {
    const actions = this.listeActions();
    $('principal').hidden = actions.length === 0;
    $('principal-texte').textContent = actions[0]?.titre ?? '';
    $('bouton-actions').hidden = actions.length < 2;
    document.querySelector('.pied-separateur').hidden = actions.length < 2;
  }

  // --- Actions --------------------------------------------------------------------------
  // Chaque action : {titre, icone, raccourci, faire}. La première est l'action principale (Entrée),
  // la deuxième l'action secondaire (Ctrl+Entrée).
  listeActions() {
    const vue = this.vue;
    if (!vue) return [];
    const revenir = { titre: 'Revenir', icone: 'go-previous-symbolic', faire: () => this.revenir() };
    if (vue.type === 'texte') {
      return [{ titre: 'Copier le texte', icone: 'edit-copy-symbolic', faire: () => this.copier(vue.texte) }, revenir];
    }
    if (vue.type === 'elements') {
      const element = vue.visibles?.[this.index];
      const liste = [];
      if (element) {
        liste.push({ titre: 'Utiliser', icone: 'system-search-symbolic', faire: () => this.valider() });
        if (vue.creation.suppression) {
          liste.push({ titre: vue.aSupprimer === element.cle ? 'Confirmer la suppression' : 'Supprimer', icone: 'user-trash-symbolic',
            raccourci: ['Ctrl', 'X'], faire: () => this.supprimerElement() });
        }
        liste.push({ titre: 'Copier le nom', icone: 'edit-copy-symbolic', faire: () => this.copier(element.titre) });
      }
      if (vue.creation.ajoutable !== false) {
        liste.push({ titre: `Ajouter : ${vue.creation.titre}`, icone: 'list-add-symbolic', raccourci: ['Ctrl', 'N'],
          faire: () => this.empiler({ type: 'formulaire', creation: vue.creation, valeurs: {}, champ: 0 }) });
      }
      liste.push(revenir);
      return liste;
    }
    if (vue.type === 'ajout' || vue.type === 'contenu') {
      const creation = vue.creations?.[this.index];
      const liste = [];
      if (creation && vue.type === 'ajout') liste.push({ titre: `Ajouter : ${creation.titre}`, icone: creation.icone, faire: () => this.valider() });
      else if (creation) liste.push({ titre: `Voir : ${creation.titre_pluriel}`, icone: creation.icone, faire: () => this.valider() });
      liste.push(revenir);
      return liste;
    }
    if (vue.type === 'formulaire') {
      return [
        { titre: 'Enregistrer', icone: 'document-save-symbolic', faire: () => this.enregistrer() },
        { titre: 'Annuler', icone: 'go-previous-symbolic', faire: () => this.revenir() },
      ];
    }
    if (vue.type === 'reglages') {
      const reglage = this.reglagesLignes[this.index];
      const liste = [];
      if (reglage) liste.push({ titre: reglage.titreAction(), icone: reglage.icone, faire: () => reglage.activer() });
      liste.push({ titre: "Réinitialiser l'apparence", icone: 'edit-undo-symbolic', faire: () => this.reinitialiserApparence() });
      liste.push(revenir);
      return liste;
    }
    if (vue.type === 'argument') {
      const saisie = this.entree.value.trim();
      const liste = [{ titre: vue.resultat.titre, icone: vue.resultat.icone, faire: () => this.valider() }];
      if (saisie) liste.push({ titre: 'Copier la saisie', icone: 'edit-copy-symbolic', faire: () => this.copier(saisie) });
      liste.push({ titre: 'Revenir à la recherche', icone: 'go-previous-symbolic', faire: () => this.revenir() });
      return liste;
    }
    const resultat = this.resultats[this.index];
    if (!resultat) return [];
    const saisie = this.entree.value.trim();
    const liste = [{ titre: this.titrePrincipal(resultat), icone: resultat.icone, faire: () => this.valider() }];
    if (resultat.module === 'calcul') {
      liste.push({ titre: 'Copier le calcul complet', icone: 'edit-copy-symbolic', faire: () => this.copier(`${saisie} = ${resultat.argument}`) });
    } else if (resultat.module === 'fichiers') {
      liste.push({ titre: 'Afficher dans le dossier', icone: 'folder-open-symbolic',
        faire: () => this.executer({ ...resultat, commande: 'fichiers.montrer', icone: 'folder-open-symbolic' }, resultat.argument) });
      liste.push({ titre: 'Copier le chemin', icone: 'edit-copy-symbolic', faire: () => this.copier(resultat.argument) });
    } else if (resultat.argument) {
      liste.push({ titre: 'Copier le texte recherché', icone: 'edit-copy-symbolic', faire: () => this.copier(resultat.argument) });
    }
    if (resultat.attend_argument && resultat.argument === null && saisie) {
      liste.push({ titre: `Lancer avec « ${saisie} »`, icone: 'system-search-symbolic', faire: () => this.executer(resultat, saisie) });
    }
    if (this.peutEtreFavori(resultat)) {
      liste.push({ titre: resultat.favori ? 'Retirer des favoris' : 'Ajouter aux favoris',
        icone: resultat.favori ? 'non-starred-symbolic' : 'starred-symbolic', raccourci: ['Ctrl', 'Maj', 'F'],
        faire: () => this.basculerFavori(resultat) });
    }
    liste.push({ titre: 'Copier le nom', icone: 'edit-copy-symbolic', faire: () => this.copier(resultat.titre) });
    liste.push({ titre: 'Ajouter un lien, un snippet…', icone: 'list-add-symbolic', faire: () => this.ouvrirAjout() });
    liste.push({ titre: 'Réglages de Déclic', icone: 'emblem-system-symbolic', faire: () => this.ouvrirReglages() });
    liste.push({ titre: 'Fermer Déclic', icone: 'window-close-symbolic', faire: () => this.fermer() });
    return liste;
  }

  titrePrincipal(resultat) {
    if (this.aConfirmer === this.cle(resultat)) return 'Confirmer';
    if (resultat.attend_argument && resultat.argument === null) return `Saisir ${resultat.attend_argument}`;
    switch (resultat.module) {
      case 'app': return "Ouvrir l'application";
      case 'fichiers': return 'Ouvrir';
      case 'calcul': return 'Copier la réponse';
      case 'liens': return 'Ouvrir dans le navigateur';
      case 'snippets': return 'Utiliser le snippet';
      case 'scripts': case 'script': return 'Lancer le script';
      case 'creer': return 'Ouvrir le formulaire';
      case 'auto': return 'Lancer';
      case 'identifiants': return resultat.commande === 'identifiants.remplir' ? 'Remplir la page' : 'Se connecter';
      default: return 'Exécuter';
    }
  }

  async copier(texte) {
    await window.declic.copier(texte);
    this.fermerActions();
    this.toast('Copié dans le presse-papiers');
  }

  basculerActions() {
    if (this.actions) this.fermerActions();
    else this.ouvrirActions();
  }

  ouvrirActions() {
    const liste = this.listeActions();
    if (liste.length === 0) return;
    const panneau = $('actions');
    panneau.replaceChildren();
    const lignes = liste.map((action, i) => {
      const ligne = el('div', 'ligne');
      ligne.setAttribute('role', 'menuitem');
      ligne.append(icone(action.icone, 16), el('span', 'titre', action.titre));
      if (i === 0) ligne.append(touche('↵'));
      else if (action.raccourci) action.raccourci.forEach((t) => ligne.append(touche(t)));
      else if (i === 1) ligne.append(touche('Ctrl'), touche('↵'));
      ligne.addEventListener('mousemove', () => {
        if (this.actions && this.actions.index !== i) {
          this.actions.index = i;
          this.majActions();
        }
      });
      ligne.addEventListener('click', () => this.lancerAction(i));
      panneau.append(ligne);
      return ligne;
    });
    panneau.hidden = false;
    this.actions = { liste, lignes, index: 0 };
    this.majActions();
  }

  majActions() {
    this.actions.lignes.forEach((ligne, i) => ligne.classList.toggle('choisie', i === this.actions.index));
    this.actions.lignes[this.actions.index]?.scrollIntoView({ block: 'nearest' });
  }

  fermerActions() {
    $('actions').hidden = true;
    $('actions').replaceChildren();
    this.actions = null;
  }

  lancerAction(i) {
    const action = (this.actions?.liste ?? this.listeActions())[i];
    this.fermerActions();
    action?.faire();
  }

  // --- Clavier ----------------------------------------------------------------------
  toucheClavier(e) {
    if (!this.ouverte) return;
    const ctrl = e.ctrlKey;
    const cle = e.key;
    const stop = () => { e.preventDefault(); e.stopPropagation(); };

    if (cle === 'Escape') { stop(); this.revenir(); return; }
    if (ctrl && (cle === 'k' || cle === 'K')) { stop(); this.basculerActions(); return; }
    if (e.altKey && cle === 'ArrowLeft') { stop(); this.revenir(); return; }
    if (ctrl && cle === ',') { stop(); this.ouvrirReglages(); return; }
    if (ctrl && !e.shiftKey && (cle === 'n' || cle === 'N') && !this.actions) { stop(); this.ouvrirAjout(); return; }
    if (ctrl && e.shiftKey && (cle === 'f' || cle === 'F') && !this.actions && this.vue.type === 'recherche') {
      stop();
      this.basculerFavori(this.resultats[this.index]);
      return;
    }
    if (ctrl && (cle === 'x' || cle === 'X') && !this.actions && this.vue.type === 'elements') { stop(); this.supprimerElement(); return; }
    if (!this.actions && this.vue.type === 'formulaire') {
      if (this.toucheFormulaire(e)) stop();
      return;
    }
    if (!this.actions && this.vue.type === 'reglages' && (cle === 'ArrowLeft' || cle === 'ArrowRight')) {
      stop();
      this.reglagesLignes[this.index]?.ajuster(cle === 'ArrowRight' ? 1 : -1);
      return;
    }

    const haut = cle === 'ArrowUp' || (ctrl && cle === 'p');
    const bas = cle === 'ArrowDown' || (ctrl && cle === 'n');
    if (this.actions) {
      const n = this.actions.lignes.length;
      if (haut || bas) {
        this.actions.index = (this.actions.index + (bas ? 1 : n - 1)) % n;
        this.majActions();
      } else if (cle === 'Enter') {
        this.lancerAction(this.actions.index);
      }
      stop(); // le panneau d'actions garde le clavier
      return;
    }
    if (haut || bas) {
      stop();
      if (this.lignes.length > 1) {
        const n = this.lignes.length;
        this.index = (this.index + (bas ? 1 : n - 1)) % n;
        this.aConfirmer = null;
        this.annulerSuppression();
        this.majSelection();
      }
      return;
    }
    if (cle === 'PageDown' || cle === 'PageUp') {
      stop();
      if (this.lignes.length) {
        this.index = cle === 'PageDown' ? this.lignes.length - 1 : 0;
        this.majSelection();
      }
      return;
    }
    if (cle === 'Enter') {
      stop();
      if (ctrl) this.lancerAction(1);
      else this.valider();
      return;
    }
    if (cle === 'Tab') {
      stop();
      const resultat = this.resultats[this.index];
      if (this.vue.type === 'recherche' && resultat?.attend_argument && resultat.argument === null) this.empiler({ type: 'argument', resultat });
      return;
    }
    if (cle === 'Backspace' && this.pile.length > 1 && this.entree.value === '') {
      stop();
      this.revenir();
    }
  }

  // --- Réglages ---------------------------------------------------------------------------
  ouvrirReglages() {
    if (this.vue?.type === 'reglages') return;
    this.empiler({ type: 'reglages' });
  }

  async regler(modifs) {
    try {
      this.reglages = await window.declic.regler(modifs);
      this.appliquerApparence();
    } catch (e) {
      this.toast(`Réglage impossible : ${e.message}`, 'erreur');
    }
  }

  async reinitialiserApparence() {
    this.reglages = await window.declic.reinitialiser();
    this.appliquerApparence();
    this.toast('Apparence par défaut rétablie');
  }

  async afficherReglages() {
    this.viderListe();
    this.resultats = [];
    this.reglagesLignes = [];
    this.afficherVide(false);
    const r = () => this.reglages;

    this.liste.append(this.section('Arrière-plan'));
    this.ajouterCurseur('weather-fog-symbolic', "Flouter l'arrière-plan", 'flouRayon', 0, 100, 5, '');
    this.ajouterCurseur('display-brightness-symbolic', "Assombrir l'arrière-plan", 'assombrissement', 0, 80, 5);
    this.liste.append(this.section('Barre'));
    this.ajouterCurseur('view-reveal-symbolic', 'Opacité de la barre', 'opaciteBarre', 10, 100, 5);
    this.ajouterCurseur('display-brightness-symbolic', 'Assombrir la barre', 'assombrirBarre', 0, 100, 5);

    this.liste.append(this.section('Windows'));
    const { raccourci, actif } = await window.declic.raccourci().catch(() => ({ raccourci: 'Alt+Espace', actif: false }));
    this.ajouterReglage('preferences-system-symbolic', 'Raccourci pour ouvrir Déclic', [el('span', actif ? 'type' : 'alerte', actif ? raccourci : `${raccourci} (déjà pris)`)], true, {
      activer: () => this.toast('Modifiable dans %APPDATA%\\Declic\\barre.json (« raccourci »)'),
      ajuster: () => {}, maj: () => {}, titreAction: () => 'Voir',
    });
    const demarrage = el('span', 'interrupteur');
    let demarre = await window.declic.demarrageWindows().catch(() => false);
    this.ajouterReglage('system-run-symbolic', 'Démarrer avec Windows', [demarrage], true, {
      activer: async () => { demarre = await window.declic.demarrageWindows(!demarre); demarrage.classList.toggle('actif', demarre); this.majPied(); },
      ajuster: async (sens) => { demarre = await window.declic.demarrageWindows(sens > 0); demarrage.classList.toggle('actif', demarre); },
      maj: () => demarrage.classList.toggle('actif', demarre),
      titreAction: () => (demarre ? 'Ne plus démarrer avec Windows' : 'Démarrer avec Windows'),
    });

    this.liste.append(this.section('Contenu'));
    this.ajouterReglage('view-list-symbolic', 'Mes liens, snippets…', [icone('go-next-symbolic', 14, 'icone type')], true, {
      activer: () => this.empiler({ type: 'contenu', creations: null }), ajuster: () => {}, maj: () => {}, titreAction: () => 'Voir et supprimer',
    });
    this.ajouterReglage('list-add-symbolic', 'Ajouter un lien de recherche, un snippet…', [icone('go-next-symbolic', 14, 'icone type')], true, {
      activer: () => this.ouvrirAjout(), ajuster: () => {}, maj: () => {}, titreAction: () => 'Ouvrir',
    });

    this.liste.append(this.section('Automatisations'));
    this.ajouterReglage('media-playback-start-symbolic', 'Mes automatisations : règles et journal', [icone('go-next-symbolic', 14, 'icone type')], true, {
      activer: () => this.executer({ commande: 'auto.journal', titre: 'Automatisations', icone: 'view-list-symbolic' }, null),
      ajuster: () => {}, maj: () => {}, titreAction: () => 'Voir',
    });
    this.ajouterReglage('document-edit-symbolic', 'Modifier les automatisations (regles.toml)', [], true, {
      activer: () => this.executer({ commande: 'auto.modifier', titre: 'Modifier les automatisations', icone: 'document-edit-symbolic' }, null),
      ajuster: () => {}, maj: () => {}, titreAction: () => 'Ouvrir',
    });

    this.liste.append(el('div', '', ''));
    this.ajouterReglage('edit-undo-symbolic', "Réinitialiser l'apparence", [], true, {
      activer: () => this.reinitialiserApparence(), ajuster: () => {}, maj: () => {}, titreAction: () => 'Réinitialiser',
    });
    this.liste.append(el('div', 'reglage-aide',
      "Le flou et l'assombrissement s'appliquent à tout l'écran autour de la barre (0 pour les couper). L'opacité règle la barre elle-même : baissez-la pour voir l'arrière-plan à travers ; les textes restent nets."));

    this.reglagesLignes.forEach((l) => l.maj());
    this.index = 0;
    this.liste.scrollTop = 0;
    this.majSelection();
  }

  ajouterCurseur(nomIcone, titre, cle, min, max, pas, unite = ' %') {
    const curseur = el('input');
    curseur.type = 'range';
    curseur.min = String(min);
    curseur.max = String(max);
    curseur.step = '1';
    curseur.tabIndex = -1;
    const valeur = el('span', 'reglage-valeur');
    curseur.addEventListener('input', () => this.regler({ [cle]: Number(curseur.value) }));
    curseur.addEventListener('change', () => this.entree.focus()); // le clavier revient à la barre
    this.ajouterReglage(nomIcone, titre, [valeur, curseur], false, {
      activer: () => this.toast('Ajustez avec ← et → ou à la souris'),
      ajuster: (sens) => this.regler({ [cle]: Math.max(min, Math.min(max, this.reglages[cle] + sens * pas)) }),
      maj: () => {
        valeur.textContent = `${this.reglages[cle]}${unite}`;
        curseur.value = String(this.reglages[cle]);
        curseur.style.setProperty('--remplissage', `${((this.reglages[cle] - min) / (max - min)) * 100}%`);
      },
      titreAction: () => 'Ajuster avec ← →',
    });
  }

  ajouterReglage(nomIcone, titre, controles, cliquable, reglage) {
    const i = this.reglagesLignes.length;
    const ligne = el('div', 'ligne reglage');
    ligne.append(icone(nomIcone, 18), el('span', 'titre', titre), ...controles);
    ligne.addEventListener('mousemove', () => {
      if (this.index !== i && !this.actions) {
        this.index = i;
        this.majSelection(false);
      }
    });
    if (cliquable) ligne.addEventListener('click', () => { this.index = i; reglage.activer(); });
    reglage.icone = nomIcone;
    this.liste.append(ligne);
    this.lignes.push(ligne);
    this.reglagesLignes.push(reglage);
  }

  // --- Ajout : liens, snippets… (les types viennent du service) ------------------------
  ouvrirAjout() {
    const vue = this.vue;
    if (['ajout', 'formulaire'].includes(vue?.type)) return;
    if (vue?.type === 'elements' && vue.creation.ajoutable === false) return;
    if (vue?.type === 'elements') this.empiler({ type: 'formulaire', creation: vue.creation, valeurs: {}, champ: 0 });
    else this.empiler({ type: 'ajout', creations: null });
  }

  revenirALaRecherche(texte = '') {
    this.fermerActions();
    this.pile = [this.pile[0]];
    this.afficherVue();
    if (texte) {
      this.entree.value = texte;
      this.entree.setSelectionRange(texte.length, texte.length);
      this.rechercher();
    }
  }

  async afficherElements(vue) {
    if (!vue.elements) {
      this.viderListe();
      try {
        vue.elements = await api.elements(vue.creation.type);
      } catch (e) {
        vue.elements = [];
        this.toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
      }
      if (!this.ouverte || this.vue !== vue) return;
    }
    const filtre = (vue.filtre ?? '').trim().toLocaleLowerCase();
    vue.visibles = vue.elements.filter((e) => !filtre || `${e.titre} ${e.sous_titre}`.toLocaleLowerCase().includes(filtre));
    this.viderListe();
    this.resultats = [];
    this.liste.append(this.section(`${vue.creation.titre_pluriel} · ${vue.elements.length}`));
    vue.visibles.forEach((element, i) => {
      const ligne = this.ligne({ titre: element.titre, sous_titre: element.sous_titre, icone: vue.creation.icone, module: 'elements', attend_argument: null, argument: null, commande: '' });
      element.accessoire = ligne.querySelector('.accessoire');
      element.accessoire.replaceChildren();
      this.brancherLigne(ligne, i, () => this.valider());
      this.liste.append(ligne);
      this.lignes.push(ligne);
    });
    this.afficherVide(vue.visibles.length === 0,
      vue.elements.length ? `Aucun élément pour « ${vue.filtre} »` : "Aucun élément pour l'instant : + pour en ajouter");
    this.index = Math.min(vue.index ?? 0, Math.max(0, vue.visibles.length - 1));
    vue.index = 0;
    this.majSelection();
  }

  annulerSuppression() {
    const vue = this.vue;
    if (vue?.type !== 'elements' || !vue.aSupprimer) return;
    vue.elements?.find((e) => e.cle === vue.aSupprimer)?.accessoire?.replaceChildren();
    vue.aSupprimer = null;
  }

  async supprimerElement() {
    const vue = this.vue;
    const element = vue?.visibles?.[this.index];
    if (vue?.type !== 'elements' || !element || !vue.creation.suppression) return;
    this.fermerActions();
    if (vue.aSupprimer !== element.cle) {
      this.annulerSuppression();
      vue.aSupprimer = element.cle;
      element.accessoire?.append(el('span', 'alerte', 'Ctrl+X pour confirmer'));
      this.majPied();
      this.toast(`Supprimer « ${element.titre} » ? Appuyez encore sur Ctrl+X`, 'alerte');
      return;
    }
    vue.aSupprimer = null;
    try {
      const reponse = await api.supprimer(vue.creation.type, element.cle);
      if (!this.ouverte || this.vue !== vue) return;
      this.toast(reponse.message || 'Supprimé', reponse.statut === 'ok' ? 'info' : 'erreur');
      vue.elements = null;
      vue.index = Math.max(0, this.index - (this.index >= vue.visibles.length - 1 ? 1 : 0));
      await this.afficherElements(vue);
    } catch (e) {
      this.toast(`Échec : ${e.message}`, 'erreur');
    }
  }

  async ouvrirCreation(type) {
    try {
      const creation = (await api.creations()).find((c) => c.type === type);
      if (creation && this.ouverte) this.empiler({ type: 'formulaire', creation, valeurs: {}, champ: 0 });
    } catch (e) {
      this.toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
    }
  }

  // gestion = true : vue « Mes ajouts » (types dont on peut voir les éléments), sinon vue « Ajouter »
  async afficherAjout(vue, gestion = false) {
    this.viderListe();
    this.resultats = [];
    this.afficherVide(false);
    if (!vue.creations) {
      try {
        vue.creations = (await api.creations()).filter((c) => (gestion ? c.gerable : c.ajoutable !== false));
      } catch (e) {
        vue.creations = [];
        this.toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
      }
      if (!this.ouverte || this.vue !== vue) return;
    }
    this.liste.append(this.section(gestion ? 'Mes ajouts' : 'Ajouter'));
    vue.creations.forEach((creation, i) => {
      const ligne = this.ligne({
        titre: gestion ? creation.titre_pluriel : creation.titre, sous_titre: creation.description, icone: creation.icone,
        module: gestion ? 'voir' : 'creer', attend_argument: null, argument: null, commande: `creer.${creation.type}`,
      });
      this.brancherLigne(ligne, i, () => this.valider());
      this.liste.append(ligne);
      this.lignes.push(ligne);
    });
    this.afficherVide(vue.creations.length === 0, 'Rien à ajouter pour le moment');
    this.index = Math.min(vue.index ?? 0, Math.max(0, vue.creations.length - 1));
    this.majSelection();
  }

  afficherFormulaire(vue) {
    this.viderListe();
    this.resultats = [];
    this.champs = [];
    this.afficherVide(false);
    this.liste.append(el('div', 'form-intro', vue.creation.description));
    vue.creation.champs.forEach((champ, i) => {
      const boite = el('div', 'champ-boite');
      boite.append(el('label', 'champ-titre', champ.obligatoire ? champ.titre : `${champ.titre} (facultatif)`));
      const element = champ.type === 'choix' ? this.champChoix(vue, champ, i) : this.champTexte(vue, champ, i);
      boite.append(element.entree);
      if (champ.aide) boite.append(el('div', 'champ-aide', champ.aide));
      this.liste.append(boite);
      this.champs.push({ champ, boite, ...element });
    });
    this.majVisibilite();
    this.majPied();
    this.focusChamp(this.prochainVisible((vue.champ ?? 0) - 1, 1));
  }

  // Champ texte, multiligne ou secret (masqué ; le mot de passe n'est gardé que le temps du formulaire)
  champTexte(vue, champ, i) {
    const entree = champ.multiligne ? el('textarea', 'champ') : el('input', 'champ');
    if (!champ.multiligne) entree.type = champ.type === 'secret' ? 'password' : 'text';
    entree.placeholder = champ.exemple ?? '';
    entree.value = vue.valeurs[champ.cle] ?? '';
    entree.spellcheck = false;
    entree.autocomplete = 'off';
    entree.addEventListener('input', () => {
      vue.valeurs[champ.cle] = entree.value;
      entree.classList.remove('erreur');
    });
    entree.addEventListener('focus', () => { vue.champ = i; });
    return { entree, valeur: () => entree.value, focus: () => entree.focus() };
  }

  // Champ à choix : ← → (ou un clic) pour passer d'une option à l'autre
  champChoix(vue, champ, i) {
    const options = champ.options ?? [];
    if (!options.some((o) => o.valeur === vue.valeurs[champ.cle])) vue.valeurs[champ.cle] = options[0]?.valeur ?? '';
    const bouton = el('button', 'champ choix');
    const libelle = el('span', 'libelle');
    const position = el('span', 'choix-position');
    bouton.append(icone('go-previous-symbolic', 12), libelle, position, icone('go-next-symbolic', 12));
    const afficher = () => {
      const k = options.findIndex((o) => o.valeur === vue.valeurs[champ.cle]);
      libelle.textContent = options[k]?.libelle ?? '(aucune option)';
      position.textContent = options.length > 1 ? `${k + 1}/${options.length}` : '';
    };
    const changer = (sens) => {
      if (!options.length) return;
      const k = options.findIndex((o) => o.valeur === vue.valeurs[champ.cle]);
      vue.valeurs[champ.cle] = options[(k + sens + options.length) % options.length].valeur;
      bouton.classList.remove('erreur');
      afficher();
      this.majVisibilite();
    };
    bouton.addEventListener('click', () => { bouton.focus(); changer(1); });
    bouton.addEventListener('focus', () => { vue.champ = i; });
    afficher();
    return { entree: bouton, valeur: () => vue.valeurs[champ.cle] ?? '', focus: () => bouton.focus(), changer };
  }

  visible(champ) {
    const si = champ.si;
    return !si || si.valeurs.includes(this.vue.valeurs[si.champ] ?? '');
  }

  majVisibilite() {
    this.champs.forEach(({ champ, boite }) => { boite.hidden = !this.visible(champ); });
  }

  // Indice du prochain champ visible après « depuis » dans le sens donné (-1 si aucun)
  prochainVisible(depuis, sens) {
    for (let i = depuis + sens; i >= 0 && i < this.champs.length; i += sens) {
      if (this.visible(this.champs[i].champ)) return i;
    }
    return -1;
  }

  focusChamp(i) {
    if (i < 0 || i >= this.champs.length) return;
    this.vue.champ = i;
    this.champs[i].focus();
    this.champs[i].boite.scrollIntoView({ block: 'nearest' });
  }

  // Renvoie true si la touche a été traitée (sinon elle va au champ : lettres, Retour arrière…)
  toucheFormulaire(e) {
    const vue = this.vue;
    const actuel = this.champs[vue.champ];
    const suivant = this.prochainVisible(vue.champ, 1);
    const cle = e.key;
    if ((cle === 'Tab' && e.shiftKey) || cle === 'ArrowUp') {
      this.focusChamp(this.prochainVisible(vue.champ, -1));
      return true;
    }
    if (cle === 'Tab' || cle === 'ArrowDown') {
      this.focusChamp(suivant);
      return true;
    }
    if (actuel?.changer && (cle === 'ArrowLeft' || cle === 'ArrowRight')) {
      actuel.changer(cle === 'ArrowRight' ? 1 : -1);
      return true;
    }
    if (cle === 'Enter') {
      if (e.shiftKey && actuel?.champ.multiligne) return false; // retour à la ligne dans le texte
      if (e.ctrlKey || suivant < 0) this.enregistrer();
      else this.focusChamp(suivant);
      return true;
    }
    if (actuel?.changer && cle === ' ') {
      actuel.changer(1);
      return true;
    }
    return false;
  }

  async enregistrer() {
    const vue = this.vue;
    if (vue?.type !== 'formulaire' || vue.enCours) return;
    const visibles = this.champs.filter(({ champ }) => this.visible(champ));
    const manquant = visibles.find(({ champ, valeur }) => champ.obligatoire && !valeur().trim());
    if (manquant) {
      this.marquerErreur(this.champs.indexOf(manquant), `Il manque : ${manquant.champ.titre}`);
      return;
    }
    vue.enCours = true;
    try {
      const valeurs = Object.fromEntries(visibles.map(({ champ, valeur }) => [champ.cle, valeur()]));
      const reponse = await api.creer(vue.creation.type, valeurs);
      if (!this.ouverte || this.vue !== vue) return;
      if (reponse.statut !== 'ok') {
        this.marquerErreur(this.champs.findIndex(({ champ }) => champ.cle === reponse.champ), reponse.message);
        return;
      }
      // le mot de passe ne reste pas en mémoire dans la vue
      vue.creation.champs.filter((c) => c.type === 'secret').forEach((c) => delete vue.valeurs[c.cle]);
      const precedente = this.pile[this.pile.length - 2];
      if (precedente?.type === 'elements') {
        // ajouté depuis « Mes ajouts » : on y revient, liste à jour
        precedente.elements = null;
        this.pile.pop();
        this.afficherVue(true);
      } else {
        // retour à la recherche, prête à servir le nouvel élément (« inrap ␣ »)
        this.revenirALaRecherche(reponse.remplir);
      }
      this.toast(reponse.message || 'Ajouté');
    } catch (e) {
      this.toast(`Échec : ${e.message}`, 'erreur');
    } finally {
      vue.enCours = false;
    }
  }

  marquerErreur(i, message) {
    this.toast(message, 'erreur');
    if (i >= 0) {
      this.champs[i].entree.classList.add('erreur');
      this.focusChamp(i);
    }
  }

  // --- Exécution ----------------------------------------------------------------------
  valider() {
    const vue = this.vue;
    if (vue.type === 'texte') { this.copier(vue.texte); return; }
    if (vue.type === 'reglages') { this.reglagesLignes[this.index]?.activer(); return; }
    if (vue.type === 'ajout') {
      const creation = vue.creations?.[this.index];
      if (creation) this.empiler({ type: 'formulaire', creation, valeurs: {}, champ: 0 });
      return;
    }
    if (vue.type === 'contenu') {
      const creation = vue.creations?.[this.index];
      if (creation) this.empiler({ type: 'elements', creation, elements: null });
      return;
    }
    if (vue.type === 'elements') {
      const element = vue.visibles?.[this.index];
      if (element) this.revenirALaRecherche(element.remplir);
      return;
    }
    if (vue.type === 'formulaire') { this.enregistrer(); return; }
    if (vue.type === 'argument') {
      const argument = this.entree.value.trim();
      if (!argument) {
        this.toast(`Tapez d'abord ${vue.resultat.attend_argument}`, 'alerte');
        return;
      }
      this.executer(vue.resultat, argument);
      return;
    }
    const resultat = this.resultats[this.index];
    if (!resultat) return;
    if (resultat.attend_argument && resultat.argument === null) {
      this.empiler({ type: 'argument', resultat });
      return;
    }
    if (resultat.confirmer && this.aConfirmer !== this.cle(resultat)) {
      this.aConfirmer = this.cle(resultat);
      this.remplirAccessoire(resultat);
      this.majPied();
      this.toast(`${resultat.titre} : appuyez encore sur Entrée pour confirmer`, 'alerte');
      return;
    }
    this.executer(resultat, resultat.argument ?? null);
  }

  async executer(resultat, argument) {
    this.aConfirmer = null;
    try {
      const reponse = await api.executer(resultat.commande, argument);
      if (!this.ouverte) return;
      if (reponse.statut === 'ok' && reponse.ouvrir?.startsWith('creer:')) {
        await this.ouvrirCreation(reponse.ouvrir.slice('creer:'.length));
      } else if (reponse.statut === 'ok' && reponse.fermer) {
        this.fermer();
        if (reponse.message) window.declic.osd(reponse.message);
      } else if (reponse.texte) {
        this.empiler({ type: 'texte', titre: resultat.titre, message: reponse.message, texte: reponse.texte });
      } else {
        this.toast(reponse.message || (reponse.statut === 'ok' ? 'Fait' : 'Échec'), reponse.statut === 'ok' ? 'info' : 'erreur');
        if (this.vue.type === 'recherche') this.majSelection();
      }
    } catch (e) {
      this.toast(`Échec : ${e.message}`, 'erreur');
    }
  }
}

window.barre = new Barre();
