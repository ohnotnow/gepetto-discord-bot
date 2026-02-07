from src.media.replicate import _extract_url


class FakeFileOutput:
    """Mimics replicate's FileOutput which converts to a URL via str()."""

    def __init__(self, url):
        self._url = url

    def __str__(self):
        return self._url


def test_extract_url_from_single_file_output():
    output = FakeFileOutput("https://replicate.delivery/image.png")
    assert _extract_url(output) == "https://replicate.delivery/image.png"


def test_extract_url_from_list_of_file_outputs():
    output = [
        FakeFileOutput("https://replicate.delivery/first.png"),
        FakeFileOutput("https://replicate.delivery/second.png"),
    ]
    assert _extract_url(output) == "https://replicate.delivery/first.png"


def test_extract_url_from_plain_string():
    assert _extract_url("https://replicate.delivery/image.png") == "https://replicate.delivery/image.png"


def test_extract_url_from_list_of_strings():
    assert _extract_url(["https://replicate.delivery/image.png"]) == "https://replicate.delivery/image.png"
