from pathlib import Path

import pytest
from PySide6.QtGui import QPageSize, QTextDocument

from app.utils.exceptions import ValidationError
from app.utils.pdf_export import export_document_to_pdf


def _make_document(html: str = "<p>Test</p>") -> QTextDocument:
    document = QTextDocument()
    document.setHtml(html)
    return document


def test_export_writes_valid_pdf_file(qapp, tmp_path) -> None:
    out = tmp_path / "out.pdf"
    export_document_to_pdf(_make_document(), out, QPageSize(QPageSize.PageSizeId.A4))

    assert out.exists()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:5] == b"%PDF-"


def test_export_creates_missing_parent_directory(qapp, tmp_path) -> None:
    out = tmp_path / "not_yet_created" / "out.pdf"
    export_document_to_pdf(_make_document(), out, QPageSize(QPageSize.PageSizeId.A4))

    assert out.exists()


def test_export_rejects_destination_whose_parent_is_a_file(qapp, tmp_path) -> None:
    blocked = tmp_path / "obstacle"
    blocked.write_text("fichier, pas dossier")
    out = blocked / "out.pdf"

    with pytest.raises(ValidationError):
        export_document_to_pdf(_make_document(), out, QPageSize(QPageSize.PageSizeId.A4))


def test_export_accepts_string_path(qapp, tmp_path) -> None:
    out = str(tmp_path / "out.pdf")
    export_document_to_pdf(_make_document(), out, QPageSize(QPageSize.PageSizeId.A4))

    assert Path(out).exists()
