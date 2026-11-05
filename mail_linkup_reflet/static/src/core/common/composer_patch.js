import {Composer} from "@mail/core/common/composer";

import {useEffect, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupCategoryIcon} from "./linkup_category_icon";
import {LinkupRefletComposer} from "./reflet_composer";

patch(Composer, {
    components: {
        ...Composer.components,
        LinkupCategoryIcon,
        LinkupRefletComposer,
    },
});

/**
 * The composer of a direct conversation of a LinkUp member carries the
 * reflection: the Reflection button, after the emoji button, shows or
 * hides the Help bar and its form above the composer. They are shown by
 * default. A message being edited, the chatter and the other kinds of
 * conversation keep the plain composer.
 *
 * The start rule of the conversation (`thread_model_patch.js`) applies to
 * every composer of Discuss and of the chat windows. In strict mode, until a
 * reflection is confirmed, a banner explains the rule in place of the text
 * field, with "Make a reflection" in a direct conversation; in incentive
 * mode, the banner sits above a composer that stays usable.
 */
patch(Composer.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupState = useState({open: true, focusRequest: 0});
        this.linkupRoot = useRef("composer");
        useEffect(
            (focusRequest) => {
                if (!focusRequest) {
                    return;
                }
                const root = this.linkupRoot.el;
                const target =
                    root?.querySelector(".o-linkup-HelpBar-category") ||
                    root?.querySelector(".o-linkup-RefletComposer");
                target?.focus();
            },
            () => [this.linkupState.focusRequest]
        );
    },

    get hasLinkupReflet() {
        const thread = this.thread;
        return Boolean(
            this.store.linkup_is_member &&
                thread?.model === "discuss.channel" &&
                thread.channel_type === "chat" &&
                !this.props.composer.message &&
                !this.env.inChatter
        );
    },

    /** `strict` or `incitative` while the start rule waits for a
     * confirmed reflection, `null` otherwise. */
    get linkupStartRule() {
        const thread = this.thread;
        if (
            !this.store.linkup_is_member ||
            thread?.model !== "discuss.channel" ||
            this.props.composer.message ||
            this.env.inChatter
        ) {
            return null;
        }
        if (thread.linkupStartRuleLocked) {
            return "strict";
        }
        if (thread.linkupStartRuleSuggested) {
            return "incitative";
        }
        return null;
    },

    /** The text field is replaced by the banner of the start rule. */
    get isLinkupLocked() {
        return this.linkupStartRule === "strict";
    },

    get linkupStartRuleTitle() {
        return this.isLinkupLocked
            ? _t("This conversation starts with a reflection")
            : _t("Start with a reflection of a real exchange");
    },

    get linkupStartRuleText() {
        return this.isLinkupLocked
            ? _t("Reflect an exchange you had in person. Free text opens once a reflection is confirmed.")
            : _t("Free text is open; a confirmed reflection creates the link.");
    },

    onClickLinkupReflet() {
        this.linkupState.open = !this.linkupState.open;
    },

    /** Open the Help bar and give it the focus. */
    onClickLinkupStart() {
        this.linkupState.open = true;
        this.linkupState.focusRequest++;
    },

    async sendMessage() {
        if (this.isLinkupLocked) {
            return;
        }
        return super.sendMessage(...arguments);
    },
});
