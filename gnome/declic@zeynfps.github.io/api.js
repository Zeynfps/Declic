// Client de l'API locale du service Déclic (HTTP + JSON sur 127.0.0.1, protégé par un jeton).
// Le port et le jeton sont lus dans ~/.local/share/declic/serveur.json, écrit par le service.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const DELAI_DEMARRAGE_MS = 4000;

function lireFichierServeur() {
    const chemin = GLib.build_filenamev([GLib.get_user_data_dir(), 'declic', 'serveur.json']);
    try {
        const [, contenu] = GLib.file_get_contents(chemin);
        const infos = JSON.parse(new TextDecoder().decode(contenu));
        if (Number.isInteger(infos.port) && typeof infos.jeton === 'string')
            return infos;
    } catch {
        // pas encore de service
    }
    return null;
}

function attendre(ms) {
    return new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
        resolve();
        return GLib.SOURCE_REMOVE;
    }));
}

export class ApiDeclic {
    constructor(settings) {
        this._settings = settings;
        this._session = new Soup.Session({timeout: 10, user_agent: 'declic-gnome/1'});
        this._processus = null;
    }

    async _requete(methode, chemin, donnees = null) {
        const infos = lireFichierServeur();
        if (!infos)
            throw new Error('service absent');
        const message = Soup.Message.new(methode, `http://127.0.0.1:${infos.port}${chemin}`);
        message.request_headers.append('Authorization', `Bearer ${infos.jeton}`);
        if (donnees !== null) {
            const corps = new TextEncoder().encode(JSON.stringify(donnees));
            message.set_request_body_from_bytes('application/json', new GLib.Bytes(corps));
        }
        const octets = await new Promise((resolve, reject) => {
            this._session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (source, resultat) => {
                try {
                    resolve(source.send_and_read_finish(resultat));
                } catch (e) {
                    reject(e);
                }
            });
        });
        const statut = message.get_status();
        const reponse = JSON.parse(new TextDecoder().decode(octets.get_data()));
        if (statut !== 200)
            throw new Error(reponse?.erreur ?? `erreur HTTP ${statut}`);
        return reponse;
    }

    // Démarre le service avec « python3 -m declic serveur » si le chemin du cœur est réglé.
    _demarrerService() {
        const dossier = this._settings.get_string('chemin-coeur');
        if (!dossier || this._processus)
            return false;
        const lanceur = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.NONE});
        lanceur.set_cwd(dossier);
        lanceur.setenv('PYTHONPATH', dossier, true);
        try {
            this._processus = lanceur.spawnv(['python3', '-m', 'declic', 'serveur']);
            this._processus.wait_async(null, () => {
                this._processus = null;
            });
            return true;
        } catch (e) {
            console.error(`Déclic : impossible de démarrer le service : ${e.message}`);
            return false;
        }
    }

    async _avecService(fonction) {
        try {
            return await fonction();
        } catch (e) {
            if (!this._demarrerService())
                throw e;
            await attendre(DELAI_DEMARRAGE_MS);
            return await fonction();
        }
    }

    rechercher(requete, limite, page = null) {
        const q = encodeURIComponent(requete);
        const p = page ? `&page=${encodeURIComponent(page)}` : '';
        return this._avecService(() => this._requete('GET', `/v1/recherche?q=${q}&limite=${limite}${p}`))
            .then(r => r.resultats);
    }

    // Texte copié, gardé dans l'historique du presse-papiers (sans relancer le service s'il est arrêté)
    ajouterPressePapiers(texte) {
        return this._requete('POST', '/v1/presse-papiers', {texte});
    }

    // Adresse de l'onglet affiché par le navigateur de ce processus (null si illisible)
    pageActive(pid) {
        return this._requete('GET', `/v1/page-active?pid=${pid}`).then(r => r.url);
    }

    // Juste avant de taper : l'onglet affiché est-il sur le site de cet identifiant ?
    verifierPage(site, pid) {
        return this._requete('GET', `/v1/verifier-page?site=${encodeURIComponent(site)}&pid=${pid}`);
    }

    executer(commande, argument) {
        return this._avecService(() => this._requete('POST', '/v1/executer', {commande, argument}));
    }

    creations() {
        return this._avecService(() => this._requete('GET', '/v1/creations')).then(r => r.creations);
    }

    creer(type, valeurs) {
        return this._avecService(() => this._requete('POST', '/v1/creer', {type, valeurs}));
    }

    elements(type) {
        return this._avecService(() => this._requete('GET', `/v1/elements?type=${encodeURIComponent(type)}`))
            .then(r => r.elements);
    }

    supprimer(type, cle) {
        return this._avecService(() => this._requete('POST', '/v1/supprimer', {type, cle}));
    }

    detruire() {
        this._session.abort();
        this._session = null;
        // Le service lancé par l'extension s'arrête avec elle.
        this._processus?.force_exit();
        this._processus = null;
    }
}
