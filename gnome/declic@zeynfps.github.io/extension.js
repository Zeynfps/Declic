// Déclic pour GNOME Shell : ouvre la barre avec un raccourci global.

import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {ApiDeclic} from './api.js';
import {Barre} from './barre.js';
import {SuiviPressePapiers} from './presse-papiers.js';
import {Saisie} from './saisie.js';

export default class DeclicExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._api = new ApiDeclic(this._settings);
        this._barre = new Barre(this._api, this._settings, this.dir);
        this._saisie = new Saisie(this._api);
        this._pressePapiers = new SuiviPressePapiers(this._api);
        Main.wm.addKeybinding(
            'ouvrir-barre', this._settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._barre.basculer());
    }

    disable() {
        Main.wm.removeKeybinding('ouvrir-barre');
        this._pressePapiers?.detruire();
        this._pressePapiers = null;
        this._saisie?.detruire();
        this._saisie = null;
        this._barre?.detruire();
        this._barre = null;
        this._api?.detruire();
        this._api = null;
        this._settings = null;
    }
}
