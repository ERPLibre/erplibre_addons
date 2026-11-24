import {_t} from "@web/core/l10n/translation";
import {browser} from "@web/core/browser/browser";
import {patch} from "@web/core/utils/patch";

import {linkupFieldMessage} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupRefletView} from "@mail_linkup_reflet/views/reflet_view/reflet_view";

/**
 * NewLink reaches a person in one of three ways (LU-F-020, LU-F-112 RM2):
 *
 * - `email`: LinkUp sends the signup link, or reaches the member who holds
 *   the address inside LinkUp;
 * - `phone`: LinkUp sends nothing (Q-25); once sent, the view shows the
 *   share link with "Copy the link", and the member sends it themself;
 * - `code`: the personal code a member gave; the invitation reaches that
 *   member inside LinkUp.
 *
 * The channel is a group of radio buttons in the first step; the preview
 * and the last step follow it.
 */
patch(LinkupRefletView.prototype, {
    startNewlink(category) {
        super.startNewlink(category);
        if (this.state.newlink) {
            Object.assign(this.state.newlink, {channel: "email", phone: "", code: "", copied: false});
        }
    },

    /** @param {"email"|"phone"|"code"} channel */
    setNewlinkChannel(channel) {
        this.state.newlink.channel = channel;
        this.state.error = null;
    },

    get newlinkChannel() {
        return this.state.newlink?.channel || "email";
    },

    get sendTarget() {
        const newlink = this.state.newlink;
        if (newlink && newlink.channel === "phone") {
            return {invite: {phone: newlink.phone.trim(), name: newlink.name.trim()}, name: this.newlinkName};
        }
        if (newlink && newlink.channel === "code") {
            return {invite: {code: newlink.code.trim(), name: newlink.name.trim()}, name: this.newlinkName};
        }
        return super.sendTarget;
    },

    /** From the contact to the card: a plausible number or code; the server checks it again. */
    newlinkNext() {
        const channel = this.newlinkChannel;
        if (channel === "email") {
            return super.newlinkNext();
        }
        this.state.error = null;
        const value = this.state.newlink[channel].trim();
        const valid = channel === "phone" ? /^\+?[\d\s().-]{7,25}$/.test(value) : /^[A-Za-z0-9\s-]{10,14}$/.test(value);
        if (!valid) {
            this.state.error = {code: "linkup.validation", field: channel, message: linkupFieldMessage(channel)};
            return;
        }
        this.state.newlink.step = "reflet";
        if (this.state.formOpen) {
            this.requestFocus("field");
        }
    },

    sentNotice(target, result) {
        if (target.invite?.phone) {
            return _t("Share link ready: send it yourself.");
        }
        if (target.invite?.code) {
            return _t("Invitation sent.");
        }
        return super.sentNotice(target, result);
    },

    get newlinkShareMessage() {
        return _t("%(name)s would like to make you a reflection on LinkUp: %(url)s", {
            name: this.store.self?.name || "",
            url: this.state.newlink?.invitation?.share_url || "/linkup/invite/••••••",
        });
    },

    get newlinkCodeText() {
        return _t(
            "The member who gave you this code receives the reflection inside LinkUp, if their settings allow it. Nobody is told otherwise."
        );
    },

    /** Copy the share link of the invitation just sent. */
    async copyShareLink() {
        const url = this.state.newlink?.invitation?.share_url;
        if (!url) {
            return;
        }
        try {
            await browser.navigator.clipboard.writeText(url);
            this.state.newlink.copied = true;
            this.state.notice = _t("Link copied.");
        } catch {
            this.state.notice = _t("Select the link and copy it.");
        }
    },

    async resendInvitation() {
        await super.resendInvitation();
        if (this.state.newlink) {
            this.state.newlink.copied = false;
        }
    },
});
