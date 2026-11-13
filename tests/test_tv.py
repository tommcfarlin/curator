

def test_hung_tv_request_is_cut_off_at_the_deadline():
    import threading, time
    import pytest
    from curator.tv import SamsungTV, TVUnavailable

    class Hung:
        def __init__(self):
            self.closed = threading.Event()
        def open(self): pass
        def close(self): self.closed.set()
        def available(self):
            # Like the library: wait for a reply that never comes, until the socket closes.
            if not self.closed.wait(5):
                return []
            raise OSError("connection closed")

    tv = SamsungTV("10.0.0.20", art_factory=Hung, deadline=0.3)
    start = time.monotonic()
    with pytest.raises(TVUnavailable):
        tv.list_art()
    assert time.monotonic() - start < 2
