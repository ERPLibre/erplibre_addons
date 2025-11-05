import logging
import subprocess

# from odoo import http
# from odoo.addons.web_settings_dashboard.controllers.main import (
#     WebSettingsDashboard,
# )
#
# _logger = logging.getLogger(__name__)
#
#
# class WebSettingsDashboardERPLibre(WebSettingsDashboard):
#     @http.route("/web_settings_dashboard/data", type="json", auth="user")
#     def web_settings_dashboard_data(self, **kw):
#         res = super(
#             WebSettingsDashboardERPLibre, self
#         ).web_settings_dashboard_data()
#         if res:
#             share = res.get("share")
#             if share:
#                 try:
#                     share["server_erplibre_commit"] = subprocess.check_output(
#                         ["git", "describe", "--tags"]
#                     ).strip()
#                 except Exception as e:
#                     _logger.error(e)
#                     try:
#                         # Try force safe.directory with git config
#                         subprocess.check_output(
#                             [
#                                 "git",
#                                 "config",
#                                 "--global",
#                                 "safe.directory",
#                                 "/ERPLibre",
#                             ]
#                         ).strip()
#                         share[
#                             "server_erplibre_commit"
#                         ] = subprocess.check_output(
#                             ["git", "describe", "--tags"]
#                         ).strip()
#                     except Exception as e:
#                         share["server_erplibre_commit"] = "ERROR".encode(
#                             "utf-8"
#                         )
#         return res
