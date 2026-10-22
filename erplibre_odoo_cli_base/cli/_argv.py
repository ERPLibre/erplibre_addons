# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Argument helpers of the ``db`` command.

Pure standard library: nothing here imports odoo, so the functions are
testable from any Python without an Odoo environment.
"""

import os

# Value-taking options of the global part of Odoo's ``db`` parser, the part
# written before the subcommand.
GLOBAL_VALUE_OPTIONS = (
    "-c",
    "--config",
    "-D",
    "--data-dir",
    "--addons-path",
    "-r",
    "--db_user",
    "-w",
    "--db_password",
    "--pg_path",
    "--db_host",
    "--db_port",
    "--db_sslmode",
)

IMAGE_SUBCOMMANDS = ("load", "dump")


def split_subcommand(cmdargs):
    """Return the index of the subcommand in ``cmdargs``, or None.

    The subcommand is the first token that is neither an option nor the
    value of one of GLOBAL_VALUE_OPTIONS. ``--option=value`` is one token.
    None means there is no subcommand, or ``-h``/``--help`` comes before it.
    """
    index = 0
    while index < len(cmdargs):
        token = cmdargs[index]
        if token in ("-h", "--help"):
            return None
        if not token.startswith("-"):
            return index
        index += 2 if token in GLOBAL_VALUE_OPTIONS else 1
    return None


def has_image_option(args):
    """Tell whether ``args`` carries ``--image`` in either spelling."""
    return any(a == "--image" or a.startswith("--image=") for a in args)


def resolve_image(value):
    """Return the zip file named by an ``--image`` value.

    ``.zip`` is appended unless already there. A value containing ``/`` is
    a path and is kept as is; a bare name lives in ``./image_db/``,
    relative to the current directory.
    """
    if not value.endswith(".zip"):
        value += ".zip"
    if "/" in value:
        return value
    return os.path.join(".", "image_db", value)


def replace_image_option(sub, args):
    """Turn ``--image NAME`` into the positional Odoo expects.

    ``args`` are the tokens after the ``load`` or ``dump`` subcommand. The
    option is removed and the resolved zip becomes the last positional:
    the dump file of ``load``, the dump path of ``dump``. It goes right
    after the last token that is not an option, else at the end. Odoo's
    ``load`` declares an optional ``database`` before ``dump_file``, so an
    option between the two positionals makes argparse bind the database
    name to ``dump_file``: ``DB --image X -n`` gives ``DB ZIP -n``, never
    ``DB -n ZIP``. The options of load and dump take no value, so every
    token that does not start with ``-`` is a positional. A ``load``
    without database positional gets Odoo's default database name, the
    file stem, which is the image name.

    Raises ValueError when the value is missing or the option is repeated.
    ``args`` without ``--image``, or a ``sub`` other than load/dump, come
    back unchanged.
    """
    if sub not in IMAGE_SUBCOMMANDS or not has_image_option(args):
        return list(args)
    result = []
    image = None
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--image" or token.startswith("--image="):
            if image is not None:
                raise ValueError("--image given twice")
            if token == "--image":
                if index + 1 >= len(args):
                    raise ValueError("--image needs a value")
                image = args[index + 1]
                index += 2
            else:
                image = token[len("--image=") :]
                index += 1
            if not image:
                raise ValueError("--image needs a value")
            continue
        result.append(token)
        index += 1
    positions = [i for i, t in enumerate(result) if not t.startswith("-")]
    at = positions[-1] + 1 if positions else len(result)
    result.insert(at, resolve_image(image))
    return result
