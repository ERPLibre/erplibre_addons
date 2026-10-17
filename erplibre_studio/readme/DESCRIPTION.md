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
  HTML, monetary). The side panel edits the label, the tooltip, required,
  read-only, hidden, and for a list the optional column; for a new field,
  its selection values or its comodel.
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
- **Apply** creates the `x_` fields and one inherited view per edited view
  in the database; applying again updates them. **Discard** goes back to
  the last Apply, **Revert** removes the fields and views of the project
  from the database.
- **ERPLibre studio generate** (`erplibre_studio_generate`) writes a
  project as a module with *code_generator*; this module does not need
  it.
