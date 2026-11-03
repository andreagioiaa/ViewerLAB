from __future__ import annotations

import pytest

from core.metadata.title_cleaner import (
    clean_title,
    extract_year,
    normalize_for_match,
    score_title,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Inception.2010.1080p.BluRay.x264-[YTS.MX]", "Inception"),
        ("The.Last.of.Us.S01E02.ITA.ENG.1080p.WEB-DL.mkv", "The Last of Us"),
        (
            "Dune.Parte.Due.2024.iTALiAN.MD.1080p.WEBRip.x264-NONAME",
            "Dune Parte Due",
        ),
        (
            "Spider-Man.No.Way.Home.2021.2160p.WEB-DL.DDP5.1.Atmos.HDR.HEVC-CMRG",
            "Spider-Man No Way Home",
        ),
        ("Jujutsu.Kaisen.S02E05.1080p.WEB-DL.AAC2.0.H.264-SubsPlease", "Jujutsu Kaisen"),
        ("2012.2009.1080p.BluRay", "2012"),
        ("Blade Runner 2049", "Blade Runner 2049"),
        ("Blade Runner 2049 1080p", "Blade Runner 2049"),
        ("Catch-22", "Catch-22"),
        ("Inception (2010)", "Inception"),
        ("The Matrix 1999 10bit 720p", "The Matrix"),
        ("Movie.Title.2022.ITALIAN.ENG.SUB.1080p.WEBRip", "Movie Title"),
        ("", ""),
    ],
)
def test_clean_title(raw: str, expected: str) -> None:
    assert clean_title(raw) == expected


def test_extract_year() -> None:
    assert extract_year("Inception (2010)") == 2010
    assert extract_year("Dune 2024") == 2024
    assert extract_year("Blade Runner 2049") is None
    assert extract_year("The Last of Us S01E02") is None


def test_normalize_and_score() -> None:
    assert normalize_for_match("The Last of Us") == "last us"
    assert score_title("The Last of Us", "The Last of Us") == 1.0
    assert score_title("Inception", "Inception") == 1.0
    assert score_title("", "Inception") == 0.0
