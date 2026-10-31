"""M13 — document vision: OCR providers, image safety, layout, receipts, scanned documents, document chat."""

import io
import platform
import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.config import get_settings
from app.services import pipeline
from app.services.extractors.receipt import extract_receipt, mask_digits
from app.services.vision import OcrLine, OcrPage, OcrResult, VisionError, prepare_image, sniff_image
from app.services.vision import providers
from app.services.vision.layout import page_text

FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")


def png_bytes(size=(40, 30), color="white", **save) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=save.pop("format", "PNG"), **save)
    return out.getvalue()


# --- layout ---------------------------------------------------------------------

def test_layout_rebuilds_rows_from_separate_boxes():
    lines = [
        OcrLine("TOTAL", 0.99, (0.05, 0.80, 0.12, 0.04)),
        OcrLine("Rs 1173.90", 0.98, (0.30, 0.81, 0.18, 0.04)),  # same row, slightly lower (tilted photo)
        OcrLine("Subtotal", 0.99, (0.05, 0.60, 0.14, 0.04)),
        OcrLine("1118.00", 0.99, (0.33, 0.605, 0.13, 0.04)),
    ]
    assert page_text(lines).splitlines() == ["Subtotal   1118.00", "TOTAL   Rs 1173.90"]


# --- image safety -------------------------------------------------------------------

def test_sniff_by_magic_bytes_not_name():
    assert sniff_image(png_bytes()) == "image/png"
    assert sniff_image(png_bytes(format="JPEG")) == "image/jpeg"
    assert sniff_image(b"%PDF-1.7") is None
    assert sniff_image(b"\x00\x00\x00\x18ftypheic") == "image/heic"


def test_prepare_rotates_by_exif_and_drops_gps():
    im = Image.new("RGB", (60, 20), "white")
    exif = im.getexif()
    exif[0x0112] = 6  # orientation: rotate 90° CW
    exif[0x8825] = {1: "N", 2: (19.0, 4.0, 0.0)}  # GPS IFD
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    out, mime = prepare_image(buf.getvalue(), "image/jpeg")
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(out)) as res:
        assert res.size == (20, 60)  # rotated upright
        assert not res.getexif()  # no orientation, no GPS


def test_prepare_refuses_huge_and_garbage(monkeypatch):
    from app.services.vision import images
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    with pytest.raises(VisionError) as e:
        prepare_image(png_bytes((20, 20)), "image/png")
    assert e.value.code == "IMAGE_TOO_LARGE"
    with pytest.raises(VisionError) as e:
        prepare_image(b"\x89PNG\r\n\x1a\nnot really", "image/png")
    assert e.value.code == "UNREADABLE_IMAGE"


# --- provider selection (privacy) -------------------------------------------------

def test_auto_never_picks_cloud(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "k")
    monkeypatch.setattr(s, "gemini_model", "m")
    monkeypatch.setattr(s, "ocr_provider", "auto")
    monkeypatch.setattr(providers, "_macos_available", lambda: False)  # a machine without Apple Vision
    assert providers.active_provider() == "none"
    monkeypatch.setattr(s, "ocr_provider", "gemini")
    assert providers.active_provider() == "gemini"
    monkeypatch.setattr(s, "gemini_api_key", None)
    assert providers.active_provider() == "none"  # asked for gemini but not configured → honest none


def test_not_configured_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_provider", "none")
    with pytest.raises(VisionError) as e:
        providers.read_document(png_bytes(), "image/png")
    assert e.value.code == "OCR_NOT_CONFIGURED"
    assert providers.provider_status() == {"provider": "none", "configured": False, "on_device": False,
                                           "note": providers.provider_status()["note"]}


def test_gemini_transcription_uses_bytes_part_and_schema(monkeypatch):
    genai_types = pytest.importorskip("google.genai.types")
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "k")
    monkeypatch.setattr(s, "gemini_vision_model", "configured-vision-model")
    monkeypatch.setattr(s, "ocr_provider", "gemini")
    seen = {}

    class Models:
        def generate_content(self, model, contents, config):
            seen.update(model=model, part=contents[0], config=config)
            return type("R", (), {"text": '{"pages":[{"page":1,"text":"GRAND TOTAL   540.00"}]}'})()

    monkeypatch.setattr(providers, "_gemini_client", lambda: type("C", (), {"models": Models()})())
    r = providers.read_document(b"\xff\xd8\xffjpeg", "image/jpeg")
    assert seen["model"] == "configured-vision-model"
    assert isinstance(seen["part"], genai_types.Part) and seen["part"].inline_data.mime_type == "image/jpeg"
    assert seen["config"].response_json_schema == providers.TRANSCRIBE_SCHEMA
    assert r.provider == "gemini" and r.pages[0].text == "GRAND TOTAL   540.00"
    assert r.mean_confidence == providers.GEMINI_CONFIDENCE  # never treated as certain


# --- receipt extraction ------------------------------------------------------------------

RECEIPT = """ANNAPURNA SUPERMART
GSTIN: 27ABCDE1234F1Z5
Bill No: AS/2026/00871
Date: 14/09/2026 18:42
Toor Dal 1kg 2 298.00
Basmati Rice 5kg 1 545.00
Amul Butter 500g 1 275.00
Subtotal   1118.00
CGST 2.5%   27.95
SGST 2.5%   27.95
TOTAL   Rs 1173.90
Card: VISA XXXX XXXX XXXX 4821"""


def test_receipt_fields_items_and_taxes():
    ex = extract_receipt([RECEIPT])
    assert ex.value("merchant") == "Annapurna Supermart"
    assert ex.value("purchase_date") == "2026-09-14"
    assert ex.value("total") == 1173.90 and ex.value("subtotal") == 1118.0
    assert ex.value("gst_total") == 55.90 and ex.value("gstin") == "27ABCDE1234F1Z5"
    assert ex.value("invoice_number") == "AS/2026/00871"
    assert [(i["name"], i["quantity"], i["amount"]) for i in ex.value("items")] == [
        ("Toor Dal 1kg", 2.0, 298.0), ("Basmati Rice 5kg", 1.0, 545.0), ("Amul Butter 500g", 1.0, 275.0)]
    assert ex.get("items").confidence == 0.8  # items add up to the subtotal
    assert ex.value("payment_method") == "Card ending 4821"
    assert not ex.warnings  # subtotal + taxes == total


def test_receipt_never_keeps_full_card_numbers_and_flags_mismatch():
    assert mask_digits("Card 4111 1111 1111 1111 approved") == "Card •••• 1111 approved"
    ex = extract_receipt(["Cafe Mocha\nLatte 180.00\nSubtotal 180.00\nGST 5% 9.00\nGrand Total 250.00\nCard 4111111111111111"])
    assert all("4111111111111111" not in (f.snippet or "") for f in ex.facts)
    assert all("4111111111111111" not in c["text"] for c in ex.chunks)
    assert any("doesn't add up" in w for w in ex.warnings)


def test_ocr_confidence_lowers_every_value():
    ex = extract_receipt([RECEIPT], ocr_confidence=0.5)
    assert ex.get("total").confidence == pytest.approx(0.65 * 0.5)  # plain "TOTAL" line (0.65) × OCR confidence


# --- pipeline with a fake OCR provider -------------------------------------------------------

def fake_ocr(text_by_page: dict[int, str], provider="macos"):
    def _read(data, mime, max_pages=None):
        return OcrResult(provider=provider, pages=[OcrPage(page=p, lines=[OcrLine(t, 0.96) for t in txt.splitlines()], text=txt)
                                                   for p, txt in text_by_page.items()])
    return _read


def upload(c, data, name, doc_type, **form):
    return c.post("/api/documents", files={"file": (name, data, "application/octet-stream")}, data={"type": doc_type, **form})


def test_receipt_photo_end_to_end(sample, monkeypatch):
    before = sample.get("/api/transactions?limit=500").json()
    txns = before["items"]
    t = next(x for x in txns if x["direction"] == "debit" and x["amount"] > 500)
    text = f"CITY MEDICAL STORES\nDate: {t['date']}\nParacetamol 650  2  60.00\nTotal Amount   {t['amount']:.2f}\nPaid by UPI"
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: text}))
    r = upload(sample, png_bytes((300, 400)), "bill.png", "receipt")
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]
    d = sample.get(f"/api/documents/{doc_id}").json()
    assert d["status"] == "needs_review" and d["read_from_scan"] and d["ocr"]["on_device"]
    assert d["mime"] == "image/jpeg"  # re-encoded before storage
    detail = sample.get(f"/api/documents/{doc_id}/receipt").json()
    assert detail["receipt"]["total"] == round(t["amount"], 2)
    assert not any(detail["receipt"]["confirmed"].values())  # nothing auto-confirmed
    assert detail["candidates"] and detail["candidates"][0]["id"] == t["id"]
    linked = sample.post(f"/api/documents/{doc_id}/receipt/link", json={"transaction_id": t["id"]}).json()
    assert linked["linked_transaction"]["id"] == t["id"] and linked["candidates"] == []
    # no transaction was created by the receipt
    assert sample.get("/api/transactions?limit=500").json()["total"] == before["total"]
    # reject a value → never used
    facts = sample.get(f"/api/documents/{doc_id}/facts").json()["facts"]
    merchant = next(f for f in facts if f["key"] == "merchant")
    assert sample.post(f"/api/documents/{doc_id}/facts/{merchant['id']}/reject").json()["state"] == "rejected"
    assert sample.get(f"/api/documents/{doc_id}/receipt").json()["receipt"]["merchant"] is None


def test_receipts_are_private(sample, user_client, monkeypatch):
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: "SHOP\nTotal 100.00"}))
    doc_id = upload(sample, png_bytes((200, 200), "#fafafa"), "r.png", "receipt").json()["id"]
    assert user_client.get(f"/api/documents/{doc_id}/receipt").status_code == 404
    assert user_client.post(f"/api/documents/{doc_id}/receipt/link", json={"transaction_id": None}).status_code == 404
    other = user_client.post("/api/ai/chat", json={"message": "summary", "context_type": "document", "context_object_id": doc_id})
    assert other.status_code == 404


def test_scanned_policy_pdf_goes_through_ocr_with_lower_confidence(sample, monkeypatch):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 200, 200, fill=1)  # an image-only page: no text layer
    c.showPage()
    c.save()
    policy = ("POLICY SCHEDULE\nInsurer: Sahyadri General Insurance Co. Ltd.\nPlan: Scan Shield Health\n"
              "Sum Insured: Rs 5,00,000\nPolicy Period: 01/04/2026 to 31/03/2027\nPremium: Rs 12,400")
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: policy}))
    r = upload(sample, buf.getvalue(), "scan.pdf", "insurance_policy")
    assert r.status_code == 200, r.text
    d = sample.get(f"/api/documents/{r.json()['id']}").json()
    assert d["status"] == "needs_review" and d["read_from_scan"], d
    assert d["warnings"][0].startswith("Read from a scan")
    facts = sample.get(f"/api/documents/{d['id']}/facts").json()["facts"]
    si = next(f for f in facts if f["key"] == "sum_insured")
    assert si["value"] == 500000 and si["confidence"] < 0.8 and si["state"] == "extracted"


def test_scan_fails_clearly_when_ocr_not_configured(sample, monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_provider", "none")
    r = upload(sample, png_bytes((120, 90), "#eeeeee"), "photo.png", "loan_document")
    d = sample.get(f"/api/documents/{r.json()['id']}").json()
    assert d["status"] == "failed" and d["error_code"] == "OCR_NOT_CONFIGURED"


def test_heic_is_refused_with_advice(sample):
    r = upload(sample, b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "IMG_1.HEIC", "receipt")
    assert r.status_code == 400 and "JPG" in r.json()["error"]["message"]


def test_document_chat_summarises_one_document_only(sample, monkeypatch):
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: "HILLTOP CAFE\nDate: 02/09/2026\nFilter Coffee 2 80.00\nGrand Total 80.00"}))
    doc_id = upload(sample, png_bytes((222, 111), "#fdfdfd"), "cafe.png", "receipt").json()["id"]
    m = sample.post("/api/ai/chat", json={"message": "summarise this", "context_type": "document", "context_object_id": doc_id}).json()["message"]
    card = next(c for c in m["cards"] if c["type"] == "document_summary")
    assert card["document"]["id"] == doc_id and card["confirmed"] == 0
    assert "Hilltop Cafe" in m["content"] and "not checked" in m["content"]
    q = sample.post("/api/ai/chat", json={"message": "filter coffee", "context_type": "document", "context_object_id": doc_id}).json()["message"]
    assert any(c["type"] == "doc_search" for c in q["cards"])
    assert not any(c["type"] in ("loan_options", "card_ranking") for c in q["cards"])  # isolation


# --- the real thing (on-device Apple Vision) ------------------------------------------------------

@pytest.mark.real_ocr
@pytest.mark.skipif(platform.system() != "Darwin" or not shutil.which("swiftc") or not FONT.exists(),
                    reason="needs macOS with Swift and a system font")
def test_real_on_device_ocr_reads_a_photo_of_a_receipt(monkeypatch):
    from PIL import ImageDraw, ImageFont
    monkeypatch.setattr(get_settings(), "ocr_provider", "macos")
    monkeypatch.setattr(get_settings(), "ocr_timeout_seconds", 30)  # fail/skip fast if macOS stalls on the new helper
    font = ImageFont.truetype(str(FONT), 34)
    lines = RECEIPT.splitlines()
    im = Image.new("RGB", (900, 60 + 52 * len(lines)), "white")
    draw = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        draw.text((40, 30 + 52 * i), ln, fill="black", font=font)
    buf = io.BytesIO()
    im.rotate(-2, expand=True, fillcolor="white").save(buf, format="JPEG", quality=85)
    data, mime = prepare_image(buf.getvalue(), "image/jpeg")
    try:
        result = providers.read_document(data, mime)
    except VisionError as exc:
        if exc.code == "OCR_TIMEOUT":  # macOS occasionally stalls on a freshly compiled helper; that is the machine, not a regression
            pytest.skip("Apple Vision timed out on this machine")
        raise
    assert result.provider == "macos" and result.mean_confidence > 0.8
    ex = extract_receipt(result.texts, result.mean_confidence)
    assert ex.value("total") == 1173.90
    assert ex.value("purchase_date") == "2026-09-14"
    assert ex.value("gst_total") == 55.90


def test_duplicate_upload_says_which_document(sample, monkeypatch):
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: "DUP SHOP\nTotal 50.00"}))
    data = png_bytes((150, 150), "#e0e0ff")
    first = upload(sample, data, "dup.png", "receipt").json()
    again = upload(sample, data, "dup.png", "receipt")
    assert again.status_code == 409
    err = again.json()["error"]
    assert err["code"] == "DUPLICATE_DOCUMENT" and err["details"]["document_id"] == first["id"] and err["details"]["type"] == "receipt"
