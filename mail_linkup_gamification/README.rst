================================
LinkUp — Points and gamification
================================

Applies the LinkUp point scale on top of the Odoo ``gamification`` module.

Scale
=====

* ``linkup.points.rule`` holds one rule per scoring code of the core, with
  its points, its beneficiaries (both parties, the author of the
  reflection, or nobody), its caps and its decay. The default scale of the
  specification is loaded as ``noupdate`` data; a LinkUp administrator
  edits it under *Discuss › LinkUp › Points*.
* The points of ``reflect_sent`` are paid with the confirmation, together
  with the 1000 of ``reflect_confirmed`` for both parties: a rejected
  reflection costs its author 150 points, nothing more, and the karma may
  go negative.
* Any answered call between the members of an ``active`` pair pays
  ``call_answered`` (250) to both, whoever started it and from wherever,
  with a cap of one call a day per pair.

Ledger and karma
================

* ``linkup.points.ledger`` is append-only: one line per beneficiary of an
  event, unique per rule, member and ``event_key``, so an event reported
  twice pays once. A line left at 0 by a cap, a decay or the account of its
  member is kept, ``capped``, with its reason.
* Each event locks the rows of its members (``FOR NO KEY UPDATE NOWAIT``,
  in id order) before counting the caps and adding the karma, through one
  ``gamification.karma.tracking`` per member. The karma of a member thus
  equals the sum of their lines; a daily cron logs an error for any
  member where it does not (LU-NF-043), and gives each LinkUp
  administrator a to-do activity naming those members by id, unless one
  is still open for the same members.
* Each line reaches its member on ``linkup.points/awarded``; a capped line
  carries ``linkup.cap_reached``. The energy of the link of the pair
  (``energy_a`` / ``energy_b``) adds the points of each side; only the
  LinkUp administrators read those fields, a member reading their own
  side through the server.
* The uninstallation takes the points of the ledger out of the karma of
  their members, and keeps the karma earned elsewhere.
* Two indexes serve the readings by member (LU-NF-029): ``(user_id,
  date)`` for "My points", the caps and the rankings by period, and
  ``(user_id, partner_user_id)`` for the counterparts of "My points".

Caps and decay
==============

* Daily and weekly caps, for a member or within a pair, count sliding
  windows of 24 hours and 7 days: a change of time zone never pays a day
  twice. A lifetime cap of the pair stops loops of accounts confirming
  each other.
* Rounds of free text of an ``active`` pair pay ``virtual_round`` to both
  when the other member answers: 100, 50, 25, 12, 6, 3, 1, then 0, or the
  sequence of ``linkup.virtual_round_points``. Continuations and exact
  answers halve the same way. Each sequence starts again at midnight in
  the time zone of the member (``tz``, then ``linkup.timezone``, then
  ``America/Toronto``), and after a confirmation or an answered call of
  the pair. A member who changes time zone starts no sequence again
  before 23 hours have passed since the midnight of their current one.
* A confirmation or a call starts the sequences again within the caps of
  24 hours and 7 days of its rule, which count the lines that reset as
  they count the lines that pay: a call beyond the cap of the pair resets
  nothing, a confirmation after the first link of the pair still does.
* An account younger than 72 hours, or not verified, earns no points;
  penalties still apply. ``res.users._linkup_points_verified`` is the hook
  of the verification of the public signup.
* The moderation receives an automatic report when a pair confirms more
  than 3 reflections in 7 days, or a member confirms more than 5
  reflections of accounts younger than 48 hours. A minimum duration of a
  call, 0 by default, pays an answered call at its end.

Ranks and badges
================

* Five LinkUp ranks replace the native ones, whose external ids then name
  them, so an update of ``gamification`` does not bring them back. A
  member whose karma falls below the lowest rank holds none.
* Five badges, granted by the server only: first reflection, first link,
  ten links, first guess, first call. A member reads their own badges and
  grants none, the native badges included.
* A member receives no email from the gamification: ranks and badges are
  announced on the bus (``linkup.points/rank``, ``linkup.points/badge``),
  and the native challenges are closed.

API
===

* ``linkup.points.ledger.linkup_my_points(limit, offset, rule_code,
  counterpart_id, after_id)`` and the route ``/linkup/v1/me/points`` give
  the balance, rank, next rank, badges, the point scale, the people the
  member shares lines with, and the lines of the current member, never
  those of another one. ``rule_code`` and ``counterpart_id`` filter the
  lines; ``after_id`` keeps those newer than a known line, oldest first.
* ``linkup.reflet.linkup_channel_info`` adds ``link_energy``: the energy of
  the link as its reader received it.

Web client
==========

* Each ledger line rises as "+N" or "−N" above the energy of the member,
  or in the top corner, wiggling for 1.2 s (still under reduced motion),
  and a polite live region announces it ("You earn 1000 points"). The line
  comes from the bus, or from a reading of ``linkup_my_points`` right
  after an action on a reflection, so the points of an action show even
  when the bus is late; its id shows it once.
* A gain plays ``linkup-yeah`` once per event, under the sound settings of
  the core (a reward sound, off by default); discreet notifications
  (``linkup_notify_discreet``) keep it silent, and the "+N" still shows. A capped line shows
  "Sent. No more points today for this action." A new rank or badge is
  shown and announced the same way.
* The energy (karma) and rank of the member show in a bubble next to
  their avatar in the Reflet view and at the top of the LinkUp panel, with
  the energy of the link of the conversation.
* "My points" (``linkup.my_points``, *Discuss › LinkUp › My points*, the
  LinkUp section of the sidebar, the energy bubble and the ninth entry of
  the menu of the avatar): energy, rank and
  the way to the next one, badges, point scale, and the history filtered
  by event and by person, page by page, with the "?" guide.
* The guide of the core tells the points of a confirmation, a rejection
  and a guess, from the scale in force.
* "Hide the points and their animations" (``res.users.settings``, on the
  LinkUp help page) removes the energy, the bursts, their sound and the
  points in the guide; the points are still counted, and "My points"
  stays reachable.

Demonstration
=============

* The demonstration pays the reflections of the demonstration of the core
  through their scoring events, and one answered call to four pairs: the
  accounts of the demonstration are dated back before their links, so
  they earn points, and their karma equals the sum of their lines. Sam
  holds 2700 points, the rank Flame, and France 2250, the rank Spark; the
  pair Sam-Jacques holds no line. The values of the deck, such as the
  energy of a link at 32450, are not reproduced: the caps of the scale
  bound what the events of one day pay.

License
=======

AGPL-3.0 or later.
