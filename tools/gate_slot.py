"""Run a command under a host gate slot: `python tools/gate_slot.py <command> [args...]`.

This repo's `test` task runs pytest behind it. It takes a slot the way `approvals.py local-ci` does
(approvals.take_slot: the first free of the host's `GATE_SLOTS`, behind a waiting land), takes none when it already
runs under one (LOOP_GATE_SLOT_HELD names any `gate.<n>.lock`), writes its pid into the slot file so a waiting gate
can name the running process, and replaces itself with the command, which keeps the lock until it exits.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "gatekeeper/skills/gatekeeper/scripts")
)
import approvals


def main(argv: list[str]) -> None:
    fd, path = approvals.take_slot(
        lambda: print(
            f"{Path(argv[0]).name}: waiting for the host gate slot", file=sys.stderr, flush=True
        )
    )
    if fd is not None:
        os.set_inheritable(fd, True)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    os.environ[approvals.SLOT_HELD] = path
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    main(sys.argv[1:])
