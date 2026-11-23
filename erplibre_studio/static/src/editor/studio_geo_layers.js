/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUpdateProps, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";

// The colors a colored range starts from: the defaults of base_geoengine.
export const GEO_BEGIN_COLOR = "#ffffff";
export const GEO_END_COLOR = "#ff680a";
// The bounds of the number of classes (GEO_CLASS_RANGE of the server).
export const GEO_CLASS_RANGE = [1, 20];

/**
 * The form of a new vector layer of the GeoEngine view ``added`` (the
 * ``added`` of the payload): its first geo field, drawn as it is, shown
 * when the map opens.
 */
export function newGeoLayer(added) {
    const [geoField, label] = (added.geo_fields || [])[0] || ["", ""];
    return {
        id: false,
        kind: "vector",
        sequence: false,
        name: label,
        geo_field: geoField,
        geo_repr: "basic",
        attribute_field: "",
        classification: "unique",
        nb_class: 5,
        begin_color: GEO_BEGIN_COLOR,
        end_color: GEO_END_COLOR,
        active_on_startup: true,
    };
}

/**
 * The values ``save_geo_layer`` receives for the form ``form``: the
 * colored range only for a colored layer, ``sequence`` only when given.
 */
export function geoLayerValues(form) {
    const values = {
        name: (form.name || "").trim(),
        geo_field: form.geo_field || false,
        geo_repr: form.geo_repr,
        active_on_startup: Boolean(form.active_on_startup),
    };
    if (form.id) {
        values.id = form.id;
    }
    if (form.sequence) {
        values.sequence = form.sequence;
    }
    if (form.geo_repr === "colored") {
        Object.assign(values, {
            attribute_field: form.attribute_field || false,
            classification: form.classification || "unique",
            nb_class: Number(form.nb_class) || 0,
            begin_color: form.begin_color || false,
            end_color: form.end_color || false,
        });
    }
    return values;
}

/**
 * The inspector of a layer of a GeoEngine view the project adds: the form
 * of a vector layer (``layerId`` « new » for a new one), its place among
 * the vector layers, its removal; the background shows read only. The
 * editor saves through ``save_geo_layer`` and removes through
 * ``remove_geo_layer``.
 */
export class StudioGeoLayers extends Component {
    static template = "erplibre_studio.GeoLayers";
    static props = {
        editor: Object,
        // The payload of the editor (get_editor_data).
        data: Object,
        // The id of the layer shown, or « new ».
        layerId: [Number, String],
        busy: {type: Boolean, optional: true},
    };

    setup() {
        this.state = useState({form: this.formOf(this.props)});
        onWillUpdateProps((next) => {
            const layer = this.layerOf(next);
            const form = this.state.form;
            if (next.layerId !== this.props.layerId || (layer && form.id === layer.id && !this.dirty)) {
                this.state.form = this.formOf(next);
            }
        });
    }

    get added() {
        return (this.props.data.view && this.props.data.view.added) || {};
    }

    /** The layer ``props.layerId`` of the payload, or null (« new », gone). */
    layerOf(props) {
        const added = (props.data.view && props.data.view.added) || {};
        return (added.layers || []).find((layer) => layer.id === props.layerId) || null;
    }

    get layer() {
        return this.layerOf(this.props);
    }

    formOf(props) {
        if (props.layerId === "new") {
            return newGeoLayer((props.data.view && props.data.view.added) || {});
        }
        const layer = this.layerOf(props);
        if (!layer) {
            return null;
        }
        return {
            ...layer,
            // The place is sent only by a move.
            sequence: false,
            attribute_field: layer.attribute_field || "",
            classification: layer.classification || "unique",
            nb_class: layer.nb_class || 5,
            begin_color: layer.begin_color || GEO_BEGIN_COLOR,
            end_color: layer.end_color || GEO_END_COLOR,
        };
    }

    /** Whether the form differs from the layer of the payload. */
    get dirty() {
        const layer = this.layer;
        const form = this.state.form;
        if (!layer || !form) {
            return Boolean(form);
        }
        const saved = geoLayerValues(this.formOf(this.props));
        return JSON.stringify(geoLayerValues(form)) !== JSON.stringify(saved);
    }

    get isNew() {
        return this.props.layerId === "new";
    }

    get isBackground() {
        return Boolean(this.layer && this.layer.kind === "raster");
    }

    get title() {
        if (this.isNew) {
            return _t("New layer");
        }
        return this.layer ? this.layer.name : "";
    }

    get kindLabel() {
        return this.isBackground ? _t("Background layer") : _t("Layer of a geo field");
    }

    get geoFields() {
        return this.added.geo_fields || [];
    }

    get attributeFields() {
        return this.added.attribute_fields || [];
    }

    get representations() {
        return [
            ["basic", _t("Basic")],
            ["colored", _t("Colored range")],
        ];
    }

    /** The classifications, those that need a number off for another attribute. */
    get classifications() {
        const numeric = this.attributeNumeric;
        return [
            {value: "unique", label: _t("Unique value"), disabled: false},
            {value: "interval", label: _t("Interval"), disabled: !numeric},
            {value: "quantile", label: _t("Quantile"), disabled: !numeric},
        ];
    }

    get attributeNumeric() {
        const entry = this.attributeFields.find((item) => item[0] === this.state.form.attribute_field);
        return Boolean(entry && entry[2]);
    }

    get classRange() {
        return GEO_CLASS_RANGE;
    }

    /**
     * The fields the layer reads that the view does not load yet: Save
     * loads them, the map reads them from the records.
     */
    get loadNote() {
        const form = this.state.form;
        if (!form || this.isBackground) {
            return "";
        }
        const loaded = (this.props.data.layout && this.props.data.layout.loaded_fields) || [];
        const names = [form.geo_field, form.geo_repr === "colored" && form.attribute_field].filter(
            (name) => name && !loaded.includes(name)
        );
        if (!names.length) {
            return "";
        }
        return _t("Save also loads %(fields)s in the view: the map reads them from the records.", {
            fields: names.join(", "),
        });
    }

    /** The vector layers of the view in their order. */
    get vectors() {
        return (this.added.layers || []).filter((layer) => layer.kind === "vector");
    }

    /** The vector layer before (``step`` -1) or after (1) this one, or null. */
    neighbour(step) {
        const vectors = this.vectors;
        const index = vectors.findIndex((layer) => layer.id === this.props.layerId);
        if (index < 0) {
            return null;
        }
        return vectors[index + step] || null;
    }

    get canRemove() {
        return Boolean(this.layer) && !this.isBackground && this.vectors.length > 1;
    }

    setForm(key, value) {
        this.state.form[key] = value;
        if (key === "attribute_field" && !this.attributeNumeric) {
            this.state.form.classification = "unique";
        }
    }

    async save() {
        const form = this.state.form;
        if (!form || this.props.busy) {
            return;
        }
        await this.props.editor.saveGeoLayer(geoLayerValues(form));
    }

    /** Swap the layer with its neighbour ``step`` (-1 up, 1 down). */
    async move(step) {
        const other = this.neighbour(step);
        if (!other || this.props.busy) {
            return;
        }
        await this.props.editor.saveGeoLayer(geoLayerValues({...this.formOf(this.props), sequence: other.sequence}));
    }

    remove() {
        if (this.layer) {
            this.props.editor.removeGeoLayer(this.layer);
        }
    }

    close() {
        this.props.editor.selectGeoLayer(null);
    }
}
