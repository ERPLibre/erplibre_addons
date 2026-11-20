# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The modules an ERPLibre checkout suggests for a database.

``conf/module_list_image_db_odoo.json`` describes the database images that
``script/database/image_db.py`` builds: ``{image: definition}``, where a
definition holds ``image_list``, a list of ``{"module": [names]}``, and
``base``, the name of the image it starts from or "". The image
``odoo<series>_base`` is the base every ERPLibre database of that series
starts from: its modules are the suggested ones.

Nothing here touches Odoo: the functions read the file and walk the
definitions only.
"""

import json
import os

CONFIG_FILE = os.path.join("conf", "module_list_image_db_odoo.json")


class SuggestionError(Exception):
    """The configuration cannot give the modules of an image. ``code``
    names the case, ``value`` the file or image it concerns."""

    def __init__(self, code, value):
        super().__init__(f"{code}: {value}")
        self.code = code
        self.value = value


def image_name(series):
    """The base image of the Odoo ``series`` (« 18.0 »): « odoo18.0_base »."""
    return f"odoo{series}_base"


def read_config(root):
    """The image configuration of the checkout ``root``.

    Raises SuggestionError « missing » when the file does not exist,
    « unreadable » when it cannot be read or is not a JSON object.
    """
    path = os.path.join(root, CONFIG_FILE)
    if not os.path.isfile(path):
        raise SuggestionError("missing", CONFIG_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SuggestionError("unreadable", CONFIG_FILE) from error
    if not isinstance(data, dict):
        raise SuggestionError("unreadable", CONFIG_FILE)
    return data


def _own_entries(definition):
    """The ``image_list`` entries that build the image itself.

    ``image_db.py`` installs the entries one after the other in the same
    database and dumps it after each: an entry without ``pkg_name`` dumps
    the image, one with ``pkg_name`` a derived image « <image>_<pkg_name> ».
    The image therefore holds every entry up to the last one without
    ``pkg_name``.
    """
    entries = [
        e for e in definition.get("image_list") or [] if isinstance(e, dict)
    ]
    last = max(
        (i for i, entry in enumerate(entries) if not entry.get("pkg_name")),
        default=-1,
    )
    return entries[: last + 1]


def image_modules(config, image):
    """The module names of ``image`` in ``config``: those of the image its
    ``base`` names first, recursively, then the ``module`` and ``theme`` of
    its own entries, in file order. A name listed twice keeps its first
    place.

    Raises SuggestionError « unknown_image » when ``image`` or one of its
    bases is not in ``config``, « cycle » when a base leads back to an
    image already met.
    """
    chain = []
    name = image
    while name:
        if name in chain:
            raise SuggestionError("cycle", name)
        definition = config.get(name)
        if not isinstance(definition, dict):
            raise SuggestionError("unknown_image", name)
        chain.append(name)
        name = definition.get("base") or ""
    modules = []
    for name in reversed(chain):
        for entry in _own_entries(config[name]):
            names = list(entry.get("module") or [])
            if entry.get("theme"):
                names.append(entry["theme"])
            for module in names:
                if (
                    isinstance(module, str)
                    and module
                    and module not in modules
                ):
                    modules.append(module)
    return modules
