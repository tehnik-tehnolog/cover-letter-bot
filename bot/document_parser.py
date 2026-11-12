from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_RESUME_CHARS = 25_000


class DocumentParseError(Exception):
    """Raised when a resume document cannot be parsed."""


def _normalize_text(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MAX_RESUME_CHARS:
        text = text[:MAX_RESUME_CHARS].rstrip() + "\n...[текст обрезан по длине]"
    return text


def extract_text_from_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise DocumentParseError(
                    "PDF-файл защищён паролем. Снимите защиту или отправьте резюме текстом / в DOCX."
                ) from exc

        pages_text: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text)

        text = _normalize_text("\n\n".join(pages_text))
        if not text:
            raise DocumentParseError(
                "Не удалось извлечь текст из PDF (возможно, это скан без текстового слоя). "
                "Отправьте DOCX, TXT или скопируйте текст резюме."
            )
        return text
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"Ошибка при чтении PDF-файла: {exc}") from exc


def extract_text_from_docx(data: bytes) -> str:
    try:
        doc = Document(io.BytesIO(data))
        chunks: list[str] = []

        for paragraph in doc.paragraphs:
            p_text = paragraph.text.strip()
            if p_text:
                chunks.append(p_text)

        for table in doc.tables:
            for row in table.rows:
                seen_cells: set[int] = set()
                row_values: list[str] = []
                for cell in row.cells:
                    cell_id = id(cell._tc)
                    if cell_id in seen_cells:
                        continue
                    seen_cells.add(cell_id)
                    cell_text = " ".join(cell.text.split())
                    if cell_text:
                        row_values.append(cell_text)
                if row_values:
                    chunks.append(" | ".join(row_values))

        text = _normalize_text("\n".join(chunks))
        if not text:
            raise DocumentParseError("DOCX-файл пустой или не содержит текста.")
        return text
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"Ошибка при чтении DOCX-файла: {exc}") from exc


def extract_text_from_txt(data: bytes) -> str:
    decoded: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            decoded = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if decoded is None:
        raise DocumentParseError("Не удалось определить кодировку TXT-файла.")

    text = _normalize_text(decoded)
    if not text:
        raise DocumentParseError("TXT-файл пустой.")
    return text


def parse_resume_document(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            f"Формат «{ext or 'без расширения'}» не поддерживается. "
            "Отправьте файл в формате PDF, DOCX или TXT."
        )

    if ext == ".pdf":
        return extract_text_from_pdf(data)
    if ext == ".docx":
        return extract_text_from_docx(data)
    return extract_text_from_txt(data)
