from __future__ import annotations

from uuid import uuid4

from foamstudio.app.single_instance import SingleInstance


def test_second_instance_activates_the_first(qtbot) -> None:
    key = f"foamstudio-{uuid4().hex}"
    first = SingleInstance(key)
    second: SingleInstance | None = None
    try:
        assert first.already_running is False
        hits: list[bool] = []
        first.activated.connect(lambda: hits.append(True))
        second = SingleInstance(key)
        assert second.already_running is True
        qtbot.waitUntil(lambda: bool(hits))
    finally:
        if second is not None:
            second.close()
        first.close()
