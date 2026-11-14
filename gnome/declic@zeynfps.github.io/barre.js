// La barre de Déclic : une fenêtre flottante au centre de l'écran, pilotée au clavier.
// Toute la logique (recherche, classement, exécution) est dans le service ; la barre ne fait qu'afficher.
//
// Fonctionnement :
//   - une pile de vues : la recherche à la racine, puis la saisie d'un argument ou un texte à lire ;
//     le bouton ←, Échap, Alt+← ou Retour arrière (champ vide) reviennent à la vue précédente ;
//   - une barre d'actions en bas : l'action principale (Entrée) et le panneau d'actions (Ctrl+K) ;
//   - Ctrl+Entrée lance l'action secondaire, un clic hors de la fenêtre la ferme ;
//   - le bouton + en haut à droite (ou Ctrl+N) ouvre « Ajouter » : la liste de ce que les modules du
//     service savent créer (lien de recherche, snippet…), puis un petit formulaire ;
//   - le logo en bas à gauche (ou Ctrl+,) ouvre les réglages d'apparence : flou et assombrissement de l'écran
//     derrière la barre, opacité de la barre. Ils sont enregistrés dans GSettings et appliqués en direct.
//
// GNOME Shell 51 n'émet plus les anciens signaux « key-press-event » et « button-press-event » :
// le clavier passe par Clutter.KeyController et les clics par Clutter.ClickGesture ou St.Button.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Switch} from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Slider} from 'resource:///org/gnome/shell/ui/slider.js';

const DELAI_FRAPPE_MS = 60;
const DUREE_TOAST_MS = 2500;
const LARGEUR = 750;
const ICONE_PAR_DEFAUT = 'system-run-symbolic';
const TOUCHES_ENTREE = [Clutter.KEY_Return, Clutter.KEY_KP_Enter, Clutter.KEY_ISO_Enter];
const DUREE_FLOU_MS = 160;
const LARGEUR_CURSEUR = 240;
const COULEUR_BARRE = '28, 28, 31';
const CLES_APPARENCE = ['flou-actif', 'flou-rayon', 'flou-assombrissement', 'opacite-barre'];

// Réglages à curseur : clé GSettings, bornes, pas des flèches ← →, unité affichée
const CURSEURS = [
    {cle: 'flou-rayon', titre: 'Intensité du flou', icone: 'weather-fog-symbolic', min: 0, max: 100, pas: 5, unite: ' px', flou: true},
    {cle: 'flou-assombrissement', titre: "Assombrir l'arrière-plan", icone: 'display-brightness-symbolic', min: 0, max: 80, pas: 5, unite: ' %'},
    {cle: 'opacite-barre', titre: 'Opacité de la barre', icone: 'view-reveal-symbolic', min: 40, max: 100, pas: 5, unite: ' %'},
];

const TYPES = {
    app: 'Application',
    calcul: 'Calcul',
    liens: 'Lien rapide',
    ia: 'IA',
    snippets: 'Snippet',
    systeme: 'Système',
    son: 'Son',
    scripts: 'Script',
    creer: 'Ajouter',
    auto: 'Automatisation',
    identifiants: 'Identifiant',
    voir: 'Voir',
    declic: 'Déclic',
    interne: 'Déclic',
};

function icone(nom, taille, classe = 'declic-icone') {
    let gicon = null;
    try {
        gicon = Gio.Icon.new_for_string(nom || ICONE_PAR_DEFAUT);
    } catch {
        gicon = Gio.Icon.new_for_string(ICONE_PAR_DEFAUT);
    }
    return new St.Icon({gicon, icon_size: taille, style_class: classe});
}

function touche(texte) {
    return new St.Label({text: texte, style_class: 'declic-touche', y_align: Clutter.ActorAlign.CENTER});
}

function copier(texte) {
    St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, texte);
}

export class Barre {
    constructor(api, settings, dossier) {
        this._api = api;
        this._settings = settings;
        this._logo = Gio.FileIcon.new(dossier.get_child('icones').get_child('declic-logo.svg'));
        this._ouverte = false;
        this._sequence = 0;
        this._minuteur = 0;
        this._minuteurToast = 0;
        this._resultats = [];
        this._lignes = [];
        this._index = 0;
        this._pile = [];
        this._aConfirmer = null; // clé du résultat en attente de confirmation
        this._actions = null; // panneau d'actions ouvert : {liste, index, lignes}
        this._reglages = []; // lignes de la vue réglages : {activer, ajuster, maj, titreAction}
        this._idReglages = 0;
        this._etatGarde = null; // vues laissées par un clic à côté ou Super+R, rouvertes telles quelles
    }

    basculer() {
        if (this._ouverte)
            this.fermer(true);
        else
            this.ouvrir();
    }

    get _vue() {
        return this._pile[this._pile.length - 1];
    }

    // --- Construction -----------------------------------------------------------------
    _construire() {
        const moniteur = Main.layoutManager.primaryMonitor;
        this._fond = new St.Widget({
            reactive: true, style_class: 'declic-fond',
            x: 0, y: 0, width: global.stage.width, height: global.stage.height,
        });
        Main.uiGroup.add_child(this._fond);
        // Flou de ce qui est derrière la barre (tout l'écran). L'effet n'a pas de coins arrondis,
        // c'est pourquoi on floute l'écran entier plutôt que la seule zone de la barre.
        this._fond.add_effect_with_name('flou', new Shell.BlurEffect({mode: Shell.BlurMode.BACKGROUND}));

        // Clic en dehors de la fenêtre : on ferme (même principe que les dossiers de la grille d'applis)
        const clic = new Clutter.ClickGesture();
        clic.set_recognize_on_press(true);
        clic.connect('may-recognize', () => {
            const point = clic.get_coords_abs();
            return !this._contient(this._panneau, point.x, point.y);
        });
        clic.connect('recognize', () => this.fermer(true));
        this._fond.add_action(clic);

        // Clavier : capturé avant le champ de saisie, pour garder la main sur Entrée, Échap, flèches…
        this._clavier = new Clutter.KeyController();
        this._clavier.connect('key-press', () => this._touche());
        this._fond.add_action_full('declic-clavier', Clutter.EventPhase.CAPTURE, this._clavier);

        this._panneau = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL, style_class: 'declic-barre', reactive: true,
            x: moniteur.x + Math.round((moniteur.width - LARGEUR) / 2),
            y: moniteur.y + Math.round(moniteur.height * 0.2),
        });
        this._fond.add_child(this._panneau);

        // En-tête : bouton retour, puce de la commande, champ de saisie
        const entete = new St.BoxLayout({style_class: 'declic-saisie'});
        this._retour = new St.Button({
            style_class: 'declic-retour', visible: false, can_focus: false,
            child: new St.Icon({icon_name: 'go-previous-symbolic', icon_size: 16}),
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._retour.connect('clicked', () => this._revenir());
        this._puce = new St.Label({style_class: 'declic-puce', visible: false, y_align: Clutter.ActorAlign.CENTER});
        this._entree = new St.Entry({can_focus: true, x_expand: true, style_class: 'declic-entree'});
        this._entree.clutter_text.connect('text-changed', () => this._texteModifie());
        entete.add_child(this._retour);
        entete.add_child(this._puce);
        entete.add_child(this._entree);
        this._boutonAjout = new St.Button({
            style_class: 'declic-retour', can_focus: false, y_align: Clutter.ActorAlign.CENTER,
            child: new St.Icon({icon_name: 'list-add-symbolic', icon_size: 16}),
        });
        this._boutonAjout.connect('clicked', () => this._ouvrirAjout());
        entete.add_child(this._boutonAjout);
        this._panneau.add_child(entete);

        // Corps : liste de résultats, ou texte à lire
        this._corps = new St.Widget({layout_manager: new Clutter.BinLayout(), style_class: 'declic-corps', y_expand: true});
        this._liste = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, style_class: 'declic-liste'});
        this._defilement = new St.ScrollView({
            style_class: 'declic-defilement', hscrollbar_policy: St.PolicyType.NEVER,
            x_expand: true, y_expand: true,
        });
        this._defilement.set_child(this._liste);
        this._corps.add_child(this._defilement);
        this._vide = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL, style_class: 'declic-vide', visible: false,
            x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER,
        });
        this._vide.add_child(new St.Icon({icon_name: 'edit-find-symbolic', icon_size: 40, style_class: 'declic-vide-icone', x_align: Clutter.ActorAlign.CENTER}));
        this._videTexte = new St.Label({style_class: 'declic-vide-texte', x_align: Clutter.ActorAlign.CENTER});
        this._vide.add_child(this._videTexte);
        this._corps.add_child(this._vide);
        this._panneau.add_child(this._corps);

        // Pied : contexte ou message à gauche, actions à droite
        const pied = new St.BoxLayout({style_class: 'declic-pied'});
        // Logo en bas à gauche : ouvre les réglages
        this._boutonLogo = new St.Button({
            style_class: 'declic-pied-logo', can_focus: false, track_hover: true, y_align: Clutter.ActorAlign.CENTER,
            child: new St.Icon({gicon: this._logo, icon_size: 18}),
        });
        this._boutonLogo.connect('clicked', () => this._ouvrirReglages());
        this._boutonLogo.connect('notify::hover', () => {
            if (!this._minuteurToast)
                this._piedTexte.text = this._boutonLogo.hover ? 'Réglages de Déclic   Ctrl+,' : 'Déclic';
        });
        this._piedIcone = icone('system-search-symbolic', 14, 'declic-pied-icone');
        this._piedTexte = new St.Label({style_class: 'declic-pied-texte', y_align: Clutter.ActorAlign.CENTER, x_expand: true});
        this._principal = new St.Button({style_class: 'declic-pied-bouton', can_focus: false});
        const boitePrincipal = new St.BoxLayout({style_class: 'declic-pied-action'});
        this._principalTexte = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        boitePrincipal.add_child(this._principalTexte);
        boitePrincipal.add_child(touche('↵'));
        this._principal.set_child(boitePrincipal);
        this._principal.connect('clicked', () => this._valider());
        const separateur = new St.Widget({style_class: 'declic-pied-separateur', y_align: Clutter.ActorAlign.CENTER});
        this._boutonActions = new St.Button({style_class: 'declic-pied-bouton', can_focus: false});
        const boiteActions = new St.BoxLayout({style_class: 'declic-pied-action'});
        boiteActions.add_child(new St.Label({text: 'Actions', y_align: Clutter.ActorAlign.CENTER}));
        boiteActions.add_child(touche('Ctrl'));
        boiteActions.add_child(touche('K'));
        this._boutonActions.set_child(boiteActions);
        this._boutonActions.connect('clicked', () => this._basculerActions());
        pied.add_child(this._boutonLogo);
        pied.add_child(this._piedIcone);
        pied.add_child(this._piedTexte);
        pied.add_child(this._principal);
        pied.add_child(separateur);
        pied.add_child(this._boutonActions);
        this._panneau.add_child(pied);
    }

    _contient(acteur, x, y) {
        if (!acteur)
            return false;
        const [ok, lx, ly] = acteur.transform_stage_point(x, y);
        return ok && lx >= 0 && ly >= 0 && lx <= acteur.width && ly <= acteur.height;
    }

    ouvrir() {
        if (this._ouverte)
            return;
        // La page affichée par le navigateur au premier plan, pour proposer « Remplir ici »
        this._page = null;
        const precedente = global.display.focus_window;
        if (precedente && /firefox|librewolf|waterfox|floorp|zen|chrom|brave|vivaldi|opera|edge|epiphany/i
            .test(`${precedente.get_wm_class() ?? ''} ${precedente.get_gtk_application_id?.() ?? ''}`)) {
            this._api.pageActive(precedente.get_pid()).then(url => {
                this._page = url;
                if (url && this._ouverte && this._vue?.type === 'recherche')
                    this._rechercher(this._index);
            }).catch(() => {});
        }
        this._construire();
        this._grab = Main.pushModal(this._fond, {actionMode: Shell.ActionMode.NORMAL});
        if (!this._grab) {
            this._detruireActeurs();
            return;
        }
        this._ouverte = true;
        this._figerSurvol();
        this._idReglages = this._settings.connect('changed', (_s, cle) => {
            if (CLES_APPARENCE.includes(cle))
                this._appliquerApparence();
        });
        this._appliquerApparence(true);
        const garde = this._etatGarde;
        this._etatGarde = null;
        if (garde) {
            // On reprend là où on en était ; le texte est sélectionné pour pouvoir taper autre chose d'emblée
            this._pile = garde;
            this._afficherVue(true);
            if (this._entree.clutter_text.editable && this._vue.type !== 'formulaire')
                this._entree.clutter_text.set_selection(0, -1);
        } else {
            this._pile = [{type: 'recherche'}];
            this._afficherVue();
            this._entree.grab_key_focus();
            this._rechercher();
        }

        this._panneau.opacity = 0;
        this._panneau.set_pivot_point(0.5, 0.5);
        this._panneau.scale_x = this._panneau.scale_y = 0.98;
        this._panneau.ease({opacity: 255, scale_x: 1, scale_y: 1, duration: 110, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
    }

    // garder : fermeture « en passant » (clic à côté, Super+R) → on rouvrira au même endroit.
    // Sinon (Échap, commande exécutée…) on repart de zéro la prochaine fois.
    fermer(garder = false) {
        if (!this._ouverte)
            return;
        this._etatGarde = garder ? this._etatAGarder() : null;
        this._ouverte = false;
        for (const nom of ['_minuteur', '_minuteurToast', '_minuteurSurvol']) {
            if (this[nom]) {
                GLib.source_remove(this[nom]);
                this[nom] = 0;
            }
        }
        if (this._idReglages) {
            this._settings.disconnect(this._idReglages);
            this._idReglages = 0;
        }
        this._reglages = [];
        if (this._grab)
            Main.popModal(this._grab);
        this._grab = null;
        this._actions = null;
        this._aConfirmer = null;
        this._detruireActeurs();
    }

    _etatAGarder() {
        const vue = this._vue;
        if (!vue)
            return null;
        if (vue.type !== 'formulaire') {
            vue.requete = this._entree.get_text();
            vue.index = this._index;
        }
        if (vue.type === 'elements')
            vue.filtre = vue.requete;
        if (this._pile.length === 1 && vue.type === 'recherche' && !vue.requete)
            return null; // barre vide : rien à retrouver
        // Les mots de passe tapés dans un formulaire ne restent pas en mémoire
        for (const v of this._pile) {
            v.creation?.champs?.filter(c => c.type === 'secret').forEach(c => delete v.valeurs?.[c.cle]);
        }
        return this._pile;
    }

    _detruireActeurs() {
        this._fond?.destroy();
        this._fond = null;
        this._panneau = null;
        this._clavier = null;
    }

    detruire() {
        this.fermer();
    }

    // --- Vues (pile de navigation) ------------------------------------------------------
    _empiler(vue) {
        this._fermerActions();
        this._vue.requete = this._entree.get_text();
        this._vue.index = this._index;
        this._pile.push(vue);
        this._afficherVue();
    }

    _revenir() {
        if (this._actions) {
            this._fermerActions();
            return;
        }
        if (this._pile.length <= 1) {
            this.fermer();
            return;
        }
        this._pile.pop();
        this._afficherVue(true);
    }

    _afficherVue(restaurer = false) {
        const vue = this._vue;
        this._aConfirmer = null;
        this._retour.visible = this._pile.length > 1;
        this._boutonAjout.visible = vue.type === 'recherche' || (vue.type === 'elements' && vue.creation.ajoutable !== false);
        this._champs = [];
        this._reglages = [];
        const texte = this._entree.clutter_text;
        this._ignorerSaisie = true;
        if (vue.type === 'recherche') {
            this._puce.visible = false;
            texte.editable = true;
            this._entree.hint_text = 'Rechercher une appli, une commande, un calcul…';
            this._entree.set_text(restaurer ? vue.requete ?? '' : '');
            this._defilement.visible = true;
            this._ignorerSaisie = false;
            this._piedParDefaut();
            if (restaurer) {
                this._rechercher(vue.index ?? 0);
            }
        } else if (vue.type === 'argument') {
            this._puce.text = vue.resultat.titre;
            this._puce.visible = true;
            texte.editable = true;
            this._entree.hint_text = vue.resultat.attend_argument;
            this._entree.set_text(restaurer ? vue.requete ?? '' : '');
            this._ignorerSaisie = false;
            this._defilement.visible = true;
            this._afficherArgument();
        } else if (vue.type === 'texte') {
            this._puce.text = vue.titre;
            this._puce.visible = true;
            this._entree.hint_text = '';
            this._entree.set_text('');
            texte.editable = false;
            this._ignorerSaisie = false;
            this._afficherTexte(vue);
        } else if (vue.type === 'reglages') {
            this._puce.text = 'Réglages';
            this._puce.visible = true;
            this._entree.hint_text = '↑ ↓ pour choisir, ← → pour ajuster';
            this._entree.set_text('');
            texte.editable = false;
            this._ignorerSaisie = false;
            this._afficherReglages();
        } else if (vue.type === 'contenu') {
            this._puce.text = 'Mes ajouts';
            this._puce.visible = true;
            this._entree.hint_text = 'Liens, snippets…';
            this._entree.set_text('');
            texte.editable = false;
            this._ignorerSaisie = false;
            this._afficherAjout(vue, true);
        } else if (vue.type === 'elements') {
            this._puce.text = vue.creation.titre_pluriel;
            this._puce.visible = true;
            this._entree.hint_text = 'Filtrer…   Entrée : utiliser · Ctrl+X : supprimer';
            texte.editable = true;
            this._entree.set_text(restaurer ? vue.filtre ?? '' : '');
            this._ignorerSaisie = false;
            this._afficherElements(vue);
        } else if (vue.type === 'ajout') {
            this._puce.text = 'Ajouter';
            this._puce.visible = true;
            this._entree.hint_text = 'Que voulez-vous ajouter ?';
            this._entree.set_text('');
            texte.editable = false;
            this._ignorerSaisie = false;
            this._afficherAjout(vue);
        } else if (vue.type === 'formulaire') {
            this._puce.text = vue.creation.titre;
            this._puce.visible = true;
            this._entree.hint_text = 'Tab : champ suivant · ← → : choisir · Entrée : enregistrer';
            this._entree.set_text('');
            texte.editable = false;
            this._ignorerSaisie = false;
            this._afficherFormulaire(vue);
            return; // le focus va au champ du formulaire, pas à l'en-tête
        }
        texte.set_selection(-1, -1); // curseur en fin de texte, sans sélection héritée d'une autre vue
        this._entree.grab_key_focus();
    }

    _texteModifie() {
        if (this._ignorerSaisie || !this._ouverte)
            return;
        this._aConfirmer = null;
        if (this._vue.type === 'argument') {
            this._afficherArgument();
            return;
        }
        if (this._vue.type === 'elements') {
            this._vue.filtre = this._entree.get_text();
            this._afficherElements(this._vue);
            return;
        }
        if (this._vue.type !== 'recherche')
            return;
        if (this._minuteur)
            GLib.source_remove(this._minuteur);
        this._minuteur = GLib.timeout_add(GLib.PRIORITY_DEFAULT, DELAI_FRAPPE_MS, () => {
            this._minuteur = 0;
            this._rechercher();
            return GLib.SOURCE_REMOVE;
        });
    }

    // --- Recherche --------------------------------------------------------------------
    async _rechercher(index = 0) {
        const numero = ++this._sequence;
        const requete = this._entree.get_text();
        try {
            const resultats = await this._api.rechercher(requete, this._settings.get_int('nombre-resultats'), this._page);
            if (numero !== this._sequence || !this._ouverte || this._vue.type !== 'recherche')
                return; // une recherche plus récente est partie, ou l'on a changé de vue
            this._resultats = resultats;
            this._index = Math.min(index, Math.max(0, resultats.length - 1));
            this._afficherListe(requete);
        } catch (e) {
            if (numero === this._sequence && this._ouverte && this._vue.type === 'recherche') {
                this._resultats = [];
                this._afficherListe(requete);
                this._toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
            }
        }
    }

    _afficherListe(requete) {
        this._liste.destroy_all_children();
        this._lignes = [];
        let section = null;
        this._resultats.forEach((resultat, i) => {
            const nom = resultat.section || (resultat.module === 'calcul' ? 'Calculatrice' : requete ? 'Résultats' : 'Suggestions');
            if (nom !== section) {
                section = nom;
                this._liste.add_child(nom === 'Suggestions'
                    ? this._enteteSuggestions()
                    : new St.Label({text: nom, style_class: 'declic-section'}));
            }
            const ligne = resultat.module === 'calcul'
                ? this._carteCalcul(resultat, requete)
                : this._ligne(resultat);
            this._brancherLigne(ligne, i, () => this._valider());
            this._liste.add_child(ligne);
            this._lignes.push(ligne);
        });
        this._defilement.vadjustment.value = 0;
        this._vide.visible = this._resultats.length === 0;
        this._videTexte.text = requete ? `Aucun résultat pour « ${requete} »` : 'Rien à proposer pour le moment';
        this._majSelection();
    }

    // En-tête « Suggestions » avec un bouton pour les effacer (oublie l'historique d'usage)
    _enteteSuggestions() {
        const boite = new St.BoxLayout({x_expand: true});
        boite.add_child(new St.Label({text: 'Suggestions', style_class: 'declic-section', x_expand: true, y_align: Clutter.ActorAlign.CENTER}));
        const bouton = new St.Button({
            style_class: 'declic-effacer', label: 'Effacer', can_focus: false, track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        bouton.connect('clicked', () => this._effacerSuggestions());
        boite.add_child(bouton);
        return boite;
    }

    async _effacerSuggestions() {
        try {
            const reponse = await this._api.executer('declic.effacer-suggestions', null);
            if (!this._ouverte)
                return;
            this._toast(reponse.message || 'Suggestions effacées', reponse.statut === 'ok' ? 'info' : 'erreur');
            if (this._vue.type === 'recherche')
                this._rechercher();
        } catch (e) {
            this._toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
        }
    }

    // Le clavier a la priorité : quand les lignes se reconstruisent sous une souris immobile
    // (ouverture, frappe), le survol ne doit pas voler la sélection. Il ne compte qu'une fois
    // le pointeur réellement déplacé depuis la dernière touche.
    _figerSurvol() {
        const [x, y] = global.get_pointer();
        this._pointeurFige = {x, y};
        // Un pointeur qui bouge à l'intérieur d'une ligne déjà survolée n'émet pas notify::hover :
        // on surveille donc sa position tant que le survol est figé.
        if (!this._minuteurSurvol) {
            this._minuteurSurvol = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 80, () => {
                if (this._ouverte && this._pointeurFige)
                    this._verifierSurvol();
                if (this._ouverte && this._pointeurFige)
                    return GLib.SOURCE_CONTINUE;
                this._minuteurSurvol = 0;
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    // Si le pointeur a bougé depuis la dernière touche, la ligne qu'il survole devient la sélection.
    _verifierSurvol() {
        if (!this._pointeurFige || !this._survolVoulu())
            return;
        if (this._actions) {
            const i = this._actions.lignes.findIndex(l => l.hover);
            if (i >= 0 && i !== this._actions.index) {
                this._actions.index = i;
                this._majActions();
            }
            return;
        }
        const i = this._lignes.findIndex(l => l.hover);
        if (i >= 0 && i !== this._index) {
            this._index = i;
            this._aConfirmer = null;
            this._majSelection();
        }
    }

    _survolVoulu() {
        if (!this._pointeurFige)
            return true;
        const [x, y] = global.get_pointer();
        if (x === this._pointeurFige.x && y === this._pointeurFige.y)
            return false;
        this._pointeurFige = null;
        return true;
    }

    _brancherLigne(ligne, i, activer) {
        ligne.connect('notify::hover', () => {
            if (ligne.hover && this._index !== i && !this._actions && this._survolVoulu()) {
                this._index = i;
                this._aConfirmer = null;
                this._majSelection();
            }
        });
        ligne.connect('clicked', () => {
            this._index = i;
            activer();
        });
    }

    _ligne(resultat) {
        const boite = new St.BoxLayout({style_class: 'declic-ligne-boite', x_expand: true});
        boite.add_child(icone(resultat.icone, 22));
        boite.add_child(new St.Label({text: resultat.titre, style_class: 'declic-titre', y_align: Clutter.ActorAlign.CENTER}));
        if (resultat.sous_titre && resultat.sous_titre !== TYPES[resultat.module]) {
            const sous = new St.Label({text: resultat.sous_titre, style_class: 'declic-sous-titre', y_align: Clutter.ActorAlign.CENTER, x_expand: true});
            sous.clutter_text.ellipsize = 3; // Pango.EllipsizeMode.END
            boite.add_child(sous);
        } else {
            boite.add_child(new St.Widget({x_expand: true}));
        }
        const accessoire = new St.BoxLayout({style_class: 'declic-accessoire', y_align: Clutter.ActorAlign.CENTER});
        resultat._accessoire = accessoire;
        boite.add_child(accessoire);
        this._remplirAccessoire(resultat);
        return new St.Button({style_class: 'declic-ligne', child: boite, x_expand: true, track_hover: true, can_focus: false});
    }

    _remplirAccessoire(resultat) {
        const accessoire = resultat._accessoire;
        if (!accessoire)
            return;
        accessoire.destroy_all_children();
        if (this._aConfirmer === this._cle(resultat)) {
            accessoire.add_child(new St.Label({text: 'Entrée pour confirmer', style_class: 'declic-alerte', y_align: Clutter.ActorAlign.CENTER}));
            return;
        }
        if (resultat.attend_argument && resultat.argument === null) {
            accessoire.add_child(touche('Tab'));
            accessoire.add_child(new St.Label({text: resultat.attend_argument, style_class: 'declic-type', y_align: Clutter.ActorAlign.CENTER}));
            return;
        }
        if (resultat.favori)
            accessoire.add_child(new St.Icon({icon_name: 'starred-symbolic', icon_size: 12, style_class: 'declic-etoile', y_align: Clutter.ActorAlign.CENTER}));
        accessoire.add_child(new St.Label({text: TYPES[resultat.module] ?? 'Commande', style_class: 'declic-type', y_align: Clutter.ActorAlign.CENTER}));
    }

    // Les favoris restent en haut de la barre vide ; « Effacer » (les suggestions) ne les touche pas
    _peutEtreFavori(resultat) {
        return resultat && resultat.module !== 'calcul' &&
            !/^(favoris|creer)\./.test(resultat.commande) && !resultat.commande.startsWith('identifiants.remplir');
    }

    async _basculerFavori(resultat) {
        if (!this._peutEtreFavori(resultat))
            return;
        try {
            const reponse = await this._api.executer('favoris.basculer', JSON.stringify({
                commande: resultat.commande, argument: resultat.argument ?? null,
                titre: resultat.titre, icone: resultat.icone ?? '',
            }));
            if (!this._ouverte)
                return;
            this._toast(reponse.message || 'Fait', reponse.statut === 'ok' ? 'info' : 'erreur');
            if (this._vue.type === 'recherche')
                this._rechercher(this._index);
        } catch (e) {
            this._toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
        }
    }

    _carteCalcul(resultat, requete) {
        const expression = (resultat.sous_titre || requete).split(' · ')[0];
        const reponse = resultat.argument ?? resultat.titre.replace(/^=\s*/, '');
        const boite = new St.BoxLayout({style_class: 'declic-calcul', x_expand: true});
        const moitie = (valeur, legende) => {
            const colonne = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true, style_class: 'declic-calcul-moitie'});
            const label = new St.Label({text: valeur, style_class: 'declic-calcul-valeur', x_align: Clutter.ActorAlign.CENTER});
            label.clutter_text.ellipsize = 3;
            colonne.add_child(label);
            colonne.add_child(new St.Label({text: legende, style_class: 'declic-calcul-legende', x_align: Clutter.ActorAlign.CENTER}));
            return colonne;
        };
        boite.add_child(moitie(expression, 'Calcul'));
        boite.add_child(new St.Icon({icon_name: 'go-next-symbolic', icon_size: 20, style_class: 'declic-calcul-fleche', y_align: Clutter.ActorAlign.CENTER}));
        boite.add_child(moitie(reponse, 'Réponse'));
        return new St.Button({style_class: 'declic-ligne declic-ligne-calcul', child: boite, x_expand: true, track_hover: true, can_focus: false});
    }

    _afficherArgument() {
        const vue = this._vue;
        const saisie = this._entree.get_text().trim();
        this._liste.destroy_all_children();
        this._lignes = [];
        this._liste.add_child(new St.Label({text: vue.resultat.titre, style_class: 'declic-section'}));
        const ligne = this._ligne({
            ...vue.resultat,
            sous_titre: saisie ? `« ${saisie} »` : `Tapez ${vue.resultat.attend_argument}, puis Entrée`,
            attend_argument: null, argument: '',
        });
        this._brancherLigne(ligne, 0, () => this._valider());
        this._liste.add_child(ligne);
        this._lignes.push(ligne);
        this._index = 0;
        this._vide.visible = false;
        this._majSelection();
    }

    _afficherTexte(vue) {
        this._liste.destroy_all_children();
        this._lignes = [];
        this._resultats = [];
        if (vue.message)
            this._liste.add_child(new St.Label({text: vue.message, style_class: 'declic-section'}));
        const label = new St.Label({text: vue.texte, style_class: 'declic-texte'});
        label.clutter_text.line_wrap = true;
        label.clutter_text.selectable = true;
        this._liste.add_child(label);
        this._defilement.visible = true;
        this._defilement.vadjustment.value = 0;
        this._vide.visible = false;
        this._majPied();
    }

    _cle(resultat) {
        return `${resultat.commande}|${resultat.argument ?? ''}`;
    }

    _majSelection() {
        this._lignes.forEach((ligne, i) => {
            if (i === this._index)
                ligne.add_style_pseudo_class('selected');
            else
                ligne.remove_style_pseudo_class('selected');
        });
        const ligne = this._lignes[this._index];
        if (ligne) {
            const ajustement = this._defilement.vadjustment;
            const [haut, bas] = [ligne.y, ligne.y + ligne.height];
            // l'en-tête de section juste au-dessus reste visible quand on remonte
            const marge = this._index === 0 ? ligne.y : 0;
            if (haut - marge < ajustement.value)
                ajustement.value = haut - marge;
            else if (bas > ajustement.value + ajustement.page_size)
                ajustement.value = bas - ajustement.page_size;
        }
        this._majPied();
    }

    // --- Pied et messages ---------------------------------------------------------------
    _piedParDefaut() {
        this._piedIcone.visible = false; // l'icône d'état ne sert qu'aux messages
        this._piedTexte.text = 'Déclic';
        this._piedTexte.remove_style_class_name('erreur');
        this._piedTexte.remove_style_class_name('alerte');
    }

    _toast(message, genre = 'info') {
        if (!this._ouverte)
            return;
        this._piedIcone.visible = true;
        this._piedIcone.gicon = Gio.Icon.new_for_string(
            genre === 'erreur' ? 'dialog-error-symbolic' : genre === 'alerte' ? 'dialog-warning-symbolic' : 'emblem-ok-symbolic');
        this._piedTexte.text = message;
        this._piedTexte.remove_style_class_name('erreur');
        this._piedTexte.remove_style_class_name('alerte');
        if (genre !== 'info')
            this._piedTexte.add_style_class_name(genre);
        if (this._minuteurToast)
            GLib.source_remove(this._minuteurToast);
        const duree = genre === 'erreur' ? 2 * DUREE_TOAST_MS : DUREE_TOAST_MS; // le temps de lire l'explication
        this._minuteurToast = GLib.timeout_add(GLib.PRIORITY_DEFAULT, duree, () => {
            this._minuteurToast = 0;
            if (this._ouverte)
                this._piedParDefaut();
            return GLib.SOURCE_REMOVE;
        });
    }

    _majPied() {
        const actions = this._listeActions();
        this._principal.visible = actions.length > 0;
        this._principalTexte.text = actions[0]?.titre ?? '';
        this._boutonActions.visible = actions.length > 1;
    }

    // --- Actions --------------------------------------------------------------------------
    // Chaque action : {titre, icone, raccourci, faire}. La première est l'action principale (Entrée),
    // la deuxième l'action secondaire (Ctrl+Entrée).
    _listeActions() {
        const vue = this._vue;
        if (!vue)
            return [];
        if (vue.type === 'texte') {
            return [
                {titre: 'Copier le texte', icone: 'edit-copy-symbolic', faire: () => this._copier(vue.texte)},
                {titre: 'Revenir', icone: 'go-previous-symbolic', faire: () => this._revenir()},
            ];
        }
        if (vue.type === 'elements') {
            const element = vue.visibles?.[this._index];
            const liste = [];
            if (element) {
                liste.push({titre: 'Utiliser', icone: 'system-search-symbolic', faire: () => this._valider()});
                if (vue.creation.suppression)
                    liste.push({titre: vue.aSupprimer === element.cle ? 'Confirmer la suppression' : 'Supprimer',
                        icone: 'user-trash-symbolic', raccourci: ['Ctrl', 'X'], faire: () => this._supprimerElement()});
                liste.push({titre: 'Copier le nom', icone: 'edit-copy-symbolic', faire: () => this._copier(element.titre)});
            }
            if (vue.creation.ajoutable !== false) {
                liste.push({titre: `Ajouter : ${vue.creation.titre}`, icone: 'list-add-symbolic', raccourci: ['Ctrl', 'N'],
                    faire: () => this._empiler({type: 'formulaire', creation: vue.creation, valeurs: {}, champ: 0})});
            }
            liste.push({titre: 'Revenir', icone: 'go-previous-symbolic', faire: () => this._revenir()});
            return liste;
        }
        if (vue.type === 'ajout' || vue.type === 'contenu') {
            const creation = vue.creations?.[this._index];
            const liste = [];
            if (creation && vue.type === 'ajout')
                liste.push({titre: `Ajouter : ${creation.titre}`, icone: creation.icone, faire: () => this._valider()});
            else if (creation)
                liste.push({titre: `Voir : ${creation.titre_pluriel}`, icone: creation.icone, faire: () => this._valider()});
            liste.push({titre: 'Revenir', icone: 'go-previous-symbolic', faire: () => this._revenir()});
            return liste;
        }
        if (vue.type === 'formulaire') {
            return [
                {titre: 'Enregistrer', icone: 'document-save-symbolic', faire: () => this._enregistrer()},
                {titre: 'Annuler', icone: 'go-previous-symbolic', faire: () => this._revenir()},
            ];
        }
        if (vue.type === 'reglages') {
            const reglage = this._reglages[this._index];
            const liste = [];
            if (reglage)
                liste.push({titre: reglage.titreAction(), icone: reglage.icone, faire: () => reglage.activer()});
            liste.push({titre: "Réinitialiser l'apparence", icone: 'edit-undo-symbolic', faire: () => this._reinitialiserApparence()});
            liste.push({titre: 'Revenir', icone: 'go-previous-symbolic', faire: () => this._revenir()});
            return liste;
        }
        if (vue.type === 'argument') {
            const saisie = this._entree.get_text().trim();
            const liste = [{titre: vue.resultat.titre, icone: vue.resultat.icone, faire: () => this._valider()}];
            if (saisie)
                liste.push({titre: 'Copier la saisie', icone: 'edit-copy-symbolic', faire: () => this._copier(saisie)});
            liste.push({titre: 'Revenir à la recherche', icone: 'go-previous-symbolic', faire: () => this._revenir()});
            return liste;
        }
        const resultat = this._resultats[this._index];
        if (!resultat)
            return [];
        const liste = [{titre: this._titrePrincipal(resultat), icone: resultat.icone, faire: () => this._valider()}];
        if (resultat.module === 'calcul') {
            liste.push({titre: 'Copier le calcul complet', icone: 'edit-copy-symbolic',
                faire: () => this._copier(`${this._entree.get_text().trim()} = ${resultat.argument}`)});
        } else if (resultat.module === 'fichiers') {
            liste.push({titre: 'Afficher dans le dossier', icone: 'folder-open-symbolic',
                faire: () => this._executer({...resultat, commande: 'fichiers.montrer', icone: 'folder-open-symbolic'}, resultat.argument)});
            liste.push({titre: 'Copier le chemin', icone: 'edit-copy-symbolic', faire: () => this._copier(resultat.argument)});
        } else if (resultat.argument) {
            liste.push({titre: 'Copier le texte recherché', icone: 'edit-copy-symbolic', faire: () => this._copier(resultat.argument)});
        }
        if (resultat.attend_argument && resultat.argument === null && this._entree.get_text().trim()) {
            liste.push({titre: `Lancer avec « ${this._entree.get_text().trim()} »`, icone: 'system-search-symbolic',
                faire: () => this._executer(resultat, this._entree.get_text().trim())});
        }
        if (this._peutEtreFavori(resultat)) {
            liste.push({titre: resultat.favori ? 'Retirer des favoris' : 'Ajouter aux favoris',
                icone: resultat.favori ? 'non-starred-symbolic' : 'starred-symbolic',
                raccourci: ['Ctrl', 'Maj', 'F'], faire: () => this._basculerFavori(resultat)});
        }
        liste.push({titre: 'Copier le nom', icone: 'edit-copy-symbolic', faire: () => this._copier(resultat.titre)});
        liste.push({titre: 'Ajouter un lien, un snippet…', icone: 'list-add-symbolic', faire: () => this._ouvrirAjout()});
        liste.push({titre: 'Réglages de Déclic', icone: 'emblem-system-symbolic', faire: () => this._ouvrirReglages()});
        liste.push({titre: 'Fermer Déclic', icone: 'window-close-symbolic', faire: () => this.fermer()});
        return liste;
    }

    _titrePrincipal(resultat) {
        if (this._aConfirmer === this._cle(resultat))
            return 'Confirmer';
        if (resultat.attend_argument && resultat.argument === null)
            return `Saisir ${resultat.attend_argument}`;
        switch (resultat.module) {
        case 'app': return "Ouvrir l'application";
        case 'fichiers': return 'Ouvrir';
        case 'calcul': return 'Copier la réponse';
        case 'liens': return 'Ouvrir dans le navigateur';
        case 'snippets': return 'Utiliser le snippet';
        case 'scripts': return 'Lancer le script';
        case 'creer': return 'Ouvrir le formulaire';
        case 'auto': return 'Lancer';
        case 'identifiants': return resultat.commande === 'identifiants.remplir' ? 'Remplir la page' : 'Se connecter';
        default: return 'Exécuter';
        }
    }

    _copier(texte) {
        copier(texte);
        this._fermerActions();
        this._toast('Copié dans le presse-papiers');
    }

    _basculerActions() {
        if (this._actions)
            this._fermerActions();
        else
            this._ouvrirActions();
    }

    _ouvrirActions() {
        const liste = this._listeActions();
        if (liste.length === 0)
            return;
        const panneau = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, style_class: 'declic-actions', reactive: true});
        const lignes = liste.map((action, i) => {
            const boite = new St.BoxLayout({style_class: 'declic-ligne-boite', x_expand: true});
            boite.add_child(icone(action.icone, 16));
            boite.add_child(new St.Label({text: action.titre, x_expand: true, y_align: Clutter.ActorAlign.CENTER}));
            if (i === 0)
                boite.add_child(touche('↵'));
            else if (action.raccourci)
                action.raccourci.forEach(t => boite.add_child(touche(t)));
            else if (i === 1)
                [touche('Ctrl'), touche('↵')].forEach(t => boite.add_child(t));
            const ligne = new St.Button({style_class: 'declic-ligne', child: boite, x_expand: true, track_hover: true, can_focus: false});
            ligne.connect('notify::hover', () => {
                if (ligne.hover && this._actions && this._survolVoulu()) {
                    this._actions.index = i;
                    this._majActions();
                }
            });
            ligne.connect('clicked', () => this._lancerAction(i));
            panneau.add_child(ligne);
            return ligne;
        });
        this._fond.add_child(panneau);
        // ancré en bas à droite, au-dessus du pied
        const [px, py] = this._panneau.get_transformed_position();
        const [, largeurNat] = panneau.get_preferred_width(-1);
        const [, hauteurNat] = panneau.get_preferred_height(largeurNat);
        panneau.x = Math.round(px + this._panneau.width - largeurNat - 10);
        panneau.y = Math.round(py + this._panneau.height - hauteurNat - 48);
        this._actions = {liste, lignes, panneau, index: 0};
        this._majActions();
    }

    _majActions() {
        this._actions.lignes.forEach((ligne, i) => {
            if (i === this._actions.index)
                ligne.add_style_pseudo_class('selected');
            else
                ligne.remove_style_pseudo_class('selected');
        });
    }

    _fermerActions() {
        this._actions?.panneau.destroy();
        this._actions = null;
    }

    _lancerAction(i) {
        const action = (this._actions?.liste ?? this._listeActions())[i];
        this._fermerActions();
        action?.faire();
    }

    // --- Clavier ----------------------------------------------------------------------
    _touche() {
        this._verifierSurvol();
        this._figerSurvol();
        const [, symbole] = this._clavier.get_key();
        const [, presse, verrouille, bloque] = this._clavier.get_state();
        const etat = presse | verrouille | bloque;
        const ctrl = (etat & Clutter.ModifierType.CONTROL_MASK) !== 0;
        const alt = (etat & Clutter.ModifierType.MOD1_MASK) !== 0;

        if (symbole === Clutter.KEY_Escape) {
            this._revenir();
            return Clutter.EVENT_STOP;
        }
        if (ctrl && (symbole === Clutter.KEY_k || symbole === Clutter.KEY_K)) {
            this._basculerActions();
            return Clutter.EVENT_STOP;
        }
        if (alt && symbole === Clutter.KEY_Left) {
            this._revenir();
            return Clutter.EVENT_STOP;
        }
        if (ctrl && symbole === Clutter.KEY_comma) {
            this._ouvrirReglages();
            return Clutter.EVENT_STOP;
        }
        if (ctrl && (symbole === Clutter.KEY_n || symbole === Clutter.KEY_N)) {
            this._ouvrirAjout();
            return Clutter.EVENT_STOP;
        }
        if (ctrl && (symbole === Clutter.KEY_f || symbole === Clutter.KEY_F) &&
            (etat & Clutter.ModifierType.SHIFT_MASK) && !this._actions && this._vue.type === 'recherche') {
            this._basculerFavori(this._resultats[this._index]);
            return Clutter.EVENT_STOP;
        }
        if (ctrl && (symbole === Clutter.KEY_x || symbole === Clutter.KEY_X) && !this._actions && this._vue.type === 'elements') {
            this._supprimerElement();
            return Clutter.EVENT_STOP;
        }
        if (!this._actions && this._vue.type === 'formulaire')
            return this._toucheFormulaire(symbole, presse | verrouille | bloque);
        if (!this._actions && this._vue.type === 'reglages' &&
            (symbole === Clutter.KEY_Left || symbole === Clutter.KEY_Right)) {
            this._reglages[this._index]?.ajuster(symbole === Clutter.KEY_Right ? 1 : -1);
            return Clutter.EVENT_STOP;
        }

        const haut = symbole === Clutter.KEY_Up || (ctrl && symbole === Clutter.KEY_p);
        const bas = symbole === Clutter.KEY_Down || (ctrl && symbole === Clutter.KEY_n);
        if (this._actions) {
            const n = this._actions.lignes.length;
            if (haut || bas) {
                this._actions.index = (this._actions.index + (bas ? 1 : n - 1)) % n;
                this._majActions();
            } else if (TOUCHES_ENTREE.includes(symbole)) {
                this._lancerAction(this._actions.index);
            }
            return Clutter.EVENT_STOP; // le panneau d'actions garde le clavier
        }

        if (haut || bas) {
            if (this._lignes.length > 1) {
                const n = this._lignes.length;
                this._index = (this._index + (bas ? 1 : n - 1)) % n;
                this._aConfirmer = null;
                this._annulerSuppression();
                this._majSelection();
            }
            return Clutter.EVENT_STOP;
        }
        if (symbole === Clutter.KEY_Page_Down || symbole === Clutter.KEY_Page_Up) {
            if (this._lignes.length) {
                this._index = symbole === Clutter.KEY_Page_Down ? this._lignes.length - 1 : 0;
                this._majSelection();
            }
            return Clutter.EVENT_STOP;
        }
        if (TOUCHES_ENTREE.includes(symbole)) {
            if (ctrl)
                this._lancerAction(1);
            else
                this._valider();
            return Clutter.EVENT_STOP;
        }
        if (symbole === Clutter.KEY_Tab) {
            const resultat = this._resultats[this._index];
            if (this._vue.type === 'recherche' && resultat?.attend_argument && resultat.argument === null)
                this._empiler({type: 'argument', resultat});
            return Clutter.EVENT_STOP;
        }
        if (symbole === Clutter.KEY_BackSpace && this._pile.length > 1 && this._entree.get_text() === '') {
            this._revenir();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    // --- Réglages d'apparence ------------------------------------------------------------
    _appliquerApparence(ouverture = false) {
        if (!this._fond)
            return;
        const s = this._settings;
        const actif = s.get_boolean('flou-actif');
        const echelle = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const rayon = actif ? s.get_int('flou-rayon') * echelle : 0;
        const flou = this._fond.get_effect('flou');
        flou.enabled = rayon > 0;
        // L'assombrissement est un voile noir peint par le fond, par-dessus le flou
        // (la « brightness » de l'effet n'agit pas quand le flou est coupé).
        this._fond.set_style(`background-color: rgba(0, 0, 0, ${s.get_int('flou-assombrissement') / 100});`);
        if (ouverture) {
            const mode = Clutter.AnimationMode.EASE_OUT_QUAD;
            this._fond.opacity = 0;
            this._fond.ease({opacity: 255, duration: DUREE_FLOU_MS, mode});
            if (rayon > 0) {
                flou.radius = 0;
                this._fond.ease_property('@effects.flou.radius', rayon, {duration: DUREE_FLOU_MS, mode});
            }
        } else {
            flou.radius = rayon;
        }
        this._panneau?.set_style(`background-color: rgba(${COULEUR_BARRE}, ${s.get_int('opacite-barre') / 100});`);
        this._reglages.forEach(r => r.maj());
        if (this._vue?.type === 'reglages')
            this._majPied();
    }

    _ouvrirReglages() {
        if (this._vue?.type === 'reglages')
            return;
        this._empiler({type: 'reglages'});
    }

    _reinitialiserApparence() {
        CLES_APPARENCE.forEach(cle => this._settings.reset(cle));
        this._toast('Apparence par défaut rétablie');
    }

    _afficherReglages() {
        this._liste.destroy_all_children();
        this._lignes = [];
        this._resultats = [];
        this._reglages = [];
        this._vide.visible = false;
        this._defilement.visible = true;
        const s = this._settings;

        this._liste.add_child(new St.Label({text: 'Arrière-plan', style_class: 'declic-section'}));

        // Interrupteur du flou
        const interrupteur = new Switch(s.get_boolean('flou-actif'));
        // c'est la ligne entière qui bascule : sinon un clic sur l'interrupteur le basculerait deux fois
        interrupteur.reactive = false;
        interrupteur.connect('notify::state', () => {
            if (interrupteur.state !== s.get_boolean('flou-actif'))
                s.set_boolean('flou-actif', interrupteur.state);
        });
        const basculer = () => interrupteur.toggle();
        this._ajouterReglage(
            this._boiteReglage('weather-fog-symbolic', "Flouter l'arrière-plan", interrupteur), true, {
                icone: 'weather-fog-symbolic',
                activer: basculer,
                ajuster: sens => {
                    interrupteur.state = sens > 0;
                },
                maj: () => {
                    interrupteur.state = s.get_boolean('flou-actif');
                },
                titreAction: () => (s.get_boolean('flou-actif') ? 'Désactiver le flou' : 'Activer le flou'),
            });

        // Curseurs
        CURSEURS.forEach(c => {
            if (c.cle === 'opacite-barre')
                this._liste.add_child(new St.Label({text: 'Barre', style_class: 'declic-section'}));
            const versCurseur = v => (v - c.min) / (c.max - c.min);
            const curseur = new Slider(versCurseur(s.get_int(c.cle)));
            curseur.y_align = Clutter.ActorAlign.CENTER;
            curseur.width = LARGEUR_CURSEUR * St.ThemeContext.get_for_stage(global.stage).scale_factor;
            const valeur = new St.Label({style_class: 'declic-reglage-valeur', y_align: Clutter.ActorAlign.CENTER});
            const ecrire = v => {
                v = Math.max(c.min, Math.min(c.max, Math.round(v)));
                if (v !== s.get_int(c.cle))
                    s.set_int(c.cle, v);
            };
            curseur.can_focus = false;
            curseur.connect('notify::value', () => ecrire(c.min + curseur.value * (c.max - c.min)));
            // le curseur prend la main (grab) pendant le glissement : on rend ensuite le clavier au champ
            curseur.connect('drag-end', () => this._entree?.grab_key_focus());
            const boite = this._boiteReglage(c.icone, c.titre, curseur, valeur);
            const maj = () => {
                const v = s.get_int(c.cle);
                valeur.text = `${v}${c.unite}`;
                if (Math.abs(curseur.value - versCurseur(v)) > 0.5 / (c.max - c.min))
                    curseur.value = versCurseur(v);
                // l'intensité n'a pas d'effet quand le flou est coupé
                boite.opacity = c.flou && !s.get_boolean('flou-actif') ? 110 : 255;
            };
            this._ajouterReglage(boite, false, {
                icone: c.icone,
                activer: () => this._toast('Ajustez avec ← et → ou à la souris'),
                ajuster: sens => ecrire(s.get_int(c.cle) + sens * c.pas),
                maj,
                titreAction: () => 'Ajuster avec ← →',
            });
        });

        // Ajout de liens, snippets…
        this._liste.add_child(new St.Label({text: 'Contenu', style_class: 'declic-section'}));
        const boiteMes = this._boiteReglage('view-list-symbolic', 'Mes liens, snippets…', null);
        boiteMes.add_child(new St.Icon({icon_name: 'go-next-symbolic', icon_size: 14, style_class: 'declic-type', y_align: Clutter.ActorAlign.CENTER}));
        this._ajouterReglage(boiteMes, true, {
            icone: 'view-list-symbolic',
            activer: () => this._empiler({type: 'contenu', creations: null}),
            ajuster: () => {},
            maj: () => {},
            titreAction: () => 'Voir et supprimer',
        });
        const boiteAjout = this._boiteReglage('list-add-symbolic', 'Ajouter un lien de recherche, un snippet…', null);
        boiteAjout.add_child(new St.Icon({icon_name: 'go-next-symbolic', icon_size: 14, style_class: 'declic-type', y_align: Clutter.ActorAlign.CENTER}));
        this._ajouterReglage(boiteAjout, true, {
            icone: 'list-add-symbolic',
            activer: () => this._ouvrirAjout(),
            ajuster: () => {},
            maj: () => {},
            titreAction: () => 'Ouvrir',
        });

        // Automatisations
        this._liste.add_child(new St.Label({text: 'Automatisations', style_class: 'declic-section'}));
        const boiteAuto = this._boiteReglage('media-playback-start-symbolic', 'Mes automatisations : règles et journal', null);
        boiteAuto.add_child(new St.Icon({icon_name: 'go-next-symbolic', icon_size: 14, style_class: 'declic-type', y_align: Clutter.ActorAlign.CENTER}));
        this._ajouterReglage(boiteAuto, true, {
            icone: 'media-playback-start-symbolic',
            activer: () => this._executer({commande: 'auto.journal', titre: 'Automatisations', icone: 'view-list-symbolic'}, null),
            ajuster: () => {},
            maj: () => {},
            titreAction: () => 'Voir',
        });
        const boiteRegles = this._boiteReglage('document-edit-symbolic', 'Modifier les automatisations (regles.toml)', null);
        this._ajouterReglage(boiteRegles, true, {
            icone: 'document-edit-symbolic',
            activer: () => this._executer({commande: 'auto.modifier', titre: 'Modifier les automatisations', icone: 'document-edit-symbolic'}, null),
            ajuster: () => {},
            maj: () => {},
            titreAction: () => 'Ouvrir',
        });

        // Réinitialisation
        this._liste.add_child(new St.Widget({height: 6}));
        this._ajouterReglage(
            this._boiteReglage('edit-undo-symbolic', "Réinitialiser l'apparence", null), true, {
                icone: 'edit-undo-symbolic',
                activer: () => this._reinitialiserApparence(),
                ajuster: () => {},
                maj: () => {},
                titreAction: () => 'Réinitialiser',
            });

        const aide = new St.Label({
            style_class: 'declic-reglage-aide',
            text: "Le flou s'applique à tout l'écran derrière la barre. Baissez l'opacité de la barre pour le voir aussi à travers elle.",
        });
        aide.clutter_text.line_wrap = true;
        this._liste.add_child(aide);

        this._reglages.forEach(r => r.maj());
        this._index = 0;
        this._defilement.vadjustment.value = 0;
        this._majSelection();
    }

    _boiteReglage(nomIcone, titre, controle, valeur = null) {
        const boite = new St.BoxLayout({style_class: 'declic-reglage', x_expand: true});
        boite.add_child(icone(nomIcone, 18));
        boite.add_child(new St.Label({text: titre, x_expand: true, style_class: 'declic-titre', y_align: Clutter.ActorAlign.CENTER}));
        if (valeur)
            boite.add_child(valeur);
        if (controle)
            boite.add_child(controle);
        return boite;
    }

    // cliquable : ligne entière cliquable (interrupteur, bouton) ; sinon le curseur garde la souris
    _ajouterReglage(boite, cliquable, reglage) {
        const i = this._reglages.length;
        let ligne;
        if (cliquable) {
            ligne = new St.Button({style_class: 'declic-ligne', child: boite, x_expand: true, track_hover: true, can_focus: false});
            this._brancherLigne(ligne, i, () => reglage.activer());
        } else {
            ligne = new St.Bin({style_class: 'declic-ligne', child: boite, x_expand: true, reactive: true, track_hover: true});
            ligne.connect('notify::hover', () => {
                if (ligne.hover && this._index !== i && !this._actions && this._survolVoulu()) {
                    this._index = i;
                    this._majSelection();
                }
            });
        }
        this._liste.add_child(ligne);
        this._lignes.push(ligne);
        this._reglages.push(reglage);
    }

    // --- Ajout : liens, snippets… (les types viennent du service) ------------------------
    _ouvrirAjout() {
        const vue = this._vue;
        if (['ajout', 'formulaire'].includes(vue?.type))
            return;
        if (vue?.type === 'elements' && vue.creation.ajoutable === false)
            return;
        if (vue?.type === 'elements') // on ajoute un élément du type affiché
            this._empiler({type: 'formulaire', creation: vue.creation, valeurs: {}, champ: 0});
        else
            this._empiler({type: 'ajout', creations: null});
    }

    _revenirALaRecherche(texte = '') {
        this._fermerActions();
        this._pile = [this._pile[0]];
        this._afficherVue();
        if (texte) {
            this._entree.set_text(texte);
            this._entree.clutter_text.set_cursor_position(-1);
        }
    }

    async _afficherElements(vue) {
        if (!vue.elements) {
            this._liste.destroy_all_children();
            this._lignes = [];
            try {
                vue.elements = await this._api.elements(vue.creation.type);
            } catch (e) {
                vue.elements = [];
                this._toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
            }
            if (!this._ouverte || this._vue !== vue)
                return;
        }
        const filtre = (vue.filtre ?? '').trim().toLocaleLowerCase();
        vue.visibles = vue.elements.filter(e => !filtre ||
            `${e.titre} ${e.sous_titre}`.toLocaleLowerCase().includes(filtre));
        this._liste.destroy_all_children();
        this._lignes = [];
        this._resultats = [];
        this._vide.visible = false;
        this._defilement.visible = true;
        this._liste.add_child(new St.Label({
            text: `${vue.creation.titre_pluriel} · ${vue.elements.length}`, style_class: 'declic-section',
        }));
        vue.visibles.forEach((element, i) => {
            const ligne = this._ligne({
                titre: element.titre, sous_titre: element.sous_titre, icone: vue.creation.icone,
                module: 'elements', attend_argument: null, argument: null, commande: '',
            });
            element._accessoire = ligne.get_child().get_last_child();
            element._accessoire.destroy_all_children();
            this._brancherLigne(ligne, i, () => this._valider());
            this._liste.add_child(ligne);
            this._lignes.push(ligne);
        });
        this._vide.visible = vue.visibles.length === 0;
        this._videTexte.text = vue.elements.length
            ? `Aucun élément pour « ${vue.filtre} »`
            : `Aucun élément pour l'instant : + pour en ajouter`;
        this._index = Math.min(vue.index ?? 0, Math.max(0, vue.visibles.length - 1));
        vue.index = 0;
        this._majSelection();
    }

    _annulerSuppression() {
        const vue = this._vue;
        if (vue?.type !== 'elements' || !vue.aSupprimer)
            return;
        vue.elements?.find(e => e.cle === vue.aSupprimer)?._accessoire?.destroy_all_children();
        vue.aSupprimer = null;
    }

    async _supprimerElement() {
        const vue = this._vue;
        const element = vue?.visibles?.[this._index];
        if (vue?.type !== 'elements' || !element || !vue.creation.suppression)
            return;
        this._fermerActions();
        if (vue.aSupprimer !== element.cle) {
            this._annulerSuppression();
            vue.aSupprimer = element.cle;
            element._accessoire?.add_child(new St.Label({
                text: 'Ctrl+X pour confirmer', style_class: 'declic-alerte', y_align: Clutter.ActorAlign.CENTER,
            }));
            this._majPied();
            this._toast(`Supprimer « ${element.titre} » ? Appuyez encore sur Ctrl+X`, 'alerte');
            return;
        }
        vue.aSupprimer = null;
        try {
            const reponse = await this._api.supprimer(vue.creation.type, element.cle);
            if (!this._ouverte || this._vue !== vue)
                return;
            this._toast(reponse.message || 'Supprimé', reponse.statut === 'ok' ? 'info' : 'erreur');
            vue.elements = null;
            vue.index = Math.max(0, this._index - (this._index >= vue.visibles.length - 1 ? 1 : 0));
            await this._afficherElements(vue);
        } catch (e) {
            this._toast(`Échec : ${e.message}`, 'erreur');
        }
    }

    async _ouvrirCreation(type) {
        try {
            const creation = (await this._api.creations()).find(c => c.type === type);
            if (creation && this._ouverte)
                this._empiler({type: 'formulaire', creation, valeurs: {}, champ: 0});
        } catch (e) {
            this._toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
        }
    }

    // gestion = true : vue « Mes ajouts » (types dont on peut voir les éléments), sinon vue « Ajouter »
    async _afficherAjout(vue, gestion = false) {
        this._liste.destroy_all_children();
        this._lignes = [];
        this._resultats = [];
        this._vide.visible = false;
        this._defilement.visible = true;
        if (!vue.creations) {
            try {
                vue.creations = (await this._api.creations()).filter(c => gestion ? c.gerable : c.ajoutable !== false);
            } catch (e) {
                vue.creations = [];
                this._toast(`Le service Déclic ne répond pas (${e.message})`, 'erreur');
            }
            if (!this._ouverte || this._vue !== vue)
                return;
        }
        this._liste.add_child(new St.Label({text: gestion ? 'Mes ajouts' : 'Ajouter', style_class: 'declic-section'}));
        vue.creations.forEach((creation, i) => {
            const ligne = this._ligne({
                titre: gestion ? creation.titre_pluriel : creation.titre, sous_titre: creation.description,
                icone: creation.icone, module: gestion ? 'voir' : 'creer', attend_argument: null, argument: null,
                commande: `creer.${creation.type}`,
            });
            this._brancherLigne(ligne, i, () => this._valider());
            this._liste.add_child(ligne);
            this._lignes.push(ligne);
        });
        this._vide.visible = vue.creations.length === 0;
        this._videTexte.text = 'Rien à ajouter pour le moment';
        this._index = Math.min(vue.index ?? 0, Math.max(0, vue.creations.length - 1));
        this._majSelection();
    }

    _afficherFormulaire(vue) {
        this._liste.destroy_all_children();
        this._lignes = [];
        this._resultats = [];
        this._champs = [];
        this._vide.visible = false;
        this._defilement.visible = true;
        const description = new St.Label({text: vue.creation.description, style_class: 'declic-reglage-aide declic-form-intro'});
        description.clutter_text.line_wrap = true;
        this._liste.add_child(description);
        vue.creation.champs.forEach((champ, i) => {
            const boite = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, style_class: 'declic-champ-boite'});
            boite.add_child(new St.Label({
                text: champ.obligatoire ? champ.titre : `${champ.titre} (facultatif)`, style_class: 'declic-champ-titre',
            }));
            const element = champ.type === 'choix'
                ? this._champChoix(vue, champ, i)
                : this._champTexte(vue, champ, i);
            boite.add_child(element.entree);
            if (champ.aide) {
                const aide = new St.Label({text: champ.aide, style_class: 'declic-champ-aide'});
                aide.clutter_text.line_wrap = true;
                boite.add_child(aide);
            }
            this._liste.add_child(boite);
            this._champs.push({champ, boite, ...element});
        });
        this._majVisibilite();
        this._majPied();
        this._focusChamp(this._prochainVisible((vue.champ ?? 0) - 1, 1));
    }

    // Champ texte, multiligne ou secret (masqué ; le mot de passe n'est gardé que le temps du formulaire)
    _champTexte(vue, champ, i) {
        const Classe = champ.type === 'secret' ? St.PasswordEntry : St.Entry;
        const entree = new Classe({
            style_class: 'declic-champ', can_focus: true, x_expand: true, hint_text: champ.exemple ?? '',
            text: vue.valeurs[champ.cle] ?? '',
        });
        if (champ.multiligne) {
            entree.clutter_text.single_line_mode = false;
            entree.clutter_text.line_wrap = true;
            entree.add_style_class_name('multiligne');
        }
        entree.clutter_text.connect('text-changed', () => {
            vue.valeurs[champ.cle] = entree.get_text();
            entree.remove_style_class_name('erreur');
        });
        entree.clutter_text.connect('key-focus-in', () => {
            vue.champ = i;
        });
        return {entree, valeur: () => entree.get_text(), focus: () => entree.grab_key_focus()};
    }

    // Champ à choix : ← → (ou un clic) pour passer d'une option à l'autre
    _champChoix(vue, champ, i) {
        const options = champ.options ?? [];
        if (!options.some(o => o.valeur === vue.valeurs[champ.cle]))
            vue.valeurs[champ.cle] = options[0]?.valeur ?? '';
        const libelle = new St.Label({x_expand: true, y_align: Clutter.ActorAlign.CENTER});
        const position = new St.Label({style_class: 'declic-choix-position', y_align: Clutter.ActorAlign.CENTER});
        const boite = new St.BoxLayout({x_expand: true, style_class: 'declic-choix-boite'});
        boite.add_child(new St.Icon({icon_name: 'go-previous-symbolic', icon_size: 12, style_class: 'declic-choix-fleche'}));
        boite.add_child(libelle);
        boite.add_child(position);
        boite.add_child(new St.Icon({icon_name: 'go-next-symbolic', icon_size: 12, style_class: 'declic-choix-fleche'}));
        const bouton = new St.Button({
            style_class: 'declic-champ declic-choix', can_focus: true, x_expand: true, child: boite,
        });
        const afficher = () => {
            const k = options.findIndex(o => o.valeur === vue.valeurs[champ.cle]);
            libelle.text = options[k]?.libelle ?? '(aucune option)';
            position.text = options.length > 1 ? `${k + 1}/${options.length}` : '';
        };
        const changer = sens => {
            if (!options.length)
                return;
            const k = options.findIndex(o => o.valeur === vue.valeurs[champ.cle]);
            vue.valeurs[champ.cle] = options[(k + sens + options.length) % options.length].valeur;
            bouton.remove_style_class_name('erreur');
            afficher();
            this._majVisibilite();
        };
        bouton.connect('clicked', () => {
            bouton.grab_key_focus();
            changer(1);
        });
        bouton.connect('key-focus-in', () => {
            vue.champ = i;
        });
        afficher();
        return {entree: bouton, valeur: () => vue.valeurs[champ.cle] ?? '', focus: () => bouton.grab_key_focus(), changer};
    }

    _visible(champ) {
        const si = champ.si;
        return !si || si.valeurs.includes(this._vue.valeurs[si.champ] ?? '');
    }

    _majVisibilite() {
        this._champs.forEach(({champ, boite}) => {
            boite.visible = this._visible(champ);
        });
    }

    // Indice du prochain champ visible après « depuis » dans le sens donné (-1 si aucun)
    _prochainVisible(depuis, sens) {
        for (let i = depuis + sens; i >= 0 && i < this._champs.length; i += sens) {
            if (this._visible(this._champs[i].champ))
                return i;
        }
        return -1;
    }

    _focusChamp(i) {
        if (i < 0 || i >= this._champs.length)
            return;
        this._vue.champ = i;
        const {boite, focus} = this._champs[i];
        focus();
        // garder le champ visible
        const ajustement = this._defilement.vadjustment;
        if (boite.y < ajustement.value)
            ajustement.value = boite.y;
        else if (boite.y + boite.height > ajustement.value + ajustement.page_size)
            ajustement.value = boite.y + boite.height - ajustement.page_size;
    }

    _toucheFormulaire(symbole, etat) {
        const ctrl = (etat & Clutter.ModifierType.CONTROL_MASK) !== 0;
        const maj = (etat & Clutter.ModifierType.SHIFT_MASK) !== 0;
        const vue = this._vue;
        const actuel = this._champs[vue.champ];
        const suivant = this._prochainVisible(vue.champ, 1);
        if (symbole === Clutter.KEY_ISO_Left_Tab || (symbole === Clutter.KEY_Tab && maj) || symbole === Clutter.KEY_Up) {
            this._focusChamp(this._prochainVisible(vue.champ, -1));
            return Clutter.EVENT_STOP;
        }
        if (symbole === Clutter.KEY_Tab || symbole === Clutter.KEY_Down) {
            this._focusChamp(suivant);
            return Clutter.EVENT_STOP;
        }
        if (actuel?.changer && (symbole === Clutter.KEY_Left || symbole === Clutter.KEY_Right)) {
            actuel.changer(symbole === Clutter.KEY_Right ? 1 : -1);
            return Clutter.EVENT_STOP;
        }
        if (TOUCHES_ENTREE.includes(symbole)) {
            if (maj && actuel?.champ.multiligne) {
                // retour à la ligne dans le texte (le champ ne le fait pas seul : Entrée y « valide »)
                const texte = actuel.entree.clutter_text;
                texte.delete_selection();
                texte.insert_unichar('\n');
                return Clutter.EVENT_STOP;
            }
            if (ctrl || suivant < 0)
                this._enregistrer();
            else
                this._focusChamp(suivant);
            return Clutter.EVENT_STOP;
        }
        if (actuel?.changer && symbole === Clutter.KEY_space) {
            actuel.changer(1);
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE; // le reste (lettres, Retour arrière, ← → dans un texte…) va au champ
    }

    async _enregistrer() {
        const vue = this._vue;
        if (vue?.type !== 'formulaire' || vue.enCours)
            return;
        const visibles = this._champs.filter(({champ}) => this._visible(champ));
        const manquant = visibles.find(({champ, valeur}) => champ.obligatoire && !valeur().trim());
        if (manquant) {
            this._marquerErreur(this._champs.indexOf(manquant), `Il manque : ${manquant.champ.titre}`);
            return;
        }
        vue.enCours = true;
        try {
            const valeurs = Object.fromEntries(visibles.map(({champ, valeur}) => [champ.cle, valeur()]));
            const reponse = await this._api.creer(vue.creation.type, valeurs);
            if (!this._ouverte || this._vue !== vue)
                return;
            if (reponse.statut !== 'ok') {
                const i = this._champs.findIndex(({champ}) => champ.cle === reponse.champ);
                this._marquerErreur(i, reponse.message);
                return;
            }
            // le mot de passe ne reste pas en mémoire dans la vue
            vue.creation.champs.filter(c => c.type === 'secret').forEach(c => delete vue.valeurs[c.cle]);
            const precedente = this._pile[this._pile.length - 2];
            if (precedente?.type === 'elements') {
                // ajouté depuis « Mes ajouts » : on y revient, liste à jour
                precedente.elements = null;
                this._pile.pop();
                this._afficherVue(true);
            } else {
                // retour à la recherche, prête à servir le nouvel élément (« inrap ␣ »)
                this._revenirALaRecherche(reponse.remplir);
            }
            this._toast(reponse.message || 'Ajouté');
        } catch (e) {
            this._toast(`Échec : ${e.message}`, 'erreur');
        } finally {
            vue.enCours = false;
        }
    }

    _marquerErreur(i, message) {
        this._toast(message, 'erreur');
        if (i >= 0) {
            this._champs[i].entree.add_style_class_name('erreur');
            this._focusChamp(i);
        }
    }

    // --- Exécution ----------------------------------------------------------------------
    _valider() {
        const vue = this._vue;
        if (vue.type === 'texte') {
            this._copier(vue.texte);
            return;
        }
        if (vue.type === 'reglages') {
            this._reglages[this._index]?.activer();
            return;
        }
        if (vue.type === 'ajout') {
            const creation = vue.creations?.[this._index];
            if (creation)
                this._empiler({type: 'formulaire', creation, valeurs: {}, champ: 0});
            return;
        }
        if (vue.type === 'contenu') {
            const creation = vue.creations?.[this._index];
            if (creation)
                this._empiler({type: 'elements', creation, elements: null});
            return;
        }
        if (vue.type === 'elements') {
            const element = vue.visibles?.[this._index];
            if (element)
                this._revenirALaRecherche(element.remplir);
            return;
        }
        if (vue.type === 'formulaire') {
            this._enregistrer();
            return;
        }
        if (vue.type === 'argument') {
            const argument = this._entree.get_text().trim();
            if (!argument) {
                this._toast(`Tapez d'abord ${vue.resultat.attend_argument}`, 'alerte');
                return;
            }
            this._executer(vue.resultat, argument);
            return;
        }
        const resultat = this._resultats[this._index];
        if (!resultat)
            return;
        if (resultat.attend_argument && resultat.argument === null) {
            this._empiler({type: 'argument', resultat});
            return;
        }
        if (resultat.confirmer && this._aConfirmer !== this._cle(resultat)) {
            this._aConfirmer = this._cle(resultat);
            this._remplirAccessoire(resultat);
            this._majPied();
            this._toast(`${resultat.titre} : appuyez encore sur Entrée pour confirmer`, 'alerte');
            return;
        }
        this._executer(resultat, resultat.argument ?? null);
    }

    async _executer(resultat, argument) {
        this._aConfirmer = null;
        try {
            const reponse = await this._api.executer(resultat.commande, argument);
            if (!this._ouverte)
                return;
            if (reponse.statut === 'ok' && reponse.ouvrir?.startsWith('creer:')) {
                await this._ouvrirCreation(reponse.ouvrir.slice('creer:'.length));
            } else if (reponse.statut === 'ok' && reponse.fermer) {
                this.fermer();
                if (reponse.message)
                    Main.osdWindowManager.showAll(Gio.Icon.new_for_string(resultat.icone || ICONE_PAR_DEFAUT), reponse.message, null, null);
            } else if (reponse.texte) {
                this._empiler({type: 'texte', titre: resultat.titre, message: reponse.message, texte: reponse.texte});
            } else {
                this._toast(reponse.message || (reponse.statut === 'ok' ? 'Fait' : 'Échec'), reponse.statut === 'ok' ? 'info' : 'erreur');
                if (this._vue.type === 'recherche')
                    this._majSelection();
            }
        } catch (e) {
            this._toast(`Échec : ${e.message}`, 'erreur');
        }
    }
}
