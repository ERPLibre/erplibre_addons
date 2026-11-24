# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §5 P4: the three follow-up options of the member whose turn it
is, played by Sam with Jacques.

Sam holds the options on an exact answer of Jacques. "Continuer le
reflet" and its exact answer give the turn back to Sam; "Parler de soi"
by a call, "Parler de soi" by text and "Terminer ça là" each end a turn,
and a second outcome of the same turn is refused. Before each of the last
two, and before the first one when the section before left no options to
Sam, the options open again as the guide says: Sam sends Jacques a new
reflection, Jacques confirms it and answers "Oui, c'est exactement ça !".

Builds on the pair Sam–Jacques that P1 to P3 leave active. Leaves
``run.memory["p4_close_id"]``, the closing reflection that ends the
section.
"""

import time

from driver import StepFailure
from selenium.webdriver.common.keys import Keys

from .j1_p1_send import open_reflet_view, pick_in_list, quote, user
from .j1_p2_validate import expect_bursts, has_badge
from .j1_p3_precision import (
    ALREADY_ANSWERED,
    CARD,
    CARD_JS,
    OPTION,
    Card,
    category_id,
    check_delta,
    karma_of,
    ledger_lines,
    received_card,
    show_thread,
)

SECTION = "P4"
TITLE = "Les trois options de suite (guide §5 P4)"

OPTIONS = ".o-linkup-RefletActions[data-mode='options']"
CONTINUE_FORM = ".o-linkup-RefletActions-form[data-form='continue']"
SELF_FORM = ".o-linkup-RefletActions-form[data-form='self']"
CLOSE_FORM = ".o-linkup-RefletActions-form[data-form='close']"
EXACT_FORM = ".o-linkup-RefletActions-form[data-form='exact']"
TEXT = ".o-linkup-RefletActions-text"
SEND = ".o-linkup-RefletActions-send"

CONTINUE_TITLE = "Donc si je comprends bien…"
SELF_TITLE = "Je voudrais te parler de quelque chose qui me tient à cœur."
CLOSING = "Merci pour notre discussion."
OPTION_LABELS = {
    ".o-linkup-RefletActions-continue": "Continuer le reflet",
    ".o-linkup-RefletActions-self": "Parler de soi",
    ".o-linkup-RefletActions-end": "Terminer ça là",
}
CONTINUE_TEXTS = (
    "je t'aide à préparer la fête du quartier",
    "je t'aide aussi à ranger après la fête",
)
SELF_TEXT = "un moment calme le soir pour lire"
# The texts of the reflections that open the options again, (you said,
# understood), taken in turn; ``reopening_texts`` numbers each use, so that the
# understood text of every reopening is unique.
REOPENING_TEXTS = (
    (
        "que tu as repeint la cuisine ce week-end",
        "tu es fier de la cuisine repeinte",
    ),
    (
        "que tu cours tous les matins avant le travail",
        "courir t'aide à bien commencer",
    ),
    (
        "que tu cherches un club de lecture",
        "tu veux rencontrer d'autres lecteurs",
    ),
)
REOPENING_CATEGORY = "observation"
RULE_LABELS = {
    "continue_sent": "Reflet continué",
    "continue_confirmed": "Suite confirmée",
    "call_answered": "Appel répondu",
}
BADGE_FIRST_CALL = "Premier appel"


# State in the database ---------------------------------------------


def pair_turn(run):
    """``(id, kind, state, response_state, recipient login, guess_state)``
    of the reflection holding the turn of the pair Sam–Jacques, or None."""
    rows = run.sql(
        "SELECT r.id, r.kind, r.state, r.response_state, u.login, coalesce(r.guess_state, '')"
        " FROM linkup_link l JOIN linkup_reflet r ON r.id = l.turn_reflet_id"
        " JOIN res_users u ON u.id = r.recipient_id"
        " JOIN res_users a ON a.id = l.user_a_id JOIN res_users b ON b.id = l.user_b_id"
        " WHERE ARRAY[a.login, b.login]::text[] <@ ARRAY['sam', 'jacques']"
    )
    return rows[0] if rows else None


def pair_turn_id(run):
    """Id of the reflection holding the turn of the pair, or ""."""
    turn = pair_turn(run)
    return turn[0] if turn else ""


def child_of(run, parent_id, kind, timeout=10):
    """``(id, author, recipient, category code, understood, body_text)``
    of the single child ``kind`` of a reflection, waited for ``timeout``
    seconds: a click returns before the server wrote it."""
    deadline = time.monotonic() + timeout
    rows = children(run, parent_id, kind)
    while not rows and time.monotonic() < deadline:
        time.sleep(0.5)
        rows = children(run, parent_id, kind)
    if len(rows) != 1:
        raise StepFailure(f"enfants « {kind} » du reflet {parent_id} : {rows}")
    row = rows[0]
    return [int(row[0])] + row[1:]


def children(run, parent_id, kind):
    return run.sql(
        "SELECT r.id, a.login, b.login, coalesce(c.code, ''), coalesce(r.understood, ''),"
        " coalesce(r.body_text, '')"
        " FROM linkup_reflet r JOIN res_users a ON a.id = r.author_id"
        " JOIN res_users b ON b.id = r.recipient_id"
        " LEFT JOIN linkup_category c ON c.id = r.category_id"
        f" WHERE r.parent_id = {int(parent_id)} AND r.kind = {quote(kind)}"
    )


def starter(run, code, field):
    """The French starter (``starter_self`` or ``starter_reflect``) of a
    category."""
    return run.sql(
        f"SELECT {field}->>'fr_CA' FROM linkup_category WHERE code = {quote(code)}"
    )[0][0]


def rule_lines(run, reflet_id, code):
    """``[(login, points, cap_reason)]`` of every line of rule ``code`` on
    a reflection, sorted."""
    return [
        (login, points, reason)
        for login, rule, points, reason in ledger_lines(run, reflet_id)
        if rule == code
    ]


def check_rule(run, reflet_id, code, points):
    """Check that rule ``code`` paid ``points`` to Jacques and to Sam on a
    reflection, one line each."""
    lines = rule_lines(run, reflet_id, code)
    expected = [("jacques", points, ""), ("sam", points, "")]
    run.check(
        lines == expected,
        f"registre {code} du reflet {reflet_id} : {lines}, attendu {expected}",
    )


def check_refused(run, persona, reflet_id, method, args):
    """Check that the server refuses a second outcome of the turn."""
    answer = persona.rpc("linkup.reflet", method, [[reflet_id], *args])
    run.check(
        ALREADY_ANSWERED in str(answer.get("error", "")),
        f"seconde issue {method} du reflet {reflet_id} : {answer}, attendu le refus « {ALREADY_ANSWERED} »",
    )


# Screen ------------------------------------------------------------


def options_card(persona):
    """The card of the conversation that offers the three options."""
    return Card(
        persona,
        f"{CARD}[data-kind='answer_exact'][data-role='recipient']",
        OPTIONS,
        "",
    )


def continue_card(persona, understood):
    """The continued reflection received by ``persona``, by its text."""
    return Card(
        persona,
        f"{CARD}[data-kind='continue'][data-role='recipient']",
        ".o-linkup-RefletCard-understood",
        understood,
    )


def card_title(persona, card):
    element = persona.js(
        CARD_JS, card.css, card.part, card.text, ".o-linkup-RefletCard-title"
    )
    return element.text.strip() if element else None


def sam_options(run):
    """Show the conversation of Sam with Jacques and wait for the three
    options there; return the card."""
    sam = run.persona("sam")
    show_thread(sam, "jacques", user(run, "jacques")[2])
    card = options_card(sam)
    card.wait(what="les trois options chez Sam")
    return card


def open_option(run, card, button, form):
    """Click an option of the card and wait for its form."""
    card.click(button, OPTION_LABELS[button])
    return card.wait(lambda s: form in s["forms"], f"formulaire {form} ouvert")


def send_form(run, persona, form_css):
    """Send the open form to Jacques, then wait until the options left the
    conversation of Sam."""
    jacques_name = user(run, "jacques")[2]
    persona.click(f"{form_css} {SEND}", f"Envoyer à {jacques_name}")
    persona.wait_gone(OPTIONS)


def send_reflection(run, sam, texts):
    """Write a reflection in the Reflet view of Sam and send it to Jacques
    with "Envoyer à…"."""
    code, you_said, understood = texts
    jacques_name = user(run, "jacques")[2]
    open_reflet_view(sam)
    sam.click(f".o-linkup-HelpBar-category[data-code='{code}']")
    sam.find(f".o-linkup-RefletForm-title svg[data-code='{code}']")
    sam.type(".o-linkup-RefletForm-youSaid", you_said)
    sam.type(".o-linkup-RefletForm-understood", understood)
    sam.click(".o-linkup-RefletView-sendTo", "Envoyer à…")
    pick_in_list(run, sam, jacques_name)
    sam.keys(Keys.ENTER, css=".o-linkup-RefletView-picker")
    sam.find_text(
        ".o-linkup-RefletView-notice", f"Reflet envoyé à {jacques_name}."
    )


def answer_exact(run, card):
    """Answer "Oui, c'est exactement ça !" on a card of Jacques."""
    sam_name = user(run, "sam")[2]
    card.click(".o-linkup-RefletActions-exact", "Oui, c'est exactement ça !")
    card.wait(
        lambda s: "exact" in s["forms"],
        "formulaire « Oui, c'est exactement ça ! » ouvert",
    )
    card.click(f"{EXACT_FORM} {SEND}", f"Envoyer à {sam_name}")


def reopening_texts(index):
    """``(category, you said, understood)`` of the reopening ``index``,
    from 0: the texts of ``REOPENING_TEXTS`` in turn, the understood text
    numbered from the second round of them on."""
    you_said, understood = REOPENING_TEXTS[index % len(REOPENING_TEXTS)]
    round_ = index // len(REOPENING_TEXTS)
    if round_:
        understood = f"{understood} ({round_ + 1})"
    return REOPENING_CATEGORY, you_said, understood


def reopen_options(run):
    """Open the options again by the route of the guide: a new reflection
    of Sam that Jacques confirms and answers exactly. Return the id of the
    exact answer, whose turn Sam holds."""
    index = run.memory.get("p4_reopenings", 0)
    run.memory["p4_reopenings"] = index + 1
    texts = reopening_texts(index)
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    send_reflection(run, sam, texts)
    rows = run.sql(
        "SELECT r.id FROM linkup_reflet r JOIN res_users a ON a.id = r.author_id"
        " WHERE a.login = 'sam' AND r.kind = 'initial' AND r.state = 'sent'"
        f" AND r.understood = {quote(texts[2])}"
    )
    run.check(len(rows) == 1, f"reflet de réouverture « {texts[2]} » : {rows}")
    initial_id = int(rows[0][0])

    show_thread(jacques, "sam", user(run, "sam")[2])
    received_card(jacques, "sent", texts[2]).click(
        ".o-linkup-RefletActions-confirm", "C'est un lien !"
    )
    card = received_card(jacques, "confirmed", texts[2])
    card.wait(
        lambda s: "answer" in s["modes"],
        "reflet de réouverture confirmé, réponse offerte",
    )
    answer_exact(run, card)
    exact_id = child_of(run, initial_id, "answer_exact")[0]
    run.check(
        pair_turn_id(run) == str(exact_id),
        f"la réponse exacte {exact_id} ne tient pas le tour",
    )
    return exact_id


def ensure_options(run):
    """The id of the exact answer whose options Sam holds, and whether the
    options had to be opened again."""
    turn = pair_turn(run)
    if (
        turn
        and turn[1] == "answer_exact"
        and turn[2:5] == ["sent", "none", "sam"]
    ):
        return int(turn[0]), False
    return reopen_options(run), True


ACCEPT_CALL = ".o-discuss-CallInvitation button.btn-success:has(> i.fa-phone)"


def answer_call(persona):
    """Answer the incoming call from its invitation, at the top right of
    the screen, once the notifications over it are closed."""
    persona.find(ACCEPT_CALL, timeout=30)
    persona.close_notifications()
    persona.click(ACCEPT_CALL)


def hang_up(persona, channel_id, run):
    """Leave the call of the conversation from its call bar, then wait
    until the member has no call session left in it."""
    persona.click(
        ".o-discuss-CallActionList button.btn-danger:has(> i.fa-phone)"
    )
    partner_id = user(run, persona.login_name)[1]
    persona.wait_until(
        lambda _d: run.sql(
            "SELECT count(*) FROM discuss_channel_rtc_session s"
            " JOIN discuss_channel_member m ON m.id = s.channel_member_id"
            f" WHERE s.channel_id = {int(channel_id)} AND m.partner_id = {partner_id}"
        )[0][0]
        == "0",
        "fin de la session d'appel",
    )


# Steps -------------------------------------------------------------


def continue_round(run, text, points):
    """Sam continues the reflection with the starter of Action; check
    that ``continue_sent`` pays ``points`` to each. Return the id of the
    continued reflection and its card at Jacques."""
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    exact_id = int(pair_turn_id(run))
    before = karma_of(run, "sam", "jacques")
    sam.record_points()
    jacques.record_points()

    card = sam_options(run)
    state = open_option(
        run, card, ".o-linkup-RefletActions-continue", "continue"
    )
    run.check(
        CONTINUE_TITLE in state["actions"],
        f"titre du formulaire : {state['actions']!r}",
    )
    card.click(f"{CONTINUE_FORM} {OPTION}[data-code='action']")
    amorce = starter(run, "action", "starter_reflect")
    state = card.wait(
        lambda s: s["pressed"] == ["action"]
        and (s["text"] or "").startswith(amorce),
        f"Action choisie, amorce « {amorce} » insérée",
    )
    understood = f"{amorce} {text}."
    sam.type(f"{CONTINUE_FORM} {TEXT}", understood)
    send_form(run, sam, CONTINUE_FORM)

    reflet_id, author, recipient, code, saved, _body = child_of(
        run, exact_id, "continue"
    )
    run.check(
        [author, recipient, code, saved]
        == ["sam", "jacques", "action", understood],
        f"reflet continué {reflet_id} : {[author, recipient, code, saved]}",
    )
    check_rule(run, reflet_id, "continue_sent", points)
    after = check_delta(run, before, {"sam": points, "jacques": points})
    for persona in (sam, jacques):
        expect_bursts(
            run,
            persona,
            [("gain", points, RULE_LABELS["continue_sent"])],
            f"+{points} affiché chez {persona.login_name}",
        )

    show_thread(jacques, "sam", user(run, "sam")[2])
    received = continue_card(jacques, understood)
    received.wait(
        lambda s: s["header"] == ["action"] and "answer" in s["modes"],
        "chez Jacques, le reflet continué porte l'icône Action et offre la réponse",
    )
    title = card_title(jacques, received)
    run.check(
        title == CONTINUE_TITLE, f"titre de la carte chez Jacques : {title!r}"
    )
    return reflet_id, received, f"{before} → {after}"


def exact_round(run, received, continue_id, points):
    """Jacques answers the continued reflection exactly; check that
    ``continue_confirmed`` pays ``points`` to each and that Sam holds the
    options again. Return the id of the exact answer and the karma
    before → after."""
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    before = karma_of(run, "sam", "jacques")
    sam.record_points()
    jacques.record_points()
    answer_exact(run, received)
    jacques.find(f"{CARD}[data-kind='answer_exact'][data-role='author']")
    exact_id = child_of(run, continue_id, "answer_exact")[0]
    check_rule(run, exact_id, "continue_confirmed", points)
    after = check_delta(run, before, {"sam": points, "jacques": points})
    for persona in (sam, jacques):
        expect_bursts(
            run,
            persona,
            [("gain", points, RULE_LABELS["continue_confirmed"])],
            f"+{points} affiché chez {persona.login_name}",
        )
    run.check(
        pair_turn_id(run) == str(exact_id),
        f"la réponse exacte {exact_id} ne tient pas le tour",
    )
    sam_options(run)
    run.check(
        not jacques.finds(OPTIONS),
        "Jacques voit les options alors que le tour est à Sam",
    )
    return exact_id, f"{before} → {after}"


def p4_1(run):
    exact_id, reopened = ensure_options(run)
    state = sam_options(run).read()
    run.check(
        "Et maintenant ?" in state["actions"],
        f"question des options : {state['actions']!r}",
    )
    for label in OPTION_LABELS.values():
        run.check(
            label in state["actions"],
            f"option « {label} » absente : {state['actions']!r}",
        )
    run.check(
        not run.persona("jacques").finds(OPTIONS),
        "Jacques voit les options alors que le tour est à Sam",
    )
    continue_id, _received, points = continue_round(
        run, CONTINUE_TEXTS[0], 250
    )
    run.memory["p4_continue_id"] = continue_id
    origin = (
        "options rouvertes par un nouveau reflet confirmé"
        if reopened
        else f"options de la réponse {exact_id}"
    )
    return f"{origin} ; reflet continué {continue_id}, icône Action chez Jacques ; points {points}"


def p4_2(run):
    jacques = run.persona("jacques")
    show_thread(jacques, "sam", user(run, "sam")[2])
    continue_id = run.memory["p4_continue_id"]
    understood = run.sql(
        f"SELECT understood FROM linkup_reflet WHERE id = {int(continue_id)}"
    )[0][0]
    received = continue_card(jacques, understood)
    _first, first_points = exact_round(run, received, continue_id, 250)

    # The decay: the same round again in the day pays half.
    second_id, received, second_continue = continue_round(
        run, CONTINUE_TEXTS[1], 125
    )
    exact_id, second_exact = exact_round(run, received, second_id, 125)
    run.memory["p4_exact_id"] = exact_id
    return (
        f"exactement ça : +250 chacun {first_points} ; tour suivant : continuer +125 {second_continue},"
        f" exactement ça +125 {second_exact} ; le tour revient à Sam"
    )


def p4_3(run):
    jacques_name = user(run, "jacques")[2]
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    exact_id, reopened = ensure_options(run)
    channel_id = int(
        run.sql(f"SELECT channel_id FROM linkup_reflet WHERE id = {exact_id}")[
            0
        ][0]
    )
    run.check(
        not has_badge(run, "jacques", "badge_first_call"),
        "Jacques a déjà le badge « Premier appel »",
    )
    before = karma_of(run, "sam", "jacques")
    sam.record_points()
    jacques.record_points()

    card = sam_options(run)
    state = open_option(run, card, ".o-linkup-RefletActions-self", "self")
    run.check(
        SELF_TITLE in state["actions"],
        f"titre du formulaire : {state['actions']!r}",
    )
    order = sam.js(
        """
        const form = document.querySelector(arguments[0]);
        const first = form && form.querySelector("button, .o-linkup-CategoryPicker-option, textarea");
        const call = form && form.querySelector(".o-linkup-RefletActions-call");
        const video = form && form.querySelector(".o-linkup-RefletActions-video");
        const after = (a, b) => Boolean(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
        return {
            first: first ? first.className : null,
            call: call ? call.textContent.trim() : null,
            video: video ? video.textContent.trim() : null,
            before: after(video, form.querySelector(".o-linkup-CategoryPicker-option"))
                && after(video, form.querySelector("textarea")),
        };
        """,
        SELF_FORM,
    )
    run.check(
        order["call"] == f"Appeler {jacques_name}"
        and order["video"] == f"Visio avec {jacques_name}",
        f"boutons d'appel : {order}",
    )
    run.check(
        "o-linkup-RefletActions-call" in (order["first"] or "")
        and order["before"],
        f"les boutons d'appel ne viennent pas en premier : {order}",
    )

    card.click(
        f"{SELF_FORM} .o-linkup-RefletActions-call", f"Appeler {jacques_name}"
    )
    answer_call(jacques)
    jacques.wait_until(
        lambda _d: len(rule_lines(run, exact_id, "call_answered")) == 2,
        "appel répondu inscrit au registre",
        30,
    )
    check_rule(run, exact_id, "call_answered", 250)
    after = check_delta(run, before, {"sam": 250, "jacques": 250})
    run.check(
        pair_turn_id(run) == "",
        f"le tour reste au reflet {pair_turn_id(run)} après l'appel",
    )
    run.check(
        has_badge(run, "jacques", "badge_first_call"),
        "badge « Premier appel » non accordé à Jacques",
    )
    sam.wait_gone(OPTIONS)
    expect_bursts(
        run,
        jacques,
        [
            ("gain", 250, RULE_LABELS["call_answered"]),
            ("badge", None, f"Nouveau badge : {BADGE_FIRST_CALL}"),
        ],
        "chez Jacques : +250 et badge Premier appel annoncés",
    )
    expect_bursts(
        run,
        sam,
        [("gain", 250, RULE_LABELS["call_answered"])],
        "+250 affiché chez Sam",
    )
    check_refused(run, sam, exact_id, "action_close", [])

    hang_up(sam, channel_id, run)
    hang_up(jacques, channel_id, run)
    origin = "options rouvertes ; " if reopened else ""
    return f"{origin}appel répondu : +250 chacun {before} → {after}, fin du tour, badge Premier appel ; seconde issue refusée"


def p4_4(run):
    sam_name = user(run, "sam")[2]
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    exact_id, _reopened = ensure_options(run)

    card = sam_options(run)
    open_option(run, card, ".o-linkup-RefletActions-self", "self")
    card.click(f"{SELF_FORM} {OPTION}[data-code='needs']")
    amorce = starter(run, "needs", "starter_self")
    run.check(amorce == "J'ai besoin de :", f"amorce de Besoins : {amorce!r}")
    card.wait(
        lambda s: s["pressed"] == ["needs"]
        and (s["text"] or "").startswith(amorce),
        f"Besoins choisi, amorce « {amorce} » insérée",
    )
    body = f"{amorce} {SELF_TEXT}."
    sam.type(f"{SELF_FORM} {TEXT}", body)
    send_form(run, sam, SELF_FORM)

    disclosure_id, author, recipient, code, _u, saved = child_of(
        run, exact_id, "self_disclosure"
    )
    run.check(
        [author, recipient, code, saved] == ["sam", "jacques", "needs", body],
        f"« Parler de soi » {disclosure_id} : {[author, recipient, code, saved]}",
    )
    run.check(
        pair_turn_id(run) == str(disclosure_id),
        f"le tour n'est pas à Jacques : {pair_turn(run)}",
    )

    show_thread(jacques, "sam", sam_name)
    received = Card(
        jacques,
        f"{CARD}[data-kind='self_disclosure'][data-role='recipient']",
        ".o-linkup-RefletCard-bodyText",
        SELF_TEXT,
    )
    state = received.wait(
        lambda s: s["modes"] == ["rephrase"],
        "chez Jacques, « Parler de soi » à reformuler",
    )
    invite = f"{sam_name} t'a parlé de quelque chose qui lui tient à cœur. Reformule-le pour montrer ce que tu as compris."
    run.check(
        invite in state["actions"],
        f"invitation à reformuler : {state['actions']!r}",
    )
    received.click(".o-linkup-RefletActions-rephrase", "Écrire un reflet")
    reflect = starter(run, "needs", "starter_reflect")
    received.wait(
        lambda s: "continue" in s["forms"]
        and s["pressed"] == ["needs"]
        and (s["text"] or "").startswith(reflect),
        f"formulaire de reformulation, Besoins et « {reflect} » préremplis",
    )
    received.click(f"{CONTINUE_FORM} .o-linkup-RefletActions-back")
    received.wait(
        lambda s: s["modes"] == ["rephrase"] and not s["forms"],
        "formulaire refermé",
    )
    check_refused(run, sam, exact_id, "action_close", [])
    return f"« Parler de soi » {disclosure_id} : Jacques doit reformuler (« {reflect} »)"


def p4_5(run):
    sam_name = user(run, "sam")[2]
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    exact_id, _reopened = ensure_options(run)
    before = karma_of(run, "sam", "jacques")
    sam.record_points()
    jacques.record_points()

    card = sam_options(run)
    state = open_option(run, card, ".o-linkup-RefletActions-end", "close")
    run.check(
        state["text"] == CLOSING,
        f"texte de clôture : {state['text']!r}, attendu {CLOSING!r}",
    )
    send_form(run, sam, CLOSE_FORM)

    close_id = child_of(run, exact_id, "close")[0]
    run.memory["p4_close_id"] = close_id
    lines = ledger_lines(run, close_id)
    run.check(
        all(points == 0 for _login, _rule, points, _reason in lines),
        f"registre de la clôture : {lines}",
    )
    after = check_delta(run, before, {"sam": 0, "jacques": 0})
    show_thread(jacques, "sam", sam_name)
    closing = Card(
        jacques,
        f"{CARD}[data-kind='close'][data-role='recipient']",
        ".o-linkup-RefletCard-title",
        CLOSING,
    )
    closing.wait(what=f"chez Jacques, « {CLOSING} » reçu")
    run.settle()
    for persona in (sam, jacques):
        seen = persona.recorded_points()["bursts"]
        run.check(
            not seen,
            f"points affichés chez {persona.login_name} pour la clôture : {seen}",
        )
    check_refused(
        run,
        sam,
        exact_id,
        "action_continue",
        [category_id(run, "action"), "Donc si je comprends bien, encore."],
    )
    return f"clôture {close_id} « {CLOSING} » reçue par Jacques, 0 point {before} → {after} ; seconde issue refusée"


STEPS = [
    (
        "P4.1",
        "« Continuer le reflet » + amorce Action, envoyer : +250 chacun ; icône d'amorce chez l'autre",
        p4_1,
    ),
    (
        "P4.2",
        "L'autre répond « Oui, c'est exactement ça ! » : +250 chacun (décroissance 250, 125… dans la journée)",
        p4_2,
    ),
    (
        "P4.3",
        "« Parler de soi » : appel / visio en premier ; Sam appelle, Jacques répond : +250 chacun, fin du tour, badge Premier appel",
        p4_3,
    ),
    (
        "P4.4",
        "« Parler de soi » par texte, amorce Besoins « J'ai besoin de : … » : l'autre doit reformuler",
        p4_4,
    ),
    (
        "P4.5",
        "« Terminer ça là » : « Merci pour notre discussion » envoyé, 0 point",
        p4_5,
    ),
]
