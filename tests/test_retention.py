import os
import time

from wastatus.retention import group_files, prune


def make_clip(directory, stem, *, age=0.0, size=1000, frame=False):
    clip = directory / f"{stem}.mp4"
    clip.write_bytes(b"x" * size)
    for suffix in (".caption.txt", ".status2.txt", ".json"):
        (directory / f"{stem}{suffix}").write_text("text")
    if frame:
        (directory / f"{stem}.png").write_text("text")
    if age:
        when = time.time() - age
        for path in group_files(directory, stem):
            os.utime(path, (when, when))
    return clip


def test_group_collects_the_clip_and_its_sidecars(tmp_path):
    make_clip(tmp_path, "a")
    assert {p.name for p in group_files(tmp_path, "a")} == {
        "a.mp4", "a.caption.txt", "a.status2.txt", "a.json"
    }


def test_group_includes_a_frame_still_when_one_exists(tmp_path):
    make_clip(tmp_path, "a", frame=True)
    assert {p.name for p in group_files(tmp_path, "a")} == {
        "a.mp4", "a.caption.txt", "a.status2.txt", "a.json", "a.png"
    }


def test_the_job_sidecar_is_pruned_with_its_clip(tmp_path):
    """The page reads `{stem}.json` to put a clip back in the form. One left behind
    after its clip is gone is an orphan the page would happily read."""
    make_clip(tmp_path, "old", age=1000)
    make_clip(tmp_path, "new")
    prune(tmp_path, keep=1)

    assert not (tmp_path / "old.json").exists()
    assert (tmp_path / "new.json").exists()


def test_a_frame_still_is_pruned_with_its_clip(tmp_path):
    make_clip(tmp_path, "old", age=1000, frame=True)
    make_clip(tmp_path, "new", frame=True)
    prune(tmp_path, keep=1)

    assert not list(tmp_path.glob("old*"))
    assert (tmp_path / "new.png").exists()


def test_nothing_is_removed_below_the_threshold(tmp_path):
    for i in range(3):
        make_clip(tmp_path, f"clip{i}", age=i * 100)
    assert not prune(tmp_path, keep=5)
    assert len(list(tmp_path.glob("*.mp4"))) == 3


def test_oldest_clips_are_removed_first(tmp_path):
    for i in range(5):
        make_clip(tmp_path, f"clip{i}", age=i * 100)  # clip0 newest, clip4 oldest
    result = prune(tmp_path, keep=2)

    assert result.groups == 3
    remaining = {p.stem for p in tmp_path.glob("*.mp4")}
    assert remaining == {"clip0", "clip1"}


def test_sidecars_go_with_their_clip(tmp_path):
    make_clip(tmp_path, "old", age=1000)
    make_clip(tmp_path, "new")
    prune(tmp_path, keep=1)

    assert not list(tmp_path.glob("old*"))
    assert len(list(tmp_path.glob("new*"))) == 4


def test_reported_counts_and_bytes_are_real(tmp_path):
    make_clip(tmp_path, "old", age=1000, size=5000)
    make_clip(tmp_path, "new", size=5000)
    result = prune(tmp_path, keep=1)

    assert result.groups == 1
    assert result.files == 4
    assert result.bytes == 5000 + len("text") * 3


def test_keep_zero_disables_pruning(tmp_path):
    make_clip(tmp_path, "a", age=1000)
    make_clip(tmp_path, "b")
    assert not prune(tmp_path, keep=0)
    assert len(list(tmp_path.glob("*.mp4"))) == 2


def test_missing_directory_is_not_an_error(tmp_path):
    assert not prune(tmp_path / "nope", keep=5)
