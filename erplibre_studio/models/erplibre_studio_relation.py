# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import sql

from .. import arch as studio_arch
from .erplibre_studio_project import protected_model

# The keys of the definition of an x2many that fix its relation: they never
# change once the field is in the draft.
RELATION_KEYS = (
    "relation",
    "relation_field",
    "inverse_new",
    "relation_table",
    "column1",
    "column2",
)


class ErplibreStudioProject(models.Model):
    """The relational fields of a project: one2many (to an existing inverse
    many2one, or to one the project creates on the comodel), many2many (to
    a relation table named after the module), and the many2one."""

    _inherit = "erplibre.studio.project"

    # ── definitions ─────────────────────────────────────────────────────

    def _studio_field_definitions(self, model):
        """{name: (definition, change)} of the new fields of the project on
        ``model``: those its add_field changes add, and the inverse many2one
        a one2many of the project creates on ``model`` (with the change of
        that one2many)."""
        self.ensure_one()
        result = {}
        for change in self._project_field_changes():
            payload = change._payload()
            definition = payload.get("field") or {}
            if change.model == model:
                result[payload.get("field_name")] = (definition, change)
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse and definition.get("relation") == model:
                result.setdefault(inverse[0], (inverse[1], change))
        return result

    def _studio_inverse_definition(self, model, definition):
        """(name, definition) of the many2one the one2many ``definition``
        of ``model`` creates on its comodel, or None. What it does when its
        record is deleted comes from the comodel, whatever the payload says:
        « cascade » on a model of the project, « set null » on a model of the
        database, whose records the deletion of a record of the project must
        never take with it."""
        inverse = definition.get("inverse_new") or {}
        if definition.get("ttype") != "one2many" or not inverse.get("name"):
            return None
        comodel = definition.get("relation")
        return inverse["name"], {
            "ttype": "many2one",
            "field_description": inverse.get("field_description") or inverse["name"],
            "readonly": False,
            "help": "",
            "relation": model,
            "on_delete": (
                "cascade" if comodel in self._studio_new_models() else "set null"
            ),
        }

    def _studio_all_definitions(self):
        """[(model, name, definition, change)] of every new field of the
        project, in the order Apply creates them: the scalar fields and the
        many2one (inverse many2one included), then the many2many, then the
        one2many, whose inverse must exist first."""
        self.ensure_one()
        items = []
        for change in self._project_field_changes():
            payload = change._payload()
            definition = payload.get("field") or {}
            items.append((change.model, payload.get("field_name"), definition, change))
            inverse = self._studio_inverse_definition(change.model, definition)
            if inverse:
                items.append((definition["relation"], *inverse, change))
        rank = {"many2many": 1, "one2many": 2}
        return sorted(items, key=lambda item: rank.get(item[2].get("ttype"), 0))

    # ── one2many / many2many ────────────────────────────────────────────

    def _studio_model_label(self, model):
        line = self.new_model_ids.filtered(lambda m: m.model == model)[:1]
        if line:
            return (line.name or "").strip() or model
        return self.env["ir.model"]._get(model).name or model

    def _studio_display_field(self, comodel):
        """The field an inline sub-list of ``comodel`` shows: ``x_name`` on
        a model of the project, else the stored field of its record names,
        else ``display_name``. An editable sub-list needs a field to type
        in: a comodel that requires its name cannot take a line without
        it."""
        if comodel in self._studio_new_models():
            return "x_name"
        Comodel = self.env.get(comodel)
        field = Comodel._fields.get(Comodel._rec_name) if Comodel is not None else None
        if field is not None and field.store and field.type == "char":
            return field.name
        return "display_name"

    def _studio_inverse_choices(self, model, comodel):
        """[{name, label, pending}] of the many2one fields of ``comodel`` to
        ``model``, the inverses a one2many of ``model`` to ``comodel`` can
        take: those of the registry (or of the simulated fields of a model of
        the project not created yet), and the new many2one of the project
        on ``comodel``, inverses of other one2many included."""
        self.ensure_one()
        choices = {}
        line = self._studio_pending_line(comodel)
        if line:
            infos = self._studio_simulated_fields(line)
            for name, info in infos.items():
                if info.get("type") == "many2one" and info.get("relation") == model:
                    choices[name] = {
                        "name": name,
                        "label": info.get("string") or name,
                        "pending": True,
                    }
        elif comodel in self.env:
            for name, field in self.env[comodel]._fields.items():
                if field.type == "many2one" and field.comodel_name == model:
                    choices[name] = {
                        "name": name,
                        "label": field.string or name,
                        "pending": False,
                    }
        for name, (definition, _change) in self._studio_field_definitions(
            comodel
        ).items():
            if definition.get("ttype") == "many2one" and (
                definition.get("relation") == model
            ):
                choices.setdefault(
                    name,
                    {
                        "name": name,
                        "label": definition.get("field_description") or name,
                        "pending": True,
                    },
                )
        return sorted(choices.values(), key=lambda c: c["label"].lower())

    def _studio_proposed_field_name(self, model, comodel, label=None):
        """The name a new relational field of ``model`` labelled ``label``
        (the label of ``comodel`` when none) takes: the one Apply gives it."""
        label = (label or "").strip() or self._studio_model_label(comodel)
        return studio_arch.field_name_from_label(label, self._taken_field_names(model))

    def _studio_proposed_inverse(self, model, comodel, taken=None):
        """(name, label) of the many2one a new one2many of ``model`` to
        ``comodel`` would create on ``comodel``: « x_<model label>_id », free
        on the comodel."""
        label = self._studio_model_label(model)
        taken = self._taken_field_names(comodel) | set(taken or ())
        return studio_arch.field_name_from_label(f"{label} id", taken), label

    def _clean_one2many(self, model, name, field):
        """The relation keys of a new one2many ``name`` of ``model``: its
        comodel and its inverse, a many2one of the comodel to ``model``, or
        ``inverse_new``, the many2one the project creates on the comodel
        (``field["inverse"]`` = {create: true, name, field_description})."""
        comodel = self._clean_relation(field)
        inverse = field.get("inverse") or {}
        if not (inverse.get("create") or field.get("inverse_new")):
            relation_field = field.get("relation_field")
            names = [c["name"] for c in self._studio_inverse_choices(model, comodel)]
            if relation_field not in names:
                raise UserError(
                    self.env._(
                        "%(name)s is not a many2one of %(comodel)s to %(model)s: "
                        "choose an inverse, or let the studio create one.",
                        name=relation_field,
                        comodel=comodel,
                        model=model,
                    )
                )
            return {"relation": comodel, "relation_field": relation_field}
        if protected_model(comodel):
            raise UserError(
                self.env._(
                    "The studio does not add fields to %(model)s: choose an "
                    "existing inverse.",
                    model=comodel,
                )
            )
        inverse = inverse or field.get("inverse_new") or {}
        taken = {name} if comodel == model else set()
        proposed, label = self._studio_proposed_inverse(model, comodel, taken)
        label = (inverse.get("field_description") or "").strip() or label
        self._check_field_texts(label, "")
        inverse_name = (inverse.get("name") or "").strip() or proposed
        if inverse_name != proposed and (
            inverse_name in self._taken_field_names(comodel) or inverse_name in taken
        ):
            raise UserError(
                self.env._("The field %(name)s already exists.", name=inverse_name)
            )
        if not studio_arch.valid_field_name(inverse_name):
            raise UserError(
                self.env._(
                    "%(name)s is not a valid field name: x_ then lower case "
                    "letters, digits and underscores.",
                    name=inverse_name,
                )
            )
        on_delete = "cascade" if comodel in self._studio_new_models() else "set null"
        return {
            "relation": comodel,
            "relation_field": inverse_name,
            "inverse_new": {
                "name": inverse_name,
                "field_description": label,
                "on_delete": on_delete,
            },
        }

    def _clean_many2many(self, model, name, field):
        """The relation keys of a new many2many ``name`` of ``model``: its
        comodel, and the relation table and columns the server names
        (``arch.many2many_names``); a client value of these is ignored."""
        self.ensure_one()
        comodel = self._clean_relation(field)
        table, column1, column2 = studio_arch.many2many_names(
            self.module_name, model, comodel, name, self._studio_relation_table_names()
        )
        return {
            "relation": comodel,
            "relation_table": table,
            "column1": column1,
            "column2": column2,
        }

    def _kept_relation(self, name, field, existing):
        """The relation keys of ``existing``, the definition of the x2many
        ``name``; UserError when ``field`` changes one of them."""
        kept = {key: existing[key] for key in RELATION_KEYS if key in existing}
        for key, value in kept.items():
            if key in field and field[key] != value:
                raise UserError(
                    self.env._(
                        "The relation of the field %(name)s cannot change.", name=name
                    )
                )
        return kept

    def _studio_relation_table_names(self):
        """The table names a new many2many cannot take: the tables of the
        database, the relation tables of the fields, and those of the
        many2many in the drafts of every project."""
        self.env.cr.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        )
        taken = {row[0] for row in self.env.cr.fetchall()}
        self.env.cr.execute(
            "SELECT relation_table FROM ir_model_fields WHERE relation_table IS NOT NULL"
        )
        taken |= {row[0] for row in self.env.cr.fetchall()}
        for change in (
            self.env["erplibre.studio.change"]
            .sudo()
            .search(
                [
                    ("change_type", "=", "add_field"),
                    ("payload", "ilike", "relation_table"),
                ]
            )
        ):
            table = (change._payload().get("field") or {}).get("relation_table")
            if table:
                taken.add(table)
        return taken

    def _studio_check_inverse_removal(self, changes):
        """Raise UserError when ``changes`` (add_field changes of the project
        that leave the draft) hold a one2many whose new inverse another
        one2many of the project, which stays, takes as its inverse."""
        self.ensure_one()
        staying = self._project_field_changes() - changes
        for change in changes.filtered(lambda c: c.change_type == "add_field"):
            definition = change._payload().get("field") or {}
            inverse = self._studio_inverse_definition(change.model, definition)
            if not inverse:
                continue
            for other in staying:
                other_def = other._payload().get("field") or {}
                if (
                    other_def.get("ttype") == "one2many"
                    and other_def.get("relation") == definition["relation"]
                    and other_def.get("relation_field") == inverse[0]
                    and not other_def.get("inverse_new")
                ):
                    raise UserError(
                        self.env._(
                            "The field %(field)s creates %(inverse)s, the inverse "
                            "of %(other)s: remove %(other)s first.",
                            field=change.field_name,
                            inverse=f"{definition['relation']}.{inverse[0]}",
                            other=f"{other.model}.{other.field_name}",
                        )
                    )

    def _studio_inverse_dependents(self, changes):
        """``changes`` (changes of the project that leave the draft) with the
        changes of the project that show a many2one one of their one2many
        creates on its comodel (``inverse_new``), and the changes that
        depend on the nodes these add, until none is added: the inverse
        leaves the draft with its one2many."""
        self.ensure_one()
        result = changes
        todo = changes
        while todo:
            names = {}
            for change in todo.filtered(lambda c: c.change_type == "add_field"):
                definition = change._payload().get("field") or {}
                inverse = self._studio_inverse_definition(change.model, definition)
                if inverse:
                    names.setdefault(definition["relation"], set()).add(inverse[0])
            found = self._studio_changes_of_fields(names) if names else changes.browse()
            todo = found - result
            result |= found
        return result

    def _studio_check_relations(self):
        """Raise UserError when a relational field of the draft no longer
        applies: its comodel left the registry and the project, the inverse
        of a one2many is no longer a many2one to its model, the table of a
        many2many is too long or taken by another field."""
        self.ensure_one()
        new_models = self._studio_new_models()
        Fields = self.env["ir.model.fields"].sudo()
        tables = {}
        for model, name, definition, _change in self._studio_all_definitions():
            ttype = definition.get("ttype")
            relation = definition.get("relation")
            if ttype not in ("many2one", *studio_arch.X2MANY_TYPES):
                continue
            label = f"{model}.{name}"
            Comodel = self.env.get(relation) if relation else None
            if relation not in new_models and (
                Comodel is None or Comodel._transient or Comodel._abstract
            ):
                raise UserError(
                    self.env._(
                        "The comodel %(model)s of the field %(name)s does not "
                        "exist.",
                        model=relation,
                        name=label,
                    )
                )
            if ttype == "one2many" and not definition.get("inverse_new"):
                names = [
                    c["name"] for c in self._studio_inverse_choices(model, relation)
                ]
                if definition.get("relation_field") not in names:
                    raise UserError(
                        self.env._(
                            "The inverse %(inverse)s of the field %(name)s is no "
                            "longer a many2one to %(model)s.",
                            inverse=definition.get("relation_field"),
                            name=label,
                            model=model,
                        )
                    )
            if ttype == "one2many" and definition.get("inverse_new"):
                if protected_model(relation):
                    raise UserError(
                        self.env._(
                            "The studio does not add fields to %(model)s: choose "
                            "an existing inverse.",
                            model=relation,
                        )
                    )
            if ttype == "many2many":
                table = definition.get("relation_table") or ""
                columns = (definition.get("column1"), definition.get("column2"))
                own = Fields.search(
                    [
                        ("model", "=", model),
                        ("name", "=", name),
                        ("relation_table", "=", table),
                    ],
                    limit=1,
                )
                if (
                    len(table) > studio_arch.TABLE_NAME_SIZE
                    or not studio_arch.valid_field_name(table)
                    or not all(studio_arch.valid_column_name(c) for c in columns)
                    or columns[0] == columns[1]
                    # A table of the database, which the field would write
                    # into, and drop with the field.
                    or (not own and sql.table_exists(self.env.cr, table))
                ):
                    raise UserError(
                        self.env._(
                            "%(table)s is not a valid relation table for the "
                            "field %(name)s.",
                            table=table,
                            name=label,
                        )
                    )
                other = Fields.search(
                    [
                        ("relation_table", "=", table),
                        "!",
                        "&",
                        ("model", "=", model),
                        ("name", "=", name),
                    ],
                    limit=1,
                )
                if table in tables or other:
                    raise UserError(
                        self.env._(
                            "The relation table %(table)s of the field %(name)s "
                            "is used by another field.",
                            table=table,
                            name=label,
                        )
                    )
                tables[table] = label
