"""
session_log.py -- saves everything the bot prints to a timestamped log
file in logs/, so the full history of a run survives even if the console
can't be copied or the window gets closed. The console itself looks
exactly as before; only the file gets a [date time] prefix on each line.
"""

import os
import sys
import time


class _Tee:
    def __init__(self, console, logfile):
        self.console, self.logfile, self.at_line_start = console, logfile, True

    def write(self, text):
        self.console.write(text)
        out = []
        for piece in text.splitlines(keepends=True):
            if self.at_line_start:
                out.append(time.strftime("[%Y-%m-%d %H:%M:%S] "))
            out.append(piece)
            self.at_line_start = piece.endswith("\n")
        try:
            self.logfile.write("".join(out))
            self.logfile.flush()
        except (OSError, ValueError):
            pass            # a full disk or closed file must never stop the bot
        return len(text)

    def flush(self):
        self.console.flush()

    def __getattr__(self, name):     # encoding, isatty, fileno, ...
        return getattr(self.console, name)


def start(prefix="sweet_scent"):
    """Starts copying stdout and stderr (tracebacks too) to a new log file.
    Returns the file's path."""
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", time.strftime(f"{prefix}_%Y%m%d_%H%M%S.txt"))
    logfile = open(path, "a", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, logfile)
    sys.stderr = _Tee(sys.__stderr__, logfile)
    return path
