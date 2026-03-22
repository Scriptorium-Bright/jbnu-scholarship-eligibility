from app.storage import LocalRawStorage


def test_phase4_local_raw_storage_saves_and_reads_notice_html_and_attachment(tmp_path):
    storage = LocalRawStorage(base_path=str(tmp_path / "raw"))

    html_path = storage.save_notice_html("jbnu-main", "402100", "<html><body>notice</body></html>")
    attachment_path = storage.save_attachment("jbnu-main", "402100", "guide.pdf", b"fake-pdf")

    assert storage.exists(html_path)
    assert storage.exists(attachment_path)
    assert storage.read_text(html_path) == "<html><body>notice</body></html>"
    assert storage.read_bytes(attachment_path) == b"fake-pdf"
