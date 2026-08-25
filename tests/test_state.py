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


def test_corrupted_state_self_heals(tmp_path, capsys):
    from orgpipe import layout
    layout.orgpipe_dir(tmp_path).mkdir(parents=True)
    layout.state_path(tmp_path).write_text("{truncated", encoding="utf-8")
    assert state.read_state(tmp_path) == {"stages": {}}
    assert not state.is_done(tmp_path, "denoise")


def test_state_missing_stages_key(tmp_path):
    from orgpipe import layout
    layout.orgpipe_dir(tmp_path).mkdir(parents=True)
    layout.state_path(tmp_path).write_text("{}", encoding="utf-8")
    assert state.read_state(tmp_path) == {"stages": {}}


def test_clear_downstream(tmp_path):
    for s in ("denoise", "fiji", "suite2p", "roi"):
        state.mark(tmp_path, s, "done")
    removed = state.clear_downstream(tmp_path, "suite2p")
    assert removed == ["roi"]
    st = state.read_state(tmp_path)["stages"]
    assert "roi" not in st and st["suite2p"]["status"] == "done"
    assert state.clear_downstream(tmp_path, "roi") == []
