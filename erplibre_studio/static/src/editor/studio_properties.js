/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, status, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {useDebounced} from "@web/core/utils/timing";
import {NAME_CHECK_DELAY} from "./studio_field_name";

/**
 * The field ``apply_operation`` adds for the properties dialog ``state``:
 * the many2one it reads its definition through (``definition_record``),
 * then an existing properties definition field of its comodel
 * (``definition_record_field``) or the one the studio creates there
 * (``definition_new``, named ``state.newName``, else the name the server
 * proposed).
 */
export function propertiesField(state, container) {
    const field = {
        ttype: "properties",
        field_description: state.label.trim(),
        definition_record: state.container,
    };
    if (state.mode === "create") {
        field.definition_new = {
            name: state.newName.trim() || container.proposed.name,
            field_description: container.proposed.label,
        };
    } else {
        field.definition_record_field = state.definition;
    }
    return field;
}

/**
 * The dialog of a new properties field of ``model``: the many2one it reads
 * its definition through (its container), then where the properties are
 * defined on the comodel of that many2one, an existing properties
 * definition field or one the studio creates, then its label.
 * ``loadChoices()`` answers ``get_properties_choices`` once, when the
 * dialog opens; ``save(field)`` answers whether the server took the field;
 * ``checkName(comodel, name, label)`` answers ``check_field_name`` for the
 * name of the definition field the studio creates, which Create then needs
 * « available »: each check is numbered, an older answer that arrives late
 * is dropped.
 */
export class StudioPropertiesDialog extends Component {
    static template = "erplibre_studio.PropertiesDialog";
    static components = {Dialog};
    static props = {
        model: String,
        modelLabel: String,
        loadChoices: Function,
        save: Function,
        checkName: {type: Function, optional: true},
        close: Function,
    };

    setup() {
        this.state = useState({
            containers: null,
            error: null,
            loading: true,
            // The name of the chosen many2one.
            container: "",
            // « existing »: ``definition`` names a definition field of the
            // comodel; « create »: the studio creates ``newName``.
            mode: "create",
            definition: "",
            newName: "",
            nameCheck: null,
            nameChecking: false,
            label: _t("Properties"),
            saving: false,
        });
        this.nameRequest = 0;
        this.scheduleNameCheck = useDebounced(() => this.checkNewName(), NAME_CHECK_DELAY);
        this.load();
    }

    async load() {
        try {
            const choices = await this.props.loadChoices();
            if (status(this) === "destroyed") {
                return;
            }
            this.state.containers = (choices && choices.containers) || [];
            this.state.loading = false;
            if (this.state.containers.length) {
                await this.setContainer(this.state.containers[0].name);
            }
        } catch (error) {
            if (status(this) !== "destroyed") {
                Object.assign(this.state, {
                    loading: false,
                    containers: null,
                    error: (error.data && error.data.message) || error.message || String(error),
                });
            }
        }
    }

    get containers() {
        return this.state.containers || [];
    }

    /** The chosen container, {name, label, comodel, comodel_label, pending, definitions, proposed}. */
    get container() {
        return this.containers.find((c) => c.name === this.state.container) || null;
    }

    get definitions() {
        return (this.container && this.container.definitions) || [];
    }

    containerLabel(container) {
        return `${container.label} (${container.comodel_label})`;
    }

    get definedOnLabel() {
        const container = this.container;
        return _t("Where the properties are defined on %(model)s", {
            model: container ? container.comodel_label : "",
        });
    }

    get createLabel() {
        return _t("Create %(label)s", {label: this.container ? this.container.proposed.label : ""});
    }

    /**
     * Choose the many2one ``name``: its first definition field when its
     * comodel has one, else the one the studio would create.
     */
    async setContainer(name) {
        this.state.container = name;
        const container = this.container;
        if (!container) {
            return;
        }
        const names = container.definitions.map((d) => d.name);
        Object.assign(this.state, {
            definition: names[0] || "",
            mode: names.length ? "existing" : "create",
            newName: container.proposed.name,
            nameCheck: null,
        });
        await this.checkNewName();
    }

    setMode(mode) {
        this.state.mode = mode;
    }

    /** Read the properties from the existing definition field ``name`` of the comodel. */
    setDefinition(name) {
        Object.assign(this.state, {mode: "existing", definition: name});
    }

    /** Type the name of the definition field: checked once the typing pauses. */
    setNewName(value) {
        this.state.newName = value;
        this.state.nameCheck = null;
        this.scheduleNameCheck();
    }

    /** Ask the server whether the name of the definition field applies on the comodel. */
    async checkNewName() {
        const container = this.container;
        const name = this.state.newName.trim();
        const request = ++this.nameRequest;
        if (!this.props.checkName || !name || !container) {
            Object.assign(this.state, {nameCheck: null, nameChecking: false});
            return;
        }
        this.state.nameChecking = true;
        const check = await this.props.checkName(container.comodel, name, container.proposed.label);
        if (request !== this.nameRequest || status(this) === "destroyed") {
            return;
        }
        Object.assign(this.state, {nameCheck: check, nameChecking: false});
    }

    /** Whether the name of the definition field is empty: nothing to check. */
    get newNameEmpty() {
        return !this.state.newName.trim();
    }

    /** The answer of the last check when it is about the name on screen, else null. */
    get nameCheck() {
        const check = this.state.nameCheck;
        return check && check.name === this.state.newName.trim() ? check : null;
    }

    /** Whether the name of the definition field may be sent: checked available, or no check to make. */
    get newNameOk() {
        if (!this.props.checkName) {
            return Boolean(this.state.newName.trim());
        }
        const check = this.nameCheck;
        return Boolean(!this.state.nameChecking && check && check.status === "available");
    }

    get canSave() {
        const state = this.state;
        if (state.saving || state.loading || !this.container || !state.label.trim()) {
            return false;
        }
        if (state.mode === "create") {
            return this.newNameOk;
        }
        return this.definitions.some((d) => d.name === state.definition);
    }

    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.saving = true;
        if (await this.props.save(propertiesField(this.state, this.container))) {
            this.props.close();
            return;
        }
        this.state.saving = false;
    }
}
