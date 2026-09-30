from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

import pdfplumber


@dataclass(frozen=True)
class Chunk:
    text: str
    embedding_text: str
    page: int
    index: int
    kind: str
    section_title: str
    visual_bbox: tuple[float, float, float, float] | None = None
    visual_kind: str = "full_page"


@dataclass(frozen=True)
class TableRow:
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class PdfCorpus:
    title: str
    page_count: int
    chunks: list[Chunk]
    page_text: dict[int, str]


def normalize_text(value: str) -> str:
    value = re.sub(r"(?<=\w)-\n(?=\w)", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def split_text(text: str, max_chars: int = 1600, overlap_chars: int = 220) -> list[str]:
    """Split at natural boundaries while preserving modest retrieval overlap."""
    remaining = normalize_text(text)
    chunks: list[str] = []
    while len(remaining) > max_chars:
        split_at = remaining.rfind(". ", 0, max_chars)
        if split_at >= int(max_chars * 0.55):
            split_at += 1
        else:
            split_at = max(
                remaining.rfind("\n", 0, max_chars),
                remaining.rfind(" ", 0, max_chars),
            )
        if split_at < int(max_chars * 0.55):
            split_at = max_chars
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[max(0, split_at - overlap_chars) :].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _section_title(text: str, fallback: str) -> str:
    for line in normalize_text(text).splitlines():
        candidate = line.strip(" -|:")
        if 3 <= len(candidate) <= 140 and not candidate.isdigit():
            return candidate
    return fallback


def _inside_table(obj: dict, bboxes: list[tuple[float, float, float, float]]) -> bool:
    if obj.get("object_type") != "char":
        return True
    x = (float(obj["x0"]) + float(obj["x1"])) / 2
    y = (float(obj["top"]) + float(obj["bottom"])) / 2
    return not any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in bboxes)


def _clean_cell(value: object) -> str:
    return normalize_text(str(value or "")).replace("\n", " ")


def table_row_texts(page) -> tuple[list[TableRow], list[tuple[float, float, float, float]]]:
    rows: list[TableRow] = []
    bboxes: list[tuple[float, float, float, float]] = []
    try:
        tables = page.find_tables()
    except Exception:  # noqa: BLE001
        return rows, bboxes

    for table_number, table in enumerate(tables, start=1):
        extracted = table.extract() or []
        if not extracted:
            continue
        bboxes.append(tuple(float(value) for value in table.bbox))
        width = max((len(row or []) for row in extracted), default=0)
        if width < 2:
            continue
        first = [_clean_cell(cell) for cell in (extracted[0] or [])]
        has_header = len(extracted) > 1 and sum(bool(cell) for cell in first) >= 2
        headers = [cell or f"Column {index + 1}" for index, cell in enumerate(first)]
        data_rows = extracted[1:] if has_header else extracted
        geometry_rows = table.rows[1:] if has_header else table.rows
        for row_number, (row, geometry) in enumerate(
            zip(data_rows, geometry_rows), start=1
        ):
            cells = [_clean_cell(cell) for cell in (row or [])]
            cells.extend([""] * (width - len(cells)))
            if sum(bool(cell) for cell in cells) < 2:
                continue
            pairs = [
                f"{headers[index] if index < len(headers) else f'Column {index + 1}'}: {cell}"
                for index, cell in enumerate(cells)
                if cell
            ]
            row_text = " | ".join(pairs)
            if 20 <= len(row_text) <= 2200:
                rows.append(
                    TableRow(
                        text=f"Table {table_number}, row {row_number}\n{row_text}",
                        bbox=tuple(float(value) for value in geometry.bbox),
                    )
                )
    return rows, bboxes


def _embedding_text(title: str, page: int, section: str, kind: str, text: str) -> str:
    return "\n".join(
        [
            f"Document: {title}",
            f"PDF page: {page}",
            f"Section: {section}",
            f"Content type: {kind}",
            text,
        ]
    )


def extract_pdf(pdf_path: Path) -> PdfCorpus:
    title = pdf_path.stem.replace("_", " ").replace("-", " ").strip()
    chunks: list[Chunk] = []
    page_text: dict[int, str] = {}
    chunk_index = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            raw_text = normalize_text(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
            table_rows, table_bboxes = table_row_texts(page)
            narrative_page = page.filter(lambda obj: _inside_table(obj, table_bboxes))
            narrative = normalize_text(
                narrative_page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            )
            if not narrative and not table_rows:
                continue

            page_text[page_number] = raw_text
            section = _section_title(narrative or raw_text, f"Page {page_number}")
            for text in split_text(narrative):
                chunk_index += 1
                chunks.append(
                    Chunk(
                        text=text,
                        embedding_text=_embedding_text(
                            title, page_number, section, "narrative", text
                        ),
                        page=page_number,
                        index=chunk_index,
                        kind="narrative",
                        section_title=section,
                    )
                )
            for table_row in table_rows:
                chunk_index += 1
                chunks.append(
                    Chunk(
                        text=table_row.text,
                        embedding_text=_embedding_text(
                            title, page_number, section, "table row", table_row.text
                        ),
                        page=page_number,
                        index=chunk_index,
                        kind="table_row",
                        section_title=section,
                        visual_bbox=table_row.bbox,
                        visual_kind="table_row_crop",
                    )
                )

        page_count = len(pdf.pages)

    if not chunks:
        raise ValueError(
            "No searchable text was extracted. This demo requires a text-based PDF; "
            "run OCR before uploading scanned documents."
        )
    return PdfCorpus(title=title, page_count=page_count, chunks=chunks, page_text=page_text)


def stable_chunk_id(source_id: str, chunk: Chunk) -> str:
    payload = f"{source_id}|{chunk.page}|{chunk.index}|{chunk.kind}|{chunk.text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
