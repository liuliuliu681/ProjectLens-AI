import json

import pandas as pd
import pytest

from core.file_loader import FileLoadError, load_file
from core.experiment_parser import parse_file


def test_load_csv(tmp_path):
    path = tmp_path / "runs.csv"
    path.write_text("name,recall,precision\nA,0.5,0.6\n", encoding="utf-8")
    frame = load_file(path)
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["name", "recall", "precision"]


def test_load_json(tmp_path):
    path = tmp_path / "run.json"
    value = {"name": "A", "metrics": {"recall": 0.5}}
    path.write_text(json.dumps(value), encoding="utf-8")
    assert load_file(path) == value


@pytest.mark.parametrize("content", ["", "name,recall\n"])
def test_empty_csv(tmp_path, content):
    path = tmp_path / "empty.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(FileLoadError, match="CSV"):
        load_file(path)


def test_csv_encoding_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"name,recall\nA,\xff")
    assert parse_file(path).status == "unrecognized"


@pytest.mark.parametrize("content", ["", "  "])
def test_empty_json(tmp_path, content):
    path = tmp_path / "empty.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(FileLoadError, match="为空"):
        load_file(path)


def test_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    result = parse_file(path)
    assert result.status == "unrecognized"
    assert result.errors


@pytest.mark.parametrize("suffix", [".txt", ".log", ".xlsx"])
def test_unsupported_extension(tmp_path, suffix):
    path = tmp_path / f"run{suffix}"
    path.write_text("anything", encoding="utf-8")
    result = parse_file(path)
    assert result.status == "unrecognized"
    assert "不支持" in result.errors[0]
