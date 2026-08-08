"""Deterministic, supplied-payload-only reporting helpers.

The functions in this module serialize values already computed by the B2-D2
lifecycle.  They do not import scientific modules, discover inputs, read seed
files, or inspect predecessor source trees.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import csv
from io import BytesIO, StringIO
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


class ReportingError(RuntimeError):
    """Raised when a report payload or output target is invalid."""


def _atomic_write_bytes(
    path: Path,
    payload: bytes,
    *,
    overwrite: bool = False,
) -> Path:
    """Write bytes durably; new artifacts are exclusive by default."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        try:
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o644,
            )
        except FileExistsError as error:
            raise ReportingError(f"refusing to overwrite artifact: {target}") from error
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            raise
        return target

    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def write_text(
    path: Path,
    text: str,
    *,
    overwrite: bool = False,
) -> Path:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return _atomic_write_bytes(path, text.encode("utf-8"), overwrite=overwrite)


def write_json(
    path: Path,
    payload: Any,
    *,
    overwrite: bool = False,
) -> Path:
    """Write deterministic strict JSON with one trailing newline."""

    try:
        rendered = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ReportingError("payload is not strict JSON data") from error
    return write_text(path, rendered, overwrite=overwrite)


def write_jsonl(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    overwrite: bool = False,
) -> Path:
    """Write canonical one-object-per-line JSON in supplied row order."""

    rendered: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ReportingError(f"JSONL row {index} is not a mapping")
        try:
            rendered.append(
                json.dumps(
                    dict(row),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
        except (TypeError, ValueError) as error:
            raise ReportingError(f"JSONL row {index} is not strict JSON") from error
    text = "".join(f"{line}\n" for line in rendered)
    return write_text(path, text, overwrite=overwrite)


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    fieldnames: Sequence[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Write a deterministic RFC-4180-style table with LF line endings."""

    materialized = [dict(row) for row in rows]
    if fieldnames is None:
        columns = sorted({str(key) for row in materialized for key in row})
    else:
        columns = [str(value) for value in fieldnames]
    if not columns:
        raise ReportingError("CSV fieldnames may not be empty")
    if len(columns) != len(set(columns)):
        raise ReportingError("CSV fieldnames must be unique")
    if any(set(row) - set(columns) for row in materialized):
        raise ReportingError("CSV row contains a field outside fieldnames")

    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=columns,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(materialized)
    return write_text(path, stream.getvalue(), overwrite=overwrite)


def write_markdown(
    path: Path,
    markdown: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Write already-rendered Markdown without interpreting its claims."""

    if not isinstance(markdown, str):
        raise TypeError("markdown must be str")
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return write_text(path, normalized, overwrite=overwrite)


def write_final_audit_report(
    path: Path,
    markdown: str,
    *,
    overwrite: bool = False,
) -> Path:
    """Named wrapper emphasizing that the caller supplies all conclusions."""

    return write_markdown(path, markdown, overwrite=overwrite)


def _finite_values(values: Sequence[Any], *, label: str) -> list[float]:
    result: list[float] = []
    for index, value in enumerate(values):
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise ReportingError(f"{label}[{index}] is not numeric") from error
        if not math.isfinite(numeric):
            raise ReportingError(f"{label}[{index}] is not finite")
        result.append(numeric)
    return result


def _pyplot() -> Any:
    """Import the non-interactive plotting backend only when requested."""

    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        from matplotlib import pyplot as plt
    except ImportError as error:
        raise ReportingError("matplotlib is required to render figures") from error
    return plt


def _write_png(
    path: Path,
    figure: Any,
    *,
    dpi: int,
    overwrite: bool,
) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".png":
        raise ReportingError("deterministic figure outputs must use .png")
    buffer = BytesIO()
    figure.savefig(
        buffer,
        format="png",
        dpi=int(dpi),
        facecolor="white",
        metadata={"Software": "LA1.3-ARA-B2-D2 reporting"},
    )
    return _atomic_write_bytes(target, buffer.getvalue(), overwrite=overwrite)


def save_line_figure(
    path: Path,
    series: Mapping[str, tuple[Sequence[Any], Sequence[Any]]],
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    dpi: int = 160,
    overwrite: bool = False,
) -> Path:
    """Render supplied x/y series; no values are derived or simulated."""

    if not series:
        raise ReportingError("line figure requires at least one series")
    plt = _pyplot()
    figure, axis = plt.subplots(figsize=(7.0, 4.2), layout="constrained")
    try:
        for label in sorted(series):
            x_values, y_values = series[label]
            x = _finite_values(x_values, label=f"{label}.x")
            y = _finite_values(y_values, label=f"{label}.y")
            if len(x) != len(y) or not x:
                raise ReportingError(f"series {label!r} has invalid lengths")
            axis.plot(x, y, marker="o", linewidth=1.5, label=str(label))
        axis.set_title(str(title))
        axis.set_xlabel(str(xlabel))
        axis.set_ylabel(str(ylabel))
        axis.grid(True, alpha=0.25)
        if len(series) > 1:
            axis.legend(frameon=False)
        return _write_png(path, figure, dpi=dpi, overwrite=overwrite)
    finally:
        plt.close(figure)


def save_heatmap_figure(
    path: Path,
    matrix: Sequence[Sequence[Any]],
    *,
    row_labels: Sequence[str],
    column_labels: Sequence[str],
    title: str,
    colorbar_label: str = "",
    vmin: float | None = None,
    vmax: float | None = None,
    dpi: int = 160,
    overwrite: bool = False,
) -> Path:
    """Render a finite rectangular matrix supplied by the caller."""

    values = [
        _finite_values(row, label=f"matrix[{index}]")
        for index, row in enumerate(matrix)
    ]
    if not values or not values[0] or any(len(row) != len(values[0]) for row in values):
        raise ReportingError("heatmap matrix must be non-empty and rectangular")
    if len(row_labels) != len(values) or len(column_labels) != len(values[0]):
        raise ReportingError("heatmap label dimensions do not match matrix")
    plt = _pyplot()
    figure, axis = plt.subplots(figsize=(7.0, 5.5), layout="constrained")
    try:
        image = axis.imshow(values, aspect="auto", vmin=vmin, vmax=vmax)
        axis.set_title(str(title))
        axis.set_yticks(range(len(row_labels)), labels=[str(x) for x in row_labels])
        axis.set_xticks(
            range(len(column_labels)),
            labels=[str(x) for x in column_labels],
            rotation=45,
            ha="right",
        )
        colorbar = figure.colorbar(image, ax=axis)
        if colorbar_label:
            colorbar.set_label(str(colorbar_label))
        return _write_png(path, figure, dpi=dpi, overwrite=overwrite)
    finally:
        plt.close(figure)


def save_bar_figure(
    path: Path,
    labels: Sequence[str],
    values: Sequence[Any],
    *,
    title: str,
    ylabel: str,
    dpi: int = 160,
    overwrite: bool = False,
) -> Path:
    if len(labels) != len(values) or not labels:
        raise ReportingError("bar labels and values must have equal non-zero length")
    numeric = _finite_values(values, label="values")
    plt = _pyplot()
    figure, axis = plt.subplots(figsize=(7.0, 4.2), layout="constrained")
    try:
        axis.bar(range(len(labels)), numeric)
        axis.set_xticks(range(len(labels)), labels=[str(x) for x in labels], rotation=30)
        axis.set_title(str(title))
        axis.set_ylabel(str(ylabel))
        axis.grid(axis="y", alpha=0.25)
        return _write_png(path, figure, dpi=dpi, overwrite=overwrite)
    finally:
        plt.close(figure)


def save_table_figure(
    path: Path,
    rows: Sequence[Sequence[Any]],
    *,
    columns: Sequence[str],
    title: str,
    dpi: int = 160,
    overwrite: bool = False,
) -> Path:
    if not columns or any(len(row) != len(columns) for row in rows):
        raise ReportingError("table rows must match the non-empty columns")
    plt = _pyplot()
    height = max(2.4, 0.36 * (len(rows) + 2))
    figure, axis = plt.subplots(figsize=(8.5, height), layout="constrained")
    try:
        axis.axis("off")
        axis.set_title(str(title))
        table = axis.table(
            cellText=[[str(value) for value in row] for row in rows],
            colLabels=[str(value) for value in columns],
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.0, 1.25)
        return _write_png(path, figure, dpi=dpi, overwrite=overwrite)
    finally:
        plt.close(figure)


__all__ = [
    "ReportingError",
    "save_bar_figure",
    "save_heatmap_figure",
    "save_line_figure",
    "save_table_figure",
    "write_csv",
    "write_final_audit_report",
    "write_json",
    "write_jsonl",
    "write_markdown",
    "write_text",
]
