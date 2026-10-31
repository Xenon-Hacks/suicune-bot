"""
alarm.py -- tells your phone when the bot stops for a shiny (or an
encounter it couldn't tell): a Discord message with the alert screenshot.

Setup: py alarm.py --setup saves "discord_webhook_url" to config.json
(see README "Discord alert"). Messages start with @everyone so they notify
even on "Only @mentions" servers; "discord_ping_everyone": false turns that
off. config.json is gitignored, so the URL never ends up on GitHub.
Without it the bot pauses for a shiny exactly as before.

Nothing here may ever stop the bot from pausing: every failure is printed
and swallowed, and the upload runs in the background so the pause starts
immediately.

    py alarm.py --test      sends a test message
"""

import glob
import json
import os
import threading
import urllib.request
import uuid

DISCORD_TIMEOUT = 20   # seconds for the webhook upload
BOT_NAME = "Suicune Bot"   # the sender name shown in Discord


def format_alert(kind, name, encounters, runtime_s, detail="", test=False):
    """The alert text, laid out like the original mockup:
        ✨ **Shiny Suicune found!**
        shiny flash: 5 inverted frame(s), ...
        Encounter #1,284 · 9h 12m of runtime
        Bot is paused, waiting for you.
    kind: "shiny", or "unsure" when the bot couldn't tell; `detail` says
    why."""
    title = {"shiny": f"✨ **Shiny {name} found!**",
             }.get(kind, f"❓ **Possible shiny {name}!** The bot couldn't "
                         f"tell, check it yourself.")
    h, m = divmod(int(runtime_s // 60), 60)
    runtime = f"{h}h {m}m" if h else f"{m}m"
    lines = [title]
    if detail:
        lines.append(detail)
    lines.append(f"Encounter #{encounters:,} · {runtime} of runtime")
    last = "Bot is paused, waiting for you."
    if test:
        last += " *(test alert -- no shiny, nothing paused)*"
    lines.append(last)
    return "\n".join(lines)


def _multipart(fields, files):
    """multipart/form-data body for urllib (no requests needed)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"{name}\"\r\nContent-Type: application/json\r\n\r\n"
                     .encode() + value.encode() + b"\r\n")
    for i, (path, ctype) in enumerate(files):
        with open(path, "rb") as f:
            data = f.read()
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"files[{i}]\"; filename=\"{os.path.basename(path)}\"\r\n"
                     f"Content-Type: {ctype}\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def send_discord(webhook_url, message, attachments=(), ping_everyone=True):
    """Posts `message` with the given files. Returns True on success.
    ping_everyone starts it with @everyone, so Discord notifies even when the
    server is set to "Only @mentions" (the default for new servers)."""
    types = {".png": "image/png"}
    files = [(p, types.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))
             for p in attachments if p and os.path.exists(p)]
    # @everyone goes at the END, so the notification still opens with the
    # headline ("Suicune Bot: ✨ Shiny Suicune found! ...").
    payload = {"username": BOT_NAME, "content": message,
               "allowed_mentions": {"parse": []}}
    if ping_everyone:
        payload["content"] = message + "\n@everyone"
        payload["allowed_mentions"] = {"parse": ["everyone"]}
    body, ctype = _multipart({"payload_json": json.dumps(payload)}, files)
    req = urllib.request.Request(webhook_url, data=body, method="POST",
                                 headers={"Content-Type": ctype,
                                          "User-Agent": "suicune-bot"})
    with urllib.request.urlopen(req, timeout=DISCORD_TIMEOUT) as resp:
        return 200 <= resp.status < 300


def notify(cfg, message, picture=None):
    """Sends the alert in the background. Returns a wait() function the
    caller can use to let a slow upload finish. Never raises."""
    url = cfg.get("discord_webhook_url")
    if not url:
        return lambda timeout=0: None

    def post():
        try:
            send_discord(url, message, [picture],
                         ping_everyone=cfg.get("discord_ping_everyone", True))
            print("  (Discord alert sent)", flush=True)
        except Exception as e:
            print(f"  (Discord alert failed: {e} -- the bot is still paused "
                  f"and waiting for you)", flush=True)
    poster = threading.Thread(target=post, daemon=True)
    poster.start()
    return lambda timeout=5.0: poster.join(timeout=timeout)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="send a test alert")
    parser.add_argument("--setup", action="store_true",
                        help="paste your Discord webhook URL and save it to config.json")
    args = parser.parse_args()
    if not (args.test or args.setup):
        parser.print_help()
        raise SystemExit(0)
    try:
        with open("config.json") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}
    if args.setup:
        url = input("Paste the Webhook URL from Discord (right-click -> Paste), "
                    "then press ENTER:\n> ").strip().strip('"')
        if not url.startswith(("https://discord.com/api/webhooks/",
                               "https://discordapp.com/api/webhooks/")):
            raise SystemExit("That doesn't look like a Discord webhook URL (it should "
                             "start with https://discord.com/api/webhooks/). Nothing saved.")
        cfg["discord_webhook_url"] = url
        with open("config.json", "w") as f:
            json.dump(cfg, f, indent=2)
        print("Saved to config.json. Sending a test message...")
    if not cfg.get("discord_webhook_url"):
        raise SystemExit("No discord_webhook_url in config.json yet -- see the "
                         "README's 'Shiny alarm' section.")
    # Attach a battle image like a real alert: the newest alert screenshot
    # if there is one, otherwise the 3DS screen right now.
    shots = sorted(glob.glob(os.path.join("alerts", "*.png")), key=os.path.getmtime)
    picture = shots[-1] if shots else None
    if picture is None:
        try:
            import cv2
            import shared_frame
            cap = shared_frame.SharedFrameCapture(rotation=cfg.get("shared_rotation", 1))
            if shared_frame.wait_until_available(cap, timeout=3.0):
                picture = "test_alert.png"
                cv2.imwrite(picture, cap.frame())
        except Exception:
            picture = None   # the text still goes out
    print(f"Attaching: {picture or 'no image (no alert screenshot or NTR-VC frame found)'}")
    wait = notify(cfg, format_alert("shiny", "Suicune", 1284, 9 * 3600 + 12 * 60,
                                    test=True), picture)
    wait(DISCORD_TIMEOUT)
