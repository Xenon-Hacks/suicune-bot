"""
calibrate.py -- one-time setup helper. Run this BEFORE suicune_bot.py.

Always reads the picture from the frame-sharing NTR-VC (NTRViewer-HR
frame-share build), the same source the bot uses, so NTR-VC can stay
minimised the whole time. There's no screen-capture mode any more and no
capture region to drag. Have the frame-sharing ntrviewer.exe running and
connected to the 3DS before you start (py test_shared_frame.py checks
that).

It needs two things:
  1. the battle indicator -- a spot that changes once the battle starts;
  2. the overworld start screen -- what your save loads into (outside the
     Tin Tower door), so the bot knows when to stop mashing A and step UP.
Species/shininess use the NORMAL/SHINY sprite folders instead.

Usage:
    py calibrate.py                  whatever isn't set yet (both, first time)
    py calibrate.py --battle         redo the battle indicator
    py calibrate.py --overworld      redo the overworld start screen
    py calibrate.py --overworld-add  add a shot of it at another time of day
"""

import argparse
import glob
import json
import os
import sys

import cv2

import shared_frame

CONFIG_PATH = "config.json"
SCREEN_ONLY_KEYS = ["capture_region", "frame_source"]   # from the old
                                    # screen-capture setup; ROIs measured on
                                    # the screen don't fit the shared picture


def select_region(prompt, img):
    print(prompt)
    print("Drag a box, then press ENTER or SPACE to confirm (C to cancel).")
    r = cv2.selectROI("calibrate - " + prompt, img, showCrosshair=True)
    cv2.waitKey(1)  # let the window finish one more redraw before closing --
                     # skipping this can crash/hang cv2's GUI teardown on Windows
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    x, y, w, h = (int(v) for v in r)
    print(f"Got a {w}x{h} box at ({x}, {y}).")
    return x, y, w, h


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return {}
    if "capture_region" in cfg or cfg.get("frame_source") == "screen":
        # Left over from screen capture: those boxes were measured on a
        # different picture, so start them over.
        print("config.json was set up for screen capture -- clearing it so "
              "both boxes are redone on the shared picture.")
        cfg = {k: v for k, v in cfg.items()
               if k not in SCREEN_ONLY_KEYS + ["battle_indicator_roi", "overworld_roi"]}
    cfg.pop("frame_source", None)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"Saved {CONFIG_PATH}")


_cap = None


def grab(cfg):
    """The current picture from the frame-sharing NTR-VC."""
    global _cap
    if _cap is None:
        _cap = shared_frame.SharedFrameCapture(rotation=cfg.get("shared_rotation", 1))
        if not shared_frame.wait_until_available(_cap, timeout=15.0):
            raise SystemExit("No frames from the frame-sharing NTR-VC -- start "
                             "it, connect it to the 3DS, and try again "
                             "(py test_shared_frame.py checks the connection).")
    return _cap.frame()


def calibrate_battle_indicator(cfg):
    """A region that looks visibly different before vs. during the battle
    -- e.g. where the HP box appears. Captured twice: once now (any
    pre-battle screen), once in the Suicune battle."""
    input("Get the game to any PRE-BATTLE screen (e.g. standing at the "
          "saved spot, or the title screen), then press ENTER here: ")
    frame = grab(cfg)
    x, y, w, h = select_region(
        "Drag a box around a spot that will clearly change once the "
        "battle starts (e.g. where the HP box appears).", frame)
    if w == 0 or h == 0:
        print("Empty selection, aborting.")
        sys.exit(1)
    cfg["battle_indicator_roi"] = {"left": x, "top": y, "width": w, "height": h}

    input("Now let a cycle run all the way into the battle (step into Tin "
          "Tower, let the cutscene play). Once you're in it, press ENTER "
          "here: ")
    frame2 = grab(cfg)
    cv2.imwrite("ref_battle.png", frame2[y:y + h, x:x + w])
    print("Saved ref_battle.png.")
    save_config(cfg)
    return cfg


def calibrate_overworld(cfg):
    """The overworld screen your save loads into. The bot stops mashing A
    as soon as this is back on screen after a reset, and only then steps
    UP. Saved as ref_overworld_start.png."""
    input("Soft-reset and load your save, so you're standing at the saved "
          "spot (in front of the Tin Tower door, facing up) with no text "
          "box or menu open. Then press ENTER here: ")
    frame = grab(cfg)
    x, y, w, h = select_region(
        "Drag a box around a large part of the overworld around your "
        "character (the tower, door and trees, not just the character). "
        "Keep it INSIDE the game picture -- no black side bars.", frame)
    if w == 0 or h == 0:
        print("Empty selection, aborting.")
        sys.exit(1)
    cfg["overworld_roi"] = {"left": x, "top": y, "width": w, "height": h}
    for old in glob.glob("ref_overworld_start*.png"):
        os.remove(old)       # extra time-of-day shots belong to the old box
    cv2.imwrite("ref_overworld_start.png", frame[y:y + h, x:x + w])
    print("Saved ref_overworld_start.png.")
    save_config(cfg)
    return cfg


def add_overworld_shot(cfg):
    """Adds another picture of the same saved spot, for a different time of
    day (morning/day/night recolour the outdoors in Crystal). Uses the box
    already chosen, so nothing to drag. The bot accepts whichever matches
    best."""
    if "overworld_roi" not in cfg:
        print("Run py calibrate.py --overworld first.")
        sys.exit(1)
    input("Load your save so you're standing at the saved spot with no text "
          "box or menu open (at a different time of day from the existing "
          "shots). Then press ENTER here: ")
    r = cfg["overworld_roi"]
    frame = grab(cfg)
    n = 2
    while os.path.exists(f"ref_overworld_start_{n}.png"):
        n += 1
    path = f"ref_overworld_start_{n}.png"
    cv2.imwrite(path, frame[r["top"]:r["top"] + r["height"], r["left"]:r["left"] + r["width"]])
    print(f"Saved {path}.")
    return cfg


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--battle", action="store_true",
                         help="redo the battle indicator")
    parser.add_argument("--overworld", action="store_true",
                         help="redo the overworld start screen")
    parser.add_argument("--overworld-add", action="store_true",
                         help="add another overworld start shot (a different "
                              "time of day)")
    args = parser.parse_args()

    try:
        cfg = load_config()
        if args.battle:
            cfg = calibrate_battle_indicator(cfg)
        elif args.overworld:
            cfg = calibrate_overworld(cfg)
        elif args.overworld_add:
            cfg = add_overworld_shot(cfg)
        else:
            # Only run whichever steps aren't already saved, so re-running
            # this after an interruption doesn't redo steps that worked.
            if "battle_indicator_roi" not in cfg:
                cfg = calibrate_battle_indicator(cfg)
            else:
                print("battle_indicator_roi already set -- skipping (use "
                      "--battle to redo it).")
            if "overworld_roi" not in cfg:
                cfg = calibrate_overworld(cfg)
            else:
                print("overworld_roi already set -- skipping (use "
                      "--overworld to redo it).")
            save_config(cfg)
            print("\nAll set. Run:\n"
                  "    py test_walk.py --ip <3ds ip>\n"
                  "    py suicune_bot.py --ip <3ds ip>")
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        input("\nDone -- press ENTER to close this window.")
