import {Component, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";

import {linkupConsentLabels, linkupSensitiveHelp} from "./linkup_community_texts";

/**
 * The banners of the Reflet view that stand between a new member and their
 * first reflection:
 *
 * - the consents their account still needs (`linkup_consent_missing`,
 *   LU-F-111), one checkbox each, none checked in advance, accepted
 *   together through `linkup.consent.action_grant`;
 * - the verification of their address (`linkup_email_verified`, LU-F-110
 *   RM3), with "Send the link again" (`linkup_resend_verification`),
 *   refused with `linkup.rate_limited` a moment after the previous one.
 *
 * The server refuses every exchange while either one is pending; the
 * banners only say why, and the bus takes them away once done.
 */
export class LinkupCommunityNotice extends Component {
    static template = "mail_linkup_community.LinkupCommunityNotice";
    static components = {LinkupErrorAlert};
    static props = {};

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.orm = useService("orm");
        this.state = useState({checked: {}, busy: false, error: null, notice: ""});
    }

    get missing() {
        return this.store.linkup_is_member ? this.store.linkup_consent_missing || [] : [];
    }

    get unverified() {
        return Boolean(this.store.linkup_is_member) && this.store.linkup_email_verified === false;
    }

    /** @param {string} purpose */
    consentLabel(purpose) {
        return linkupConsentLabels()[purpose] || purpose;
    }

    get sensitiveHelp() {
        return linkupSensitiveHelp();
    }

    get canAccept() {
        return this.missing.length > 0 && this.missing.every((purpose) => this.state.checked[purpose]);
    }

    /**
     * @param {string} purpose
     * @param {boolean} value
     */
    toggle(purpose, value) {
        this.state.checked[purpose] = value;
    }

    /** @param {Function} call */
    async run(call) {
        if (this.state.busy) {
            return null;
        }
        this.state.busy = true;
        this.state.error = null;
        this.state.notice = "";
        try {
            return await call();
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    async accept() {
        if (!this.canAccept) {
            return;
        }
        const missing = [...this.missing];
        const result = await this.run(() => this.orm.silent.call("linkup.consent", "action_grant", [missing]));
        if (result) {
            this.store.linkup_consent_missing = [];
            this.state.notice = _t("Thank you: your consents are recorded.");
        }
    }

    async resend() {
        const result = await this.run(() => this.orm.silent.call("res.users", "linkup_resend_verification", []));
        if (result?.verified) {
            this.store.linkup_email_verified = true;
        } else if (result) {
            this.state.notice = _t("A new link was sent to %(email)s.", {email: result.email});
        }
    }
}
