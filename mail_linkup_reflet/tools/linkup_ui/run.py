# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Play the LinkUp acceptance guide in browsers, with Selenium.

From the root of the ERPLibre checkout, with the ERPLibre venv::

    .venv.erplibre/bin/python \\
      odoo18.0/addons/ERPLibre_erplibre_addons/mail_linkup_reflet/tools/linkup_ui/run.py \\
      --out tasks/linkup_ui [--rebuild] [--headed] [--only P1,P2]

1. A template database (``<db>_tpl``) is built once by ``linkup_recette.py``
   and kept; ``--rebuild`` builds it again.
2. ``<db>`` is a fresh copy of the template, with its filestore: every
   run starts from the state the guide describes. The acceptance database
   of the owner is never opened.
3. ``linkup_recette.py --passwords-only`` gives the accounts of the copy
   new passwords; they stay in this process's memory and are never
   printed nor written.
4. Odoo serves the copy on 127.0.0.1, one worker, outgoing mail refused.
5. The sections play in the order of the guide, each in browsers of its
   personas; ``report.md``, ``report.json`` and the screenshots of the
   failures go to ``--out/<timestamp>``.
6. Odoo stops; the copy stays for inspection until the next run.

Exit code: 0 every step OK, 1 a step KO or blocked, 2 the run itself
failed (database, server).
"""

import argparse
import glob
import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import driver  # noqa: E402

TOOLS = os.path.dirname(HERE)
RECETTE = os.path.join(TOOLS, "linkup_recette.py")
# The Odoo 18 venv of the checkout; its name carries the Python version.
ODOO_VENV_GLOB = ".venv.odoo18.0_python3*/bin/python"
# The only databases the run creates, copies and drops: the copy, and
# variants of it. ``_tpl`` names the template of a copy, never a copy.
DATABASE_NAME = re.compile(r"linkup_recette_ui(_[a-z0-9_]+)?")

# The sections of the guide, in the order they build on each other.
SECTIONS = [
    ("A", "scenarios.j1_access"),
    ("P1", "scenarios.j1_p1_send"),
    ("P2", "scenarios.j1_p2_validate"),
    ("P3", "scenarios.j1_p3_precision"),
    ("P4", "scenarios.j1_p4_options"),
    ("P5", "scenarios.j1_p5_happiness"),
    ("N", "scenarios.j1_newlink"),
]

PASSWORD_LINE = re.compile(r"^  (\S+)\s.*\s(\S+)$")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-d", "--database", default="linkup_recette_ui")
    parser.add_argument("--port", type=int, default=18969)
    parser.add_argument("--out", default="linkup_ui_report")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--only", help="Sections to play, separated by commas (A,P1,...)."
    )
    parser.add_argument(
        "--keep-server",
        action="store_true",
        help="Leave Odoo running after the run (stop it with its PID).",
    )
    return parser.parse_args()


def odoo_venv():
    """The Python of the Odoo 18 venv of the checkout, the one of the highest
    Python version when several exist."""
    found = sorted(
        glob.glob(ODOO_VENV_GLOB),
        key=lambda path: tuple(int(n) for n in re.findall(r"\d+", path)),
    )
    if not found:
        raise SystemExit(
            f"No Odoo 18 venv ({ODOO_VENV_GLOB}): run from the root of the"
            " ERPLibre checkout, with Odoo 18.0 installed."
        )
    return found[-1]


def check_database_name(name):
    """Refuse any database the run may not drop."""
    if not DATABASE_NAME.fullmatch(name) or name.endswith("_tpl"):
        raise SystemExit(
            f"Refused database {name!r}: the run only plays on"
            " linkup_recette_ui or linkup_recette_ui_<suffix>, never on a"
            " template (_tpl)."
        )


def recette(database, port, *flags):
    """Run linkup_recette.py on ``database``; return its standard output,
    which holds passwords and is never printed here."""
    env = dict(os.environ, PYTHONPATH="odoo18.0/odoo")
    result = subprocess.run(
        [
            odoo_venv(),
            RECETTE,
            "-d",
            database,
            "--http-port",
            str(port),
            *flags,
        ]
        + ["--", "-c", "config.conf"],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        tail = "\n".join(result.stderr.splitlines()[-15:])
        raise SystemExit(f"linkup_recette.py failed on {database}:\n{tail}")
    return result.stdout


def database_exists(name):
    out = subprocess.run(
        [
            "psql",
            "-d",
            "postgres",
            "-At",
            "-c",
            "SELECT 1 FROM pg_database WHERE datname = '%s'" % name,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return bool(out.strip())


def data_dir():
    with open("config.conf") as fh:
        for line in fh:
            if line.startswith("data_dir"):
                return line.split("=", 1)[1].strip()
    return os.path.expanduser("~/.local/share/Odoo")


def fresh_copy(template, name):
    """Drop ``name`` and recreate it from ``template``, filestore
    included. ``name`` must pass ``check_database_name``, and nothing is
    dropped unless ``template`` exists."""
    check_database_name(name)
    if not database_exists(template):
        raise SystemExit(f"Template {template} missing: {name} kept as is.")
    subprocess.run(["dropdb", "--if-exists", name], check=True)
    subprocess.run(["createdb", "-T", template, name], check=True)
    store = os.path.join(data_dir(), "filestore")
    shutil.rmtree(os.path.join(store, name), ignore_errors=True)
    if os.path.isdir(os.path.join(store, template)):
        shutil.copytree(
            os.path.join(store, template), os.path.join(store, name)
        )


def parse_passwords(stdout):
    passwords = {}
    inside = False
    for line in stdout.splitlines():
        if line.startswith("Accounts of the acceptance database"):
            inside = True
            continue
        if inside:
            if not line.startswith("  ") or line.strip().startswith("Login"):
                if passwords and not line.startswith("  "):
                    break
                continue
            match = PASSWORD_LINE.match(line)
            if match:
                passwords[match.group(1)] = match.group(2)
    if not passwords:
        raise SystemExit("No account read from linkup_recette.py.")
    return passwords


def start_server(database, port, log_path):
    log = open(log_path, "w")
    process = subprocess.Popen(
        [
            "./run.sh",
            "-d",
            database,
            "--db-filter",
            f"^{database}$",
            "--http-port",
            str(port),
            "--http-interface",
            "127.0.0.1",
            "--smtp",
            "127.0.0.1",
            "--smtp-port",
            "1",
            "--workers",
            "0",
            "--no-database-list",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}/web/health"
    for _ in range(180):
        if process.poll() is not None:
            raise SystemExit(f"Odoo stopped at start: see {log_path}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return process
        except OSError:
            pass
        time.sleep(1)
    stop_server(process)
    raise SystemExit(f"Odoo did not answer on {url}: see {log_path}")


def stop_server(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


def main():
    options = parse_args()
    if not os.path.isfile("config.conf"):
        raise SystemExit("Run from the root of the ERPLibre checkout.")
    odoo_venv()
    check_database_name(options.database)
    template = f"{options.database}_tpl"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.abspath(os.path.join(options.out, stamp))
    os.makedirs(out_dir, exist_ok=True)

    if options.rebuild or not database_exists(template):
        print(f"Building {template} (a few minutes)…", flush=True)
        recette(template, options.port, "--replace")
    print(f"Copying {template} to {options.database}…", flush=True)
    fresh_copy(template, options.database)
    passwords = parse_passwords(
        recette(options.database, options.port, "--passwords-only")
    )

    wanted = (
        {s.strip() for s in options.only.split(",")} if options.only else None
    )
    print(f"Starting Odoo on 127.0.0.1:{options.port}…", flush=True)
    server = start_server(
        options.database, options.port, os.path.join(out_dir, "odoo.log")
    )
    run = driver.Run(
        f"http://localhost:{options.port}",
        options.database,
        passwords,
        out_dir,
        headless=not options.headed,
    )
    try:
        for code, module_name in SECTIONS:
            if wanted and code not in wanted:
                continue
            module = importlib.import_module(module_name)
            print(f"\n{module.SECTION} — {module.TITLE}", flush=True)
            run.run_section(module)
    finally:
        run.quit()
        if options.keep_server:
            print(f"Odoo keeps running, PID {server.pid}.")
        else:
            stop_server(server)
    counts = run.write_report("LinkUp J1 — recette Selenium")
    print(f"\n{counts} — {out_dir}/report.md")
    return 0 if set(counts) <= {driver.OK} else 1


if __name__ == "__main__":
    sys.exit(main())
