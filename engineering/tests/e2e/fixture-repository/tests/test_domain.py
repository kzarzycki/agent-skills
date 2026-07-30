from src.domain import Subscription


def test_cancel_deactivates_subscription() -> None:
    assert Subscription(active=True).cancel() == Subscription(active=False)
