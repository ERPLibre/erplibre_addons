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
  views, its window action and its menu go into the views file; each app
  of the project that a model goes in becomes a top-level menu, with a
  copy of the icon chosen for it in `static/description/`; the icon of
  the first app is the icon of the module.
- The one2many, many2many and many2one fields of the project keep their
  relation: the inverse of a one2many (the many2one the studio creates on
  its comodel included, on a new or an existing model), the relation
  table and columns of a many2many, which the module then owns, and what
  a many2one does when its record is deleted.
- The groups of the project go into `security/erplibre_studio_groups.xml`,
  the first data file: the category of each app that has groups, then
  each group after the groups it implies. An upgrade sets exactly the
  groups the project gives each group to imply; the users keep their
  groups.
- The access rights and record rules of the project, on its new models
  and on the existing models, go into `security/`; the rows of the other
  modules stay theirs; a row or a rule on a group of the project names
  the group of the module. The modules of the groups, of the groups the
  groups of the project imply, of the parent menus, of the existing models
  and of the fields the rule domains name become dependencies.
- Every regeneration rewrites the same module with the next version.
- **Install the generated module** installs it in this database.
- The generated module does not depend on *code_generator* nor on
  *ERPLibre studio*: it installs on any database.

The module installs by itself when both *erplibre_studio* and
*code_generator* are installed.
