from moroccan_crawler.parsing import detect_language, normalize_text, source_domain


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text(["  السلام  ", "", "عليكم "]) == "السلام عليكم"


def test_detects_mixed_moroccan_content() -> None:
    assert detect_language("مرحبا au Maroc") == "ar+fr"


def test_normalizes_source_domain() -> None:
    assert source_domain("https://www.example.ma/page") == "example.ma"
