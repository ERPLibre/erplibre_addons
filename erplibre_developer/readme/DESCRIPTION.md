Adds a **Developer panel** to the debug menu of every view. It opens a
drawer on the right side of the page, which stays usable beside it, and
follows the views the user navigates to.

- **Views & inheritance**: the view shown (id, external id, module,
  model, type, priority, mode, file and line), every view combined into
  it in the order Odoo applies them, with their module, priority, mode,
  inheritance specs (XPath and position) and own arch, then the combined
  arch.
- **Fields & modules**: each field the view shows, its type, the module
  and the file line that define it, and the modules that override it:
  a later declaration, its compute, inverse or search method, its
  onchange methods and its constraints. The origins are read from the
  classes of the model in the running server.
- **Code & repository**: for each module involved, its path, its
  versions, its git repository and the state of that repository (from
  the last *ERPLibre info* snapshot, or read on demand with
  `repo_state.py`), and its recent commits.
- **Dev actions**: upgrade a module (`-u`), reload the assets, show the
  recent commits.

Hovering a view or a field in the drawer highlights it in the page;
**Inspect** selects in the drawer the field clicked in the page.

Without an IDE opener, a file shows as `path:line` with a copy button;
*ERPLibre developer - DevOps IDE* adds an **Open in IDE** button.
