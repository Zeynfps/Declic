// Historique du presse-papiers : chaque texte copié est envoyé au service Déclic, qui le garde (voir
// coeur/declic/modules/presse_papiers.py ; dans la barre : « pp »). Sous Wayland, seul GNOME Shell peut suivre
// le presse-papiers : c'est donc l'extension qui s'en charge.

import Meta from 'gi://Meta';
import St from 'gi://St';

// Marques posées par les gestionnaires de mots de passe (KeePassXC, KDE…) : ces textes ne sont jamais gardés
const SECRETS = ['x-kde-passwordManagerHint', 'application/x-kde-passwordManagerHint'];
const TEXTE = /^(text\/plain|UTF8_STRING|STRING|TEXT)/;

export class SuiviPressePapiers {
    constructor(api) {
        this._api = api;
        this._selection = global.display.get_selection();
        this._signal = this._selection.connect('owner-changed', (_selection, type, source) => this._change(type, source));
    }

    _change(type, source) {
        if (type !== Meta.SelectionType.SELECTION_CLIPBOARD || !source)
            return;
        const mimes = source.get_mimetypes();
        if (mimes.some(m => SECRETS.includes(m)) || !mimes.some(m => TEXTE.test(m)))
            return;
        St.Clipboard.get_default().get_text(St.ClipboardType.CLIPBOARD, (_presse, texte) => {
            if (texte && this._api)
                this._api.ajouterPressePapiers(texte).catch(() => {});
        });
    }

    detruire() {
        if (this._signal)
            this._selection.disconnect(this._signal);
        this._signal = 0;
        this._api = null;
    }
}
