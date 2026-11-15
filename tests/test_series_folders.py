from vistoflow.library.media_manager import MediaManager

# nomi reali di cartelle «Serie TV» preparate a mano
FILES = [
    "LA CASA DI CARTA/STAGIONE 1/La casa di carta EP.01 S01.mp4",
    "LA CASA DI CARTA/STAGIONE 2/La casa di carta EP.02 S02.mp4",
    "Stranger Things/Stagione 4/S04e07.mp4",
    "YOU/Stagione 3/YOU S03 03.mp4",
    "13 REASONS WHY/STAGIONE 2/Tredici.2x05.La.Macchina.Tracciarighe.iTA.AAC.WEBRip.x264-ADE.CreW.mkv",
    "DRAGONBALL/1-DRAGONBALL Z/2-SAGA DI FREEZER/Dragon Ball Z 060.mp4",
    "DRAGONBALL/2-DRAGONBALL GT/1- SAGA DELLE SFERE DEL DRAGO DALLE STELLE NERE/8.mp4",
    "SOUTH PARK/South.Park.iTA.s01e02.avi",
]


def test_each_first_level_folder_is_one_series(tmp_path):
    root = tmp_path / "Serie TV"
    for name in FILES:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"")
    manager = MediaManager(str(tmp_path / "settings.json"))
    manager.series_roots = [str(root)]
    got = {
        r["path"][len(str(root)) + 1:].replace("\\", "/"): (r["kind"], r["series"], r["group"], r["season"], r["episode"])
        for r in (manager.describe(str(root / name)) for name in FILES)
    }
    assert got == {
        FILES[0]: ("serie", "LA CASA DI CARTA", "", "1", "1"),
        FILES[1]: ("serie", "LA CASA DI CARTA", "", "2", "2"),
        FILES[2]: ("serie", "Stranger Things", "", "4", "7"),
        FILES[3]: ("serie", "YOU", "", "3", "3"),
        FILES[4]: ("serie", "13 REASONS WHY", "", "2", "5"),
        FILES[5]: ("serie", "DRAGONBALL", "DRAGONBALL Z › SAGA DI FREEZER", "1", "60"),
        FILES[6]: ("serie", "DRAGONBALL", "DRAGONBALL GT › SAGA DELLE SFERE DEL DRAGO DALLE STELLE NERE", "1", "8"),
        FILES[7]: ("serie", "SOUTH PARK", "", "1", "2"),
    }


def test_outside_the_series_folder_the_file_name_decides(tmp_path):
    manager = MediaManager(str(tmp_path / "settings.json"))
    manager.series_roots = [str(tmp_path / "Serie TV")]
    film = tmp_path / "Film" / "Salvate il soldato Ryan.mp4"
    assert manager.describe(str(film))["kind"] == "film"
