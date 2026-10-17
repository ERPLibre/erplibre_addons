1. Activate the developer mode.
2. On any view, open the debug menu (the bug icon) and choose
   **Developer panel**.
3. Hover a view or a field to see it in the page; click the crosshair to
   inspect, then click a field of the page.
4. The **Code & repository** tab reads the repositories when it is
   opened: **Read the clones** reads them again with `repo_state.py`
   instead of the last snapshot.
5. **Upgrade (-u)** opens the confirmation of *ERPLibre info*: the module
   is marked to upgrade and the server restarts, so the upgrade runs at
   the next start with the code on disk. **Reload the assets** deletes the
   generated bundles and reloads the page.
6. Without a clipboard (a page not served over HTTPS nor from
   localhost), the copy button shows the path in a selected field of the
   panel, to copy by hand.
