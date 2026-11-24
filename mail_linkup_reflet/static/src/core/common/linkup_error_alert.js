import {Component} from "@odoo/owl";

import {browser} from "@web/core/browser/browser";

/**
 * The message of a refused LinkUp action, with what the member can do
 * about it (LU-F-093): "Try again" after a lost connection, which runs the
 * action again from scratch, and "Log in" after an expired session, which
 * reloads the page onto the login screen; the draft of a reflection stays
 * on the server. Every other code shows its message only.
 *
 * @typedef {Object} Props
 * @property {{code: string, message: string}} error as `linkupErrorInfo` gives it
 * @property {Function} [onRetry] runs the refused action again
 * @property {string} [className] the classes of the alert
 * @extends {Component<Props, Env>}
 */
export class LinkupErrorAlert extends Component {
    static template = "mail_linkup_reflet.LinkupErrorAlert";
    static props = ["error", "onRetry?", "className?"];

    get canRetry() {
        return this.props.error.code === "network" && Boolean(this.props.onRetry);
    }

    get needsLogin() {
        return this.props.error.code === "session";
    }

    retry() {
        this.props.onRetry?.();
    }

    login() {
        browser.location.reload();
    }
}
