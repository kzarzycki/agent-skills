from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subscription:
    active: bool

    def cancel(self) -> Subscription:
        return Subscription(active=False)
