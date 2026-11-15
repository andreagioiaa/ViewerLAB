import pytest

from vistoflow.watchlist import Watchlist, runtime_minutes

CSV = """Date,Name,Year,Letterboxd URI
2021-10-24,Dune,2021,https://boxd.it/fA7G
2021-10-30,Heat,1995,https://boxd.it/2bg8
2021-10-30,Cube,1997,https://boxd.it/2aoU
"""


def _csv(tmp_path, text=CSV):
    path = tmp_path / "watchlist.csv"
    path.write_text("﻿" + text, encoding="utf-8")  # Letterboxd/Excel: BOM in testa
    return path


def test_a_second_import_adds_only_the_new_films(tmp_path):
    store = Watchlist(tmp_path / "watchlist.json")
    assert store.import_letterboxd(_csv(tmp_path)) == (3, 0)
    more = CSV + "2026-11-02,Resident Evil,2002,https://boxd.it/28z2\n"
    assert store.import_letterboxd(_csv(tmp_path, more)) == (1, 3)
    assert len(Watchlist(tmp_path / "watchlist.json").items) == 4  # salvata


def test_a_film_added_from_imdb_is_not_imported_twice(tmp_path):
    store = Watchlist(tmp_path / "watchlist.json")
    assert store.add("Dune", "2021")
    assert store.import_letterboxd(_csv(tmp_path)) == (2, 1)


def test_sorting_both_ways_keeps_unknown_values_last(tmp_path):
    store = Watchlist(tmp_path / "watchlist.json")
    store.import_letterboxd(_csv(tmp_path))
    store.set_imdb(store.items[0]["key"], {"rating": "8.0", "runtime": "155 min", "tmdb_id": 438631})  # Dune
    store.set_imdb(store.items[1]["key"], {"rating": "8.3", "runtime": "170 min", "tmdb_id": 949})  # Heat
    store.set_imdb(store.items[2]["key"], None)  # Cube: non trovato
    names = lambda field, desc: [i["name"] for i in store.sorted(field, desc)]
    assert names("rating", True) == ["Heat", "Dune", "Cube"]
    assert names("rating", False) == ["Dune", "Heat", "Cube"]
    assert names("runtime", False) == ["Dune", "Heat", "Cube"]
    assert names("year", False) == ["Heat", "Cube", "Dune"]
    assert names("year", True) == ["Dune", "Cube", "Heat"]
    assert store.missing_imdb() == []  # Cube non viene ricercato di nuovo


def test_runtime_formats():
    assert runtime_minutes("142 min") == 142
    assert runtime_minutes("2h 22min") == 142
    assert runtime_minutes("") is None


def test_a_csv_that_is_not_letterboxd_is_refused(tmp_path):
    with pytest.raises(ValueError):
        Watchlist(tmp_path / "w.json").import_letterboxd(_csv(tmp_path, "a,b\n1,2\n"))


def test_cards_saved_without_tmdb_id_are_looked_up_again_but_kept_on_failure(tmp_path):
    store = Watchlist(tmp_path / "watchlist.json")
    store.add("Heat", "1995", imdb={"rating": "8.3"})  # scheda di una versione precedente
    assert [i["name"] for i in store.missing_imdb()] == ["Heat"]
    store.set_imdb(store.items[0]["key"], None)  # IMDb non lo ritrova
    assert store.items[0]["imdb"] == {"rating": "8.3"} and store.missing_imdb() == []
