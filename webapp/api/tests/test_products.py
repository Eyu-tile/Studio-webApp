"""A client's products: the card and packshots editors keep, the library clips that show the product, the product a
project sells, and what a Claude turn gets from it (the card and packshots in its workspace, the rules in its
instructions)."""
import uuid

import httpx

from app.db import SessionLocal
from app.models import LibraryClip
from tests.test_agent import FakeClient, _result, engine_on  # noqa: F401 - engine_on is a fixture
from tests.test_api import brand, project
from worker.main import run_one

SERUM = {"name": "Night Serum", "pitch": "Overnight repair serum for dry skin",
         "benefits": ["Skin feels softer by morning", "  ", "Fragrance free"],
         "claims_ok": ["Dermatologist tested"], "claims_no": ["Cures acne", "Clinically proven"],
         "price": "$48 / 30 ml", "links": ["https://example.com/night-serum"], "notes": "Always shown on marble."}
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def _packshot(client, product_id: str, name="serum-front.png", kind="packshot") -> dict:
    r = client.post(f"/api/products/{product_id}/files", json={"filename": name, "size": len(PNG), "mime": "image/png",
                                                                "kind": kind})
    assert r.status_code == 201, r.text
    start = r.json()
    put = httpx.put(start["upload_url"], content=PNG, headers={"Content-Type": "image/png"})
    assert put.status_code == 200, put.text
    done = client.post(f"/api/product-files/{start['file']['id']}/complete")
    assert done.status_code == 200, done.text
    return done.json()


def test_a_product_card_with_packshots_and_clips(admin, make_user):
    b = brand(admin, "Lumen")
    r = admin.post(f"/api/brands/{b['id']}/products", json=SERUM)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["slug"] == "night-serum" and p["benefits"] == ["Skin feels softer by morning", "Fragrance free"]
    assert admin.post(f"/api/brands/{b['id']}/products", json=SERUM).json()["slug"] == "night-serum-2"

    f = _packshot(admin, p["id"])
    assert f["status"] == "ready" and f["url"]
    bad = admin.post(f"/api/products/{p['id']}/files", json={"filename": "x.exe", "size": 10, "mime": "application/x-msdownload"})
    assert bad.status_code == 415
    with SessionLocal() as db:
        db.add(LibraryClip(brand_id=uuid.UUID(b["id"]), external_id="c1", name="serum-hero.mov", kind="video",
                           info={"product": "night serum 30ml"}))
        db.add(LibraryClip(brand_id=uuid.UUID(b["id"]), external_id="c2", name="day-cream.mov", kind="video",
                           info={"product": "Day Cream"}))
        db.commit()
    d = admin.get(f"/api/products/{p['id']}").json()
    assert d["image_url"] and d["file_count"] == 1 and [c["name"] for c in d["clips"]] == ["serum-hero.mov"]
    assert {s["key"]: s["done"] for s in admin.get(f"/api/brands/{b['id']}/setup").json()["steps"]}["products"]

    # roles: viewers read, editors edit the card, leads archive; other brands don't see it
    admin.post(f"/api/brands/{b['id']}/members", json={"email": "vi@example.com", "role": "viewer"})
    admin.post(f"/api/brands/{b['id']}/members", json={"email": "ed@example.com", "role": "editor"})
    vi, ed = make_user("vi@example.com"), make_user("ed@example.com")
    assert vi.get(f"/api/brands/{b['id']}/products").status_code == 200
    assert vi.post(f"/api/brands/{b['id']}/products", json=SERUM).status_code == 403
    assert ed.patch(f"/api/products/{p['id']}", json={"price": "$52"}).json()["price"] == "$52"
    assert ed.patch(f"/api/products/{p['id']}", json={"archived": True}).status_code == 403
    other = brand(admin, "Northwind")
    admin.post(f"/api/brands/{other['id']}/members", json={"email": "out@example.com", "role": "lead"})
    assert make_user("out@example.com").get(f"/api/products/{p['id']}").status_code == 404


def test_a_project_sells_one_product(admin):
    b, other = brand(admin, "Lumen"), brand(admin, "Northwind")
    p = admin.post(f"/api/brands/{b['id']}/products", json=SERUM).json()
    elsewhere = admin.post(f"/api/brands/{other['id']}/products", json={"name": "Cold Brew"}).json()
    r = admin.post(f"/api/brands/{b['id']}/projects", json={"name": "Serum UGC", "kind": "tiktok", "product_id": p["id"]})
    assert r.status_code == 201 and r.json()["product_name"] == "Night Serum"
    pid = r.json()["id"]
    assert admin.post(f"/api/brands/{b['id']}/projects", json={"name": "x", "product_id": elsewhere["id"]}).status_code == 422
    assert admin.patch(f"/api/projects/{pid}", json={"clear_product": True}).json()["product_id"] is None
    assert admin.patch(f"/api/projects/{pid}", json={"product_id": p["id"]}).json()["product_id"] == p["id"]
    assert admin.get(f"/api/products/{p['id']}").json()["projects"][0]["name"] == "Serum UGC"


def test_claude_gets_the_card_packshots_and_rules(admin, engine_on):  # noqa: F811
    b = brand(admin, "Lumen")
    admin.patch(f"/api/brands/{b['id']}", json={"description": "Clean skincare for people with sensitive skin."})
    serum = admin.post(f"/api/brands/{b['id']}/products", json=SERUM).json()
    admin.post(f"/api/brands/{b['id']}/products", json={"name": "Day Cream", "pitch": "SPF 30 moisturiser"})
    _packshot(admin, serum["id"])
    _packshot(admin, serum["id"], "lumen-logo.png", "logo")
    p = project(admin, b["id"])
    admin.patch(f"/api/projects/{p['id']}", json={"product_id": serum["id"]})
    seen = {}

    async def script(options, cwd):
        seen["prompt"] = options.system_prompt["append"]
        card = cwd / "video-studio" / "library" / b["slug"] / "products" / "night-serum"
        seen["card"] = (card / "product.md").read_text()
        seen["files"] = sorted(str(x.relative_to(card)) for x in card.rglob("*.png"))
        seen["other"] = (cwd / "video-studio" / "library" / b["slug"] / "products" / "day-cream" / "product.md").exists()
        yield _result()
    FakeClient.script = script
    assert admin.post(f"/api/projects/{p['id']}/claude/threads", json={"text": "Write a 30 s UGC script"}).status_code == 201
    assert run_one("w", ("agent",))
    assert "## Never claim or imply\n- Cures acne\n- Clinically proven" in seen["card"]
    assert seen["files"] == ["logos/lumen-logo.png", "packshots/serum-front.png"] and seen["other"]
    prompt = seen["prompt"]
    assert "## The product: Night Serum" in prompt and "products/night-serum/product.md" in prompt
    assert "packshots/serum-front.png" in prompt and "Day Cream: SPF 30 moisturiser" in prompt
    assert "Clean skincare for people with sensitive skin." in prompt
