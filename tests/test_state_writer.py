import json
import threading

import pytest

from simcore22.engine import state_writer


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    folder = tmp_path / "state"
    monkeypatch.setattr(state_writer, "STATE_DIR", str(folder))
    monkeypatch.setattr(state_writer, "LEADERBOARD_FILE", str(folder / "leaderboard.json"))
    return folder


def test_state_files_default_to_the_project_folder_not_the_launch_folder():
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    assert Path(state_writer.STATE_DIR) == project_root / "state"


def test_leaderboard_roundtrip_leaves_no_temp_file(state_dir):
    state_writer.write_leaderboard_state("Mammoth Dunes", "Winter", 3, "Stroke Play", [{"name": "Zoë"}])

    data = json.loads((state_dir / "leaderboard.json").read_text(encoding="utf-8"))
    assert data["course_name"] == "Mammoth Dunes" and data["players"] == [{"name": "Zoë"}]
    assert [p.name for p in state_dir.iterdir()] == ["leaderboard.json"]  # no .tmp left behind


def test_a_viewer_reading_constantly_never_sees_a_half_written_file(state_dir):
    """The viewers poll these files while the engine rewrites them."""
    state_writer.write_leaderboard_state("A", "L", 1, "F", [])
    path = state_dir / "leaderboard.json"
    stop, bad = threading.Event(), []

    def reader():
        # what the viewers do: read_state returns None if it hit the instant of the swap
        while not stop.is_set():
            data = state_writer.read_state(str(path))
            if data is not None and len(data["players"]) not in (0, 50):
                bad.append(data)  # half a file would have a partial player list

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for n in range(150):
            state_writer.write_leaderboard_state("A", "L", n, "F", [{"name": f"p{i}"} for i in range(50)])
    finally:
        stop.set()
        thread.join()

    assert bad == []
