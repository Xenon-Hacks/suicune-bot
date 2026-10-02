"""
test_walk.py -- runs the REAL soft reset -> mash to overworld -> step UP ->
cutscene -> battle sequence once (same code path as suicune_bot.py),
so you can confirm it lands in the battle before leaving it unattended.

Requires calibrate.py to have saved battle_indicator_roi, overworld_roi,
ref_battle.png and ref_overworld_start.png, and the frame-sharing NTR-VC
running (it can be minimised).

Stand your save one tile below the event tile, facing up, in the
overworld, with no menu open, THEN run:

    py test_walk.py --ip <3ds ip>
"""

import argparse

from luma_input import Luma3DSInput
import reset_menu
import walk_menu
import watch
from suicune_bot import in_battle, load_config, make_capture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True)
    args = parser.parse_args()

    cfg = load_config()
    cap = make_capture(cfg)
    pad = Luma3DSInput(args.ip)
    watch.install(pad)

    print("Make sure your save is standing one tile below the event tile, "
          "facing up, in the overworld, with no menu open.")
    input("Press ENTER to soft-reset, walk up and mash through to the battle: ")

    try:
        reset_menu.soft_reset(pad)
        reached = walk_menu.mash_to_overworld(pad, cap, cfg, in_battle)
        if reached is None:
            print("\nThe saved overworld never showed up. Watch the (overworld "
                  "match: X.XX) lines: if they never got near "
                  f"{walk_menu.OVERWORLD_MATCH_THRESHOLD}, redo "
                  "py calibrate.py --overworld.")
            return
        if reached == "battle":
            print("\nA battle started before any step -- the save is probably "
                  "already standing on the event tile.")
            return
        if not walk_menu.walk_up(pad, cap):
            print("\nThe step UP never registered. Check the character can "
                  "actually walk up from the saved spot.")
            return
        if reset_menu.mash_to_battle(pad, cap, cfg, in_battle,
                                     timeout=walk_menu.CUTSCENE_TIMEOUT):
            print("\nThe battle started -- confirm you're actually looking at "
                  "the wild encounter now.")
        else:
            print("\nNo battle after the cutscene. If the cutscene is just "
                  "long, raise CUTSCENE_TIMEOUT in walk_menu.py; otherwise "
                  "check the battle_indicator_roi calibration.")
    finally:
        pad.close()
        print("Released control back to the physical buttons.")


if __name__ == "__main__":
    main()
