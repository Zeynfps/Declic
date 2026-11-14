// Saisie d'un identifiant dans une page de connexion, à la demande du service Déclic.
//
// Aussi : ValiderPage(adresse, délai) appuie sur Entrée pour envoyer une question pré-remplie (IA).
// Le service appelle SaisirIdentifiant(site, délai) sur le bus de session (après avoir ouvert la page, ou
// depuis « Remplir ici » dans la barre).
// Garde-fous :
//   - on attend que la fenêtre active soit un navigateur, puis le service vérifie l'ADRESSE de l'onglet affiché
//     (https, site enregistré ou sous-domaine) : avant l'identifiant, puis de nouveau avant le mot de passe ;
//   - le mot de passe est lu ici, dans le trousseau GNOME, au dernier moment : il ne passe ni par le service,
//     ni par le presse-papiers, ni par un fichier ;
//   - avant chaque caractère, on revérifie que la même fenêtre est toujours active, sinon on arrête net ;
//   - une seule saisie à la fois.
// La frappe passe par un clavier virtuel de GNOME Shell (même chemin que le clavier réel).

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Secret from 'gi://Secret';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const CHEMIN = '/app/declic/Shell';
const INTERFACE = `<node>
  <interface name="app.declic.Shell">
    <method name="SaisirIdentifiant">
      <arg type="s" direction="in" name="site"/>
      <arg type="i" direction="in" name="delai"/>
    </method>
    <method name="ValiderPage">
      <arg type="s" direction="in" name="adresse"/>
      <arg type="i" direction="in" name="delai"/>
    </method>
  </interface>
</node>`;

const NAVIGATEURS = /firefox|librewolf|waterfox|floorp|zen|chrom|brave|vivaldi|opera|edge|epiphany/i;
const PAUSE_APRES_FOCUS_MS = 700; // laisse la page finir de se charger et placer le curseur
const PAUSE_TOUCHE_MS = 12;
const DELAI_MAX_S = 60;
// Envoi d'une question pré-remplie (IA) : laisse la zone de saisie apparaître, puis Entrée, au plus 3 fois
// tant que la page n'a pas changé (une fois la question partie, le site change d'adresse : on s'arrête).
const PAUSE_AVANT_ENTREE_MS = 1500;
const ESSAIS_ENTREE = 3;

// Schéma partagé avec le service (declic/plateforme/linux.py : SCHEMA_COFFRE)
const SCHEMA = Secret.Schema.new('app.declic.Identifiant', Secret.SchemaFlags.NONE, {
    'declic-site': Secret.SchemaAttributeType.STRING,
    'declic-nom': Secret.SchemaAttributeType.STRING,
    'declic-adresse': Secret.SchemaAttributeType.STRING,
    'declic-identifiant': Secret.SchemaAttributeType.STRING,
    'declic-titre': Secret.SchemaAttributeType.STRING,
});

function attendre(ms) {
    return new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
        resolve();
        return GLib.SOURCE_REMOVE;
    }));
}

function enPromesse(debut, fin) {
    return new Promise((resolve, reject) => debut((_o, res) => {
        try {
            resolve(fin(res));
        } catch (e) {
            reject(e);
        }
    }));
}

export class Saisie {
    constructor(api) {
        this._api = api;
        this._enCours = false;
        this._clavier = null;
        this._dbus = Gio.DBusExportedObject.wrapJSObject(INTERFACE, this);
        this._dbus.export(Gio.DBus.session, CHEMIN);
    }

    detruire() {
        this._dbus?.unexport();
        this._dbus = null;
        this._clavier = null;
        this._annule = true;
    }

    // Méthode D-Bus : répond tout de suite, la saisie se fait ensuite (le résultat est notifié)
    SaisirIdentifiant(site, delai) {
        this._saisir(site, Math.max(1, Math.min(DELAI_MAX_S, delai)))
            .catch(e => Main.notify('Déclic : connexion abandonnée', e.message));
    }

    // Méthode D-Bus : appuie sur Entrée dans le navigateur quand il affiche cette page (question d'une IA)
    ValiderPage(adresse, delai) {
        this._validerPage(adresse, Math.max(1, Math.min(DELAI_MAX_S, delai)))
            .catch(e => log(`Déclic : question non envoyée (${e.message})`));
    }

    // « https://claude.ai/new?q=… » → « https://claude.ai/new » : la requête peut être retirée par le site
    _sansRequete(adresse) {
        try {
            const uri = GLib.Uri.parse(adresse, GLib.UriFlags.NONE);
            return `${uri.get_scheme()}://${uri.get_host()}${uri.get_path() || '/'}`.toLowerCase();
        } catch {
            return null;
        }
    }

    async _surLaPage(attendu) {
        const fenetre = global.display.focus_window;
        if (!this._navigateur(fenetre))
            return null;
        const url = await this._api.pageActive(fenetre.get_pid()).catch(() => null);
        return url && this._sansRequete(url) === attendu && global.display.focus_window === fenetre ? fenetre : null;
    }

    async _validerPage(adresse, delai) {
        const attendu = this._sansRequete(adresse);
        if (!attendu)
            throw new Error('adresse illisible');
        this._jeton = (this._jeton ?? 0) + 1; // une nouvelle question remplace la précédente
        const jeton = this._jeton;
        const limite = GLib.get_monotonic_time() + delai * 1e6;
        let fenetre = null;
        while (!fenetre) {
            if (this._annule || jeton !== this._jeton || GLib.get_monotonic_time() > limite)
                throw new Error('la page de l\'IA n\'est pas apparue au premier plan');
            fenetre = await this._surLaPage(attendu);
            if (!fenetre)
                await attendre(300);
        }
        for (let i = 0; i < ESSAIS_ENTREE; i++) {
            await attendre(PAUSE_AVANT_ENTREE_MS);
            if (this._annule || jeton !== this._jeton)
                return;
            // question déjà partie (le site a changé d'adresse), autre onglet ou autre fenêtre : on ne touche à rien
            if (await this._surLaPage(attendu) !== fenetre)
                return;
            await this._touche(Clutter.KEY_Return, fenetre);
        }
    }

    _navigateur(fenetre) {
        if (!fenetre)
            return false;
        const appli = `${fenetre.get_wm_class() ?? ''} ${fenetre.get_gtk_application_id?.() ?? ''}`;
        return NAVIGATEURS.test(appli);
    }

    // Attend qu'un navigateur soit au premier plan ET que son onglet soit sur le bon site (la page peut
    // encore se charger ou passer par des redirections). Renvoie la fenêtre.
    async _attendrePage(site, delai) {
        const limite = GLib.get_monotonic_time() + delai * 1e6;
        let raison = 'aucun navigateur au premier plan';
        while (GLib.get_monotonic_time() < limite && !this._annule) {
            const fenetre = global.display.focus_window;
            if (this._navigateur(fenetre)) {
                const verdict = await this._api.verifierPage(site, fenetre.get_pid());
                if (verdict.ok && global.display.focus_window === fenetre)
                    return fenetre;
                raison = verdict.raison || raison;
            }
            await attendre(400);
        }
        throw new Error(`${raison} : rien n'a été tapé`);
    }

    async _reverifier(site, fenetre) {
        const verdict = await this._api.verifierPage(site, fenetre.get_pid());
        if (!verdict.ok || global.display.focus_window !== fenetre)
            throw new Error(`${verdict.raison || 'la fenêtre a changé'} : mot de passe non tapé`);
    }

    async _lireCoffre(site) {
        const elements = await enPromesse(
            cb => Secret.password_search(SCHEMA, {'declic-site': site}, Secret.SearchFlags.UNLOCK, null, cb),
            res => Secret.password_search_finish(res));
        if (!elements?.length)
            throw new Error(`identifiant « ${site} » absent du trousseau`);
        const identifiant = elements[0].get_attributes()['declic-identifiant'] ?? '';
        const motDePasse = await enPromesse(
            cb => Secret.password_lookup(SCHEMA, {'declic-site': site}, null, cb),
            res => Secret.password_lookup_finish(res));
        if (motDePasse === null)
            throw new Error('mot de passe illisible (trousseau verrouillé ?)');
        return [identifiant, motDePasse];
    }

    _appareil() {
        if (!this._clavier) {
            const siege = global.stage.get_context().get_backend().get_default_seat();
            this._clavier = siege.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        }
        return this._clavier;
    }

    async _touche(keyval, fenetre) {
        if (this._annule || global.display.focus_window !== fenetre)
            throw new Error('la fenêtre a changé pendant la saisie : arrêt immédiat');
        const clavier = this._appareil();
        const t = GLib.get_monotonic_time();
        clavier.notify_keyval(t, keyval, Clutter.KeyState.PRESSED);
        clavier.notify_keyval(t + 1, keyval, Clutter.KeyState.RELEASED);
        await attendre(PAUSE_TOUCHE_MS);
    }

    async _taper(texte, fenetre) {
        for (const caractere of texte)
            await this._touche(Clutter.unicode_to_keysym(caractere.codePointAt(0)), fenetre);
    }

    async _saisir(site, delai) {
        if (this._enCours)
            throw new Error('une autre connexion est déjà en cours');
        this._enCours = true;
        this._annule = false;
        let motDePasse = null;
        try {
            const fenetre = await this._attendrePage(site, delai);
            let identifiant;
            [identifiant, motDePasse] = await this._lireCoffre(site);
            await attendre(PAUSE_APRES_FOCUS_MS);
            await this._taper(identifiant, fenetre);
            await this._touche(Clutter.KEY_Tab, fenetre);
            await this._reverifier(site, fenetre);
            await this._taper(motDePasse, fenetre);
            await this._touche(Clutter.KEY_Return, fenetre);
        } finally {
            motDePasse = null;
            this._enCours = false;
        }
    }
}
