import {Component, onWillStart, useEffect, useRef, useState} from "@odoo/owl";

import {browser} from "@web/core/browser/browser";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {deserializeDateTime, formatDate, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {imageUrl} from "@web/core/utils/urls";

import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupGuideButton} from "@mail_linkup_reflet/core/common/linkup_guide";

import {linkupConsentLabels, linkupSensitiveHelp} from "../../core/common/linkup_community_texts";
import {LinkupProfileSafety} from "./linkup_profile_safety";

/** The largest photo the profile sends, as the server checks it. */
const PHOTO_MAX_BYTES = 5 * 1024 * 1024;

/**
 * The profile of the member (client action `linkup.profile`, LU-F-082):
 *
 * - identity: the pseudonym (LU-F-113), the photo, seen by the linked
 *   members only (Q-27), and the language;
 * - contact: the address, nobody else sees it, with its verification and
 *   "Send the link again", and the phone, optional;
 * - privacy: who may send a first reflection (LU-F-016 RM7), the personal
 *   code to give (LU-F-112 RM2), the consents with the date and version
 *   of the last decision (LU-F-111), and what the signup declared;
 * - safety: the decisions of the moderation about the member, the reports
 *   they made and the members they block (`LinkupProfileSafety`);
 * - data: the download of everything LinkUp keeps about the member
 *   (`/linkup/v1/me/export`, LU-F-117 RM1), and the deletion of the
 *   account after a delay of grace, cancelled meanwhile (RM2, RM3).
 *
 * Every write goes through `res.users.linkup_profile_write` and
 * `linkup.consent.action_grant` / `action_revoke`, which check it again;
 * a refusal shows the message of its `linkup_code`. The action context
 * `linkup_section` (`identity`, `contact`, `privacy`, `safety` or `data`) gives the focus to
 * the heading of that section, as the menu of the avatar opens it.
 */
export class LinkupProfile extends Component {
    static template = "mail_linkup_community.LinkupProfile";
    static components = {LinkupErrorAlert, LinkupGuideButton, LinkupProfileSafety};
    static props = ["*"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.store = useState(useService("mail.store"));
        this.root = useRef("root");
        this.photoInput = useRef("photoInput");
        this.state = useState({
            loaded: false,
            loadError: false,
            profile: null,
            form: {name: "", email: "", phone: "", lang: ""},
            busy: false,
            error: null,
            errorSection: null,
            notice: "",
            noticeSection: null,
            photoVersion: 0,
        });
        onWillStart(() => this.load());
        useEffect(
            (loaded) => {
                const section = this.props.action?.context?.linkup_section;
                const heading = loaded && section && this.root.el?.querySelector(`#o-linkup-Profile-${section}Title`);
                if (heading) {
                    heading.scrollIntoView?.({block: "start"});
                    heading.focus();
                }
            },
            () => [this.state.loaded]
        );
    }

    async load() {
        try {
            this.apply(await this.orm.silent.call("res.users", "linkup_profile_info", []));
            this.state.loaded = true;
        } catch {
            this.state.loadError = true;
        }
    }

    /** @param {Object} profile as `linkup_profile_info` gives it */
    apply(profile) {
        this.state.profile = profile;
        Object.assign(this.state.form, {
            name: profile.name,
            email: profile.email,
            phone: profile.phone,
            lang: profile.lang,
        });
        this.store.linkup_email_verified = profile.email_verified;
    }

    get profile() {
        return this.state.profile;
    }

    get photoUrl() {
        return imageUrl("res.partner", this.profile.partner_id, "avatar_128", {
            unique: this.state.photoVersion || "",
        });
    }

    get scopes() {
        return [
            {value: "nobody", label: _t("Nobody")},
            {value: "code", label: _t("People who have my code")},
            {value: "email_or_code", label: _t("People who know my email address or have my code")},
        ];
    }

    get ageLabel() {
        const labels = {
            "18_24": _t("18 to 24"),
            "25_34": _t("25 to 34"),
            "35_44": _t("35 to 44"),
            "45_54": _t("45 to 54"),
            "55_64": _t("55 to 64"),
            "65_plus": _t("65 and over"),
        };
        return labels[this.profile.age_bracket] || _t("Not declared");
    }

    get residenceLabel() {
        return this.profile.jurisdiction === "CA" ? _t("Canada") : _t("Not declared");
    }

    /** @param {Object} consent a row of `linkup_consents_info` */
    consentLabel(consent) {
        return linkupConsentLabels()[consent.purpose] || consent.label;
    }

    /** @param {Object} consent */
    consentDetail(consent) {
        if (!consent.date) {
            return _t("Never given");
        }
        const date = formatDateTime(deserializeDateTime(consent.date));
        return consent.granted
            ? _t("Given on %(date)s, version %(version)s", {date, version: consent.version})
            : _t("Withdrawn on %(date)s", {date});
    }

    get sensitiveHelp() {
        return linkupSensitiveHelp();
    }

    /**
     * Run a write of one section, showing its message or its refusal in
     * that section.
     *
     * @param {string} section
     * @param {Function} call returns the new profile, or another value
     * @param {string} [notice]
     */
    async run(section, call, notice = _t("Saved.")) {
        if (this.state.busy) {
            return null;
        }
        this.state.busy = true;
        this.state.error = null;
        this.state.notice = "";
        try {
            const result = await call();
            this.state.notice = notice;
            this.state.noticeSection = section;
            return result;
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
            this.state.errorSection = section;
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    /** @param {Object} vals */
    write(section, vals, notice) {
        return this.run(
            section,
            async () => {
                const profile = await this.orm.silent.call("res.users", "linkup_profile_write", [vals]);
                this.apply(profile);
                return profile;
            },
            notice
        );
    }

    saveIdentity() {
        const form = this.state.form;
        return this.write("identity", {name: form.name, lang: form.lang});
    }

    async saveContact() {
        const form = this.state.form;
        const changed = form.email.trim() !== this.profile.email;
        await this.write(
            "contact",
            {email: form.email.trim(), phone: form.phone},
            changed ? _t("Saved. Click the link sent to your new address to confirm it.") : _t("Saved.")
        );
    }

    /** @param {string} scope */
    setScope(scope) {
        return this.write("privacy", {first_reflet_scope: scope});
    }

    choosePhoto() {
        this.photoInput.el?.click();
    }

    /** @param {Event} ev */
    async onPhotoChange(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (file.size > PHOTO_MAX_BYTES || !file.type.startsWith("image/")) {
            this.state.error = {
                code: "linkup.validation",
                field: "image",
                message: _t("Choose a photo in a common format, of at most 5 MB."),
            };
            this.state.errorSection = "identity";
            return;
        }
        const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        const result = await this.write("identity", {image: data}, _t("Photo changed."));
        if (result) {
            this.state.photoVersion = Date.now();
        }
    }

    async removePhoto() {
        const result = await this.write("identity", {image: false}, _t("Photo removed."));
        if (result) {
            this.state.photoVersion = Date.now();
        }
    }

    resendVerification() {
        return this.run(
            "contact",
            () => this.orm.silent.call("res.users", "linkup_resend_verification", []),
            _t("A new link was sent to your address.")
        );
    }

    async copyCode() {
        try {
            await browser.navigator.clipboard.writeText(this.profile.code);
            this.state.notice = _t("Code copied.");
        } catch {
            this.state.notice = _t("Select the code and copy it.");
        }
        this.state.noticeSection = "privacy";
    }

    async newCode() {
        const code = await this.run(
            "privacy",
            () => this.orm.silent.call("res.users", "linkup_regenerate_code", []),
            _t("New code: the former one no longer works.")
        );
        if (code) {
            this.profile.code = code;
        }
    }

    /**
     * Grant or withdraw a consent, at once.
     *
     * @param {Object} consent
     * @param {boolean} granted
     */
    async toggleConsent(consent, granted) {
        const method = granted ? "action_grant" : "action_revoke";
        const consents = await this.run(
            "privacy",
            () => this.orm.silent.call("linkup.consent", method, [[consent.purpose]]),
            granted ? _t("Consent given.") : _t("Consent withdrawn.")
        );
        if (consents) {
            this.profile.consents = consents;
        }
    }

    /** The address that downloads the data of the member, as a file. */
    get exportUrl() {
        return "/linkup/v1/me/export";
    }

    /** The day the account is erased, once its deletion is asked. */
    get deletionText() {
        const date = this.profile.deletion_date;
        if (!date) {
            return "";
        }
        return _t("Your account will be deleted on %(date)s. Until then, you can cancel.", {
            date: formatDate(deserializeDateTime(date)),
        });
    }

    /** @param {Object} info as `linkup_request_deletion` returns it */
    applyDeletion(info) {
        Object.assign(this.profile, {
            deletion_requested: info.deletion_requested,
            deletion_date: info.deletion_date,
            deletion_grace_days: info.deletion_grace_days,
        });
    }

    requestDeletion() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete my account?"),
            body: _t(
                "In %(days)s days, your account is erased: your pseudonym becomes “Deleted member”, your address, phone and photo leave, and the texts of your reflections and messages are erased. Your points stay, without your name, in the energy of the links of the others. Until then, you can cancel.",
                {days: this.profile.deletion_grace_days}
            ),
            confirmLabel: _t("Delete my account"),
            confirm: () =>
                this.run(
                    "data",
                    async () => {
                        this.applyDeletion(await this.orm.silent.call("res.users", "linkup_request_deletion", []));
                    },
                    _t("Deletion requested.")
                ),
            cancel: () => {},
        });
    }

    async cancelDeletion() {
        await this.run(
            "data",
            async () => {
                this.applyDeletion(await this.orm.silent.call("res.users", "linkup_cancel_deletion", []));
            },
            _t("Deletion cancelled: your account stays as it is.")
        );
    }

    /** @param {string} section */
    errorIn(section) {
        return this.state.errorSection === section ? this.state.error : null;
    }

    /** @param {string} section */
    noticeIn(section) {
        return this.state.noticeSection === section ? this.state.notice : "";
    }
}

registry.category("actions").add("linkup.profile", LinkupProfile);
