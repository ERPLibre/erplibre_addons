/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";

// The sections of a removal report, in the order they show (REPORT_SECTIONS
// of the server).
export const REPORT_SECTIONS = [
    "models",
    "fields",
    "tables",
    "groups",
    "categories",
    "menus",
    "actions",
    "views",
    "access",
    "rules",
    "members",
    "others",
];

/** The title of a section of a removal report. */
export function reportTitle(section) {
    return (
        {
            models: _t("Models and their records"),
            fields: _t("Fields and their values"),
            tables: _t("Relation tables"),
            groups: _t("Groups and their members"),
            categories: _t("Categories of groups"),
            menus: _t("Menus"),
            actions: _t("Actions"),
            views: _t("Views"),
            access: _t("Access rights"),
            rules: _t("Record rules"),
            members: _t("Members who lose a group"),
            others: _t("Other records deleted with them"),
        }[section] || section
    );
}

/** The line of ``item`` in the section ``section`` of a removal report. */
export function reportItemText(section, item) {
    switch (section) {
        case "models":
            return _t("%(name)s (%(model)s): %(count)s record(s)", item);
        case "fields":
            return _t("%(label)s (%(model)s.%(name)s): %(filled)s value(s)", item);
        case "groups":
            return _t("%(name)s: %(users)s member(s)", item);
        case "members":
            return _t("%(name)s: %(users)s member(s) of %(via)s lose it", item);
        case "access":
            return item.group ? `${item.name} (${item.group})` : item.name;
        case "rules":
            return `${item.name} (${item.model})`;
        case "views":
            return `${item.name} (${item.kind === "default" ? _t("default") : _t("inherited")})`;
        case "tables":
            return item;
        default:
            return item.name;
    }
}

/**
 * The non-empty sections of the removal report ``report``
 * (``_studio_removal_report`` of the server): [{key, title, items}], each
 * item {text, warn}; ``warn`` marks what holds data: records, values or
 * members.
 */
export function reportSections(report) {
    return REPORT_SECTIONS.map((key) => ({
        key,
        title: reportTitle(key),
        items: ((report && report[key]) || []).map((item) => ({
            text: reportItemText(key, item),
            warn: Boolean(item && (item.count || item.filled || item.users)),
        })),
    })).filter((section) => section.items.length);
}

/**
 * The confirmation of an action that removes from the database what the
 * project created: the removal report, then the action. ``refused`` (a
 * message) replaces the button: the server refuses the action now.
 * ``confirm(digest)`` runs it with the digest of the report on screen and
 * answers whether it went through; the dialog then closes. When it did
 * not, ``reload()`` reads the report again ({report, digest, refused}): a
 * report that changed shows with a warning, and the next confirmation
 * sends its digest.
 */
export class StudioConfirmDialog extends Component {
    static template = "erplibre_studio.ConfirmDialog";
    static components = {Dialog};
    static props = {
        title: String,
        intro: String,
        report: Object,
        digest: {type: [String, Boolean], optional: true},
        refused: {type: [String, Boolean], optional: true},
        confirmLabel: String,
        confirm: Function,
        reload: {type: Function, optional: true},
        close: Function,
    };

    setup() {
        this.state = useState({
            running: false,
            report: this.props.report,
            digest: this.props.digest || false,
            refused: this.props.refused || false,
            stale: false,
        });
    }

    get sections() {
        return reportSections(this.state.report);
    }

    get changesRemoved() {
        return this.state.report.changes_removed || 0;
    }

    get changesText() {
        return _t("%(count)s change(s) of the default views go with these views.", {count: this.changesRemoved});
    }

    async confirm() {
        if (this.state.running || this.state.refused) {
            return;
        }
        this.state.running = true;
        if (await this.props.confirm(this.state.digest)) {
            this.props.close();
            return;
        }
        const answer = this.props.reload && (await this.props.reload());
        if (answer) {
            const refused = answer.refused || false;
            const stale = answer.digest !== this.state.digest || refused !== this.state.refused;
            Object.assign(this.state, {report: answer.report, digest: answer.digest, refused, stale});
        }
        this.state.running = false;
    }
}
