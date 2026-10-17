Writes an *ERPLibre studio* project as a module, with *code_generator*.

- **Generate the module**, in the form of an applied studio project,
  writes the module into an addons repository of the running Odoo
  version: one `x_` field per new field of the project, one inherited
  view per edited view, under the external ids the database already
  uses, a readme and the dependencies read from the edited views.
- Every regeneration rewrites the same module with the next version.
- **Install the generated module** installs it in this database.
- The generated module does not depend on *code_generator* nor on
  *ERPLibre studio*: it installs on any database.

The module installs by itself when both *erplibre_studio* and
*code_generator* are installed.
