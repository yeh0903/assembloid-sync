from orgpipe import state


def test_empty_state(tmp_path):
    assert state.read_state(tmp_path) == {"stages": {}}
    assert not state.is_done(tmp_path, "denoise")


def test_mark_done_and_skip(tmp_path):
    state.mark(tmp_path, "denoise", "done")
    assert state.is_done(tmp_path, "denoise")
    assert state.is_done(tmp_path, "denoise", smoke=True)  # real done satisfies smoke ask


def test_smoke_done_does_not_satisfy_real(tmp_path):
    state.mark(tmp_path, "denoise", "done", smoke=True)
    assert state.is_done(tmp_path, "denoise", smoke=True)
    assert not state.is_done(tmp_path, "denoise", smoke=False)


def test_failed_records_error(tmp_path):
    state.mark(tmp_path, "fiji", "failed", error="boom")
    assert not state.is_done(tmp_path, "fiji")
    assert state.read_state(tmp_path)["stages"]["fiji"]["error"] == "boom"
