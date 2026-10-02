"""
reset_menu.py -- soft-resets the game and mashes A from the very first
available frame (boot logos -> title screen -> CONTINUE -> the loading
flash -> any pre-battle dialogue) until the wild Pokemon's battle begins.

This is the static-encounter equivalent of sweet_scent.py, but far
simpler, because of what soft-resetting buys you:

  * Every screen between the reset and the battle only ever needs A
    (title screen, CONTINUE, dialogue text). None of them is a menu
    where landing on the wrong item does something irreversible -- so
    unlike the Sweet Scent field-menu path, there's no cursor to
    verify and no "safe buttons only" rule needed. A can just be
    mashed.
  * There's no flee logic at all. Sweet Scent has to run from every
    non-shiny encounter using a carefully cursor-verified RUN, because
    it's mid-save and can't afford to lose progress. A soft reset
    doesn't have that problem: your last save is standing right in
    front of the static Pokemon, so resetting again *is* "try once
    more" -- there's nothing to escape from.
  * The reset combo itself (A+B+SELECT+START) works from the
    overworld, from any menu, or mid-battle. That makes it this bot's
    only recovery mechanism too: if mash_to_battle() ever times out
    stuck somewhere, the next soft_reset() starts clean from the exact
    same save, no matter what was on screen.

Safety notes:
  * The one assumption this relies on: CONTINUE (not NEW GAME) is
    already the highlighted option when the save-select screen opens,
    which is how Gen II behaves once a save exists. If your cartridge/
    VC save ever defaults somewhere else, mashing A could confirm the
    wrong thing -- check this by hand once after your first real
    reset.
  * It never sends a directional button. The only input this module
    ever sends is A (for mashing) and the one A+B+SELECT+START combo
    (for resetting), so it can never walk the character or move a
    cursor by accident.
"""

import time

from luma_input import Button
import ntr_status

RESET_HOLD = 0.3           # A+B+SELECT+START must land as one combo --
                            # held longer than a normal menu tap since
                            # this goes out over UDP with no delivery
                            # guarantee (a partial combo does nothing).
RESET_GAP = 0.5             # settle time after the combo, before the
                            # first boot frame is expected. Was 1.0; an A
                            # pressed on the black boot screen does nothing,
                            # so mashing can start sooner (suicune_bot
                            # speed-up, 2026-10-02)
RESET_RESEND = 8            # resend the held-combo packet often across
                            # the hold window -- the same reasoning as
                            # luma_input.tap()'s own `resend`, just with
                            # more margin since a dropped reset means
                            # starting the whole loop over
MASH_HOLD = 0.15            # A's hold length while mashing through logos/
                            # title/continue/dialogue
MASH_INTERVAL = 0.2         # gap between mashed A presses. Was 0.35: each
                            # A-gated screen (copyright, title, CONTINUE,
                            # save summary) waited up to a full press cycle
                            # for the next A. MASH_HOLD is unchanged, so
                            # presses aren't any easier to lose.
MASH_TIMEOUT = 30.0         # ceiling for one boot-to-battle attempt.
                            # Traced against the pokecrystal decompile
                            # (github.com/pret/pokecrystal): with A held
                            # down from the first frame, the copyright
                            # screen + GameFreak-Presents skip-check +
                            # title-logo scroll-in add up to a fixed,
                            # unskippable ~2.5-4.5s before CONTINUE is
                            # even reachable -- the intro movie itself is
                            # reliably skipped, not played. 30s leaves
                            # generous room on top of that floor for save
                            # load + whatever pre-battle dialogue this
                            # encounter has. Confirmed against ~2,500 real
                            # cycles (normally 13.6-15.4s, rare outliers up
                            # to ~29.5s): every 30s timeout logged was a
                            # genuine failure, never a slow cycle clipped.
                            # (The old SLOW_CYCLE_WARNING was removed in V1:
                            # it fired on ordinary 15.2-15.4s cycles and
                            # was pure log noise.)


def soft_reset(pad):
    """A+B+SELECT+START together -- the Game Boy/Color soft-reset combo.
    Works from the overworld, a menu, or mid-battle, so it's also this
    bot's entire recovery mechanism: whatever the screen was showing,
    this always starts over from the last save."""
    print("  Soft-resetting (A+B+SELECT+START)...", flush=True)
    pad.tap(Button.A, Button.B, Button.SELECT, Button.START,
            hold=RESET_HOLD, gap=RESET_GAP, resend=RESET_RESEND)


def mash_to_battle(pad, cap, cfg, in_battle, heartbeat=lambda: None,
                    timeout=MASH_TIMEOUT) -> bool:
    """Presses A roughly every MASH_INTERVAL seconds, starting from the
    first frame after a soft reset, until the battle starts. Every
    screen in between only ever advances on A and doesn't care whether
    A lands once or twice, so unlike the Sweet Scent menu path this
    never needs to check what's actually on screen between presses --
    it just needs to know when to stop, which is what in_battle()
    (the same battle-indicator check used everywhere else in this
    bot) is for.

    Returns True once in_battle() is confirmed. Returns False on
    timeout (the caller then soft-resets and tries the whole thing
    again -- cheap, since nothing irreversible can have happened)."""
    start = time.time()
    end = start + timeout
    presses = 0
    while time.time() < end:
        heartbeat()
        if in_battle(cap, cfg):
            elapsed = time.time() - start
            print(f"  Battle started after {presses} A presses "
                  f"({elapsed:.1f}s).", flush=True)
            return True
        if ntr_status.is_down():
            # The picture may be stale -- never mash blind into a frozen
            # frame, just wait for the stream to come back.
            time.sleep(0.25)
            continue
        pad.tap(Button.A, hold=MASH_HOLD, gap=MASH_INTERVAL)
        presses += 1
    print(f"  No battle after {presses} A presses over {timeout:.0f}s -- "
          "giving up on this attempt.", flush=True)
    return False
