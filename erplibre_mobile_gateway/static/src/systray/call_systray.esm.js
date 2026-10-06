/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import {Component, onWillStart, useState} from "@odoo/owl";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {useDropdownState} from "@web/core/dropdown/dropdown_hooks";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";

/** Combien d'appels le menu montre. Au-dela, on ouvre la liste complete. */
const LIMITE = 12;

/**
 * Icone de telephone dans la barre systeme : les derniers appels, et une
 * pastille quand il en arrive un.
 *
 * <p>L'historique n'est PAS charge en permanence. Il l'est a l'ouverture du
 * menu, et rafraichi quand le bus annonce un appel. Interroger le serveur en
 * boucle pour un evenement qui arrive quelques fois par jour couterait plus
 * que ce qu'il rapporte.
 */
export class CallSystray extends Component {
    static components = {Dropdown};
    static props = [];
    static template = "erplibre_mobile_gateway.CallSystray";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dropdown = useDropdownState();
        this.state = useState({calls: [], nouveaux: 0, chargement: false});

        // Le compte de depart vient du SERVEUR, pas de cet onglet. Un
        // compteur ne vivant qu'en memoire repartait a zero a chaque
        // rechargement : l'appel recu pendant que le navigateur etait ferme
        // — celui qu'on veut justement retrouver — ne laissait aucune trace.
        onWillStart(async () => {
            this.state.nouveaux = await this.compterNonVus();
        });

        const bus = this.env.services.bus_service;
        if (bus) {
            bus.subscribe("erplibre_incoming_call", async () => {
                // On REDEMANDE le compte au serveur au lieu d'incrementer.
                // A la connexion, le bus rejoue les annonces manquees : un
                // increment aveugle les ajoutait au compte deja renvoye par
                // le serveur, et la pastille annoncait deux appels pour un.
                this.state.nouveaux = await this.compterNonVus();
                if (this.dropdown.isOpen) {
                    // Menu ouvert : l'utilisateur regarde la liste, donc il
                    // voit l'appel arriver — rien ne reste « non vu ».
                    this.state.nouveaux = 0;
                    this.orm
                        .call("res.users", "erplibre_call_mark_seen", [])
                        .catch(() => {});
                    this.charger();
                }
            });
        }
    }

    /** Appels entrants non consultes, selon le marque-page du serveur. */
    async compterNonVus() {
        try {
            return await this.orm.call("res.users", "erplibre_call_unseen", []);
        } catch {
            // La barre systeme se charge pour tout le monde : un utilisateur
            // sans droit sur les appels ne doit pas voir une erreur RPC a
            // chaque page.
            return 0;
        }
    }

    async charger() {
        this.state.chargement = true;
        try {
            this.state.calls = await this.orm.searchRead(
                "erplibre.mobile.call",
                [],
                [
                    "number",
                    "direction",
                    "source",
                    "state",
                    "duration_display",
                    "requested_at",
                    "partner_id",
                ],
                {limit: LIMITE, order: "id desc"}
            );
        } finally {
            this.state.chargement = false;
        }
    }

    async onBeforeOpen() {
        this.state.nouveaux = 0;
        // Ouvrir le menu vaut consultation, et cela doit survivre au
        // rechargement — sinon la pastille reapparaitrait indefiniment.
        this.orm.call("res.users", "erplibre_call_mark_seen", []).catch(() => {});
        return this.charger();
    }

    /** Icone d'un appel : le sens, et s'il a abouti. */
    icone(call) {
        if (call.state === "failed" || call.state === "expired") {
            return "fa-phone-square text-danger";
        }
        if (call.direction === "in") {
            return "fa-arrow-down text-success";
        }
        return "fa-arrow-up text-primary";
    }

    /**
     * L'heure d'un appel, dans le fuseau de qui regarde.
     *
     * `searchRead` renvoie la valeur brute telle qu'elle est stockee : de
     * l'UTC. Les vues d'Odoo convertissent d'elles-memes, pas un composant
     * qui lit l'ORM directement — d'ou des heures decalees ici alors que le
     * formulaire affichait juste. Sur un journal d'appels, un decalage de
     * quelques heures fait chercher un appel au mauvais moment de la journee.
     */
    heure(call) {
        if (!call.requested_at) {
            return "";
        }
        try {
            return formatDateTime(deserializeDateTime(call.requested_at));
        } catch {
            // Une valeur illisible ne doit pas vider la ligne : mieux vaut
            // afficher le brut que rien.
            return call.requested_at;
        }
    }

    libelle(call) {
        return call.partner_id ? call.partner_id[1] : call.number;
    }

    ouvrirAppel(call) {
        this.dropdown.close();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "erplibre.mobile.call",
            res_id: call.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    ouvrirContact(call, ev) {
        // Empeche l'ouverture de la fiche d'appel : depuis le menu, cliquer
        // un nom veut dire « montre-moi cette personne », pas « montre-moi
        // cet appel ».
        ev.stopPropagation();
        if (!call.partner_id) {
            return;
        }
        this.dropdown.close();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: call.partner_id[0],
            views: [[false, "form"]],
            target: "current",
        });
    }

    ouvrirTout() {
        this.dropdown.close();
        this.action.doAction(
            "erplibre_mobile_gateway.action_erplibre_mobile_call",
            {clearBreadcrumbs: true}
        );
    }

    get titre() {
        return _t("Appels de la passerelle");
    }
}

registry
    .category("systray")
    .add("erplibre_mobile_gateway.calls", {Component: CallSystray},
         {sequence: 25});
