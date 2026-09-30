import grat


def test_public_api_is_importable() -> None:
    assert callable(grat.run_grat)
    assert callable(grat.read_report)
    assert grat.__all__ == ["read_report", "run_grat"]
