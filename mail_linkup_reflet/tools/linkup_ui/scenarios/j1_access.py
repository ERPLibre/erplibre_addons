# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §4: access checks A1 to A5, before the journeys."""

import re

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from driver import StepFailure

SECTION = "A"
TITLE = "Contrôles d'accès (guide §4)"

APPS_TOGGLE = (
    ".o_navbar_apps_menu .dropdown-toggle, .o_navbar_apps_menu button"
)
APP = ".o-dropdown--menu .o_app, .o-dropdown--menu .dropdown-item"


LINE = ".o-linkup-MyPoints-line"
RULE_FILTER = ".o-linkup-MyPoints-filterRule"
PERSON_FILTER = ".o-linkup-MyPoints-filterCounterpart"
# The rule and the person the history of Sam is filtered on: three calls
# of the demonstration pay ``call_answered``, and France is the
# counterpart of four of his lines.
FILTER_RULE = "call_answered"
FILTER_PERSON = "france"
SAM_BALANCE = 2700
FIRE_THRESHOLD = 10000


def visible_apps(persona):
    """The names of the app switcher, which closes again with Escape."""
    persona.click(APPS_TOGGLE)
    persona.find(APP)
    names = sorted(
        {e.text.strip() for e in persona.finds(APP) if e.text.strip()}
    )
    persona.keys(Keys.ESCAPE)
    persona.wait_gone(".o-dropdown--menu")
    return names


def digits(text):
    return re.sub(r"\D", "", text)


def sam_lines(run, where=""):
    """``[(rule code, counterpart login)]`` of the ledger lines of Sam,
    sorted, restricted by the SQL condition ``where``."""
    rows = run.sql(
        "SELECT r.code, coalesce(p.login, '') FROM linkup_points_ledger l"
        " JOIN res_users u ON u.id = l.user_id"
        " JOIN linkup_points_rule r ON r.id = l.rule_id"
        " LEFT JOIN res_users p ON p.id = l.partner_user_id"
        f" WHERE u.login = 'sam' {where}"
    )
    return sorted((code, login) for code, login in rows)


def shown_lines(persona):
    """``[(rule code, counterpart name)]`` of the history shown, sorted."""
    return sorted(
        (
            line.get_attribute("data-code"),
            line.find_element(
                "css selector", ".o-linkup-MyPoints-lineCounterpart"
            ).text.strip(),
        )
        for line in persona.finds(LINE)
    )


def wait_history(persona, expected, names, what):
    """Wait until the history shows exactly the lines ``expected`` (rule
    code, counterpart login), each login read as its name in ``names``."""
    wanted = sorted((code, names.get(login, "—")) for code, login in expected)
    last = {}

    def holds(_driver):
        last["shown"] = shown_lines(persona)
        return last["shown"] == wanted

    try:
        persona.wait_until(holds, what)
    except StepFailure:
        raise StepFailure(
            f"{what} : affiché {last.get('shown')}, attendu {wanted}"
        ) from None


def section_items(persona, section):
    """The entries under the top menu ``section`` of the current app."""
    persona.click(
        ".o_menu_sections .dropdown-toggle, .o_menu_sections button", section
    )
    persona.find(".o-dropdown--menu .dropdown-item")
    items = [
        e.text.strip()
        for e in persona.finds(".o-dropdown--menu .dropdown-item")
    ]
    return items


def a1(run):
    sam = run.persona("sam")
    sam.find(".o-linkup-RefletView")
    apps = visible_apps(sam)
    run.check(apps == ["Discussion"], f"applications visibles : {apps}")


def a2(run):
    sam = run.persona("sam")
    items = section_items(sam, "LinkUp")
    for name in ("Vue Reflet", "Mes points", "Aide"):
        run.check(name in items, f"« {name} » absent du menu LinkUp : {items}")
    run.check("Points" not in items, f"« Points » visible : {items}")
    run.memory["a2_items"] = items
    return ", ".join(items)


def a3(run):
    sam = run.persona("sam")
    sam.click(".o-dropdown--menu .dropdown-item", "Mes points")
    balance = sam.text(".o-linkup-MyPoints-balanceValue")
    run.check(
        digits(balance) == str(SAM_BALANCE),
        f"solde : {balance!r}, attendu {SAM_BALANCE}",
    )
    rank = sam.text(".o-linkup-MyPoints-rankName")
    run.check(rank == "Flamme", f"rang : {rank!r}, attendu Flamme")
    fire = run.sql(
        "SELECT karma_min FROM gamification_karma_rank WHERE name->>'fr_CA' = 'Feu'"
    )
    run.check(
        fire == [[str(FIRE_THRESHOLD)]],
        f"seuil du rang Feu : {fire}, le guide dit 10 000",
    )
    nxt = sam.text(".o-linkup-MyPoints-nextRank")
    to_go = FIRE_THRESHOLD - SAM_BALANCE
    run.check(
        "Feu" in nxt and digits(nxt) == str(to_go),
        f"prochain rang : {nxt!r}, attendu Feu dans {to_go} points",
    )
    badges = [
        e.text.strip() for e in sam.finds(".o-linkup-MyPoints-badgeName")
    ]
    run.check(any(badges), f"aucun badge affiché : {badges!r}")

    names = {
        login: name
        for login, name in run.sql(
            "SELECT u.login, p.name FROM res_users u JOIN res_partner p ON p.id = u.partner_id"
        )
    }
    everything = sam_lines(run)
    run.check(everything, "aucune ligne de points de Sam en base")
    wait_history(sam, everything, names, "historique complet")

    by_rule = sam_lines(run, f"AND r.code = '{FILTER_RULE}'")
    run.check(
        0 < len(by_rule) < len(everything),
        f"lignes {FILTER_RULE} de Sam : {by_rule}",
    )
    Select(sam.find(RULE_FILTER)).select_by_value(FILTER_RULE)
    wait_history(
        sam, by_rule, names, f"historique filtré sur l'événement {FILTER_RULE}"
    )
    Select(sam.find(RULE_FILTER)).select_by_value("")
    wait_history(sam, everything, names, "historique sans filtre d'événement")

    by_person = sam_lines(run, f"AND p.login = '{FILTER_PERSON}'")
    run.check(
        0 < len(by_person) < len(everything),
        f"lignes de Sam avec {FILTER_PERSON} : {by_person}",
    )
    Select(sam.find(PERSON_FILTER)).select_by_visible_text(
        names[FILTER_PERSON]
    )
    wait_history(
        sam, by_person, names, f"historique filtré sur {names[FILTER_PERSON]}"
    )
    Select(sam.find(PERSON_FILTER)).select_by_value("")
    wait_history(sam, everything, names, "historique sans filtre de personne")
    return (
        f"solde {balance} ; {nxt} ; badges {badges} ; historique {len(everything)} lignes,"
        f" {len(by_rule)} {FILTER_RULE}, {len(by_person)} avec {names[FILTER_PERSON]}"
    )


def a4(run):
    admin = run.persona("linkup_admin")
    apps = visible_apps(admin)
    run.check(apps == ["Discussion"], f"applications visibles : {apps}")
    if not admin.has(".o_menu_brand", "Discussion"):
        admin.goto("/odoo/discuss")
        admin.wait_webclient()
    items = section_items(admin, "LinkUp")
    for name in ("Règles de points", "Registre des points"):
        run.check(
            any(name in i for i in items), f"« {name} » absent : {items}"
        )
    return ", ".join(items)


def a5(run):
    admin = run.persona("linkup_admin")
    admin.click(".o-dropdown--menu .dropdown-item", "Registre des points")
    admin.find(".o_list_view .o_data_row")
    rows = run.sql(
        "SELECT count(*), count(*) FILTER (WHERE capped) FROM linkup_points_ledger"
    )
    total, capped = int(rows[0][0]), int(rows[0][1])
    run.check(total > 0, "registre vide")
    run.check(capped == 0, f"{capped} ligne(s) capped en base")
    shown = len(admin.finds(".o_list_view .o_data_row"))
    pager = admin.text(".o_pager_limit")
    run.check(
        shown == total and digits(pager) == str(total),
        f"liste : {shown} lignes, total du pager {pager!r} ; en base {total}",
    )
    ticked = [
        box.is_selected()
        for box in admin.driver.find_elements(
            "css selector",
            ".o_list_view .o_data_row td[name='capped'] input[type='checkbox']",
        )
    ]
    run.check(
        len(ticked) == total,
        f"colonne capped : {len(ticked)} cases pour {total} lignes",
    )
    run.check(
        not any(ticked), f"colonne capped : {sum(ticked)} case(s) cochée(s)"
    )

    # The filter "Plafonné" of the search panel keeps no line.
    admin.click(".o_searchview_dropdown_toggler")
    admin.click(
        ".o_filter_menu .o-dropdown-item, .o_filter_menu .dropdown-item",
        "Plafonné",
    )
    admin.find_text(".o_searchview_facet", "Plafonné")
    admin.wait_until(
        lambda _d: not admin.finds(".o_list_view .o_data_row"),
        "aucune ligne sous le filtre Plafonné",
    )
    admin.keys(Keys.ESCAPE)
    admin.click(".o_searchview_facet .o_facet_remove")
    admin.wait_until(
        lambda _d: len(admin.finds(".o_list_view .o_data_row")) == total,
        f"{total} lignes sans filtre",
    )
    return f"{total} lignes affichées (pager {pager}), aucune case capped ; filtre Plafonné : 0 ligne"


STEPS = [
    (
        "A1",
        "sam arrive sur la Vue Reflet ; seule l'application Discussion",
        a1,
    ),
    (
        "A2",
        "Discussion › LinkUp : Vue Reflet, Mes points, Aide ; pas de Points",
        a2,
    ),
    (
        "A3",
        "Mes points : 2700, Flamme, prochain rang Feu 10 000, badges, filtres",
        a3,
    ),
    (
        "A4",
        "linkup_admin : Discussion seulement ; Règles de points, Registre des points",
        a4,
    ),
    ("A5", "Registre des points : lignes de la démo, aucune capped", a5),
]
