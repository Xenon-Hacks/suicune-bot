# Suicune Shiny Hunter (Pokemon Crystal) -- V2

## What's new in V2 (vs. V1)

V1 ran 17 clean cycles at 29.0 s each:
reset 1.3 s, menus to overworld 8.5 s, step 0.5 s, cutscene 16.9 s (fixed
by the game), shiny check 2.0 s. V2 trims the parts the bot controls:

- `RESET_GAP` 1.0 -> 0.5 s (reset_menu.py): A on the black boot screen
  does nothing, so mashing starts sooner.
- `MASH_INTERVAL` 0.35 -> 0.2 s (reset_menu.py): A every 0.35 s instead of
  0.5 s. `MASH_HOLD` is unchanged, so presses aren't easier to lose.
- `OVERWORLD_CONFIRM` 0.5 -> 0.25 s (walk_menu.py): every other screen
  scored 0.00-0.08 against 0.75 in V1's log. The settle wait before the
  step is unchanged.
- Each encounter line now ends with a per-phase timing breakdown, e.g.
  `(reset+menus 7.2s, step 0.5s, cutscene 16.9s, check 2.0s, cycle 27.4s)`.

Nothing after the battle starts (the shiny check) changed.

A variant of `static_encounter_bot_v1` for encounters that need **one step
before the cutscene starts** (e.g. Suicune). The original static bot is
untouched; this folder is a separate copy with its own config, logs and
alerts.

## The premise

Save your game standing **one tile below the tile that triggers the
event, facing up**, with nothing directly in front of you that can be
talked to. For Suicune that's right outside the
Tin Tower door: the step walks into the door, the game walks you up
inside on its own, and the battle starts about 16 s later. Every attempt
is then:

1. **Soft reset** (A + B + SELECT + START), same as the static bot.
2. **Mash A** through the boot logos, title screen, CONTINUE and the save
   summary, and **stop the moment the saved overworld is back on
   screen** (matched against `ref_overworld_start.png`).
3. **Step UP once.** The bot checks the screen actually changed (a tile
   of scrolling, or the cutscene starting); if it only turned or the
   press was lost, it presses UP again, up to 3 times.
4. **Mash A through the cutscene** until the battle starts.
5. **Identify** the encounter exactly like the static bot. Not shiny:
   back to step 1. Shiny, unsure or unrecognised: stop and wait for you.

The only inputs ever sent are A, UP (only once the overworld is
confirmed) and the reset combo.

## Setup

This bot **always** reads the picture from the frame-sharing NTR-VC
(NTRViewer-HR frame-share build), so NTR-VC can be minimised, covered or
moved while it runs. There is no screen-capture mode.

1. `py -m pip install -r requirements.txt`
2. Start the frame-sharing ntrviewer.exe and connect it to the 3DS.
   `py test_shared_frame.py` checks it (the game should be upright; if
   not, put `"shared_rotation": N` in config.json).
3. `py calibrate.py` -- two steps, both on the shared picture (no window
   switching needed):
   - **battle indicator**: a box around a spot that changes once the
     battle starts, shot once before and once in the Suicune battle;
   - **overworld start screen**: load your save to the saved spot, then a
     box around a large part of the overworld around your character,
     kept inside the game picture (no black side bars).
   `--battle` / `--overworld` redo one of them.
4. `py test_walk.py --ip <3ds ip>` runs one full cycle so you can watch it
   land in the battle.

### Time of day

The spot outside Tin Tower is outdoors, so Crystal recolours it for
morning (4:00), day (10:00) and night (18:00). The bot compares it in
grayscale, which copes with most of that, but if a run crosses one of
those times and the `(overworld match: X.XX)` lines drop near
`OVERWORLD_MATCH_THRESHOLD`, load the save at that time of day and run
`py calibrate.py --overworld-add`. It keeps the same box and adds one more
picture; the bot uses whichever matches best. (`--overworld` starts over
and deletes the extra ones.)

## Running it

```
py suicune_bot.py --ip <3ds ip>
```

Each cycle prints, e.g.:

```
  Soft-resetting (A+B+SELECT+START)...
  Overworld loaded after 31 A presses (12.4s).
  Walking one tile UP (press 1/3)...
  Step taken -- waiting for the cutscene and battle.
  Battle started after 9 A presses (6.2s).
[0.4 min] Encounter #1... Suicune (#1), normal colours (shiny-ness -0.03). Resetting.
```

## Tuning (walk_menu.py)

- `OVERWORLD_MATCH_THRESHOLD` (0.75) -- watch the `(overworld match: X.XX)`
  lines. The saved spot should read well above it, the title/CONTINUE
  screens well below.
- `WALK_HOLD` (0.25 s) / `WALK_TRIES` (3) -- how long UP is held and how
  many presses before giving up on the attempt.
- `WALK_DIFF` (4.0) -- how much the whole screen must change to count as
  "moved". Turning on the spot stays well under it.
- `CUTSCENE_TIMEOUT` (45 s) -- ceiling for step -> cutscene -> battle.

Reset timing, NTR-VC minimising, freeze handling, logs and the hang report
all work exactly as in `static_encounter_bot_v1/README.md`. Logs go to
`logs/suicune_<date>_<time>.txt`.
