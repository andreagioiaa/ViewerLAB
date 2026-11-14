from vistoflow.html_site import _extract_stream_urls


def test_webmanifest_is_not_a_webm_stream():
    html = '<link rel="manifest" href="https://example.org/manifest.webmanifest">'
    assert _extract_stream_urls(html, "https://example.org/") == []


def test_real_streams_are_still_found():
    html = r'<script>var a="https://cdn.example.org/v/movie.webm?t=1"; var b="https:\/\/cdn.example.org\/hls\/index.m3u8";</script>'
    urls = [url for _, url in _extract_stream_urls(html, "https://example.org/")]
    assert "https://cdn.example.org/v/movie.webm?t=1" in urls
    assert "https://cdn.example.org/hls/index.m3u8" in urls
