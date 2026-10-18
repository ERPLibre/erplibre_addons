/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useSubEnv} from "@odoo/owl";
import {dialogService} from "@web/core/dialog/dialog_service";
import {_t} from "@web/core/l10n/translation";
import {formatDateTime, deserializeDateTime} from "@web/core/l10n/dates";
import {registry} from "@web/core/registry";
import {View} from "@web/views/view";

// The methods of the orm service a preview forwards to the server for a
// model of the database: they read, never write.
export const READ_METHODS = [
    "fields_get",
    "get_views",
    "name_search",
    "web_name_search",
    "read",
    "web_read",
    "search_read",
    "web_search_read",
    "search_count",
    "read_group",
    "web_read_group",
];
// The view types of the preview of a model not created yet (MODEL_VIEW_TYPES).
export const PREVIEW_VIEW_TYPES = ["form", "list", "search"];

/** A call of the preview that would write: nothing is saved. */
export class PreviewWriteError extends Error {
    constructor(model, method) {
        super(`Preview: ${model}.${method} is not sent.`);
        this.name = "PreviewWriteError";
        this.model = model;
        this.method = method;
    }
}

/** The field a view of the pending model ``model`` of ``data`` shows when the answer has none: its name. */
function nameField(data, model) {
    const fields = (data.models[model] || {}).fields || {};
    return "x_name" in fields ? "x_name" : "display_name";
}

/**
 * The views of ``model``, a model of ``data`` not created yet, that
 * ``requested`` ([[id, type]] of get_views) names: those of the answer for
 * the model previewed, else a view that shows its name (the sub-lists and
 * the dialogs of its comodels).
 */
export function pendingViews(data, model, requested = []) {
    const own = model === data.model ? data.views : {};
    const name = nameField(data, model);
    const fallback = {
        form: `<form><sheet><group><field name="${name}"/></group></sheet></form>`,
        list: `<list><field name="${name}"/></list>`,
        kanban: `<kanban><templates><t t-name="card"><field name="${name}"/></t></templates></kanban>`,
        search: `<search><field name="${name}"/></search>`,
    };
    const views = {...own};
    for (const [, type] of requested) {
        if (!views[type] && fallback[type]) {
            views[type] = {arch: fallback[type], id: false};
        }
    }
    return views;
}

/**
 * The answer of the preview to ``onchange`` on ``model``, a model of the
 * database the preview shows a sub-list of: an empty value for each field
 * of ``spec`` it knows, never a call (the inverse of a one2many of the
 * preview does not exist on the server).
 */
export function localOnchange(data, model, spec = {}) {
    const fields = (data.models[model] || {}).fields || {};
    const value = {};
    for (const name of Object.keys(spec || {})) {
        if (fields[name]) {
            value[name] = ["one2many", "many2many"].includes(fields[name].type) ? [] : false;
        }
    }
    return {value};
}

/**
 * The answer of the preview to ``method`` on ``model``, a model of
 * ``data`` not created yet: no record, the defaults of a new one.
 */
export function pendingAnswer(data, model, method, args = [], kwargs = {}) {
    switch (method) {
        case "onchange":
            return {value: {...((data.model_defaults || {})[model] || {})}};
        case "web_search_read":
            return {length: 0, records: []};
        case "web_read_group":
            return {groups: [], length: 0};
        case "read_progress_bar":
            return {};
        case "search_count":
            return 0;
        case "fields_get":
            return {...((data.models[model] || {}).fields || {})};
        case "get_views":
            return {models: data.models, views: pendingViews(data, model, kwargs.views)};
        case "search_read":
        case "read_group":
        case "name_search":
        case "web_name_search":
        case "read":
        case "web_read":
        case "search":
            return [];
        default:
            throw new PreviewWriteError(model, method);
    }
}

/**
 * The orm service of a preview: ``orm`` whose ``call``, through which
 * every method of the service goes, answers the models of ``data`` not
 * created yet (``data.pending_models``) itself, forwards the reads of the
 * other models (READ_METHODS), answers their ``onchange`` itself
 * (``localOnchange``) and throws a PreviewWriteError on anything else. No
 * call of the preview writes to the database.
 */
export function previewOrm(orm, data) {
    const pending = new Set(data.pending_models || []);
    const shim = Object.create(orm);
    shim.call = async function (model, method, args = [], kwargs = {}) {
        if (pending.has(model)) {
            return pendingAnswer(data, model, method, args, kwargs);
        }
        if (method === "onchange") {
            return localOnchange(data, model, args[3]);
        }
        if (READ_METHODS.includes(method)) {
            return orm.call.call(this, model, method, args, kwargs);
        }
        throw new PreviewWriteError(model, method);
    };
    shim.isPreview = true;
    return shim;
}

/**
 * The view service of a preview: ``view`` (the view service of the web
 * client) for the models of the database, the views of ``pendingViews``
 * for the models of ``data`` not created yet, which get_views does not
 * know.
 */
export function previewViewService(view, data) {
    const pending = new Set(data.pending_models || []);
    return {
        async loadViews(params, options = {}) {
            if (!pending.has(params.resModel)) {
                return view.loadViews(params, options);
            }
            const views = pendingViews(data, params.resModel, params.views);
            return {
                fields: (data.models[params.resModel] || {}).fields || {},
                relatedModels: data.models,
                views: Object.fromEntries(
                    Object.entries(views).map(([type, v]) => [type, {arch: v.arch, id: v.id || false}])
                ),
            };
        },
    };
}

/** The env of the web client that ``env`` comes from: the env a dialog gets. */
function rootEnv(env) {
    let root = env;
    for (;;) {
        const parent = Object.getPrototypeOf(root);
        if (!parent || parent === Object.prototype || !("services" in parent)) {
            return root;
        }
        root = parent;
    }
}

/**
 * The services of a preview: those of ``env`` with the orm and the view
 * service of the preview (``previewOrm``, ``previewViewService``), and a
 * dialog service whose dialogs get them too. The dialog service of the web
 * client mounts its dialogs with the env of the web client: a dialog opened
 * from a field of the preview (create a record of its comodel, choose
 * records of it) would reach the server with the real orm.
 */
export function previewServices(env, data) {
    const services = {...env.services};
    services.orm = previewOrm(env.services.orm, data);
    services.view = previewViewService(env.services.view, data);
    // The env of the web client is frozen: its services are shadowed by a
    // property of the env of the dialogs, not assigned.
    const dialogEnv = Object.create(rootEnv(env), {services: {value: services, enumerable: true}});
    const overlay = {
        add: (component, props, options = {}) =>
            env.services.overlay.add(component, props, {...options, env: dialogEnv}),
    };
    services.dialog = dialogService.start(dialogEnv, {overlay});
    return services;
}

/** A PreviewWriteError reaches the user as a notification, not as an error dialog. */
export function previewWriteErrorHandler(env, error, originalError) {
    if (originalError instanceof PreviewWriteError) {
        env.services.notification.add(_t("Preview: nothing is saved."), {type: "warning"});
        return true;
    }
    return false;
}

registry.category("error_handlers").add("erplibre_studio_preview_write", previewWriteErrorHandler, {sequence: 1});

/**
 * The props of the View of a preview answer ``data`` (the shape of
 * get_views) for ``viewType``: the arch and the fields given, so that the
 * View loads nothing; a search view shows above the list.
 */
export function previewViewProps(data, viewType) {
    const fields = data.models[data.model].fields;
    const search = data.views.search || {arch: "<search/>"};
    const props = {
        resModel: data.model,
        type: viewType,
        arch: (data.views[viewType] || {}).arch,
        fields,
        relatedModels: data.models,
        searchViewArch: search.arch,
        searchViewFields: fields,
        irFilters: [],
        actionMenus: {},
        loadIrFilters: false,
        loadActionMenus: false,
        context: {},
        display: {controlPanel: false},
    };
    if (viewType === "form") {
        props.resId = false;
    } else if (viewType === "list") {
        props.useSampleModel = true;
    } else if (viewType === "search") {
        Object.assign(props, {type: "list", arch: data.views.list.arch, useSampleModel: true, display: {}});
    }
    return props;
}

/**
 * The preview of a model of the project not created yet, rendered from the
 * answer ``data`` of ``get_model_preview``: « simulation », computed from
 * the draft, or « real », rendered by the server from the model created in
 * a savepoint then rolled back. Either way the model does not exist: the
 * orm of the preview (``previewOrm``) answers its records itself and
 * saves nothing.
 */
export class StudioModelPreview extends Component {
    static template = "erplibre_studio.ModelPreview";
    static components = {View};
    static props = {
        data: Object,
        viewType: String,
        mode: String,
        line: Object,
        project: Object,
        busy: {type: Boolean, optional: true},
        onView: Function,
        onApprove: Function,
        onUnapprove: Function,
        onClose: Function,
    };

    setup() {
        if (!this.props.data.error) {
            useSubEnv({services: previewServices(this.env, this.props.data)});
        }
        this.viewTypes = PREVIEW_VIEW_TYPES;
    }

    /** The mode the server rendered the preview in; the one asked for when it answered an error without one. */
    get renderedMode() {
        return this.props.data.mode || this.props.mode;
    }

    get isReal() {
        return this.renderedMode === "real";
    }

    get modeLabel() {
        return this.isReal ? _t("Real (rolled back)") : _t("Simulation");
    }

    /** Why the preview on screen is not in the mode asked for, or "". */
    get modeMismatch() {
        if (this.renderedMode === this.props.mode) {
            return "";
        }
        return this.isReal
            ? _t("The server rendered the real preview, not the simulation asked for.")
            : _t("The server rendered the simulation, not the real preview asked for.");
    }

    get panelId() {
        return `o_erplibre_studio_preview_panel_${this.props.line.id}`;
    }

    get viewProps() {
        return previewViewProps(this.props.data, this.props.viewType);
    }

    viewTypeLabel(viewType) {
        return {form: _t("Form"), list: _t("List"), search: _t("Search")}[viewType] || viewType;
    }

    get approvedText() {
        const project = this.props.project;
        if (!project.approved_by) {
            return "";
        }
        const date = project.approved_date ? formatDateTime(deserializeDateTime(project.approved_date)) : "";
        return _t("Approved by %(user)s on %(date)s", {user: project.approved_by[1], date});
    }
}
