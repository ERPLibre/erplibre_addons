import {Component, markup, onWillStart, useEffect, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

import {LinkupCategoryIcon} from "@mail_linkup_reflet/core/common/linkup_category_icon";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";

/**
 * The settings of `res.users.settings` the help page lets a member change,
 * in their order on the page.
 */
function linkupSettingLabels() {
    return [
        ["linkup_sound_enabled", _t("Sounds of a reflection sent and received")],
        ["linkup_reward_sounds_enabled", _t("Sound of a confirmed reflection")],
        ["linkup_notify_reflet_received", _t("Notify a received reflection")],
        ["linkup_notify_confirmed", _t("Notify a confirmed reflection")],
        ["linkup_notify_highlight", _t("Notify when someone adds to my happiness")],
        ["linkup_notify_invitation_accepted", _t("Notify when a person I invited accepts")],
        ["linkup_notify_discreet", _t("Discreet notifications: “New LinkUp event”, without any name")],
    ];
}

/**
 * The LinkUp help (client action `linkup.help`, LU-F-081 RM1): the twelve
 * categories with their pictogram, definition, what to say and not to say
 * and starter, the non-violent communication group first; the sounds and
 * notifications of the member, written to `res.users.settings`; and
 * "Replay the tour", which opens Discuss and starts the first-use tour
 * again; and the members the member blocks, each with "Unblock"
 * (`linkup.block`, LU-F-115 RM3). The texts come from `linkup.category`, in
 * the language of the member. The user menu and the LinkUp menu of Discuss
 * open it, and the menu of the avatar of the member opens it on one of its
 * sections: the action context `linkup_section` (`settings` or `blocked`)
 * gives the focus to the heading of that section once it is drawn.
 */
export class LinkupHelp extends Component {
    static template = "mail_linkup_reflet.LinkupHelp";
    static components = {LinkupCategoryIcon};
    static props = ["*"];

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.orm = useService("orm");
        this.action = useService("action");
        this.tour = useService("linkup.tour");
        this.state = useState({
            loaded: false,
            loadError: false,
            saving: false,
            blocked: [],
            blockedBusy: false,
            blockedError: "",
        });
        this.root = useRef("root");
        useEffect(
            (loaded) => {
                const section = this.props.action?.context?.linkup_section;
                const heading = loaded && section && this.root.el?.querySelector(`#o-linkup-Help-${section}Title`);
                if (heading) {
                    heading.scrollIntoView?.({block: "start"});
                    heading.focus();
                }
            },
            () => [this.state.loaded]
        );
        onWillStart(async () => {
            try {
                await Promise.all([this.store.fetchLinkupCategories(), this.loadBlocked()]);
                this.state.loaded = true;
            } catch {
                this.state.loadError = true;
            }
        });
    }

    async loadBlocked() {
        this.state.blocked = await this.orm.silent.call("linkup.block", "linkup_blocked_members", []);
    }

    /** @param {{name: string}} member */
    unblockLabel(member) {
        return _t("Unblock %(name)s", {name: member.name});
    }

    /**
     * Lift the block on a member, then read the list again.
     *
     * @param {{user_id: number}} member
     */
    async unblock(member) {
        if (this.state.blockedBusy) {
            return;
        }
        this.state.blockedBusy = true;
        this.state.blockedError = "";
        try {
            await this.orm.silent.call("linkup.block", "action_unblock", [], {user_id: member.user_id});
            await this.loadBlocked();
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.blockedError = info.message;
        } finally {
            this.state.blockedBusy = false;
        }
    }

    get cnvCategories() {
        return this.store.linkupCategories.filter((category) => category.is_cnv);
    }

    get otherCategories() {
        return this.store.linkupCategories.filter((category) => !category.is_cnv);
    }

    get settings() {
        return linkupSettingLabels().map(([field, label]) => ({
            field,
            label,
            checked: Boolean(this.store.settings?.[field]),
        }));
    }

    /** @param {import("models").LinkupCategory} category */
    definition(category) {
        return category.definition ? markup(category.definition) : "";
    }

    get intro() {
        return _t(
            "A conversation starts with the reflection of a real exchange: choose what you were told about, then rephrase it without judgement. Each category below explains what to say and what not to say."
        );
    }

    get doLabel() {
        return _t("What to say:") + " ";
    }

    get dontLabel() {
        return _t("What not to say:") + " ";
    }

    get starterLabel() {
        return _t("Starter:") + " ";
    }

    /**
     * Write one setting of the member, then keep the value the server
     * returns.
     *
     * @param {string} field
     * @param {boolean} value
     */
    async toggleSetting(field, value) {
        const settings = this.store.settings;
        if (!settings?.id) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call("res.users.settings", "set_res_users_settings", [[settings.id]], {
                new_settings: {[field]: value},
            });
            settings[field] = field in (result || {}) ? result[field] : value;
        } finally {
            this.state.saving = false;
        }
    }

    async replayTour() {
        await this.action.doAction("mail.action_discuss");
        this.tour.start();
    }
}

registry.category("actions").add("linkup.help", LinkupHelp);

registry.category("user_menuitems").add("linkup_help", (env) => ({
    type: "item",
    id: "linkup_help",
    description: _t("LinkUp help"),
    callback: () => env.services.action.doAction("mail_linkup_reflet.action_linkup_help"),
    show: () => Boolean(env.services["mail.store"]?.linkup_is_member),
    sequence: 5,
}));
