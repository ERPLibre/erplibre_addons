import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";

import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupReflet} from "@mail_linkup_reflet/core/common/linkup_reflet_model";
import {LinkupRefletCard} from "@mail_linkup_reflet/core/common/reflet_card";

/**
 * A reflection whose texts are erased for good (`content_removed`: the
 * deletion of an account, a retention period, or its recipient) comes
 * without them: the card says "Content removed" in their place
 * (LU-F-117 RM2, RM4).
 */
patch(LinkupReflet.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {boolean} */
        this.content_removed = false;
    },
});

/**
 * The recipient of a rejected or inaccurate reflection erases its texts,
 * which lend them words they did not say (LU-F-117 RM4), after a
 * confirmation; `linkup.reflet.action_erase_content` checks it again.
 */
patch(LinkupRefletCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupDialog = useService("dialog");
        this.linkupNotification = useService("notification");
    },

    get canEraseContent() {
        const reflet = this.reflet;
        return Boolean(
            this.props.interactive &&
                !this.props.compact &&
                !this.props.preview &&
                reflet.id &&
                reflet.kind === "initial" &&
                this.role === "recipient" &&
                ["rejected", "inaccurate"].includes(reflet.state) &&
                !reflet.content_removed &&
                !reflet.moderation_hidden
        );
    },

    eraseContent() {
        this.linkupDialog.add(ConfirmationDialog, {
            title: _t("Erase this reflection?"),
            body: _t("Its texts are erased for good, for both of you; the card stays, marked “Content removed”."),
            confirmLabel: _t("Erase"),
            confirm: async () => {
                try {
                    await this.orm.silent.call("linkup.reflet", "action_erase_content", [[this.reflet.id]]);
                } catch (error) {
                    const info = linkupErrorInfo(error);
                    if (!info) {
                        throw error;
                    }
                    const message = info.code === "linkup.unavailable" ? error.data?.message : "";
                    this.linkupNotification.add(message || info.message, {type: "warning"});
                }
            },
            cancel: () => {},
        });
    },
});
