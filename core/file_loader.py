"""Load supported experiment data and software test log files."""

import json
from pathlib import Path
from typing import Any

import pandas as pd


class FileLoadError(ValueError):
    """The supplied file cannot be read or is unsupported."""


def load_file(path: str | Path) -> Any:
    """Read CSV, JSON, or UTF-8 text; raise FileLoadError on input errors."""

    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in {".csv", ".json", ".txt", ".log", ".md"}:
        raise FileLoadError(f"不支持的文件类型: {suffix or '(无扩展名)'}；仅支持 .csv、.json、.txt、.log 和 .md")

    try:
        if suffix == ".csv":
            frame = pd.read_csv(file_path, encoding="utf-8-sig", dtype=object)
            if frame.empty:
                raise FileLoadError(f"CSV 没有数据行: {file_path}")
            return frame

        with file_path.open("r", encoding="utf-8-sig") as source:
            content = source.read()
        if not content.strip():
            raise FileLoadError(f"{suffix.upper()} 文件为空: {file_path}")
        return json.loads(content) if suffix == ".json" else content
    except FileLoadError:
        raise
    except pd.errors.EmptyDataError as exc:
        raise FileLoadError(f"CSV 文件为空或没有表头: {file_path}") from exc
    except (OSError, UnicodeError, pd.errors.ParserError, json.JSONDecodeError) as exc:
        raise FileLoadError(f"无法读取 {file_path}: {exc}") from exc
