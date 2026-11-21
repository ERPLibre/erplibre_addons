/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";

// The relational field types a drop opens the relation dialog for.
export const X2MANY_TYPES = ["one2many", "many2many"];
// The view types each one shows in (X2MANY_VIEW_TYPES of the server).
export const X2MANY_VIEW_TYPES = {one2many: ["form"], many2many: ["form", "list", "kanban"]};

/** Whether a new field of ``ttype`` can be dropped into a ``viewType`` view. */
export function fieldTypeFits(ttype, viewType) {
    return !X2MANY_TYPES.includes(ttype) || X2MANY_VIEW_TYPES[ttype].includes(viewType);
}

/**
 * The comodels [[model, name]] of ``comodels``, those of ``first`` (the
 * models of the project) first, whose name or label holds ``text``.
 */
export function sortComodels(comodels, first = [], text = "") {
    const filter = (text || "").trim().toLowerCase();
    const items = (comodels || []).filter(
        ([model, name]) =>
            !filter || model.toLowerCase().includes(filter) || (name || "").toLowerCase().includes(filter)
    );
    const rank = (model) => (first.includes(model) ? 0 : 1);
    return items.sort((a, b) => rank(a[0]) - rank(b[0]) || (a[1] || "").localeCompare(b[1] || ""));
}

/**
 * The field ``apply_operation`` adds for the relation dialog ``state`` of
 * a ``ttype`` field: a many2many names its comodel (the server names its
 * table); a one2many its inverse, an existing many2one or the one the
 * studio creates on the comodel.
 */
export function relationField(ttype, state) {
    const field = {ttype, field_description: state.label.trim(), relation: state.comodel};
    if (ttype === "one2many") {
        if (state.inverseMode === "create") {
            field.inverse = {
                create: true,
                name: state.choices.inverse_name,
                field_description: state.inverseLabel.trim(),
            };
        } else {
            field.relation_field = state.inverseName;
        }
    }
    return field;
}

/**
 * The dialog of a new one2many or many2many of ``model``: its comodel, its
 * label, and for a one2many its inverse many2one, chosen among those of
 * the comodel or created by the studio; for a many2many the relation table
 * the server names, shown read-only. ``loadChoices(comodel, label)``
 * answers ``get_relation_choices``; ``save(field)`` answers whether the
 * server took the field.
 */
export class StudioRelationDialog extends Component {
    static template = "erplibre_studio.RelationDialog";
    static components = {Dialog};
    static props = {
        ttype: String,
        model: String,
        modelLabel: String,
        comodels: Array,
        projectModels: {type: Array, optional: true},
        loadChoices: Function,
        save: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            comodel: "",
            filter: "",
            label: "",
            labelEdited: false,
            choices: null,
            error: null,
            loading: false,
            inverseMode: "existing",
            inverseName: "",
            inverseLabel: "",
            saving: false,
        });
        // The answer of the last request: an older one that arrives late is dropped.
        this.request = 0;
    }

    get isOne2many() {
        return this.props.ttype === "one2many";
    }

    get title() {
        return this.isOne2many ? _t("New one2many field") : _t("New many2many field");
    }

    get comodels() {
        return sortComodels(this.props.comodels, this.props.projectModels || [], this.state.filter);
    }

    comodelLabel(model) {
        const item = (this.props.comodels || []).find((m) => m[0] === model);
        return item ? item[1] : model;
    }

    /** Whether the studio may create the inverse on the comodel. */
    get canCreateInverse() {
        return Boolean(this.state.choices && !this.state.choices.protected);
    }

    get inverses() {
        return (this.state.choices && this.state.choices.inverses) || [];
    }

    get createLabel() {
        const choices = this.state.choices || {};
        return _t("Create the field %(name)s on %(comodel)s", {
            name: choices.inverse_name || "",
            comodel: this.comodelLabel(this.state.comodel),
        });
    }

    async load() {
        const {comodel, label} = this.state;
        const request = ++this.request;
        this.state.error = null;
        if (!comodel) {
            this.state.choices = null;
            return;
        }
        this.state.loading = true;
        try {
            const choices = await this.props.loadChoices(comodel, label.trim());
            if (request !== this.request) {
                return;
            }
            this.state.choices = choices;
            if (this.isOne2many) {
                const names = (choices.inverses || []).map((c) => c.name);
                if (!names.includes(this.state.inverseName)) {
                    this.state.inverseName = names[0] || "";
                }
                this.state.inverseMode = names.length || choices.protected ? "existing" : "create";
                this.state.inverseLabel = choices.inverse_label || "";
            }
        } catch (error) {
            if (request === this.request) {
                this.state.choices = null;
                this.state.error = (error.data && error.data.message) || error.message || String(error);
            }
        } finally {
            if (request === this.request) {
                this.state.loading = false;
            }
        }
    }

    /** The label follows the comodel until edited. */
    async setComodel(model) {
        this.state.comodel = model;
        if (!this.state.labelEdited) {
            this.state.label = model ? this.comodelLabel(model) : "";
        }
        await this.load();
    }

    setLabel(value) {
        this.state.label = value;
        this.state.labelEdited = true;
    }

    /** A many2many names its table after its label: ask the names again. */
    async labelChanged() {
        if (!this.isOne2many) {
            await this.load();
        }
    }

    get canSave() {
        const state = this.state;
        if (state.saving || state.loading || !state.choices || !state.comodel || !state.label.trim()) {
            return false;
        }
        if (!this.isOne2many) {
            return true;
        }
        if (state.inverseMode === "create") {
            return this.canCreateInverse && Boolean(state.inverseLabel.trim());
        }
        return Boolean(state.inverseName);
    }

    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.saving = true;
        if (await this.props.save(relationField(this.props.ttype, this.state))) {
            this.props.close();
            return;
        }
        this.state.saving = false;
    }
}
