"""
shiny_flash.py -- decides shiny / normal from the shiny ANIMATION, not from
what the Pokemon looks like. No Pokemon graphics are used.

What the game does (traced in the pokecrystal decompile,
github.com/pret/pokecrystal):

  * engine/battle/core.asm, BattleStartMessage: for a wild battle the game
    calls BattleCheckEnemyShininess. Only if the Pokemon is shiny does it
    play ANIM_SEND_OUT_MON with parameter 1 -- the shiny animation. A
    normal wild Pokemon gets no animation at all here.
  * data/moves/animations.asm, BattleAnim_SendOutMon.Shiny: the animation
    starts with BATTLE_BG_EFFECT_FLASH_INVERTED, then 8 sparkles (with the
    SFX_SHINE sound) around the Pokemon.
  * engine/battle_anims/bg_effects.asm, BattleBGEffect_FlashInverted: the
    background palette is swapped for its exact reverse (white <-> black,
    light <-> dark) for 5 frames (~83 ms), then put back. That's the "black
    flash". On the Game Boy Color (and so on the 3DS Virtual Console) only
    the battle field's own palette is reversed: its white turns black,
    while the two Pokemon keep their colours and the empty text box below
    stays white. In the real game (built from the decompile and run in an
    emulator) the screen goes from ~223 to ~86 brightness.
  * It happens after the battle-start transition (which always ends on an
    all-black screen: DoBattleTransition.done fills every palette with
    black) and before the enemy HP box and "Wild X appeared!" are drawn.
  * The 3DS Virtual Console's anti-flashing patch (vc/pokecrystal11.patch
    .template) only dims a handful of MOVE animations (Thunder, Explosion,
    Flash, ...) -- not this one, so the flash shows on the 3DS too.

So the detector looks at the frames between the end of the transition (the
last all-black frame) and the moment the battle text/HP box shows, and
looks for one short burst of "photo-negative" frames: much darker than the
battle screen around it, but not blank (the Pokemon and the text box stay
lit), lasting a few frames, with a normal battle screen on both sides.
The photo-negative test only looks at the battle field above the text box:
the text box doesn't change, and counting it watered the real flash down
to a correlation of about -0.3 (-0.2 over NTR-VC: a missed shiny), where
the field alone gives about -1.0. That holds for every species, so
nothing per-Pokemon is needed.

Battle Scene doesn't matter: with it off, BattleAnimRunScript only skips
MOVE animations (wFXAnimID's high byte is 0), and the shiny animation
(ANIM_SEND_OUT_MON, $101) isn't one. Checked in the real game too: with
Battle Scene off the flash and the sparkle sound still play.
"""

import collections

import cv2
import numpy as np

BLANK_MEAN = 40.0        # mean brightness (0-255) at or below which a frame ...
BLANK_LIT = 0.005        # ... with fewer lit pixels than this counts as blank
                         # (the all-black end of the battle transition)
LIT = 128                # a pixel this bright counts as "lit"
BATTLE_MIN_BRIGHT = 110  # the battle screen before the HP box is mostly white;
                         # a segment never this bright isn't a battle intro
DARK_RATIO = 0.6         # a flash frame is darker than this x the battle screen
BRIGHT_RATIO = 0.85      # ... and has frames at least this x as bright around it
INVERTED_MIN_LIT = 0.01  # ... and still has lit pixels (outlines turned white),
                         # unlike a blank frame
MAX_FLASH = 0.35         # s; the real flash lasts 5 frames (0.083 s). Longer
                         # dark spells are something else (a fade, a dropout)
NEIGHBOUR_GAP = 0.25     # s; a bright frame must be this close on each side
NEGATIVE_CORR = -0.3     # the flash frame is a photo-negative of the screen
                         # around it: brightness correlation must be below this
MAX_SAMPLE_GAP = 0.075   # s; with longer gaps between captured frames a
                         # 0.083 s flash could fall between two of them
SMALL = (40, 36)         # thumbnail used for the photo-negative check
FIELD_ROWS = 24          # its rows showing the battle field (Game Boy rows
                         # 0-95); the text box below them never inverts


Stat = collections.namedtuple("Stat", "t mean lit thumb")


def stat(t, native_bgr):
    """The few numbers the detector needs from one 160x144 frame."""
    lum = native_bgr.astype(np.float32).mean(axis=2)
    return Stat(t, float(lum.mean()), float((lum >= LIT).mean()),
                cv2.resize(lum, SMALL, interpolation=cv2.INTER_AREA))


def _is_blank(s):
    return s.mean <= BLANK_MEAN and s.lit < BLANK_LIT


def _corr(a, b):
    a = a.ravel() - a.mean()
    b = b.ravel() - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 1e-6 else 0.0


def analyse(stats, frame_exact=False):
    """stats: Stat tuples in time order, covering at least the end of the
    battle transition up to the battle text / HP box appearing.

    Returns a dict with "verdict" -- "shiny", "normal" or "unsure" -- and
    "reason" (a short explanation for the log), plus "flash_at" (time of
    the flash) when shiny.

    frame_exact: the frames are every single frame the game drew (BizHawk),
    so the capture-gap check is skipped."""
    stats = list(stats)
    last_blank = max((i for i, s in enumerate(stats) if _is_blank(s)), default=None)
    if last_blank is None:
        return {"verdict": "unsure",
                "reason": "never saw the black end of the battle transition, so "
                          "the start of the battle intro wasn't captured"}
    seg = stats[last_blank + 1:]
    if len(seg) < 3:
        return {"verdict": "unsure", "reason": "too few frames after the transition"}

    means = np.array([s.mean for s in seg])
    bright_ref = float(np.percentile(means, 75))
    if bright_ref < BATTLE_MIN_BRIGHT:
        return {"verdict": "unsure",
                "reason": f"the battle screen never looked like a battle intro "
                          f"(brightness {bright_ref:.0f})"}

    dark = [s.mean < DARK_RATIO * bright_ref and s.lit >= INVERTED_MIN_LIT for s in seg]
    bright = [s.mean >= BRIGHT_RATIO * bright_ref for s in seg]

    rejected = []
    i = 0
    while i < len(seg):
        if not dark[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(seg) and dark[j + 1]:
            j += 1
        before = next((k for k in range(i - 1, -1, -1) if bright[k]), None)
        after = next((k for k in range(j + 1, len(seg)) if bright[k]), None)
        duration = seg[j].t - seg[i].t
        why = None
        if before is None or seg[i].t - seg[before].t > NEIGHBOUR_GAP:
            why = "no battle screen just before it"
        elif after is None or seg[after].t - seg[j].t > NEIGHBOUR_GAP:
            why = "no battle screen just after it"
        elif duration > MAX_FLASH:
            why = f"too long for the shiny flash ({duration:.2f}s)"
        else:
            darkest = min(range(i, j + 1), key=lambda k: seg[k].mean)
            c = _corr(seg[darkest].thumb[:FIELD_ROWS],
                      seg[before].thumb[:FIELD_ROWS])
            if c > NEGATIVE_CORR:
                why = f"not a photo-negative of the screen (correlation {c:+.2f})"
            else:
                return {"verdict": "shiny", "flash_at": seg[i].t,
                        "reason": f"shiny flash: {j - i + 1} inverted frame(s), "
                                  f"brightness {seg[darkest].mean:.0f} vs "
                                  f"{bright_ref:.0f}, correlation {c:+.2f}"}
        rejected.append(why)
        i = j + 1

    if not frame_exact:
        gaps = np.diff([s.t for s in seg])
        worst = float(gaps.max()) if len(gaps) else 0.0
        if worst > MAX_SAMPLE_GAP:
            return {"verdict": "unsure",
                    "reason": f"no flash seen, but frames were captured up to "
                              f"{worst * 1000:.0f} ms apart, so a flash could "
                              f"have been missed"}
    reason = "no shiny flash"
    if rejected:
        reason += f" (ignored {len(rejected)} dark moment(s): {rejected[0]})"
    return {"verdict": "normal", "reason": reason}


class FlashRecorder:
    """Keeps the recent frame stats so analyse() can look back over the
    battle intro once the battle text shows up."""

    def __init__(self, keep_seconds=30.0):
        self.keep = keep_seconds
        self.stats = collections.deque()

    def clear(self):
        self.stats.clear()

    def add(self, t, native_bgr):
        self.stats.append(stat(t, native_bgr))
        while self.stats and t - self.stats[0].t > self.keep:
            self.stats.popleft()

    def analyse(self, frame_exact=False):
        return analyse(list(self.stats), frame_exact=frame_exact)
