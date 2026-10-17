// Copyright 2026 TechnoLibre inc. - Mathieu Benoit
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
/** @odoo-module **/

import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

// La page vient en entier d'un seul appel : son contenu est en base, et le
// composant ne sait rien d'un projet en particulier.
export class DevopsGuide extends Component {
    static template = "devops_guide.Guide";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        // Le service de visite guidée peut manquer (`web_tour` absent du
        // paquet chargé) : le bouton de visite ne s'affiche alors pas,
        // plutôt que de faire échouer le montage du composant.
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

    // Un nom de visite absent du registre JS ne lance rien : `startTour`
    // du service rend sans erreur ni effet. C'est le cas d'une visite
    // déclarée seulement dans `web.assets_tests`, chargé en mode test
    // seulement. Le bouton ne s'affiche donc que si la visite est connue,
    // plutôt que de rester muet au clic.
    canStartTour(name) {
        return Boolean(
            this.tour && name && registry.category("web_tour.tours").contains(name)
        );
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

    // Une cible SANS libellé ne rend aucun bouton : un bouton vide ne
    // portant que sa flèche n'apprend rien sur ce qu'il ouvre.
    hasButton(card) {
        const target = card.url || card.action_xmlid || card.count_model;
        return Boolean(target && card.action_label);
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
                // Les quatre vues : un décompte s'inspecte en liste, mais
                // se lit aussi par axe. Odoo engendre une vue graphique ou
                // croisée que le modèle ne déclare pas.
                view_mode: "list,form,graph,pivot",
                views: [
                    [false, "list"],
                    [false, "form"],
                    [false, "graph"],
                    [false, "pivot"],
                ],
                domain: card.count_domain || [],
            });
        }
    }

    // Le mode manuel du service active l'Onboarding de l'utilisateur EN
    // BASE (`switch_tour_enabled(true)`) quand il était inactif. Laissé
    // ainsi, chaque chargement suivant lancerait les visites natives
    // d'Odoo non consommées, et la fin de cette visite enchaînerait sur la
    // prochaine (`consume` rend la suivante tant que l'Onboarding est
    // actif). L'état d'origine se lit dans `session.tour_enabled`, valeur
    // du chargement de la page que le service ne modifie pas, et il est
    // rétabli en base sitôt la visite démarrée.
    //
    // La visite en cours n'en souffre pas tant que la page ne se recharge
    // pas : son état vit dans le localStorage (`tourState`) et le pointeur
    // dans le service, qui garde sa propre copie de l'Onboarding pour la
    // page. Un rechargement, lui, l'efface : au démarrage, le service ne
    // reprend une visite manuelle que si l'Onboarding est actif en base.
    // D'où `redirect: false`, et la règle qu'une visite lancée du guide
    // navigue par les menus, sans `url`, `goToUrl` ni `expectUnloadPage`.
    async startTour(name) {
        if (!this.canStartTour(name)) {
            return;
        }
        const restoreOnboarding = !session.tour_enabled && !session.is_public;
        await this.tour.startTour(name, { mode: "manual", redirect: false });
        if (restoreOnboarding) {
            await this.orm.call("res.users", "switch_tour_enabled", [false]);
        }
    }

    // Le formulaire du requis, dans le fil d'Ariane : le retour ramène à
    // la page du guide.
    openRequirement(requirement) {
        if (requirement && requirement.id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "devops.requirement",
                res_id: requirement.id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    // L'action vient du serveur (`action_open_guide`), qui sait seul
    // quelle page détaillée le requis désigne.
    async openGuide(requirement) {
        if (requirement && requirement.has_guide) {
            const action = await this.orm.call(
                "devops.requirement",
                "action_open_guide",
                [[requirement.id]]
            );
            await this.action.doAction(action);
        }
    }
}

registry.category("actions").add("devops_guide.page", DevopsGuide);
