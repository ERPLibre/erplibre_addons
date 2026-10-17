Writes an *ERPLibre studio* project as a module, with *code_generator*.

- **Generate the module**, in the form of an applied studio project,
  writes the module into an addons repository of the running Odoo
  version: one `x_` field per new field of the project, one inherited
  view per edited view, under the external ids the database already
  uses, a readme and the dependencies read from the edited views: the
  modules of the views, of the nodes the changes locate, of the fields
  they add or name (a filter, a group-by, a date of a timeline) and of
  the view types (*web_timeline* for a timeline view).
- A new model of the project becomes a Python model of the module, with
  its `x_name`, its fields and, with a chatter, the mail mixins (the
  module then depends on *mail*). Its default form, list and search
  views, its window action and its menu go into the views file; an app
  of the project becomes a top-level menu whose icon is the icon of the
  module, the one chosen for the app.
- The access rights and record rules of the project, on its new models
  and on the existing models, go into `security/`; the rows of the other
  modules stay theirs. The modules of the groups, of the parent menus, of
  the existing models and of the fields the rule domains name become
  dependencies.
- Every regeneration rewrites the same module with the next version.
- **Install the generated module** installs it in this database.
- The generated module does not depend on *code_generator* nor on
  *ERPLibre studio*: it installs on any database.

The module installs by itself when both *erplibre_studio* and
*code_generator* are installed.
