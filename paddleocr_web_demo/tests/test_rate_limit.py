from paddleocr.paddleocr_web_demo.app.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_limit_and_expiry():
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)
    assert limiter.allow("client", now=0)
    assert limiter.allow("client", now=1)
    assert not limiter.allow("client", now=2)
    assert limiter.allow("client", now=11)

