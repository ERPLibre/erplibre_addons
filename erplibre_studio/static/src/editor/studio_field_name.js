/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onMounted, onWillUnmount, onWillUpdateProps, status, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useDebounced} from "@web/core/utils/timing";

// How long the input waits after a keystroke before it checks the name (ms).
export const NAME_CHECK_DELAY = 250;
// The ids the input and its status take, one pair per component.
let nextId = 0;

/** The label of the new field ``field`` (an entry of the payload), or "". */
function fieldLabel(field) {
    return (field.definition && field.definition.field_description) || "";
}

/**
 * The technical name of a new field of the project, not created yet: an
 * input checked live against the rule of the database, the reserved words
 * of the ORM and the names already taken (``check_field_name``), each
 * check listed with its result. A valid name different from the current
 * one renames the field on change (« rename_field »), an empty one gives it
 * back its proposed name; « Use » and « Back
 * to the proposed name » give it back the name its label proposes, which
 * it then follows again. With ``onRename``, the field is an inverse the
 * definition of another field names: ``onRename`` renames it, and it
 * follows no label.
 *
 * Each check is a request numbered in order: an answer that arrives after
 * a newer request, or once the component is gone, is dropped. While the
 * input holds a name that does not apply, the component counts it among
 * the names that block Apply (``editor.setLocalNameBlocker``), until the
 * value applies, goes back to the current name, or the component unmounts.
 */
export class StudioFieldName extends Component {
    static template = "erplibre_studio.FieldName";
    static props = {
        editor: Object,
        // The model of the field.
        model: String,
        // The current technical name of the field.
        name: String,
        // The entry of the field in the payload (get_editor_data « fields »).
        field: Object,
        // The rule of the database (``field_name_rule`` of the payload).
        rule: {type: [Object, {value: null}], optional: true},
        busy: {type: Boolean, optional: true},
        // ``onRename(name)`` renames the field instead of « rename_field »:
        // the inverse field a relational field of the project creates,
        // named in the definition of that field. Its name follows no label.
        onRename: {type: Function, optional: true},
        // The text under the input, instead of the default one.
        help: {type: String, optional: true},
    };

    setup() {
        // ``check``: the last answer of ``check_field_name``, for the name
        // it names (``check.name``); ``checking``: a request is on its way.
        this.state = useState({value: this.props.name, check: null, checking: false});
        this.request = 0;
        // The key of this input among the local blockers of the editor.
        this.blockerKey = Symbol("field_name");
        this.inputId = `o_erplibre_studio_name_${++nextId}`;
        this.scheduleCheck = useDebounced(() => this.check(), NAME_CHECK_DELAY);
        onMounted(() => this.check());
        onWillUpdateProps((next) => {
            if (next.name !== this.props.name || next.model !== this.props.model) {
                this.scheduleCheck.cancel();
                this.request++;
                Object.assign(this.state, {value: next.name, check: null, checking: false});
                this.reportBlocker(false);
                this.check(next);
            } else if (fieldLabel(next.field) !== fieldLabel(this.props.field)) {
                // A new label proposes another name: the value stays.
                this.check(next);
            }
        });
        onWillUnmount(() => {
            this.request++;
            this.reportBlocker(false);
        });
    }

    get editor() {
        return this.props.editor;
    }

    get value() {
        return this.state.value.trim();
    }

    /** The answer of the last check when it is about the value on screen, else null. */
    get current() {
        const check = this.state.check;
        return check && check.name === (this.value || check.proposed) ? check : null;
    }

    /** Whether the name follows the label (« auto ») or was typed (« edited »). */
    get tag() {
        return this.props.field.name_auto === false ? _t("edited") : _t("auto");
    }

    get rule() {
        return this.props.rule || (this.state.check && this.state.check.rule) || null;
    }

    /** The class of the status: available, refused, or none while checking. */
    get statusClass() {
        const check = this.current;
        if (this.state.checking || !check) {
            return "text-muted";
        }
        return check.status === "available"
            ? "o_erplibre_studio_name_ok text-success-emphasis bg-success-subtle"
            : "o_erplibre_studio_name_bad text-danger-emphasis bg-danger-subtle";
    }

    /** Whether the value on screen is known not to apply. */
    get invalid() {
        const check = this.current;
        return Boolean(check && check.status !== "available");
    }

    /** The name the label proposes, offered when the value does not apply. */
    get suggestion() {
        const check = this.current;
        return this.invalid && check.proposed && check.proposed !== this.value ? check.proposed : false;
    }

    useLabel(name) {
        return _t("Use %(name)s", {name});
    }

    backLabel(name) {
        return _t("Back to the proposed name (%(name)s)", {name});
    }

    /**
     * Ask the server what the value gives, as ``props`` (the next ones
     * during an update) name the field. The answer of an older request is
     * dropped.
     */
    async check(props = this.props) {
        const value = this.value;
        const request = ++this.request;
        this.state.checking = true;
        const check = await this.editor.checkFieldName(props.model, value, props.name, fieldLabel(props.field));
        if (request !== this.request || status(this) === "destroyed") {
            return null;
        }
        Object.assign(this.state, {check, checking: false});
        this.reportBlocker(value !== props.name && check.status !== "available");
        return check;
    }

    reportBlocker(blocked) {
        this.editor.setLocalNameBlocker(this.blockerKey, blocked);
    }

    onInput(ev) {
        this.state.value = ev.target.value;
        this.scheduleCheck();
    }

    /**
     * Rename the field to the value on change: an empty value goes back to
     * the proposed name; another value only once a check of that very
     * value answered « available ».
     */
    async onChange() {
        if (this.props.busy) {
            return;
        }
        const value = this.value;
        if (value === this.props.name) {
            this.reportBlocker(false);
            return;
        }
        if (!value) {
            return this.backToProposed();
        }
        this.scheduleCheck.cancel();
        let check = this.current;
        if (!check || this.state.checking) {
            check = await this.check();
        }
        if (check && check.name === value && check.status === "available" && status(this) !== "destroyed") {
            await this.rename(value);
        }
    }

    /** Rename the field to ``name``: through ``onRename`` when given, else « rename_field ». */
    rename(name) {
        if (this.props.onRename) {
            return this.props.onRename(name);
        }
        return this.editor.renameField(this.props.name, name);
    }

    /** Take the name the label proposes, and follow the label again. */
    async useProposed() {
        const check = this.current;
        if (check && check.proposed) {
            this.state.value = check.proposed;
        }
        return this.backToProposed();
    }

    async backToProposed() {
        this.scheduleCheck.cancel();
        const old = this.props.name;
        let name = old;
        if (this.props.onRename) {
            // No label to follow: the proposed name, once, as a typed one.
            const proposed = this.state.check && this.state.check.proposed;
            if (proposed && proposed !== old) {
                await this.props.onRename(proposed);
                return;
            }
        } else {
            name = await this.editor.renameField(old, null, {auto: true});
        }
        if (name === old && status(this) !== "destroyed") {
            // The label proposes the current name: no new props reset the
            // value nor check it, so both happen here.
            this.state.value = old;
            await this.check();
        }
    }
}
