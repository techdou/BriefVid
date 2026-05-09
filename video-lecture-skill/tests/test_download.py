from video_lecture_skill.download import detect_platform, normalize_video_url, sanitize_filename


def test_normalize_bilibili_url():
    url, vid = normalize_video_url("https://www.bilibili.com/video/BV1R6NFzXE1H/")
    assert "bilibili.com" in url
    assert vid == "BV1R6NFzXE1H"


def test_normalize_bilibili_short():
    url, vid = normalize_video_url("BV1R6NFzXE1H")
    assert "bilibili.com" in url
    assert vid == "BV1R6NFzXE1H"


def test_normalize_youtube_url():
    url, vid = normalize_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "youtube.com" in url
    assert vid == "dQw4w9WgXcQ"


def test_normalize_youtube_short():
    url, vid = normalize_video_url("https://youtu.be/dQw4w9WgXcQ")
    assert "youtube.com" in url
    assert vid == "dQw4w9WgXcQ"


def test_normalize_douyin_url():
    url, vid = normalize_video_url("https://www.douyin.com/video/7123456789")
    assert "douyin.com" in url
    assert vid == "7123456789"


def test_normalize_generic_url():
    url, vid = normalize_video_url("https://example.com/some-video")
    assert url == "https://example.com/some-video"
    assert vid == ""


def test_detect_platform():
    assert detect_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert detect_platform("https://b23.tv/abc") == "bilibili"
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://youtu.be/abc") == "youtube"
    assert detect_platform("https://www.douyin.com/video/123") == "douyin"
    assert detect_platform("https://example.com/video") == "generic"


def test_sanitize_filename():
    assert sanitize_filename("hello world") == "hello world"
    result = sanitize_filename('file<>:|?*name')
    assert "_" in result
    assert "<" not in result
    assert ">" not in result
    assert sanitize_filename("") == "video_audio"
    assert sanitize_filename("a" * 200) == "a" * 120
