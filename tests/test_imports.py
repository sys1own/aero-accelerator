"""Verify the public packaging surface."""


def test_public_modules_are_importable() -> None:
    from accelerator import aero_frontend
    from accelerator import engine
    from accelerator import hin_vm
    from accelerator import shield
    from accelerator import translator

    assert aero_frontend is not None
    assert engine is not None
    assert hin_vm is not None
    assert shield is not None
    assert translator is not None
