A drag-and-drop editor of form and list views whose changes become a
module.

- **Customize this view**, in the debug menu of a form or a list and in
  the header of the *Developer panel*, opens the editor on that view.
- The editor shows the view as blocks: groups, notebook pages, columns
  and fields. Fields move by drag and drop; the palette adds existing
  fields of the model and new `x_` fields (text, integer, decimal,
  checkbox, date, date and time, selection, many2one, multiline text,
  HTML, monetary). The side panel edits the label, the tooltip, required,
  read-only, hidden, and for a list the optional column; for a new field,
  its selection values or its comodel.
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
