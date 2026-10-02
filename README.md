# Suicune Bot -- shiny Suicune hunter for Pokemon Crystal (3DS) -- V3

Soft-resets Pokemon Crystal on a 3DS over and over until Suicune is shiny,
then stops and pings your phone on Discord with a picture of the battle.

Each attempt, about 27 s:

1. **Soft reset** (A + B + SELECT + START).
2. **Mash A** through the logos, title screen, CONTINUE and the save
   summary, stopping the moment your saved spot outside Tin Tower is back.
3. **Step UP once** into the Tin Tower door (checked on screen; retried up
   to 3 times if the step didn't happen).
4. **Mash A through the cutscene** until the battle starts.
5. **Check Suicune's colours** against the NORMAL/SHINY sprites. Normal:
   back to 1. Shiny (or too close to call): **stop, send the Discord
   alert, and wait for you.**

The only buttons it ever presses are A, UP (only once the saved spot is
confirmed on screen) and the reset combo.

## What's new in V3

- **Discord shiny alert.** When the bot stops it posts, as "Suicune Bot":

  > ✨ **Shiny Suicune found!**
  > Encounter #1,284 · 9h 12m of runtime
  > Bot is paused, waiting for you.
  > @everyone
  > *(the battle screenshot)*

  The @everyone ping makes Discord notify you even when the server is set
  to "Only @mentions". A failed upload never stops the bot from pausing.
- `py alarm.py --setup` saves your webhook link (no file editing) and
  sends a test; `py alarm.py --test` sends another test any time.
- Setup instructions for new users (below).

V2 (faster cycle: reset gap, A-mash pace, overworld confirm) and V1 are
tagged `v2` and `v1` in this repo.

---

## What you need

- A **3DS with Luma3DS** (custom firmware) and **Pokemon Crystal** (3DS
  Virtual Console).
- A **Windows PC** on the same Wi-Fi as the 3DS.
- **Python 3.10+** from https://www.python.org/downloads/ (tick "Add
  python.exe to PATH" in the installer).
- The **frame-sharing NTR viewer** (`ntrviewer.exe` from the
  [NTR-VC](https://github.com/Xenon-Hacks/NTR-VC) build). It hands the
  game picture straight to the bot, so the viewer window can be minimised
  or covered while the bot runs.
- Optional: **Discord** on your phone, for the shiny alert.

## Setup (once)

### 1. Get the bot

Download this repo (green **Code** button -> **Download ZIP**, then unzip)
or `git clone` it. Open a terminal in that folder and install the Python
packages:

```
py -m pip install -r requirements.txt
```

(On Windows use `py`, not `python`, for every command here.)

### 2. Turn on InputRedirection on the 3DS

On the 3DS press **L + Down + SELECT** to open the Rosalina menu ->
**Miscellaneous options** -> **Enable InputRedirection**. Note the **IP
address** it shows (e.g. `192.168.x.x`) -- every command below needs it.

Close InputRedirectionClient-Qt or any other input tool on the PC while
the bot runs: two programs sending buttons at once makes presses land
twice or not at all.

### 3. Start the viewer

Start the frame-sharing `ntrviewer.exe`, connect it to the 3DS, then:

```
py test_shared_frame.py
```

It saves `shared_frame_test.png`. The game should be upright with black
bars left and right. If it's sideways, try `py test_shared_frame.py
--rotation 0` (or 2, 3) and put the one that works in `config.json` as
`"shared_rotation": N`.

### 4. Make your save

In Crystal, with the Clear Bell, stand **right outside the Tin Tower door
(Ecruteak City), facing up at the door**, and **save**. Every attempt
starts from this save.

### 5. Calibrate

```
py calibrate.py
```

It shows you the 3DS picture twice and asks you to drag a box each time
(drag, then ENTER or SPACE):

- **Battle box** -- on any screen before the battle, a box around a spot
  that will clearly change once the battle starts (e.g. where Suicune's
  HP box appears). Then play into the Suicune battle yourself and press
  ENTER for the second picture.
- **Overworld box** -- soft-reset (A+B+SELECT+START) and load your save,
  then a box around a big part of the scene around your character (tower,
  door, trees). **Keep it inside the game picture -- no black side bars.**

Redo one later with `py calibrate.py --battle` or `--overworld`.

### 6. Test one cycle

```
py test_walk.py --ip <3ds ip>
```

It runs one reset -> walk -> cutscene -> battle and stops (~30 s). You
should end up looking at the Suicune battle. Run it 3-5 times.

### 7. Discord alert (optional, recommended)

1. **Make a server for it** (you need to own the server to make a
   webhook): in Discord tap **+** at the bottom of the server list ->
   **Create My Own** -> **For me and my friends**.
2. **Create the webhook and copy its link:**
   - *PC:* hover the channel -> gear icon -> **Integrations** ->
     **Webhooks** -> **New Webhook** -> **Copy Webhook URL**.
   - *Phone:* tap the server name -> **Settings** -> **Integrations** ->
     **Webhooks** -> **New Webhook** -> tap it -> **Copy Webhook URL**.

   The link looks like `https://discord.com/api/webhooks/123.../AbC...`.
   Keep it private: anyone with it can post in your channel.
3. **Save it:**
   ```
   py alarm.py --setup
   ```
   Paste the link (right-click) and press ENTER. It's saved to
   `config.json` (never uploaded to GitHub) and a test alert is sent.
4. **Check your phone got it.** If not: Discord doesn't push to your phone
   while you're active in Discord on the PC (close it or wait a few
   minutes), and check notifications are allowed for Discord in the
   phone's settings.

`py alarm.py --test` sends another test any time. To turn the @everyone
ping off, add `"discord_ping_everyone": false` to `config.json`.

## Running it

```
py suicune_bot.py --ip <3ds ip>
```

You can minimise the viewer. Each attempt prints a line like:

```
[12.3 min] Encounter #27... Suicune (#27), normal colours (shiny-ness -0.05). Resetting.
  (reset+menus 7.2s, step 0.5s, cutscene 16.9s, check 2.0s, cycle 27.4s)
```

**When it finds a shiny** it stops pressing buttons, saves a screenshot
in `alerts/`, sends the Discord alert, and waits. **Take over on the 3DS
and catch it.** Pressing ENTER in the bot window resumes hunting (with a
soft reset), so only do that after you've caught it -- or if it was a
false alarm. **Ctrl+C** quits.

It also pauses if the stream dies for 30 s (viewer closed, 3DS froze) or 3
attempts in a row fail; it says why. Fix it and press ENTER.

## Troubleshooting

- **"config.json is still from the screen-capture setup"** -- run
  `py calibrate.py`.
- **"Overworld never appeared"** -- watch the `(overworld match: X.XX)`
  lines. The saved spot should score well above 0.75. Redo
  `py calibrate.py --overworld` (box inside the game picture).
- **Time of day.** The Tin Tower entrance is outdoors, so Crystal recolours
  it at 4:00 (morning), 10:00 (day) and 18:00 (night). The bot copes with
  most of that, but if the overworld score drops near 0.75 after one of
  those times, load the save then and run `py calibrate.py --overworld-add`
  to add a picture for that time of day.
- **No battle detected** -- redo `py calibrate.py --battle`.
- **Wrong option on the title screen** -- the bot mashes A, so CONTINUE
  (not NEW GAME) must be the highlighted option, which is how Crystal
  behaves once a save exists.
- **Logs** are in `logs/`; if the bot ever freezes, `hang_report.txt`
  says where.

## Tuning

`reset_menu.py`: `RESET_GAP` (0.5 s), `MASH_INTERVAL` (0.2 s), `MASH_HOLD`
(0.15 s), `MASH_TIMEOUT` (30 s).
`walk_menu.py`: `OVERWORLD_MATCH_THRESHOLD` (0.75), `OVERWORLD_CONFIRM`
(0.25 s), `WALK_HOLD` (0.25 s), `WALK_TRIES` (3), `CUTSCENE_TIMEOUT` (45 s).

## Files that stay on your PC

`config.json` (your boxes and Discord link), the `ref_*.png` calibration
pictures, `logs/`, `alerts/` and `test_alert.png` are in `.gitignore`, so
they're never uploaded.
