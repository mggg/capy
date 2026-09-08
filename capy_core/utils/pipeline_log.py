"""
Wrapper around print() for pipeline scripts.
When running a python script directly (i.e. when PIPELINE_LOG_FILE not set), `log()` behaves like `print()`.
"""

import os
import sys


def log(msg: str, *, file=None) -> None:
    """Print *msg* with immediate flush.
    Parameters
    ----------
    msg:
        The message to emit.
    file:
        Passed to ``print()`` (default: stdout).
    """
    print(msg, file=file, flush=True)


# In pipeline mode (PIPELINE_LOG_FILE set by reproduce.sh), tqdm should write
# directly to the terminal device so progress bars appear on screen but are not
# captured by the log file's tee redirect.  Pass this as `file=` to every tqdm
# call.  Falls back to None (tqdm default → stderr) when /dev/tty is
# unavailable (e.g. headless CI).
tqdm_file = None
if os.environ.get("PIPELINE_LOG_FILE"):
    try:
        tqdm_file = open("/dev/tty", "w")
    except OSError:
        pass  # no controlling terminal — tqdm will use stderr
