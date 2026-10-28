"""Stop agent code before reading submitted files and after building them."""
import os
from pathlib import Path
import pwd
import signal
import time

uid = pwd.getpwnam("agent").pw_uid
deadline = time.monotonic() + 10
while True:
    running = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == 1:
            continue
        try:
            status = dict(line.split(":", 1) for line in (process / "status").read_text().splitlines())
            if int(status["Uid"].split()[0]) != uid or status["State"].strip().startswith("Z"):
                continue
            command = (process / "cmdline").read_bytes().rstrip(b"\0").split(b"\0")
            # Freeze Harbor's keepalive. Killing it also ends PID 1 and stops the container.
            if (status["PPid"].strip() == "1" and len(command) == 2
                    and Path(os.fsdecode(command[0])).name == "sleep" and command[1] == b"infinity"):
                os.kill(int(process.name), signal.SIGSTOP)
                continue
            running.append(int(process.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    if not running:
        break
    for pid in running:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if time.monotonic() >= deadline:
        raise SystemExit("Agent processes did not stop before verification.")
    time.sleep(0.05)
