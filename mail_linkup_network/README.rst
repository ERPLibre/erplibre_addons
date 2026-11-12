=====================
LinkUp — Network view
=====================

The LinkUp Network view: the graph centred on a member, its densities, the
rankings of the contacts, the card of a link, and the quick replies to a
request for action, on the server and in the web client.

Contacts
========

* The contacts of a member are the other members of their ``active``
  links. A ``pending``, ``closed`` or ``blocked`` link adds nobody, and an
  archived account is absent: the view tells neither a reflection that
  waits or was rejected, nor a block, nor a person outside the links.
* Nothing of the community beyond the contacts shows: no anonymous node,
  no line to a stranger, no ranking of all the members (LU-NF-032).
* The context of the caller does not widen the contacts: the searches run
  with ``active_test`` on, whatever an RPC call sends.
* A suspended contact keeps their node, row and card: the view does not
  tell a sanction. A phantom reflection or highlight leaves no trace in
  the card or the graph of either member, even once the block is lifted.
* The graph, the rankings and the card run a number of queries that does
  not grow with the contacts of the member
  (``tests/test_network_performance.py``); the unique pair of
  ``linkup.link`` indexes ``(user_a_id, user_b_id)``. The response times
  are measured on the load-test database of ``mail_linkup_reflet``.

Graph
=====

* ``linkup.link.get_network_graph(level, limit)`` and the route
  ``/linkup/v1/network/graph`` give ``me`` (the energy of the member:
  their karma, decayed), ``nodes`` and ``edges``. A node gives the energy
  of the link as the member received it, and ``highlight`` when the
  contact holds an active highlight to the member.
* ``x1`` (or ``2``) draws the direct links, and the grey line between two
  contacts whose own link is ``active`` when both show their links;
  ``x2`` (or ``1``) the direct links; ``x3`` (or ``top``) the strongest
  partners, ``linkup.network_top_count`` of them (2 by default, *Settings ›
  Discuss › LinkUp › Network view*). At most 50 nodes, the strongest first.
* The graph, the rankings and the card read in a fixed number of queries,
  whatever the number of links; a test runs them with 200 links.

Energy and its decay
====================

* The energy decays with time (Q-41): a line of the ledger weighs
  ``2 ** (-d / H)``, ``d`` the whole days since its date, ``H`` the
  half-life ``linkup.energy_half_life_days`` (90 days, *Settings › Discuss
  › LinkUp › Network view*). A line counts whole its first day, half after
  90 days, a quarter after 180.
* The energy of a member is their karma (Q-08) less what the decay took
  from their lines; the energy of a link, the points the member received
  in the events of the pair, each weighted the same way. The graph, X3,
  "My partners", "The most active", the link card, the panel of a
  conversation, "Network view (n)" and the energy bubble show the decayed
  value; the rank and "My points" keep the karma.
* The decay is computed at the reading, from the dated lines, in one query
  grouped by link or by member, on the indexes ``(user_id, date)`` and
  ``link_id``: the ledger, append-only and keyed by ``event_key``, and the
  karma never change. The web client receives at its opening how much the
  decay took (``linkup_energy_decay``) and adds the points of the session
  with their full weight.
* An unset or invalid half-life takes 90 days; 0, or a negative value,
  turns the decay off: the energy is then the karma, and the energy of a
  link the sum the gamification keeps on it.

Rankings
========

* ``linkup.link.get_ranking(kind, period)`` and the route
  ``/linkup/v1/network/ranking``: ``partners`` ranks the contacts by the
  points the member received in the events of each pair, the value of the
  link card; ``active`` ranks the contacts who show their energy by the
  points they received from anybody, penalties left out, rounded to the
  hundred. ``period`` is ``all`` or ``30d``; equal values go by name.

Link card
=========

* ``linkup.link.get_link_card(user_id, reflets_only, limit)`` and the
  route ``/linkup/v1/network/link`` give the contact, the energy of the
  link as the reader received it, the date of the first link, the direct
  conversation (call, video call, conversation), the highlights both ways,
  and the thread both members read, oldest first: the comments of their
  conversation, or the carriers of their reflections only. A draft, a
  withdrawn reflection and a phantom one have no entry; the hidden themes
  follow the rules of the core.
* Any other contact, a block either way included, reads
  ``{"available": False}``.

Request for action
==================

* ``linkup.reflet.action_answer_action_request(reply)``: the recipient of a
  reflection whose category, or revealed theme, is Action posts "Agreed."
  (``agree``) or "Not for now." (``not_now``) once in the conversation of
  the pair. The reply pays and costs nothing, and closes no round of free
  text. The card of the reflection carries ``action_reply``. "Let's
  propose something else" is an ordinary precision.

Privacy
=======

* ``linkup_links_visible`` and ``linkup_energy_visible`` on ``res.users``,
  off by default: each member reads and writes their own
  (``SELF_READABLE_FIELDS``, ``SELF_WRITEABLE_FIELDS``), receives them in
  the Store, and on the bus when they change; nobody else reads them.
* A restricted member reads the karma, the rank and the badges of their own
  account only: a reading of another user gives them empty, and a search,
  an order or a grouping by them is refused. A badge lists its holders
  among the reader only, and a rank lists nobody and is not searched by
  its holders. The energy of a contact
  who shows it reaches the member rounded, through the ranking. LinkUp
  administrators and the server keep the native reading.

Web client
==========

* The client action ``linkup.network_view`` (*Discuss › LinkUp › Network
  view*, path ``linkup-network``) opens from "Network view (n)" in the
  LinkUp section of the sidebar of Discuss, n being the energy of the
  member, and from the Reflet view.
* The graph is an SVG drawn in the client, without any library: the member
  in the centre, the contacts around, strongest first, the width of each
  line and the size of each node growing with the energy of the link, a
  golden halo around a contact who puts the member in the light, and in X1
  the grey lines the server sends. The nodes are buttons over the SVG: one
  ``Tab`` stop, the arrow keys, ``Home`` and ``End`` walk them, ``Enter``
  opens the card. "The graph as a list" gives the same people in text, for
  a screen reader.
* X1, X2 and X3 are three buttons on a large screen, and one round button
  that cycles X1 → X2 → X3 → X1 on a small one, where the rankings open
  with the list button instead of standing beside the graph; each change is
  announced.
* "The most active" and "My partners" are tabs, walked with the arrow keys;
  the period (all, 30 days) applies to "The most active" only, so that "My
  partners" and the card always show the same energy of a link. A row, a node or the line of a link opens
  the card: the energy of the link, the date of the first link, Call, Video,
  Open the conversation, Put in the light, New reflection (the Reflet view
  with the contact as the recipient), and the thread of the pair, the
  member on the right, with "Reflections only". A click outside, ``Escape``
  or the energy bubble closes it and gives the focus back to what opened
  it; on a small screen the card rises from the bottom.
* The bottom left corner holds "You add to my happiness", a list walked
  with the arrow keys, and the shortcut to the Reflet view; the bottom
  right "+ NewLink", which opens the invitation of the Reflet view.
  "Back", and ``Escape`` out of a field, go back to the previous screen.
* "What my links see" writes the two preferences of the member.
* With "Hide the points and their animations", no number of points shows:
  the lines and the nodes keep one size, "The most active" and the period
  go, and "My partners" lists the contacts by name.
* Every element of the view carries the guide "?" (``data-linkup-guide``),
  and so do the quick replies. The first-use tour of the core is left as it
  is: the specification gives it no step in the Network view.
* A received request for action shows "Agreed", "Let's propose something
  else" and "Not for now" above the block of the card, until one is posted;
  "Let's propose something else" opens "I would like to clarify…", or "So
  if I understand correctly…" once the turn offers the options, and shows
  only when one of them is open to the member. Both parties then read the
  answer on the card.
* The light theme and the dark one: tokens of web and Bootstrap only, the
  dark tints in ``network_view.dark.scss``. In the light theme the lines
  reach 3:1 against the background, and the grey lines are dashed too.

Choices
=======

Decided by the owner (2026-11-12):

* Q-41: the energy of a member and of a link decays with a half-life of
  90 days, a setting (``linkup.energy_half_life_days``); Q-08 stays, the
  energy being the karma, decayed.

Applied by default, to confirm:

* A half-life of 0 turns the decay off; an unset or invalid one takes 90
  days. The decay counts whole days, so an energy does not move within
  the day of a line.

The questions of entry of Lot 3 take the recommendation of the
specification:

* Q-08: the energy of a member is their karma.
* Q-09: a grey line between two contacts needs the consent of both.
* Q-10: the bottom left corner of the view holds two buttons, the
  happiness field and the shortcut to the Reflet view.
* Q-26: the link card holds the thread of the pair, with a filter on the
  reflections.
* Q-40: X3 keeps the top N partners, N = 2; the round button of a small
  screen cycles X1 → X2 → X3 → X1, a large screen shows the three buttons
  of the mock-up; the list button of a small screen shows "The most
  active", then "My partners", then the graph again, and the energy bubble
  brings the graph back. On a large screen the rankings open on "My
  partners", the tab every member has.

License
=======

AGPL-3.0 or later.
