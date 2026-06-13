"""Single-instance lock: a second trader/watchdog must refuse to start."""
from pmtrader.core.lock import acquire_single_instance_lock


def test_first_acquire_succeeds():
    sock = acquire_single_instance_lock(port=18763)
    assert sock is not None
    sock.close()

def test_second_acquire_returns_none_while_held():
    first = acquire_single_instance_lock(port=18764)
    assert first is not None
    second = acquire_single_instance_lock(port=18764)
    assert second is None
    first.close()

def test_lock_released_when_socket_closed():
    first = acquire_single_instance_lock(port=18765)
    first.close()
    again = acquire_single_instance_lock(port=18765)
    assert again is not None
    again.close()
