/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, status, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {useDebounced} from "@web/core/utils/timing";
import {NAME_CHECK_DELAY} from "./studio_field_name";
import {GEO_TYPES} from "./studio_utils";

// The relational field types a drop opens the relation dialog for.
export const X2MANY_TYPES = ["one2many", "many2many"];
// The view types a new field of each type goes in (FIELD_TYPE_VIEW_TYPES of
// the server); a type missing from the map goes in every view. A JSON field
// shows read-only in a form or a list, a properties field in a form, beside
// the many2one it reads their definition through.
export const FIELD_TYPE_VIEW_TYPES = {
    one2many: ["form"],
    many2many: ["form", "list", "kanban"],
    json: ["form", "list"],
    properties: ["form"],
};

// The new field types a map creates from its lanes (LEAFLET_NEW_FIELD_TYPES
// of the server): a coordinate, a popup text.
export const LEAFLET_NEW_TYPES = ["float", "char"];

/** Whether a new field of ``ttype`` can be dropped into a ``viewType`` view. */
export function fieldTypeFits(ttype, viewType) {
    if (viewType === "leaflet_map") {
        return LEAFLET_NEW_TYPES.includes(ttype);
    }
    if (GEO_TYPES.includes(ttype)) {
        // geo_refusal of the server: a map per record outside a form.
        return viewType === "form";
    }
    const viewTypes = FIELD_TYPE_VIEW_TYPES[ttype];
    return !viewTypes || viewTypes.includes(viewType);
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
 * studio creates on the comodel, named ``state.inverseNew`` (else the
 * name the server proposed).
 */
export function relationField(ttype, state) {
    const field = {ttype, field_description: state.label.trim(), relation: state.comodel};
    if (ttype === "one2many") {
        if (state.inverseMode === "create") {
            field.inverse = {
                create: true,
                name: (state.inverseNew || "").trim() || state.choices.inverse_name,
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
 * server took the field; ``checkName(comodel, name, label)`` answers
 * ``check_field_name`` for the name of the inverse the studio creates,
 * which Create then needs « available »: each check is numbered, an
 * older answer that arrives late is dropped.
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
        checkName: {type: Function, optional: true},
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
            // The name of the inverse the studio creates, and the answer
            // of its last check (``nameCheck.name`` is the name checked).
            inverseNew: "",
            nameCheck: null,
            nameChecking: false,
            saving: false,
        });
        // The answer of the last request: an older one that arrives late is dropped.
        this.request = 0;
        this.nameRequest = 0;
        this.scheduleNameCheck = useDebounced(() => this.checkInverseName(), NAME_CHECK_DELAY);
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
            name: this.state.inverseNew.trim() || choices.inverse_name || "",
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
                this.state.inverseNew = choices.inverse_name || "";
                if (!choices.protected) {
                    await this.checkInverseName();
                }
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

    /** Type the name of the inverse: checked once the typing pauses. */
    setInverseNew(value) {
        this.state.inverseNew = value;
        this.state.nameCheck = null;
        this.scheduleNameCheck();
    }

    /** Ask the server whether the name of the inverse applies on the comodel. */
    async checkInverseName() {
        const name = this.state.inverseNew.trim();
        const request = ++this.nameRequest;
        if (!this.props.checkName || !name || !this.state.comodel) {
            this.state.nameCheck = null;
            return;
        }
        this.state.nameChecking = true;
        const check = await this.props.checkName(this.state.comodel, name, this.state.inverseLabel.trim());
        if (request !== this.nameRequest || status(this) === "destroyed") {
            return;
        }
        Object.assign(this.state, {nameCheck: check, nameChecking: false});
    }

    /** The answer of the last check when it is about the name on screen, else null. */
    get nameCheck() {
        const check = this.state.nameCheck;
        return check && check.name === this.state.inverseNew.trim() ? check : null;
    }

    /** Whether the name of the inverse may be sent: checked available, or no check to make. */
    get inverseNameOk() {
        if (!this.props.checkName) {
            return Boolean(this.state.inverseNew.trim());
        }
        const check = this.nameCheck;
        return Boolean(!this.state.nameChecking && check && check.status === "available");
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
            return this.canCreateInverse && Boolean(state.inverseLabel.trim()) && this.inverseNameOk;
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
