import {onWillStart, onWillUpdateProps} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";

import {LinkupHelpBar} from "./help_bar";
import {LinkupRefletFormBase} from "./reflet_form";
import {linkupFetchNewMessages} from "./store_service_patch";

/**
 * The reflection of a direct conversation, above its composer: the Help
 * bar and the form "You told me / I understood that" (`reflet_form.js`).
 *
 * The recipient is the other member of the conversation, as given by
 * `linkup.reflet.linkup_channel_info`, which also gives the draft of the
 * member to restore.
 *
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @extends {LinkupRefletFormBase<Props, Env>}
 */
export class LinkupRefletComposer extends LinkupRefletFormBase {
    static template = "mail_linkup_reflet.LinkupRefletComposer";
    static components = {...LinkupRefletFormBase.components, LinkupHelpBar};
    static props = ["thread"];

    setup() {
        super.setup();
        onWillStart(() => {
            this.load(this.props.thread);
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.thread.notEq(this.props.thread)) {
                this.load(nextProps.thread);
            }
        });
    }

    extraState() {
        return {info: null, loadError: false};
    }

    get isLoaded() {
        return Boolean(this.state.info);
    }

    async fetchInfo() {
        const thread = this.props.thread;
        const info = await this.store.fetchLinkupChannelInfo(thread.id);
        return this.props.thread.eq(thread) ? info : null;
    }

    applyInfo(info) {
        this.state.info = info;
    }

    /**
     * Read the categories and the conversation, without holding the
     * rendering of the composer; restore the draft of the member.
     *
     * @param {import("models").Thread} thread
     */
    async load(thread) {
        this.state.info = null;
        this.state.loadError = false;
        try {
            const [info] = await Promise.all([
                this.store.fetchLinkupChannelInfo(thread.id),
                this.store.fetchLinkupCategories(),
            ]);
            if (this.props.thread.notEq(thread)) {
                return;
            }
            this.state.info = info;
            if (info.draft && !this.state.formOpen) {
                this.restoreDraft(info.draft);
            }
        } catch {
            this.state.loadError = true;
        }
    }

    get available() {
        return Boolean(this.state.info?.available);
    }

    get recipientName() {
        return this.props.thread.displayName;
    }

    get recipientPersona() {
        return this.props.thread.correspondent?.persona;
    }

    get formId() {
        return `thread-${this.props.thread.id}`;
    }

    get helpLabel() {
        return _t("HELP — What did %(name)s tell you about?", {
            name: this.recipientName,
        });
    }

    get needsRealWorld() {
        return Boolean(this.state.info?.needs_real_world);
    }

    get sendTarget() {
        return {
            recipientId: this.state.info.recipient_id,
            name: this.recipientName,
            thread: this.props.thread,
        };
    }

    afterSend(target) {
        linkupFetchNewMessages(target.thread);
        this.load(target.thread);
    }
}
