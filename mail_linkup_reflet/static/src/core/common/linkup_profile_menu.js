import {Component, useEffect, useExternalListener, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {user} from "@web/core/user";
import {useService} from "@web/core/utils/hooks";

/**
 * The entries of the menu of the avatar (LU-F-080), in their order. An
 * entry with `hint` has no screen yet: it shows, disabled, with the reason.
 *
 * @returns {{id: string, label: string, icon: string, hint?: string}[]}
 */
export function linkupProfileEntries() {
    const profile = _t("Comes with the profile of the member.");
    return [
        {id: "help", label: _t("Help"), icon: "fa-question-circle-o"},
        {id: "email", label: _t("Email"), icon: "fa-envelope-o"},
        {id: "phone", label: _t("Phone"), icon: "fa-phone", hint: profile},
        {id: "photo", label: _t("Photo"), icon: "fa-camera"},
        {id: "sounds", label: _t("Sounds and notifications"), icon: "fa-bell-o"},
        {id: "privacy", label: _t("Privacy"), icon: "fa-lock", hint: profile},
        {
            id: "data",
            label: _t("My data"),
            icon: "fa-database",
            hint: _t("Comes with the export and the deletion of your data."),
        },
        {id: "blocked", label: _t("Blocked members"), icon: "fa-ban"},
    ];
}

/**
 * The avatar of the member, whose double click opens the menu of their
 * settings, also opened by the "My profile" button next to it (LU-F-080):
 * Help, Email, Phone, Photo, Sounds and notifications, Privacy, My data,
 * Blocked members.
 *
 * Help opens the LinkUp help; Sounds and notifications and Blocked members
 * open it on their section. Email and Photo open the preferences of the
 * user, where both are changed. Phone, Privacy and My data have no screen
 * yet: they are disabled, each with the reason, and lead nowhere.
 *
 * The menu is a `menu` walked with the arrow keys, `Home` and `End`;
 * opening it gives the focus to its first entry, `Escape` or a click
 * outside closes it, and `Escape` gives the focus back to "My profile".
 *
 * @typedef {Object} Props
 * @property {string} [avatarUrl]
 * @property {boolean} [highlighted] someone puts the member in the light
 * @extends {Component<Props, Env>}
 */
export class LinkupProfileMenu extends Component {
    static template = "mail_linkup_reflet.LinkupProfileMenu";
    static props = ["avatarUrl?", "highlighted?"];

    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
        this.root = useRef("root");
        this.menuRef = useRef("menu");
        this.toggleRef = useRef("toggle");
        this.state = useState({open: false});
        useExternalListener(window, "click", (ev) => {
            if (this.state.open && !this.root.el?.contains(ev.target)) {
                this.state.open = false;
            }
        });
        useEffect(
            (open) => {
                if (open) {
                    this.items()[0]?.focus();
                }
            },
            () => [this.state.open]
        );
    }

    get entries() {
        return linkupProfileEntries();
    }

    get avatarTitle() {
        return _t("Double-click: my settings");
    }

    /** @returns {HTMLElement[]} the entries of the open menu */
    items() {
        return [...(this.menuRef.el?.querySelectorAll("[role='menuitem']") || [])];
    }

    open() {
        this.state.open = true;
    }

    toggle() {
        this.state.open = !this.state.open;
    }

    close() {
        this.state.open = false;
        this.toggleRef.el?.focus();
    }

    /** @param {KeyboardEvent} ev */
    onMenuKeydown(ev) {
        const items = this.items();
        const index = items.indexOf(document.activeElement);
        let next = null;
        switch (ev.key) {
            case "ArrowDown":
                next = items[(index + 1) % items.length];
                break;
            case "ArrowUp":
                next = items[(index - 1 + items.length) % items.length];
                break;
            case "Home":
                next = items[0];
                break;
            case "End":
                next = items[items.length - 1];
                break;
            case "Escape":
                ev.preventDefault();
                ev.stopPropagation();
                this.close();
                return;
            default:
                return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        next?.focus();
    }

    /** @param {{id: string, hint?: string}} entry */
    async choose(entry) {
        if (entry.hint) {
            return;
        }
        this.state.open = false;
        switch (entry.id) {
            case "help":
                return this.action.doAction("mail_linkup_reflet.action_linkup_help");
            case "sounds":
                return this.openHelpSection("settings");
            case "blocked":
                return this.openHelpSection("blocked");
            case "email":
            case "photo":
                return this.openPreferences();
        }
    }

    /** @param {"settings"|"blocked"} section */
    openHelpSection(section) {
        return this.action.doAction("mail_linkup_reflet.action_linkup_help", {
            additionalContext: {linkup_section: section},
        });
    }

    /** The preferences of the user, as the user menu opens them. */
    async openPreferences() {
        const action = await this.orm.call("res.users", "action_get");
        return this.action.doAction({...action, res_id: user.userId});
    }
}
