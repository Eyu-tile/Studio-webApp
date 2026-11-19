"""Library learning (real `vs learn` run by the worker on a small site of clips) and lessons (dedupe, checks,
repeats on new notes, and a real QA job that catches a broken MUST lesson)."""
import functools
import http.server
import json
import subprocess
import threading

import pytest

from app import storage
from app.config import get_settings
from app.db import SessionLocal
from app.models import Asset, AssetKind, AssetStatus, Lesson, Project, Version
from tests.test_api import brand, project
from worker.main import run_one


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("site")
    for name, color in (("hero shot.mp4", "red"), ("product macro.mp4", "blue")):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=25:d=3",
                        "-f", "lavfi", "-i", "sine=d=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(d / name)],
                       check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=320x180", "-frames:v", "1",
                    str(d / "logo.jpg")], check=True)
    (d / "index.html").write_text('<a href="hero%20shot.mp4">hero shot.mp4</a> <a href="product%20macro.mp4">product macro.mp4</a> '
                                  '<img src="logo.jpg">')
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler,
                                                                               directory=str(d)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    srv.shutdown()


def test_unsafe_links_are_refused(admin, monkeypatch):
    b = brand(admin)
    monkeypatch.setattr(get_settings(), "library_allow_private_hosts", False)
    for url in ("http://127.0.0.1/x.mp4", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd",
                "https://user:pw@example.com/a.mp4", "ftp://example.com/a.mp4", "http://localhost:8000/api/healthz"):
        r = admin.post(f"/api/brands/{b['id']}/library/sources", json={"url": url})
        assert r.status_code == 422, (url, r.text)


def test_learning_a_library(admin, site):
    b = brand(admin)
    r = admin.post(f"/api/brands/{b['id']}/library/sources", json={"url": site, "name": "Client site"})
    assert r.status_code == 201 and r.json()["provider"] == "web"
    assert admin.post(f"/api/brands/{b['id']}/library/sources", json={"url": site}).status_code == 409
    assert admin.post(f"/api/brands/{b['id']}/library/scan", json={"limit": 50}).status_code == 201
    assert admin.post(f"/api/brands/{b['id']}/library/scan", json={}).status_code == 409        # already running
    assert run_one("test-worker")
    s = admin.get(f"/api/brands/{b['id']}/library/summary").json()
    assert s["last_job"]["status"] == "succeeded", s
    page = admin.get(f"/api/brands/{b['id']}/library/clips").json()
    names = sorted(c["name"] for c in page["clips"])
    assert names == ["hero shot.mp4", "logo.jpg", "product macro.mp4"], names
    hero = next(c for c in page["clips"] if c["name"] == "hero shot.mp4")
    assert hero["sampled"] and round(hero["duration"]) == 3 and hero["thumb_url"] and hero["strip_url"]
    src = admin.get(f"/api/brands/{b['id']}/library/sources").json()[0]
    assert src["status"] == "ready" and src["file_count"] == 3
    upd = admin.patch(f"/api/library/clips/{hero['id']}", json={"review": "banned", "info": {"notes": "old logo"}})
    assert upd.json()["review"] == "banned"
    assert admin.get(f"/api/brands/{b['id']}/library/clips?q=old logo").json()["total"] == 1
    assert admin.get(f"/api/brands/{b['id']}/library/clips?review=banned").json()["total"] == 1
    steps = {x["key"]: x["done"] for x in admin.get(f"/api/brands/{b['id']}/setup").json()["steps"]}
    assert steps["library"] and steps["review"] and not steps["connections"]


def test_lessons_dedupe_checks_and_retire(admin):
    b = brand(admin)
    r = admin.post(f"/api/brands/{b['id']}/lessons", json={"rule": "Keep the music bed at -22 dB or lower",
                                                           "check": {"music_gain_max": "-22"}, "must": True})
    assert r.status_code == 201 and r.json()["number"] == 1 and r.json()["check"] == {"music_gain_max": -22.0}
    assert r.json()["category"] == "music"
    dup = admin.post(f"/api/brands/{b['id']}/lessons", json={"rule": "music bed at -22 dB or lower"})
    assert dup.status_code == 409 and "L1" in dup.json()["detail"]
    assert admin.post(f"/api/brands/{b['id']}/lessons", json={"rule": "x" * 10, "check": {"nope": 1}}).status_code == 422
    lid = r.json()["id"]
    assert admin.patch(f"/api/lessons/{lid}", json={"status": "retired"}).status_code == 422          # needs why
    assert admin.patch(f"/api/lessons/{lid}", json={"status": "retired", "retired_why": "new brand book"}).status_code == 200
    assert admin.get(f"/api/brands/{b['id']}/lessons").json() == []


def test_repeat_feedback_is_flagged(admin):
    b = brand(admin)
    p = project(admin, b["id"])
    admin.post(f"/api/brands/{b['id']}/lessons", json={"rule": "Keep the music bed at -22 dB or lower under speech"})
    n = admin.post(f"/api/projects/{p['id']}/notes", json={"body": "the music is way too loud again", "start_s": 3})
    assert n.json()["lesson_link"] == "repeat" and n.json()["lesson_number"] == 1
    other = admin.post(f"/api/projects/{p['id']}/notes", json={"body": "swap the second shot"}).json()
    assert other["lesson_link"] == ""
    taught = admin.post(f"/api/brands/{b['id']}/lessons", json={"rule": "Never use the second take of the intro",
                                                                "from_note_id": other["id"]}).json()
    notes = {x["id"]: x for x in admin.get(f"/api/projects/{p['id']}/notes").json()}
    assert notes[other["id"]]["lesson_link"] == "taught" and notes[other["id"]]["lesson_id"] == taught["id"]
    assert admin.get(f"/api/brands/{b['id']}/lessons").json()[0]["repeats"] == 1


def test_house_rules_are_admin_only(admin, make_user):
    ed = make_user("ed@example.com")
    assert ed.post("/api/lessons/house", json={"rule": "Never use wipe transitions"}).status_code == 403
    assert admin.post("/api/lessons/house", json={"rule": "Never use wipe transitions",
                                                  "check": {"banned_transitions": "wipe"}}).status_code == 201


def test_qa_job_catches_a_broken_must_lesson(admin, tmp_path):
    b = brand(admin)
    p = project(admin, b["id"])
    admin.post(f"/api/brands/{b['id']}/lessons", json={"rule": "Music bed at -22 dB or lower",
                                                       "check": {"music_gain_max": -22}, "must": True})
    video = tmp_path / "v1.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=3", "-f", "lavfi",
                    "-i", "sine=d=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(video)], check=True)
    with SessionLocal() as db:
        raw = Asset(project_id=p["id"], kind=AssetKind.raw, status=AssetStatus.ready, filename="src.mp4",
                    storage_key=f"{storage.project_prefix(b['id'], p['id'])}raw/src.mp4", mime="video/mp4")
        rend = Asset(project_id=p["id"], kind=AssetKind.render, status=AssetStatus.ready, filename="v1.mp4",
                     storage_key=f"{storage.project_prefix(b['id'], p['id'])}renders/v1/v1.mp4", mime="video/mp4")
        db.add_all([raw, rend])
        db.flush()
        storage.upload_file(video, raw.storage_key, "video/mp4")
        storage.upload_file(video, rend.storage_key, "video/mp4")
        v = Version(project_id=p["id"], number=1, asset_id=rend.id,
                    edl={"source": f"asset:{raw.id}", "segments": [{"start": 0, "end": 3}],
                         "music": {"file": "bed.mp3", "gain_db": -12}})
        db.add(v)
        db.commit()
        vid = v.id
    assert admin.post(f"/api/projects/{p['id']}/jobs", json={"kind": "qa", "payload": {"version_id": str(vid)}}).status_code == 201
    assert run_one("test-worker")
    job = admin.get(f"/api/projects/{p['id']}/jobs").json()[0]
    assert job["status"] == "succeeded", job["log_tail"][-2000:]
    with SessionLocal() as db:
        qa = db.get(Version, vid).qa
        lesson = db.query(Lesson).one()
    fails = [r for r in qa["results"] if r["level"] == "FAIL"]
    assert any(r["check"] == "lesson L1" and "music at -12 dB" in r["msg"] for r in fails), json.dumps(qa)[:1500]
    assert lesson.caught == 1                                              # synced back from vs qa
    assert job["message"].startswith("QA:")
    assert Project  # (imported for readability of the fixture-free setup above)
