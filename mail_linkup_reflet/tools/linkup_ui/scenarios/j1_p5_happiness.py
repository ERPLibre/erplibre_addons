# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §5 P5: "Tu ajoutes à mon bonheur", France puts Sam in the light.

France puts Sam in the light from the happiness field of her Reflet view,
with the keyboard: Tab reaches the field, Enter opens the list of her
contacts, walked with the arrows, where Enter chooses. Sam sees the halo on his avatar, the
avatar of France hooked to it and the notification. The next exchange
puts the light out with no point: a message of Sam in their
conversation, then a call of Sam once France puts him in the light again
from the LinkUp panel. Last, a highlight leaves both screens when France
withdraws it, and when Sam hides it; the one France withdraws comes from
a drag of the field onto Sam, with the pointer of the browser.

A highlight carries no point: every step checks that no ledger line of
Sam or France appears, except the line ``call_answered`` of the call
that France answers, which the call pays on its own.

Builds on the pair Sam–France of the demonstration; earlier sections
leave no highlight. Leaves no active highlight.
"""

from driver import StepFailure
from selenium.webdriver.common.keys import Keys

from .j1_p1_send import open_reflet_view, user
from .j1_p2_validate import open_chat_with
from .j1_p3_precision import reward_sounds
from .j1_p4_options import answer_call, hang_up

SECTION = "P5"
TITLE = "Tu ajoutes à mon bonheur (guide §5 P5)"

VIEW_BODY = ".o-linkup-RefletView .o-linkup-RefletView-body"
CONTACT = ".o-linkup-RefletView-contact"
HAPPINESS = ".o-linkup-RefletView-happiness"
HAPPINESS_LIST = ".o-linkup-RefletView-happinessList"
HAPPINESS_OPTION = f"{HAPPINESS_LIST} .o-linkup-RefletView-option"
HAPPINESS_NOTICE = ".o-linkup-RefletView-happinessNotice"
SELF_AVATAR = ".o-linkup-RefletView-selfAvatar"
HIGHLIGHTS = ".o-linkup-RefletView-highlights"
HIGHLIGHTS_AVATAR = f"{HIGHLIGHTS} .o-linkup-Highlights-avatar"
SUN = ".o-linkup-RefletView-highlightedByMe"
PANEL_BUTTON = ".o-mail-Discuss-header button[name='linkup-panel']"
PANEL = ".o-linkup-Panel-content"
PANEL_HIGHLIGHT = f"{PANEL} .o-linkup-Panel-highlightButton"
PANEL_CONFIRM = f"{PANEL} .o-linkup-Panel-highlightConfirm"
PANEL_WITHDRAW = f"{PANEL} .o-linkup-Panel-highlightWithdraw"
PANEL_RECEIVED = f"{PANEL} .o-linkup-Panel-highlightReceived"
CALL_BUTTON = ".o-mail-Discuss-header button[name='call']"
COMPOSER = ".o-mail-Composer-input"

SAM_MESSAGE = "Merci pour ton soleil, ça me fait chaud au cœur."
HINT = ".o-linkup-RefletView-hint"


def happiness_notice(name):
    """The notice of the happiness field once ``name`` is in the light."""
    return (
        f"{name} voit ton avatar sur le sien jusqu'à votre prochain échange."
    )


# State in the database ---------------------------------------------


def highlights(run):
    """``[id, sender, recipient, active, context, channel id, reason]`` of
    every highlight between Sam and France, oldest first."""
    return run.sql(
        "SELECT h.id, s.login, r.login, h.active::text, h.context,"
        " coalesce(h.channel_id::text, ''), coalesce(h.extinguished_reason, '')"
        " FROM linkup_highlight h JOIN res_users s ON s.id = h.sender_id"
        " JOIN res_users r ON r.id = h.recipient_id"
        " WHERE ARRAY[s.login, r.login]::text[] <@ ARRAY['sam', 'france']"
        " ORDER BY h.id"
    )


def active_highlights(run):
    return [row for row in highlights(run) if row[3] == "true"]


def wait_active(run, persona, context, channel_id=""):
    """Wait for the single active highlight France → Sam and check how it
    was sent; return its id."""
    persona.wait_until(
        lambda _d: active_highlights(run), "mise en lumière active en base"
    )
    rows = active_highlights(run)
    expected = ["france", "sam", "true", context, str(channel_id)]
    run.check(
        len(rows) == 1 and rows[0][1:6] == expected,
        f"mises en lumière actives : {rows}, attendu une seule {expected}",
    )
    return rows[0][0]


def wait_out(run, persona, highlight_id, reason):
    """Wait until the highlight is out, and check its reason."""
    persona.wait_until(
        lambda _d: not active_highlights(run),
        f"mise en lumière {highlight_id} éteinte en base",
    )
    row = [r for r in highlights(run) if r[0] == highlight_id][0]
    run.check(
        row[6] == reason,
        f"mise en lumière {highlight_id} éteinte pour « {row[6]} », attendu « {reason} »",
    )


def ledger_mark(run):
    return int(
        run.sql("SELECT coalesce(max(id), 0) FROM linkup_points_ledger")[0][0]
    )


def new_lines(run, mark):
    """``[(login, rule code, points)]`` of the ledger lines of Sam and
    France written after ``mark``."""
    rows = run.sql(
        "SELECT u.login, r.code, l.points FROM linkup_points_ledger l"
        " JOIN res_users u ON u.id = l.user_id JOIN linkup_points_rule r ON r.id = l.rule_id"
        f" WHERE l.id > {int(mark)} AND u.login IN ('sam', 'france') ORDER BY l.id"
    )
    return [(login, code, int(points)) for login, code, points in rows]


def karma(run):
    return {login: run.points(login) for login in ("sam", "france")}


def check_no_points(run, mark, before):
    """Check that no ledger line of Sam or France appeared since ``mark``
    and that their karma did not move."""
    lines = new_lines(run, mark)
    run.check(
        not lines, f"lignes de points depuis la mise en lumière : {lines}"
    )
    after = karma(run)
    run.check(
        after == before,
        f"points : {before} → {after}, attendu aucun changement",
    )


# Screen ------------------------------------------------------------


def reflet_view(persona):
    """The Reflet view of ``persona``, opened from the menu unless it is
    the current screen."""
    if not persona.has(VIEW_BODY):
        open_reflet_view(persona)
    persona.find(VIEW_BODY)


def row(run, login):
    return f"{CONTACT}[data-user-id='{user(run, login)[0]}']"


def show_chat(run, persona, login):
    """The direct conversation of ``persona`` with ``login``."""
    name = user(run, login)[2]
    if persona.has(f".o-mail-Discuss-threadName[title='{name}']"):
        return
    reflet_view(persona)
    open_chat_with(persona, user(run, login)[0], name)


def open_panel(persona):
    """The LinkUp panel of the open conversation, loaded."""
    if not persona.has(PANEL):
        persona.close_notifications()
        persona.click(PANEL_BUTTON)
    persona.find(f"{PANEL} .o-linkup-Panel-link")


def pick_happiness(run, persona, name):
    """Reach the happiness field with Tab from the hint of the view, open
    it with Enter, walk its list with the down arrow to ``name`` and choose
    it with Enter. Return the number of Tab pressed."""
    persona.find(f"{HAPPINESS}:enabled")
    persona.click(HINT)
    presses = persona.tab_to(f"{HAPPINESS}:enabled")
    persona.keys(Keys.ENTER, css=f"{HAPPINESS}:focus")
    persona.find(f"{HAPPINESS_LIST}:focus")
    names = [e.text.strip() for e in persona.finds(HAPPINESS_OPTION)]
    run.check(
        name in names, f"« {name} » absent de la liste du bonheur : {names}"
    )
    index = names.index(
        persona.find(f"{HAPPINESS_OPTION}.o-isActive").text.strip()
    )
    while names[index] != name:
        persona.keys(Keys.ARROW_DOWN, css=HAPPINESS_LIST)
        index = (index + 1) % len(names)
        persona.find_text(f"{HAPPINESS_OPTION}.o-isActive", names[index])
    persona.keys(Keys.ENTER, css=HAPPINESS_LIST)
    return presses


def check_sun(run, france, on):
    """In the Reflet view of France, the sun on the row of Sam is shown
    (``on``) or gone."""
    reflet_view(france)
    sun = f"{row(run, 'sam')} {SUN}"
    if not on:
        france.wait_gone(sun)
        return None
    element = france.find(sun)
    title = element.get_attribute("title")
    sam_name = user(run, "sam")[2]
    run.check(
        title == f"Tu mets {sam_name} en lumière",
        f"titre du soleil : {title!r}",
    )
    run.check(
        element.find_elements("css selector", "i.fa-sun-o"),
        "icône soleil absente du contact Sam",
    )
    suns = len(france.finds(SUN))
    run.check(
        suns == 1,
        f"{suns} contacts de France portent un soleil, attendu Sam seul",
    )
    return title


def halo_state(persona, run):
    """What the header and the contacts of Sam's Reflet view show of the
    highlights he received."""
    return persona.js(
        """
        const [selfCss, boxCss, avatarCss, rowCss] = arguments;
        const self = document.querySelector(selfCss);
        const box = document.querySelector(boxCss);
        const row = document.querySelector(rowCss);
        const rowAvatar = row && row.querySelector(".o-linkup-RefletView-avatar");
        const hidden = row && row.querySelector(".o-linkup-RefletView-highlightedBy");
        return {
            halo: Boolean(self && self.classList.contains("o-linkup-isHighlighted")),
            box: box ? box.getAttribute("title") : null,
            avatars: [...document.querySelectorAll(avatarCss)].map((img) => img.getAttribute("src")),
            contactHalo: Boolean(rowAvatar && rowAvatar.classList.contains("o-linkup-isHighlighted")),
            contactLabel: hidden ? hidden.textContent.trim() : null,
        };
        """,
        SELF_AVATAR,
        HIGHLIGHTS,
        HIGHLIGHTS_AVATAR,
        row(run, "france"),
    )


def check_halo(run, sam, on):
    """In the Reflet view of Sam, the halo and the avatar of France are
    shown (``on``) or gone; return what the view shows."""
    reflet_view(sam)
    france_name = user(run, "france")[2]
    if on:
        sam.find(f"{SELF_AVATAR}.o-linkup-isHighlighted")
        sam.find(HIGHLIGHTS_AVATAR)
        state = halo_state(sam, run)
        france_avatar = f"res.partner/{user(run, 'france')[1]}/avatar_128"
        run.check(
            len(state["avatars"]) == 1
            and france_avatar in state["avatars"][0],
            f"mini-avatar accroché : {state['avatars']}, attendu celui de France ({france_avatar})",
        )
        run.check(
            state["box"] == f"Qui ajoute à ton bonheur : {france_name}",
            f"libellé du halo : {state['box']!r}",
        )
        run.check(
            state["contactHalo"]
            and state["contactLabel"] == f"{france_name} ajoute à ton bonheur",
            f"contact France chez Sam : {state}",
        )
        return state
    sam.wait_gone(HIGHLIGHTS)
    sam.wait_gone(f"{SELF_AVATAR}.o-linkup-isHighlighted")
    state = halo_state(sam, run)
    run.check(
        not state["halo"]
        and not state["avatars"]
        and not state["contactHalo"]
        and not state["contactLabel"],
        f"la mise en lumière reste visible chez Sam : {state}",
    )
    return state


def highlight_from_panel(run, france):
    """France puts Sam in the light from the LinkUp panel of their
    conversation, after its confirmation."""
    sam_name = user(run, "sam")[2]
    show_chat(run, france, "sam")
    open_panel(france)
    france.click(
        f"{PANEL_HIGHLIGHT}[aria-pressed='false']", "Tu ajoutes à mon bonheur"
    )
    question = france.find(PANEL_CONFIRM).text
    run.check(
        f"Mettre {sam_name} en lumière ?" in question,
        f"question de confirmation : {question!r}",
    )
    france.click(
        f"{PANEL_CONFIRM} .o-linkup-Panel-highlightConfirmButton",
        "Mettre en lumière",
    )
    france.find(f"{PANEL_HIGHLIGHT}[aria-pressed='true']")
    france.find_text(PANEL_WITHDRAW, "Retirer ma mise en lumière")


def chat_id(run):
    """Id of the direct conversation of Sam and France."""
    rows = run.sql(
        "SELECT c.id FROM discuss_channel c WHERE c.channel_type = 'chat' AND ("
        " SELECT array_agg(u.login::text ORDER BY u.login) FROM discuss_channel_member m"
        " JOIN res_users u ON u.partner_id = m.partner_id WHERE m.channel_id = c.id"
        ") = ARRAY['france', 'sam']::text[]"
    )
    if len(rows) != 1:
        raise StepFailure(f"conversation Sam–France : {rows}")
    return int(rows[0][0])


# Steps -------------------------------------------------------------


def p5_1(run):
    sam_name = user(run, "sam")[2]
    sam = run.persona("sam")
    france = run.persona("france")
    run.check(
        not active_highlights(run),
        f"mise en lumière déjà active : {active_highlights(run)}",
    )
    run.memory["p5_mark"] = ledger_mark(run)
    run.memory["p5_karma"] = karma(run)
    # Sam stays on his screen: the notification and the sound reach him
    # live, as France sends.
    sam.record_notifications()
    sam.record_sounds()

    reflet_view(france)
    hint = france.find(HAPPINESS).text
    run.check("Tu ajoutes à mon bonheur" in hint, f"champ bonheur : {hint!r}")
    presses = pick_happiness(run, france, sam_name)
    notice = france.find(HAPPINESS_NOTICE).text.strip()
    run.check(
        notice == happiness_notice(sam_name),
        f"avis après la mise en lumière : {notice!r}",
    )
    highlight_id = wait_active(run, france, "drag")
    run.memory["p5_highlight_id"] = highlight_id
    title = check_sun(run, france, True)
    check_no_points(run, run.memory["p5_mark"], run.memory["p5_karma"])
    return (
        f"variante clavier du champ bonheur ({presses} Tab, Entrée, flèches, Entrée) ;"
        f" mise en lumière {highlight_id} ; soleil « {title} » ; 0 point"
    )


def p5_2(run):
    france_name = user(run, "france")[2]
    sam = run.persona("sam")
    expected = f"{france_name} ajoute à ton bonheur."
    sam.wait_until(
        lambda _d: any(
            n["body"] == expected for n in sam.recorded_notifications()
        ),
        f"notification « {expected} »",
    )
    notification = [
        n for n in sam.recorded_notifications() if n["body"] == expected
    ][0]
    run.check(
        notification["title"] == "LinkUp",
        f"titre de la notification : {notification}",
    )
    # Ting is a reward sound: it plays only with the reward sounds on.
    rewards = reward_sounds(run, "sam")
    if rewards == "activés":
        sam.wait_until(
            lambda _d: any(
                "linkup_ting" in src for src in sam.played_sounds()
            ),
            "son Ting joué, sons de récompense activés",
        )
    else:
        run.settle()
    ting = any("linkup_ting" in src for src in sam.played_sounds())
    run.check(
        ting == (rewards == "activés"),
        f"son Ting joué : {ting}, sons de récompense {rewards}",
    )
    check_halo(run, sam, True)
    sound = (
        f"son Ting {'joué' if ting else 'muet'} (sons de récompense {rewards})"
    )
    return f"halo sur l'avatar de Sam, mini-avatar de France, contact France auréolé ; notification « {expected} » ; {sound}"


def p5_3(run):
    sam = run.persona("sam")
    france = run.persona("france")
    mark, before = run.memory["p5_mark"], run.memory["p5_karma"]

    # Sam writes to France: his message puts out the light he received.
    highlight_id = run.memory["p5_highlight_id"]
    show_chat(run, sam, "france")
    sam.type(COMPOSER, SAM_MESSAGE)
    sam.keys(Keys.ENTER, css=COMPOSER)
    sam.find_text(".o-mail-Message-body", SAM_MESSAGE)
    wait_out(run, sam, highlight_id, "message")
    check_halo(run, sam, False)
    check_sun(run, france, False)
    check_no_points(run, mark, before)

    # Sam calls France: the call puts out the light as soon as it rings.
    channel_id = chat_id(run)
    highlight_from_panel(run, france)
    call_highlight = wait_active(run, france, "thread", channel_id)
    check_halo(run, sam, True)
    show_chat(run, sam, "france")
    sam.close_notifications()
    sam.click(CALL_BUTTON)
    wait_out(run, sam, call_highlight, "call")
    check_no_points(run, mark, before)
    france.find(f"{PANEL_HIGHLIGHT}[aria-pressed='false']")
    run.check(
        not france.has(PANEL_WITHDRAW),
        "« Retirer ma mise en lumière » reste offert après l'appel",
    )

    answer_call(france)
    france.wait_until(
        lambda _d: len(new_lines(run, mark)) >= 2,
        "appel répondu inscrit au registre",
        30,
    )
    lines = new_lines(run, mark)
    run.check(
        sorted((login, code) for login, code, _p in lines)
        == [("france", "call_answered"), ("sam", "call_answered")],
        f"lignes de points après l'appel : {lines}, attendu le seul « call_answered » de l'appel",
    )
    hang_up(sam, channel_id, run)
    hang_up(france, channel_id, run)
    check_halo(run, sam, False)
    check_sun(run, france, False)
    run.memory["p5_mark"] = ledger_mark(run)
    run.memory["p5_karma"] = karma(run)
    paid = ", ".join(f"{login} +{points}" for login, _c, points in lines)
    return (
        f"message de Sam : mise en lumière {highlight_id} éteinte (message), 0 point ;"
        f" appel de Sam : mise en lumière {call_highlight} (panneau) éteinte dès l'appel, 0 point ;"
        f" l'appel répondu paie son propre call_answered ({paid})"
    )


def p5_4(run):
    sam_name = user(run, "sam")[2]
    sam = run.persona("sam")
    france = run.persona("france")
    mark, before = run.memory["p5_mark"], run.memory["p5_karma"]

    # France drags the happiness field onto Sam, then withdraws it.
    reflet_view(france)
    france.drag(HAPPINESS, row(run, "sam"))
    notice = france.find(HAPPINESS_NOTICE).text.strip()
    run.check(
        notice == happiness_notice(sam_name),
        f"avis après le glisser : {notice!r}",
    )
    dragged = wait_active(run, france, "drag")
    check_sun(run, france, True)
    check_halo(run, sam, True)
    show_chat(run, france, "sam")
    open_panel(france)
    france.click(PANEL_WITHDRAW, "Retirer ma mise en lumière")
    wait_out(run, france, dragged, "withdrawn")
    france.find(f"{PANEL_HIGHLIGHT}[aria-pressed='false']")
    check_halo(run, sam, False)
    check_sun(run, france, False)

    # France puts Sam in the light again; Sam hides it from his panel.
    highlight_from_panel(run, france)
    hidden = wait_active(run, france, "thread", chat_id(run))
    show_chat(run, sam, "france")
    open_panel(sam)
    label = sam.find(PANEL_RECEIVED).text
    run.check(
        f"{user(run, 'france')[2]} ajoute à ton bonheur" in label,
        f"panneau de Sam : {label!r}",
    )
    sam.click(f"{PANEL_RECEIVED} .o-linkup-Panel-highlightDismiss", "Masquer")
    wait_out(run, sam, hidden, "manual")
    sam.wait_gone(PANEL_RECEIVED)
    france.find(f"{PANEL_HIGHLIGHT}[aria-pressed='false']")
    run.check(
        not france.has(PANEL_WITHDRAW),
        "« Retirer ma mise en lumière » reste offert après le masquage",
    )
    check_halo(run, sam, False)
    check_sun(run, france, False)
    check_no_points(run, mark, before)
    return (
        f"glisser du champ sur Sam (pointeur) puis retrait par France : {dragged} éteinte des deux côtés ;"
        f" mise en lumière {hidden} masquée par Sam : éteinte des deux côtés ; 0 point"
    )


STEPS = [
    (
        "P5.1",
        "france met Sam en lumière depuis le champ bonheur : Sam porte un soleil dans ses contacts",
        p5_1,
    ),
    (
        "P5.2",
        "sam : halo sur son avatar, mini-avatar de France accroché ; notification « mise en lumière »",
        p5_2,
    ),
    (
        "P5.3",
        "sam écrit à France, puis l'appelle : la mise en lumière s'éteint ; aucun point",
        p5_3,
    ),
    (
        "P5.4",
        "france retire sa mise en lumière, puis sam la masque : elle disparaît des deux côtés",
        p5_4,
    ),
]
