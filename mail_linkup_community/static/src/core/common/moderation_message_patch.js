import {messageActionsRegistry} from "@mail/core/common/message_actions";
import {Message} from "@mail/core/common/message_model";

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupReflet} from "@mail_linkup_reflet/core/common/linkup_reflet_model";

import {LinkupReportDialog} from "./linkup_report_dialog";

/**
 * A message the moderation hid (`mail.message.linkup_hidden`, LU-F-116
 * RM2) comes without its body nor its attachments: the thread draws
 * "Message hidden by the moderation" in their place. It is neither empty,
 * edited nor reacted to.
 */
patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {boolean} */
        this.linkup_hidden = false;
    },

    computeIsEmpty() {
        return super.computeIsEmpty() && !this.linkup_hidden;
    },

    get hasTextContent() {
        return !this.linkup_hidden && super.hasTextContent;
    },

    get editable() {
        return !this.linkup_hidden && super.editable;
    },

    canAddReaction() {
        return !this.linkup_hidden && super.canAddReaction(...arguments);
    },
});

// A card whose texts the moderation hid says so in their place.
patch(LinkupReflet.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {boolean} */
        this.moderation_hidden = false;
    },
});

// "Report" in the menu of a message of another person (LU-F-114 RM1); the
// card of a reflection holds its own.
messageActionsRegistry.add("linkup-report", {
    condition: (component) => {
        const message = component.props.message;
        return Boolean(
            component.store.linkup_is_member &&
                message.thread?.model === "discuss.channel" &&
                message.persistent &&
                message.message_type === "comment" &&
                message.author &&
                !message.isSelfAuthored &&
                !message.linkup_reflet_id &&
                !message.linkup_hidden
        );
    },
    icon: "fa fa-flag",
    title: _t("Report"),
    onClick: (component) => {
        const message = component.props.message;
        component.dialog.add(LinkupReportDialog, {
            messageId: message.id,
            name: message.author.name,
        });
    },
    sequence: 120,
});
