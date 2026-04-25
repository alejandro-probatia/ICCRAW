from iccraw.raw import compat


class FakeRaw:
    opened: list[str] = []
    closed = 0

    def open_file(self, path: str) -> None:
        self.opened.append(path)

    def close(self) -> None:
        type(self).closed += 1


class FakeRawWithUnpack(FakeRaw):
    unpack_params: list[dict] = []

    def set_unpack_params(self, **kwargs) -> None:
        self.unpack_params.append(kwargs)


class FakeRawpy:
    RawPy = FakeRaw


class FakeRawpyWithUnpack:
    RawPy = FakeRawWithUnpack


def test_open_rawpy_does_not_require_set_unpack_params(monkeypatch, tmp_path):
    FakeRaw.opened = []
    FakeRaw.closed = 0
    monkeypatch.setattr(compat, "rawpy", FakeRawpy)
    raw_path = tmp_path / "capture.nef"

    with compat.open_rawpy(raw_path) as raw:
        assert isinstance(raw, FakeRaw)

    assert FakeRaw.opened == [str(raw_path)]
    assert FakeRaw.closed == 1


def test_open_rawpy_uses_set_unpack_params_when_available(monkeypatch, tmp_path):
    FakeRawWithUnpack.opened = []
    FakeRawWithUnpack.closed = 0
    FakeRawWithUnpack.unpack_params = []
    monkeypatch.setattr(compat, "rawpy", FakeRawpyWithUnpack)
    raw_path = tmp_path / "capture.nef"

    with compat.open_rawpy(raw_path, shot_select=2):
        pass

    assert FakeRawWithUnpack.unpack_params == [{"shot_select": 2}]

