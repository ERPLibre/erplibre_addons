# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §5 P2: Jacques receives the reflection Sam sent in P1 and
confirms it ("C'est un lien !"); France rejects the reflection of Sam
that waits for her in the demonstration ("Cet échange n'a pas eu lieu").

Builds on ``run.memory["p1_reflet_id"]`` and ``["p1_channel_id"]``, left
by P1, and on the browser of Jacques that P1.4 opened before the sending,
his sounds recorded. Leaves ``run.memory["p2_rejected_id"]``, the
reflection France rejected.
"""

from selenium.webdriver.common.keys import Keys

from driver import StepFailure
from .j1_p1_send import ensure_reflet_view, open_reflet_view, quote, user

SECTION = "P2"
TITLE = "Le destinataire reçoit et valide (guide §5 P2)"

VIEW = ".o-linkup-RefletView"
CONTACT = ".o-linkup-RefletView-contact"
RECEIVED = ".o-mail-Message .o-linkup-RefletCard[data-kind='initial'][data-role='recipient']"
BUTTONS = {
    ".o-linkup-RefletActions-confirm": "C'est un lien !",
    ".o-linkup-RefletActions-reject": "Cet échange n'a pas eu lieu",
    ".o-linkup-RefletActions-inaccurate": "Ce n'est pas ce que j'ai dit",
    ".o-linkup-RefletActions-ignore": "Ignorer",
}
AUTHORED = ".o-mail-Message .o-linkup-RefletCard[data-kind='initial'][data-role='author']"
COMPOSER = ".o-mail-Composer-input"
RANK_SPARK = "Étincelle"
BADGE_FIRST_LINK = "Premier lien"


def reflet_row(run, reflet_id):
    """``(state, read_date is null, understood)`` of a reflection."""
    return run.sql(
        "SELECT state, read_date IS NULL, coalesce(understood, '')"
        f" FROM linkup_reflet WHERE id = {int(reflet_id)}"
    )[0]


def ledger_of(run, reflet_id):
    """``[(login, rule code, points, cap reason)]`` of every ledger line of
    a reflection, sorted; the cap reason is "" for a line paid in full.
    Two lines of the same login and rule stay two entries."""
    rows = run.sql(
        "SELECT u.login, r.code, l.points, coalesce(l.cap_reason, '')"
        " FROM linkup_points_ledger l"
        " JOIN res_users u ON u.id = l.user_id"
        " JOIN linkup_points_rule r ON r.id = l.rule_id"
        f" WHERE l.reflet_id = {int(reflet_id)}"
    )
    return sorted(
        (login, code, int(points), reason)
        for login, code, points, reason in rows
    )


def rank_of(run, login):
    rows = run.sql(
        "SELECT coalesce(k.name->>'fr_CA', k.name->>'en_US') FROM res_users u"
        " LEFT JOIN gamification_karma_rank k ON k.id = u.rank_id"
        f" WHERE u.login = {quote(login)}"
    )
    return rows[0][0] if rows else None


def has_badge(run, login, xmlid_name):
    rows = run.sql(
        "SELECT count(*) FROM gamification_badge_user bu"
        " JOIN res_users u ON u.id = bu.user_id"
        " JOIN ir_model_data d ON d.res_id = bu.badge_id"
        " AND d.model = 'gamification.badge'"
        " AND d.module = 'mail_linkup_gamification'"
        f" WHERE u.login = {quote(login)} AND d.name = {quote(xmlid_name)}"
    )
    return int(rows[0][0]) > 0


def sound_enabled(run, login):
    """The LinkUp sound setting of ``login``; a member without settings
    has the default, on."""
    rows = run.sql(
        "SELECT s.linkup_sound_enabled FROM res_users_settings s"
        " JOIN res_users u ON u.id = s.user_id"
        f" WHERE u.login = {quote(login)}"
    )
    return not rows or rows[0][0] != "f"


def card_holding(persona, css, text):
    """The visible card matching ``css`` whose "J'ai compris que" holds
    ``text``."""

    def found(_driver):
        for card in persona.finds(css):
            for part in card.find_elements(
                "css selector", ".o-linkup-RefletCard-understood"
            ):
                if text in part.text:
                    return card
        return False

    return persona.wait_until(found, f"carte {css} « {text} »")


def click_in(persona, element, css):
    """Click the descendant ``css`` of ``element``."""
    target = element.find_element("css selector", css)
    persona.js("arguments[0].scrollIntoView({block: 'center'});", target)
    target.click()
    return target


def open_chat_with(persona, contact_user_id, name):
    """From the Reflet view, open the direct conversation with a contact:
    the notifications that cover the contacts are closed first, and the
    first-use tour Discuss starts is skipped."""
    persona.close_notifications()
    persona.click(
        f"{CONTACT}[data-user-id='{contact_user_id}'] .o-linkup-RefletView-openChat"
    )
    persona.find(f".o-mail-Discuss-threadName[title='{name}']")
    persona.pass_tour()


def p2_1(run):
    reflet_id = run.memory["p1_reflet_id"]
    sam_id, _pid, _name = user(run, "sam")
    run.check(
        "jacques" in run.personas,
        "Jacques n'était pas connecté à l'envoi de P1.4 : le son « reçu » n'a pas pu être enregistré",
    )
    jacques = run.persona("jacques")
    open_reflet_view(jacques)
    jacques.find(CONTACT)
    first = jacques.finds(CONTACT)[0]
    first_id = first.get_attribute("data-user-id")
    names = [
        e.text.strip() for e in jacques.finds(".o-linkup-RefletView-name")
    ]
    run.check(
        first_id == str(sam_id),
        f"premier contact : utilisateur {first_id} ({names[:1]}), attendu Sam ({sam_id}) ; contacts : {names}",
    )
    unread = first.find_elements("css selector", ".o-linkup-RefletView-unread")
    run.check(
        unread, f"Sam en tête mais sans marque « non lu » ; contacts : {names}"
    )
    label = unread[0].text.strip()
    run.check(
        label == "Non lus : 1",
        f"marque non lu de Sam : {label!r}, attendu « Non lus : 1 »",
    )
    state, unread_db, _ = reflet_row(run, reflet_id)
    run.check(
        (state, unread_db) == ("sent", "t"),
        f"reflet {reflet_id} : état {state}, non lu {unread_db}",
    )
    # The carrier message reached Jacques while he was logged in: its
    # sound plays as it arrives, under the sound setting of Jacques.
    if sound_enabled(run, "jacques"):
        jacques.wait_until(
            lambda _d: any(
                "linkup_received" in source
                for source in jacques.played_sounds()
            ),
            "son « reçu » joué chez Jacques à l'arrivée du reflet",
        )
        return f"Sam en tête, « {label} » ; son « reçu » joué à l'arrivée du reflet"
    run.settle()
    played = jacques.played_sounds()
    run.check(
        not any("linkup_received" in source for source in played),
        f"son « reçu » joué alors que Jacques a coupé les sons : {played}",
    )
    return f"Sam en tête, « {label} » ; sons coupés pour Jacques, aucun son « reçu »"


def check_arrow(run, persona, card, card_css, key, button_css):
    """Press ``key`` on the card and check that it clicks ``button_css``.
    The keyboard reaches the card: Shift+Tab from the composer, unless the
    card holds the focus already. A capture listener on the window takes
    that click before the button sees it, so the reflection keeps its
    state. Return the number of Shift+Tab pressed."""
    persona.js(
        """
        const [selector] = arguments;
        window.__linkupArrowClick = null;
        window.addEventListener("click", function stop(ev) {
            const button = ev.target.closest && ev.target.closest(selector);
            if (button) {
                window.__linkupArrowClick = selector;
                ev.stopPropagation();
                ev.preventDefault();
                window.removeEventListener("click", stop, true);
            }
        }, true);
        """,
        button_css,
    )
    presses = 0
    if not persona.js("return document.activeElement === arguments[0];", card):
        persona.click(COMPOSER)
        presses = persona.tab_to(card_css, reverse=True)
    run.check(
        persona.js("return document.activeElement === arguments[0];", card),
        "le focus atteint une autre carte que celle du reflet",
    )
    persona.keys(key)
    persona.wait_until(
        lambda d: d.execute_script("return window.__linkupArrowClick;")
        == button_css,
        f"{key!r} sur la carte presse {button_css}",
    )
    return presses


def p2_2(run):
    reflet_id = run.memory["p1_reflet_id"]
    sam_id, _pid, sam_name = user(run, "sam")
    jacques = run.persona("jacques")
    open_chat_with(jacques, sam_id, sam_name)
    _state, _unread, understood = reflet_row(run, reflet_id)
    css = f"{RECEIVED}[data-state='sent']"
    card = card_holding(jacques, css, understood)
    you_said = card.find_elements(
        "css selector", ".o-linkup-RefletCard-youSaid"
    )
    run.check(
        you_said and you_said[0].is_displayed(),
        "carte repliée : « Tu m'as dit » absent",
    )
    jacques.find(f"{css} .o-linkup-RefletActions[data-mode='validate']")
    for selector, label in BUTTONS.items():
        buttons = card.find_elements("css selector", selector)
        run.check(
            buttons and buttons[0].is_displayed(),
            f"bouton « {label} » absent ({selector})",
        )
        text = buttons[0].text
        run.check(
            label in text, f"bouton {selector} : {text!r}, attendu « {label} »"
        )
    shortcuts = card.get_attribute("aria-keyshortcuts") or ""
    run.check(
        {"ArrowRight", "ArrowLeft"} <= set(shortcuts.split()),
        f"raccourcis de la carte : {shortcuts!r}",
    )
    presses = check_arrow(
        run,
        jacques,
        card,
        css,
        Keys.ARROW_RIGHT,
        ".o-linkup-RefletActions-confirm",
    )
    check_arrow(
        run,
        jacques,
        card,
        css,
        Keys.ARROW_LEFT,
        ".o-linkup-RefletActions-reject",
    )
    state, _unread, _ = reflet_row(run, reflet_id)
    run.check(
        state == "sent",
        f"les flèches interceptées ont changé l'état : {state}",
    )

    # Guide P1.5: once Jacques has read the card, Sam can no longer
    # withdraw it.
    jacques.wait_until(
        lambda _d: reflet_row(run, reflet_id)[1] == "f",
        f"lecture du reflet {reflet_id} inscrite en base",
    )
    sam = run.persona("sam")
    author_card = card_holding(
        sam, f"{AUTHORED}[data-state='sent']", understood
    )
    sam.wait_until(
        lambda _d: not author_card.find_elements(
            "css selector", ".o-linkup-RefletActions-withdraw"
        ),
        "chez Sam, « Retirer ce reflet » n'est plus offert une fois le reflet lu",
    )
    return (
        f"carte dépliée, 4 boutons ; carte atteinte par {presses} Maj+Tab depuis le composeur ;"
        " → presse « C'est un lien ! », ← « Cet échange n'a pas eu lieu » (clic intercepté) ;"
        " reflet lu, « Retirer ce reflet » retiré chez Sam"
    )


def expect_bursts(run, persona, wanted, what):
    """Wait until every ``(kind, points, text)`` of ``wanted`` was shown;
    ``points`` None matches a rank or a badge."""

    def holds(record):
        shown = record["bursts"]
        return all(
            any(
                b["kind"] == kind
                and (points is None or b["points"] == points)
                and text in b["text"]
                for b in shown
            )
            for kind, points, text in wanted
        )

    try:
        return persona.wait_points(holds, what)
    except StepFailure:
        raise StepFailure(
            f"{what} ; vu : {persona.recorded_points()}"
        ) from None


def p2_3(run):
    reflet_id = run.memory["p1_reflet_id"]
    jacques = run.persona("jacques")
    sam = run.persona("sam")
    karma = {login: run.points(login) for login in ("sam", "jacques")}
    run.check(
        not has_badge(run, "jacques", "badge_first_link"),
        "Jacques a déjà le badge « Premier lien » avant de confirmer",
    )
    sam.record_points()
    jacques.record_points()
    _state, _unread, understood = reflet_row(run, reflet_id)
    card = card_holding(jacques, f"{RECEIVED}[data-state='sent']", understood)
    click_in(jacques, card, ".o-linkup-RefletActions-confirm")
    card_holding(jacques, f"{RECEIVED}[data-state='confirmed']", understood)

    run.check(
        reflet_row(run, reflet_id)[0] == "confirmed",
        "reflet non confirmé en base",
    )
    lines = ledger_of(run, reflet_id)
    expected = [
        ("jacques", "reflect_confirmed", 1000, ""),
        ("sam", "reflect_confirmed", 1000, ""),
        ("sam", "reflect_sent", 100, ""),
    ]
    run.check(
        lines == expected,
        f"registre du reflet {reflet_id} : {lines}, attendu {expected}",
    )
    after = {login: run.points(login) for login in karma}
    delta = {login: after[login] - karma[login] for login in karma}
    run.check(
        delta == {"sam": 1100, "jacques": 1000},
        f"points : {karma} → {after} (écart {delta}, attendu sam +1100, jacques +1000)",
    )
    rank = rank_of(run, "jacques")
    run.check(
        rank == RANK_SPARK, f"rang de Jacques : {rank!r}, attendu {RANK_SPARK}"
    )
    run.check(
        has_badge(run, "jacques", "badge_first_link"),
        "badge « Premier lien » non accordé à Jacques",
    )

    expect_bursts(
        run,
        jacques,
        [
            ("gain", 1000, "C'est un lien !"),
            ("rank", None, f"Nouveau rang : {RANK_SPARK}"),
            ("badge", None, f"Nouveau badge : {BADGE_FIRST_LINK}"),
        ],
        "chez Jacques : +1000, rang Étincelle et badge Premier lien annoncés",
    )
    expect_bursts(
        run,
        sam,
        [
            ("gain", 1000, "C'est un lien !"),
            ("gain", 100, "Ton reflet est confirmé"),
        ],
        "chez Sam : +1000 et +100 affichés",
    )
    return f"points {karma} → {after} ; Jacques : rang {rank}, badge {BADGE_FIRST_LINK}"


def pending_from_sam(run):
    """``(id, category code, understood)`` of the reflection of Sam
    waiting for France."""
    rows = run.sql(
        "SELECT r.id, c.code, coalesce(r.understood, '') FROM linkup_reflet r"
        " JOIN linkup_category c ON c.id = r.category_id"
        " JOIN res_users a ON a.id = r.author_id"
        " JOIN res_users b ON b.id = r.recipient_id"
        " WHERE a.login = 'sam' AND b.login = 'france'"
        " AND r.kind = 'initial' AND r.state = 'sent' ORDER BY r.id"
    )
    return rows


def p2_4(run):
    pending = pending_from_sam(run)
    run.check(
        len(pending) == 1, f"reflets de Sam en attente chez France : {pending}"
    )
    reflet_id, code, understood = pending[0]
    run.check(
        code == "emotions",
        f"catégorie du reflet en attente : {code}, attendu emotions",
    )
    sam_id, _pid, sam_name = user(run, "sam")
    karma = {login: run.points(login) for login in ("sam", "france")}
    run.check(
        ledger_of(run, reflet_id) == [],
        f"registre du reflet {reflet_id} déjà rempli",
    )

    france = run.persona("france")
    ensure_reflet_view(france)
    open_chat_with(france, sam_id, sam_name)
    run.persona("sam").record_points()
    card = card_holding(france, f"{RECEIVED}[data-state='sent']", understood)
    click_in(france, card, ".o-linkup-RefletActions-reject")
    france.find_text(".modal .modal-body", sam_name)
    france.click(
        ".modal .o-linkup-RejectDialog-confirm", "Cet échange n'a pas eu lieu"
    )
    france.wait_gone(".modal .o-linkup-RejectDialog-confirm")
    card = card_holding(
        france, f"{RECEIVED}[data-state='rejected']", understood
    )
    badge = card.find_element(
        "css selector", ".o-linkup-RefletCard-badge"
    ).text.strip()
    run.check(badge == "Rejeté", f"badge de la carte rejetée : {badge!r}")

    state = reflet_row(run, reflet_id)[0]
    run.check(state == "rejected", f"état du reflet {reflet_id} : {state}")
    lines = ledger_of(run, reflet_id)
    expected = [("sam", "reflect_rejected", -150, "")]
    run.check(
        lines == expected,
        f"registre du reflet {reflet_id} : {lines}, attendu {expected} (rien pour France)",
    )
    after = {login: run.points(login) for login in karma}
    delta = {login: after[login] - karma[login] for login in karma}
    run.check(
        delta == {"sam": -150, "france": 0},
        f"points : {karma} → {after} (écart {delta}, attendu sam −150, france 0)",
    )
    expect_bursts(
        run,
        run.persona("sam"),
        [("loss", -150, "")],
        "chez Sam : −150 affiché",
    )
    run.memory["p2_rejected_id"] = int(reflet_id)
    return f"reflet {reflet_id} rejeté, badge « {badge} » ; points {karma} → {after}"


STEPS = [
    (
        "P2.1",
        "jacques, Vue Reflet : Sam en tête des contacts, marqué non lu ; son « reçu » si les sons sont actifs",
        p2_1,
    ),
    (
        "P2.2",
        "Conversation avec Sam : carte dépliée, 4 boutons ; → / ← = les deux premiers",
        p2_2,
    ),
    (
        "P2.3",
        "« C'est un lien ! » : +1000 Jacques (rang Étincelle), Sam +1000 et +100 ; badge « Premier lien » (Jacques)",
        p2_3,
    ),
    (
        "P2.4",
        "france rejette le reflet Émotions de Sam : −150 pour Sam, rien pour France ; carte « rejeté »",
        p2_4,
    ),
]
