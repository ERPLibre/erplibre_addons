# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Rewrite, from the data files, the requirements whose text changed in
this version.

The data files are noupdate: an upgrade creates the records it does not
find and leaves the others as they are, so a requirement rewritten since
would keep its former text, and a proof its former reference. The
records listed in REWRITTEN are loaded again from their file, a hand
edit of them included; every other record keeps its own. Their
translations are dropped but for en_US, so that the loading of the
catalogs that follows this script fills them from the new texts.
"""

import copy

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL
from odoo.tools.convert import xml_import
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck_devops_requirement"

# Data file -> XML ids of its records rewritten in this version.
REWRITTEN = {
    "data/requirement_inventory.xml": ("test_sd_inv_r24_1",),
    "data/requirement_control.xml": (
        "req_sd_ctl_r27",
        "test_sd_ctl_r27_1",
        "req_sd_ctl_r43",
    ),
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for filename, xmlids in REWRITTEN.items():
        path = file_path("%s/%s" % (MODULE, filename))
        kept = etree.Element("odoo")
        for record in etree.parse(path).getroot().iter("record"):
            if record.get("id") in xmlids:
                kept.append(copy.deepcopy(record))
        xml_import(
            env, MODULE, {}, "init", noupdate=True, xml_filename=path
        ).parse(kept)
        for xmlid in xmlids:
            _keep_english_only(env.ref("%s.%s" % (MODULE, xmlid)))


def _keep_english_only(record):
    """Drop the translations of the translated fields of `record`, the
    en_US value kept."""
    record.flush_recordset()
    for name, field in record._fields.items():
        if field.translate is not True or not field.store:
            continue
        record.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = jsonb_build_object('en_US', %s->'en_US')"
                " WHERE id = %s AND %s IS NOT NULL",
                SQL.identifier(record._table),
                SQL.identifier(name),
                SQL.identifier(name),
                record.id,
                SQL.identifier(name),
            )
        )
    record.invalidate_recordset()
