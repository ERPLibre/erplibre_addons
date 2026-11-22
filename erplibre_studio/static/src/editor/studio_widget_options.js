/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillStart, onWillUpdateProps, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {evaluateExpr, parseExpr} from "@web/core/py_js/py";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {deepEqual} from "@web/core/utils/objects";
import {findBlock} from "./studio_utils";

const RELATION_TYPES = ["many2one", "one2many", "many2many"];
// The field name ``relatedFields`` receives to tell whether an option names
// a field of the comodel: no real field carries it.
const PROBE = "__studio_probe__";

// The options of the widgets whose registry entry lists none although
// they read some: the « html » field of html_editor declares no
// supportedOptions and reads these from ``options``.
export const FALLBACK_OPTIONS = {
    html: [
        {name: "height", label: _t("Height (px)"), type: "number"},
        {name: "disableImage", label: _t("No image"), type: "boolean"},
        {name: "disableVideo", label: _t("No video"), type: "boolean"},
        {name: "disableFile", label: _t("No file"), type: "boolean"},
        {name: "codeview", label: _t("Code view (debug mode)"), type: "boolean"},
    ],
};

// The options of type « field » that name a field of the comodel although
// the widget has no ``relatedFields`` that loads it: widget -> option names.
export const COMODEL_FIELD_OPTIONS = {
    statusbar: ["fold_field"],
};

// The ids the inputs take, one set per component.
let nextId = 0;

/**
 * The registry entry of the widget of a field, resolved as Odoo resolves
 * it (getFieldFromRegistry): « <viewType>.<widget> », then « <widget> »;
 * an unknown widget falls back to the field type. Answer [name, entry],
 * entry null when none matches.
 */
function widgetEntry(widget, fieldType, viewType) {
    const fields = registry.category("fields");
    const find = (key) => (key && (fields.get(`${viewType}.${key}`, null) || fields.get(key, null))) || null;
    const entry = find(widget);
    if (entry || !widget) {
        return [widget || fieldType, entry || find(fieldType)];
    }
    return [fieldType, find(fieldType)];
}

/**
 * Whether the option ``name`` of the registry entry ``entry`` names a field
 * of the comodel: ``relatedFields``, called with the probe as the value of
 * the option, lists a field named after the probe. A ``relatedFields``
 * that reads other props and throws counts as no.
 */
function readsComodelField(entry, name) {
    if (!entry || typeof entry.relatedFields !== "function") {
        return false;
    }
    try {
        const related = entry.relatedFields({options: {[name]: PROBE}, attrs: {}, context: "{}"});
        return Array.isArray(related) && related.some((field) => field && field.name === PROBE);
    } catch {
        return false;
    }
}

/**
 * The options the widget ``widget`` (empty: the widget of the type) of a
 * field of type ``fieldType`` lists in a view of type ``viewType``: the
 * ``supportedOptions`` of its registry entry, else FALLBACK_OPTIONS, else
 * none. Each spec {name, label, type, help, default, choices,
 * availableTypes} gains ``scope``, for a spec of type « field »: « comodel »
 * when the option names a field of the model a relational field points
 * to, « record » when it names a field of the model of the view; null for
 * the other types.
 */
export function widgetOptionSpecs(widget, fieldType, viewType) {
    const [name, entry] = widgetEntry(widget, fieldType, viewType);
    const specs = (entry && entry.supportedOptions) || FALLBACK_OPTIONS[name] || [];
    const relational = RELATION_TYPES.includes(fieldType);
    return specs.map((spec) => {
        let scope = null;
        if (spec.type === "field") {
            const comodel =
                relational &&
                (readsComodelField(entry, spec.name) || (COMODEL_FIELD_OPTIONS[name] || []).includes(spec.name));
            scope = comodel ? "comodel" : "record";
        }
        return {...spec, scope};
    });
}

/**
 * Whether the parsed expression ``ast`` (py_js) is a fixed value: a
 * number, a text, a boolean, None, a signed number, or a list, a tuple or a
 * dictionary of those. A name (« uid », « context ») or a call is not.
 */
function isLiteral(ast) {
    switch (ast.type) {
        case 0: // Number
        case 1: // String
        case 2: // Boolean
        case 3: // None
            return true;
        case 4: // List
        case 10: // Tuple
            return ast.value.every(isLiteral);
        case 11: // Dictionary
            return Object.values(ast.value).every(isLiteral);
        case 6: // UnaryOperator
            return ["-", "+"].includes(ast.op) && ast.right.type === 0;
        default:
            return false;
    }
}

/**
 * The options of the text ``text`` of an ``options`` attribute: {ok,
 * options}. Empty gives no option; a Python dictionary of fixed values
 * (what the server writes) or JSON gives its dictionary; an expression
 * (a name of the context, a call) or anything but a dictionary gives
 * ok false: the typed form cannot show it without changing it.
 */
export function parseOptions(text) {
    const source = (text || "").trim();
    if (!source) {
        return {ok: true, options: {}};
    }
    let value;
    try {
        if (!isLiteral(parseExpr(source))) {
            throw new Error("not a literal");
        }
        value = evaluateExpr(source);
    } catch {
        try {
            value = JSON.parse(source);
        } catch {
            return {ok: false, options: {}};
        }
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        return {ok: false, options: {}};
    }
    return {ok: true, options: value};
}

/**
 * The value an option takes for the choice ``raw`` of a selection: a
 * choice written as a list or a dictionary (« [0,90] », the size of an
 * image read as ``options.size[0]``) is that list or dictionary, any other
 * the text itself.
 */
export function choiceValue(raw) {
    if (typeof raw === "string" && (raw.startsWith("[") || raw.startsWith("{"))) {
        try {
            return JSON.parse(raw);
        } catch {
            return raw;
        }
    }
    return raw;
}

/**
 * The options of the widget of a field of a form or a list, as a form
 * built from the metadata of the widget (widgetOptionSpecs): one line per
 * option, a switch, an input or a select by type. A field option lists the
 * fields of the model of the view, or of the comodel (loaded through the
 * field service), of the types the option accepts. A key the widget does
 * not list shows apart, with its remove button. « Edit as text » swaps the
 * form for the text of the attribute; options that hold an expression, or
 * a widget that lists none, show only the text.
 *
 * Each change sends the whole dictionary through
 * ``editor.setNodeAttribute`` (« set_attribute »), with ``option_fields``:
 * option -> « record » or « comodel » for the field options it holds, which
 * the server checks. A key set back to its default, or emptied, leaves the
 * dictionary; an empty dictionary removes the attribute.
 */
export class StudioWidgetOptions extends Component {
    static template = "erplibre_studio.WidgetOptions";
    static props = {
        editor: Object,
        // The block of the field (get_editor_data « blocks »).
        block: Object,
        // The entry « options » of StudioInspector.settableOf(block).
        entry: Object,
        // The entry of the field in the payload (« fields »).
        field: Object,
        // The fields of the model of the view (« fields » of the payload).
        fields: Object,
        // The root block of the view: a record field not in it is flagged.
        blocks: {type: [Object, {value: null}], optional: true},
        viewType: String,
        busy: {type: Boolean, optional: true},
    };

    setup() {
        this.fieldService = useService("field");
        this.uid = `o_erplibre_studio_option_${++nextId}`;
        // Whether the text shows instead of the form; the fields of the
        // comodel, once loaded, for the field options of scope « comodel ».
        this.state = useState({raw: !parseOptions(this.props.entry.value).ok, comodelFields: null});
        this.loadedRelation = null;
        onWillStart(() => this.loadComodel(this.props));
        onWillUpdateProps((next) => {
            if (!parseOptions(next.entry.value).ok) {
                this.state.raw = true;
            }
            return this.loadComodel(next);
        });
    }

    /** Load the fields of the comodel of ``props.field`` when a spec needs them. */
    async loadComodel(props) {
        const relation = props.field.relation;
        const specs = this.specsOf(props);
        if (!relation || relation === this.loadedRelation || !specs.some((spec) => spec.scope === "comodel")) {
            return;
        }
        this.loadedRelation = relation;
        try {
            this.state.comodelFields = await this.fieldService.loadFields(relation);
        } catch {
            this.state.comodelFields = {};
        }
    }

    specsOf(props) {
        return widgetOptionSpecs((props.block.attrs || {}).widget || "", props.field.type, props.viewType);
    }

    get specs() {
        return this.specsOf(this.props);
    }

    get parsed() {
        return parseOptions(this.props.entry.value);
    }

    get options() {
        return this.parsed.options;
    }

    /** Whether the form can show: fixed values and a widget that lists options. */
    get canToggle() {
        return this.parsed.ok && this.specs.length > 0;
    }

    get showRaw() {
        return this.state.raw || !this.canToggle;
    }

    /** The line under the text, or "" when the form could show. */
    get rawNote() {
        if (!this.parsed.ok) {
            return _t("These options hold expressions: edit them as text.");
        }
        if (!this.specs.length) {
            return _t("This widget lists no options: edit them as text.");
        }
        return "";
    }

    toggleRaw() {
        this.state.raw = !this.state.raw;
    }

    /** The lines of the form: [{spec, id, value, present, checked, missing}]. */
    get rows() {
        const options = this.options;
        return this.specs.map((spec, index) => {
            const present = spec.name in options;
            const value = options[spec.name];
            return {
                spec,
                id: `${this.uid}_${index}`,
                value,
                present,
                checked: present ? Boolean(value) : Boolean(spec.default),
                missing: spec.scope === "record" && present && Boolean(value) && !this.inView(value),
            };
        });
    }

    /** Whether the field ``name`` has a block in the view. */
    inView(name) {
        const root = this.props.blocks;
        return Boolean(root && findBlock(root, (block) => block.kind === "field" && block.name === name));
    }

    /** The keys of the options the widget does not list. */
    get unknownKeys() {
        const names = new Set(this.specs.map((spec) => spec.name));
        return Object.keys(this.options).filter((key) => !names.has(key));
    }

    removeLabel(key) {
        return _t("Remove %(name)s", {name: key});
    }

    /** Whether the choice ``choice`` of a selection is the value of ``row``. */
    isChosen(row, choice) {
        return row.present && deepEqual(row.value, choiceValue(choice.value));
    }

    /** [[name, label]] of the fields the field option ``spec`` may name. */
    fieldChoices(spec, current) {
        const types = spec.availableTypes;
        let entries;
        if (spec.scope === "comodel") {
            entries = Object.entries(this.state.comodelFields || {});
        } else {
            entries = Object.entries(this.props.fields).filter(
                ([name, info]) => !info.pending && name !== this.props.block.name
            );
        }
        const choices = entries
            .filter(([, info]) => !types || types.includes(info.type))
            .map(([name, info]) => [name, `${info.string || name} (${name})`])
            .sort((a, b) => a[1].localeCompare(b[1]));
        if (current && !choices.some(([name]) => name === current)) {
            // A field the list does not offer stays shown.
            choices.unshift([current, current]);
        }
        return choices;
    }

    /**
     * ``option_fields`` of ``options``: option -> scope for the field options
     * it holds.
     */
    optionFields(options) {
        const result = {};
        for (const spec of this.specs) {
            if (spec.type === "field" && spec.name in options) {
                result[spec.name] = spec.scope;
            }
        }
        return result;
    }

    /** Send ``options`` as the options of the field. */
    commit(options) {
        const value = Object.keys(options).length ? options : "";
        return this.props.editor.setNodeAttribute(this.props.block, "options", value, {
            option_fields: this.optionFields(options),
        });
    }

    /**
     * Set the option ``spec`` to ``value``: an empty value, or the default
     * of the option, removes the key.
     */
    setOption(spec, value) {
        const next = {...this.options};
        const isDefault =
            spec.type === "boolean" ? Boolean(value) === Boolean(spec.default) : deepEqual(value, spec.default);
        if (value === undefined || value === null || value === "" || isDefault) {
            delete next[spec.name];
        } else {
            next[spec.name] = value;
        }
        return this.commit(next);
    }

    onText(spec, ev) {
        return this.setOption(spec, ev.target.value.trim());
    }

    onNumber(spec, ev) {
        const text = ev.target.value.trim();
        if (!text) {
            return this.setOption(spec, "");
        }
        const value = Number(text);
        if (!Number.isFinite(value)) {
            ev.target.value = this.options[spec.name] ?? "";
            return;
        }
        return this.setOption(spec, value);
    }

    onSelect(spec, ev) {
        const raw = ev.target.value;
        return this.setOption(spec, raw ? choiceValue(raw) : "");
    }

    removeKey(key) {
        const next = {...this.options};
        delete next[key];
        return this.commit(next);
    }

    /**
     * Set the options from the text of the textarea of ``ev``. A refused
     * text leaves the payload as it was: the textarea shows again what
     * the draft holds.
     */
    async setText(ev) {
        const input = ev.target;
        const text = input.value.trim();
        const parsed = parseOptions(text);
        const optionFields = parsed.ok ? this.optionFields(parsed.options) : {};
        const extra = Object.keys(optionFields).length ? {option_fields: optionFields} : {};
        const data = await this.props.editor.setNodeAttribute(this.props.block, "options", text, extra);
        if (!data) {
            input.value = this.props.entry.value || "";
        }
        return data;
    }
}
