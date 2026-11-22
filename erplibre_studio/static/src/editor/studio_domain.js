/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {DomainSelector} from "@web/core/domain_selector/domain_selector";

/**
 * The visual editor of a domain: the DomainSelector of Odoo on the model
 * ``resModel``, its code editor shown as the text mode. The selector
 * reads the fields of ``resModel`` (fields_get): the model must exist.
 * ``confirm(domain)`` sends the domain on screen to the server and answers
 * the message of a refusal, or null; a refusal shows in the dialog, which
 * stays open, else the dialog closes. ``allowExpressions``: whether a
 * value may be an expression (« user.id » of a record rule).
 */
export class StudioDomainDialog extends Component {
    static template = "erplibre_studio.DomainDialog";
    static components = {Dialog, DomainSelector};
    static props = {
        close: Function,
        resModel: String,
        domain: String,
        title: String,
        // A line above the selector, or nothing.
        text: {type: String, optional: true},
        allowExpressions: {type: Boolean, optional: true},
        confirm: Function,
    };

    setup() {
        this.state = useState({domain: this.props.domain || "[]", error: null, busy: false});
    }

    update(domain) {
        this.state.domain = domain;
        this.state.error = null;
    }

    async confirm() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        let error;
        try {
            error = await this.props.confirm(this.state.domain);
        } finally {
            this.state.busy = false;
        }
        if (error) {
            this.state.error = error;
            return;
        }
        this.props.close();
    }
}
