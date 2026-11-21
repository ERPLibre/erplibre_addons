A drag-and-drop editor of views whose changes become a module: form,
list, kanban, search and pivot views, and timeline views once
*web_timeline* is installed.

- **Customize this view**, in the debug menu of a view and in the header
  of the *Developer panel*, opens the editor on that view;
  **Customize the search view** opens it on the search view of the page.
  In the editor, the view type selector opens the default view of
  another type of the same model, in the same project.
- The editor shows the view as blocks: groups, notebook pages, columns
  and fields. Fields move by drag and drop; the palette adds existing
  fields of the model and new `x_` fields (text, integer, decimal,
  checkbox, date, date and time, selection, many2one, multiline text,
  HTML, monetary, one2many, many2many). The side panel edits the label,
  the tooltip, required, read-only, hidden, and for a list the optional
  column; for a new field, its selection values or its comodel.
- **Kanban**: the card is drawn from its template, with a drop zone
  between its nodes; the fields and the ribbon of the card, the widget of
  a field, and the options of the view (default grouping and order, quick
  create, group actions), set in the side panel when no node is selected.
  A field the card only reads stays loaded: hiding a field of the card
  makes it invisible, it does not remove it. Nothing drops into a node
  whose QWeb directive replaces its content (`t-esc`, `t-out`, `t-set`,
  `t-call`), and the `t-if` or `t-elif` of a chain is never hidden.
- **Search**: three columns, the fields to search, the filters and the
  group-by entries. A new filter is built in a small form from
  conditions (a field, an operator and a value) joined by AND, a
  many2one compared by name, a date and time typed in local time; a field
  dropped on the group-by column groups by it, by period for a date.
  Hiding a filter removes it.
- **Pivot**: one lane per axis, rows, columns and measures; a field
  dragged from the palette or from another lane lands on that axis, by
  period for a date. A lane refuses a field that cannot go on its axis.
- **Timeline**: the start and stop dates, the grouping (by a many2one or
  a many2many field: web_timeline makes one row per record), the colors
  (from a field, an operator and a value; neither a many2one nor a date
  and time), the scale, and the fields of the item template. A field
  dropped into the item shows its value (`record.<field>`, the name of a
  many2one) and is loaded by the view: the item template renders without
  the record of a kanban card, where a `<field>` does not compile.
- Each change is recorded in a **studio project**, as a draft. **Preview**
  shows the real view with the draft applied, to the editor of the
  project only.
- **Apply** creates the `x_` models and fields, their views, actions and
  menus, the access rights and rules, and one inherited view per edited
  view in the database; applying again updates them, and removes what the
  draft no longer has. **Discard** goes back to the last Apply, **Revert**
  removes from the database what the project created, the records of its
  models with them. A model another project or a module still uses (a
  field pointing at it, a view or a right on it) is not removed.
- **New models**: a project creates `x_` models. Each one comes with a
  `x_name`, a form, a list and a search view, a window action, a menu and
  an access row for the internal users, all editable afterwards like any
  other view or right. Its menu goes in an app of the project, a
  top-level menu with an icon taken from an installed module, or under an
  existing menu; a project has as many apps as it needs. With *mail*
  installed, a model can get a chatter (messages, followers and
  activities); once applied, the chatter stays. The editor creates a model
  from a dialog and lists the models of the project in its side panel; the
  form, list and search views of a model are edited before Apply creates
  it, and Apply puts the changes on the views it creates.
- **Relations**: a one2many takes an existing many2one of its comodel as
  its inverse, or the studio creates one on the comodel (deleted with the
  record when the comodel is a model of the project); a many2many gets a
  relation table named after the module. In a form, both show as a
  sub-list; in a list or a kanban, a many2many shows as tags.
- **Groups**: each app of a project is a category of groups; a group of
  the project implies other groups of the project (a manager implies the
  users) and existing groups, and is given to the users in their usual
  form, as one selection when the groups of the app imply each other in a
  chain. The access grid and the record rules name them as any group.
- **Preview of a model not created yet**: the *simulation*, the default,
  renders its views in the browser from the draft and writes nothing,
  on any database; once the draft is *approved*, the *real* preview
  creates the model inside a savepoint, renders its views as Odoo
  validates them, and rolls everything back.
- **Confirmations**: Revert, and an Apply that removes records, values or
  group members, first list what leaves the database (models with their
  record counts, fields with their values, views, menus, rights, rules,
  groups with their members); uninstalling a module a project generated
  shows the same report in the uninstall dialog of Odoo, which asks
  « I understand » first.
- **Access rights and record rules**: a grid of groups and rights (read,
  write, create, delete) on the models of the project and on existing
  models, shown next to the rights other modules give on them, and record
  rules (a domain, groups, operations) checked against the fields of
  their model; the editor shows both instead of the view. A rule names
  its groups, or is checked *Global* for every user.
- **ERPLibre studio generate** (`erplibre_studio_generate`) writes a
  project as a module with *code_generator*; this module does not need
  it.
