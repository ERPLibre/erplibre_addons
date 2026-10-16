// Copyright 2026 TechnoLibre inc. - Mathieu Benoit
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
/** @odoo-module **/

import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// La page vient en entier d'un seul appel : son contenu est en base, et le
// composant ne sait rien d'un projet en particulier.
export class DevopsGuide extends Component {
    static template = "devops_guide.Guide";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        // Le service de visite guidée est absent quand `web_tour` n'est pas
        // installé : le bouton de visite ne s'affiche alors pas, plutôt que
        // de faire échouer le montage du composant.
        this.tour = this.env.services.tour_service || null;
        this.state = useState({ page: null, loaded: false });

        onWillStart(async () => {
            const context = (this.props.action && this.props.action.context) || {};
            const page = await this.orm.call(
                "devops.guide",
                "get_page_from_context",
                [],
                { context }
            );
            for (const section of (page && page.sections) || []) {
                // `intro` arrive en chaîne : JSON ne transporte pas le
                // Markup de Python, et `t-out` échappe une chaîne nue.
                // Le champ est un Html déjà désinfecté côté serveur.
                section.intro = markup(section.intro || "");
            }
            this.state.page = page && page.title ? page : null;
            this.state.loaded = true;
        });
    }

    get canStartTour() {
        return Boolean(this.tour && this.state.page && this.state.page.tour_name);
    }

    openAction(xmlId) {
        if (xmlId) {
            this.action.doAction(xmlId);
        }
    }

    openUrl(url) {
        if (url) {
            window.open(url, "_blank");
        }
    }

    hasButton(card) {
        return Boolean(card.url || card.action_xmlid || card.count_model);
    }

    // Trois sources, dans l'ordre. Les trois vides : la carte n'a pas de
    // bouton, ce qui rend une étape de feuille de route. Le domaine arrive
    // déjà analysé du serveur.
    openCard(card) {
        if (card.url) {
            this.openUrl(card.url);
        } else if (card.action_xmlid) {
            this.openAction(card.action_xmlid);
        } else if (card.count_model) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: card.title,
                res_model: card.count_model,
                view_mode: "list,form",
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain: card.count_domain || [],
            });
        }
    }

    startTour() {
        if (this.canStartTour) {
            this.tour.startTour(this.state.page.tour_name, { mode: "manual" });
        }
    }
}

registry.category("actions").add("devops_guide.page", DevopsGuide);
