"""Unit tests for accelerate.toml parsing."""

from pathlib import Path

from accelerator.config import _parse_value, find_config, get, load_config


def test_parse_value(tmp_path: Path) -> None:
    assert _parse_value("true") is True
    assert _parse_value("false") is False
    assert _parse_value("123") == 123
    assert _parse_value('"hello"') == "hello"
    assert _parse_value("[1, 2, 3]") == [1, 2, 3]


def test_load_config(tmp_path: Path) -> None:
    config_file = tmp_path / "accelerate.toml"
    config_file.write_text(
        "[build]\n"
        'output = "./out"\n'
        "cache = true\n"
        "\n"
        "[benchmark]\n"
        'args = "35"\n',
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert get(cfg, "build", "output") == "./out"
    assert get(cfg, "build", "cache") is True
    assert get(cfg, "benchmark", "args") == "35"
    assert get(cfg, "missing", "key", default="x") == "x"


def test_find_config_searches_parents(tmp_path: Path) -> None:
    config_file = tmp_path / "accelerate.toml"
    config_file.write_text('[build]\noutput = "./x"\n', encoding="utf-8")
    nested = tmp_path / "sub" / "dir"
    nested.mkdir(parents=True)
    found = find_config(nested)
    assert found == config_file
