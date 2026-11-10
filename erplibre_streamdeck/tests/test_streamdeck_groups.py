# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase, new_test_user, tagged

USER_GROUP = "erplibre_streamdeck.group_streamdeck_user"
MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"


@tagged("post_install", "-at_install")
class TestStreamdeckGroups(TransactionCase):
    """Tout employé est utilisateur Stream Deck ; le gestionnaire l'est aussi.

    Le groupe utilisateur est impliqué par `base.group_user`, le groupe
    gestionnaire implique le groupe utilisateur, et l'administrateur est
    gestionnaire dès l'installation. Un utilisateur portail n'est ni l'un
    ni l'autre.
    """

    def test_an_employee_is_a_streamdeck_user(self):
        employee = new_test_user(
            self.env, login="zz_sd_employee", groups="base.group_user"
        )
        self.assertTrue(employee.has_group(USER_GROUP))
        self.assertFalse(employee.has_group(MANAGER_GROUP))

    def test_a_portal_user_is_not_a_streamdeck_user(self):
        portal = new_test_user(
            self.env, login="zz_sd_portal", groups="base.group_portal"
        )
        self.assertFalse(portal.has_group(USER_GROUP))
        self.assertFalse(portal.has_group(MANAGER_GROUP))

    def test_manager_implies_user(self):
        user_group = self.env.ref(USER_GROUP)
        manager_group = self.env.ref(MANAGER_GROUP)
        self.assertIn(user_group, manager_group.implied_ids)
        # Un compte qui n'a QUE le groupe gestionnaire, sans être employé,
        # reçoit le groupe utilisateur par l'implication seule.
        manager = new_test_user(
            self.env, login="zz_sd_manager", groups=MANAGER_GROUP
        )
        self.assertFalse(manager.has_group("base.group_user"))
        self.assertTrue(manager.has_group(USER_GROUP))

    def test_admin_is_manager(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(admin.has_group(MANAGER_GROUP))
        self.assertTrue(admin.has_group(USER_GROUP))
