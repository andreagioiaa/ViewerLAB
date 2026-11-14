from vistoflow.resume import ResumeStore


def test_position_survives_a_restart(tmp_path):
    path = tmp_path / "resume.json"
    store = ResumeStore(path)
    store.update("sc:film:1", 1234.5, 6000, "Film")
    store.save()
    assert ResumeStore(path).get("sc:film:1") == 1234.5


def test_the_first_seconds_and_the_credits_start_over(tmp_path):
    store = ResumeStore(tmp_path / "resume.json")
    store.update("a", 10, 6000)
    assert store.get("a") is None  # appena iniziato
    store.update("a", 3000, 6000)
    store.update("a", 5950, 6000)  # finito: dimenticato
    assert store.get("a") is None


def test_a_broken_file_is_an_empty_store(tmp_path):
    path = tmp_path / "resume.json"
    path.write_text("{not json", encoding="utf-8")
    assert ResumeStore(path).get("x") is None
