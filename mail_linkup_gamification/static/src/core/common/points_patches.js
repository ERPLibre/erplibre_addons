import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";
import {formatInteger} from "@web/views/fields/formatters";

import {LinkupGuideSheet} from "@mail_linkup_reflet/core/common/linkup_guide";
import {LinkupPanel} from "@mail_linkup_reflet/core/common/linkup_panel";
import {LinkupProfileMenu} from "@mail_linkup_reflet/core/common/linkup_profile_menu";
import {LinkupRefletActions} from "@mail_linkup_reflet/core/common/reflet_actions";
import {LinkupHelp} from "@mail_linkup_reflet/views/help/linkup_help";
import {LinkupRefletView} from "@mail_linkup_reflet/views/reflet_view/reflet_view";

import {LinkupEnergy} from "./linkup_energy";
import {linkupSignedPoints} from "./points_service";

// An action on a reflection reads the points it paid at once, without
// waiting for the bus (`linkup.points`).
patch(LinkupRefletActions.prototype, {
    async call() {
        const done = await super.call(...arguments);
        if (done) {
            await this.env.services["linkup.points"].catchUp();
        }
        return done;
    },
});

/**
 * The texts of the guide for the elements of the points, by the value of
 * their `data-linkup-guide`.
 */
function linkupPointsGuideTexts() {
    return {
        "points-energy": {
            title: _t("My energy"),
            text: _t(
                "The total of the points your links earned you: confirmed reflections, exact reformulations, calls. It is neither a number of friends nor a number of messages."
            ),
            behavior: _t("Outside the guide, this button opens “My points”."),
        },
        "points-balance": {
            title: _t("My energy"),
            text: _t("Your karma: the sum of every line of your history."),
            behavior: _t("It rises with each confirmed exchange and falls with a rejected reflection."),
        },
        "points-rank": {
            title: _t("Rank"),
            text: _t("Your rank follows your energy; the bar shows the way to the next one."),
            behavior: _t("A new rank is announced on the screen, never by email."),
        },
        "points-badges": {
            title: _t("Badges"),
            text: _t("First reflection, first link, ten links, first guess, first call."),
            behavior: _t("LinkUp gives them by itself, once each."),
        },
        "points-filters": {
            title: _t("Filters"),
            text: _t("Keep the lines of one event, or those shared with one person."),
            behavior: _t("Outside the guide, choosing a value reads the history again."),
        },
        "points-history": {
            title: _t("History of my points"),
            text: _t(
                "Each line: its date, its event, the person it was shared with and its points. A line at 0 tells why it paid nothing."
            ),
            behavior: _t("Only your own lines show here, never those of another member."),
        },
        "points-scale": {
            title: _t("Point scale"),
            text: _t("What each event earns, as the LinkUp administrator set it."),
            behavior: _t("Outside the guide, this button unfolds the scale."),
        },
    };
}

/**
 * The sentence on the points that ends the behaviour of an element of the
 * core, or `""` when the rule pays nothing.
 *
 * @param {string} key the `data-linkup-guide` of the element
 * @param {Object<string, number>} rules the points of the rules, by code
 * @returns {string}
 */
export function linkupPointsGuideSentence(key, rules) {
    switch (key) {
        case "reflet-confirm":
            if (!rules.reflect_confirmed) {
                return "";
            }
            return rules.reflect_sent
                ? _t("Each of you earns %(confirmed)s points, and the author %(sent)s more for the reflection.", {
                      confirmed: linkupSignedPoints(rules.reflect_confirmed),
                      sent: linkupSignedPoints(rules.reflect_sent),
                  })
                : _t("Each of you earns %(confirmed)s points.", {
                      confirmed: linkupSignedPoints(rules.reflect_confirmed),
                  });
        case "reflet-reject":
            return rules.reflect_rejected < 0
                ? _t("The author loses %(points)s points.", {points: formatInteger(-rules.reflect_rejected)})
                : "";
        case "guess-submit":
            return rules.theme_guessed
                ? _t("A right guess earns %(points)s points to each of you.", {
                      points: linkupSignedPoints(rules.theme_guessed),
                  })
                : "";
    }
    return "";
}

patch(LinkupGuideSheet.prototype, {
    get texts() {
        const own = linkupPointsGuideTexts()[this.key];
        if (own) {
            return own;
        }
        const texts = super.texts;
        if (!texts || this.store.settings?.linkup_hide_gamification) {
            return texts;
        }
        const sentence = linkupPointsGuideSentence(this.key, this.store.linkup_points_rules || {});
        return sentence ? {...texts, behavior: `${texts.behavior} ${sentence}`} : texts;
    },
});

// The setting that hides the points, with the sounds and notifications.
patch(LinkupHelp.prototype, {
    get settings() {
        return [
            ...super.settings,
            {
                field: "linkup_hide_gamification",
                label: _t("Hide the points and their animations"),
                checked: Boolean(this.store.settings?.linkup_hide_gamification),
            },
        ];
    },
});

// The energy of the member and of the link in the LinkUp panel.
LinkupPanel.components = {...LinkupPanel.components, LinkupEnergy};
patch(LinkupPanel.prototype, {
    get linkupPointsHidden() {
        return Boolean(this.store.settings?.linkup_hide_gamification);
    },

    /** The energy of the link as the member reads it (LU-F-071 RM2). */
    get linkEnergyLabel() {
        return _t("Energy of the link: %(points)s points", {
            points: formatInteger(this.state.info?.link_energy || 0),
        });
    },
});

// "My points" ends the menu of the avatar (LU-F-080), even with the points
// hidden: their history stays reachable.
patch(LinkupProfileMenu.prototype, {
    get entries() {
        return [
            ...super.entries,
            {
                id: "points",
                label: _t("My points"),
                icon: "fa-bolt",
                action: "mail_linkup_gamification.action_linkup_my_points",
            },
        ];
    },
});

// The energy of the member next to their avatar in the Reflet view.
LinkupRefletView.components = {...LinkupRefletView.components, LinkupEnergy};
