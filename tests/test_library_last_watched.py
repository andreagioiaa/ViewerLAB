from vistoflow.library.media_manager import MediaManager


def test_last_watched_is_the_newest_unfinished_existing_file(tmp_path):
    manager = MediaManager(str(tmp_path / "settings.json"))
    a, b, gone = tmp_path / "a.mkv", tmp_path / "b.mkv", tmp_path / "gone.mkv"
    a.write_bytes(b""), b.write_bytes(b"")
    manager.update_history(str(a), 60_000, 100_000)
    manager.update_history(str(gone), 60_000, 100_000)
    manager.update_history(str(b), 99_000, 100_000, finished=True)
    assert manager.last_watched()[1] == manager._path_key(str(a))
