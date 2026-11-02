"""PDF 三种模板与 PNG 分享卡的真实渲染验证。"""

from __future__ import annotations

import re

import pytest
from PIL import Image
from reports_helpers import (
    add_completed_analysis,
    create_record_with_analysis,
    create_record_without_signal,
)

from eclipse_health_backend.reports.fonts import (
    configure_fonts,
    find_cjk_font,
    font_supports_cjk,
)
from eclipse_health_backend.reports.share_card import CARD_SIZE


def _generate(client, record_id: str, *, format: str, template: str, redact: bool = True):
    response = client.post(
        f"/api/v1/records/{record_id}/reports",
        json={"format": format, "template": template, "redact": redact},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    ("template", "min_pages"),
    [("simple", 1), ("detailed", 2), ("doctor", 2)],
)
def test_pdf_templates_render(client, default_member, template, min_pages):
    record, _analysis_id = create_record_with_analysis(client, default_member["id"])
    body = _generate(client, record["id"], format="pdf", template=template)

    assert body["format"] == "pdf"
    assert body["template"] == template
    assert body["fileName"].endswith(".pdf")
    assert body["size"] > 20_000, body["size"]
    assert len(body["sha256"]) == 64

    download = client.get(body["downloadUrl"])
    assert download.status_code == 200
    data = download.content
    assert data.startswith(b"%PDF")
    assert download.headers["content-type"].startswith("application/pdf")
    assert body["fileName"] in download.headers["content-disposition"]
    assert len(data) == body["size"]

    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    assert pages >= min_pages, pages
    if template == "simple":
        assert pages == 1


def test_png_share_card_dimensions(client, default_member):
    record, _analysis_id = create_record_with_analysis(client, default_member["id"])
    body = _generate(client, record["id"], format="png", template="detailed")

    assert body["format"] == "png"
    assert body["fileName"].endswith(".png")
    assert body["size"] > 20_000

    download = client.get(body["downloadUrl"])
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert download.headers["content-type"] == "image/png"

    image = Image.open(__import__("io").BytesIO(download.content))
    assert image.size == CARD_SIZE


def test_report_without_waveform_still_renders(client, default_member):
    record = create_record_without_signal(client, default_member["id"])
    add_completed_analysis(record["id"])

    body = _generate(client, record["id"], format="pdf", template="simple")
    download = client.get(body["downloadUrl"])
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert body["size"] > 20_000


def test_download_metadata_headers(client, default_member):
    record, analysis_id = create_record_with_analysis(client, default_member["id"])
    body = _generate(client, record["id"], format="pdf", template="detailed")

    meta = client.get(f"/api/v1/reports/{body['reportId']}")
    assert meta.status_code == 200
    assert meta.json()["analysisId"] == analysis_id
    assert meta.json()["redacted"] is True

    download = client.get(body["downloadUrl"])
    assert download.headers["x-report-sha256"] == body["sha256"]
    assert download.headers["etag"] == f'"{body["sha256"]}"'


def test_cjk_font_available():
    path = find_cjk_font()
    assert path is not None and path.is_file(), "报告需要中文字体"
    assert font_supports_cjk(path, "心")
    name, registered = configure_fonts()
    assert name and registered == path
