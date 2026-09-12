"""End-to-end API checks. Run once per engine in a fresh process."""
import csv, io, os, sys
sys.path.insert(0, "/home/claude/personnel-registry/app")
os.chdir("/home/claude/personnel-registry/app")

from registry import bootstrap
from registry.db import engine, Base
from sqlalchemy import text, inspect

# fresh schema
with engine.begin() as c:
    for t in ["personnel", "custom_fields", "personnel_groups", "app_users", "alembic_version"]:
        c.execute(text(f"DROP TABLE IF EXISTS {t}" + (" CASCADE" if engine.dialect.name == "postgresql" else "")))

bootstrap.main()

# migration must match models exactly
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from registry import models  # noqa
with engine.connect() as c:
    diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
assert not diff, f"migration differs from models: {diff}"
print("schema matches models:", engine.dialect.name)

from fastapi.testclient import TestClient
from registry.main import app

def ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.text)
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r

anon = TestClient(app)
assert anon.get("/", follow_redirects=False).status_code == 303
assert anon.get("/login").status_code == 200
assert anon.get("/healthz").json() == {"status": "ok"}
assert anon.get("/api/groups").status_code == 401
r = anon.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
assert r.status_code == 401, r.text
assert "Content-Security-Policy" in anon.get("/login").headers

c = TestClient(app)
ok(c.post("/api/auth/login", json={"username": "ADMIN", "password": os.environ["ADMIN_PASSWORD"]}))
assert c.get("/", follow_redirects=False).status_code == 200
assert "/static/css/app.css?v=" in c.get("/").text

# groups
ops = ok(c.post("/api/groups", json={"name": "Operations", "code": "ops", "colour": "#E8B84A", "description": "Site ops"}), 201)
assert ops["code"] == "OPS" and ops["colour"] == "#e8b84a"
sec = ok(c.post("/api/groups", json={"name": "Security", "colour": "#5aa6f2", "sort_order": -1}), 201)
r = c.post("/api/groups", json={"name": "operations", "colour": "#000000"})
assert r.status_code == 409 and r.json()["detail"]["fields"]["name"], r.text
r = c.post("/api/groups", json={"name": "", "colour": "nope"})
assert r.status_code == 422 and set(r.json()["detail"]["fields"]) == {"name", "colour"}, r.text
lst = ok(c.get("/api/groups"))
assert [g["name"] for g in lst["groups"]] == ["Security", "Operations"]

# fields
clearance = ok(c.post("/api/fields", json={"label": "Clearance level", "field_type": "select", "options": ["L1", " L2 ", "l2", "", "L3"], "required": True, "show_in_table": True}), 201)
assert clearance["key"] == "clearance_level" and clearance["options"] == ["L1", "L2", "L3"]
radio = ok(c.post("/api/fields", json={"label": "Radio callsign", "group_id": sec["id"], "show_in_table": True}), 201)
badge_no = ok(c.post("/api/fields", json={"label": "Badge no.", "field_type": "number", "group_id": ops["id"]}), 201)
assert badge_no["key"] == "badge_no", badge_no
inducted = ok(c.post("/api/fields", json={"label": "Inducted", "field_type": "checkbox", "required": True}), 201)
assert inducted["required"] is False
site = ok(c.post("/api/fields", json={"label": "Clearance level", "field_type": "text"}), 201)
assert site["key"] == "clearance_level_2"
r = c.post("/api/fields", json={"label": "Empty select", "field_type": "select", "options": [" "]})
assert r.status_code == 422 and "options" in r.json()["detail"]["fields"], r.text
ok(c.put(f"/api/fields/{site['id']}", json={"label": "Site", "field_type": "url"}))
assert ok(c.get("/api/fields"))[0]["key"] in ("clearance_level", "inducted", "clearance_level_2")

# personnel
r = c.post("/api/personnel", json={"first_name": "Ana", "last_name": "Björk", "group_id": sec["id"], "extra": {"radio_callsign": "Echo-4"}})
assert r.status_code == 422 and r.json()["detail"]["fields"] == {"extra.clearance_level": "This field is required."}, r.text
p1 = ok(c.post("/api/personnel", json={
    "identifier": "SEC-001", "first_name": " Ana ", "last_name": "Björk", "preferred_name": "",
    "job_title": "Shift Lead", "role": "Security", "email": "ana@example.com", "phone": "+61 8 9000 0000",
    "status": "active", "start_date": "2024-02-29", "group_id": sec["id"], "notes": "日本語 ✓",
    "extra": {"clearance_level": "L3", "radio_callsign": "Echo-4", "badge_no": "999", "inducted": True, "bogus": 1},
}), 201)
assert p1["first_name"] == "Ana" and p1["preferred_name"] is None
assert p1["extra"] == {"clearance_level": "L3", "radio_callsign": "Echo-4", "inducted": True}, p1["extra"]
assert p1["created_at"].endswith("Z")
r = c.post("/api/personnel", json={"identifier": "sec-001", "first_name": "X", "last_name": "Y", "extra": {"clearance_level": "L1", "clearance_level_2": "ftp://x", }})
assert r.status_code == 422 and set(r.json()["detail"]["fields"]) == {"identifier", "extra.clearance_level_2"}, r.text
r = c.post("/api/personnel", json={"first_name": "X", "last_name": "Y", "start_date": "2024-13-01", "email": "nope", "status": "gone", "extra": {"clearance_level": "L9"}})
assert r.status_code == 422 and set(r.json()["detail"]["fields"]) >= {"start_date", "email", "status"}, r.text
p2 = ok(c.post("/api/personnel", json={"first_name": "=HYPERLINK(\"x\")", "last_name": "Zed", "status": "leave", "group_id": ops["id"], "extra": {"clearance_level": "L1", "badge_no": "-12.5", "inducted": False}}), 201)
assert p2["extra"]["badge_no"] == -12.5
p3 = ok(c.post("/api/personnel", json={"first_name": "Unassigned", "last_name": "Person", "status": "inactive", "extra": {"clearance_level": "L2"}}), 201)

# move Ana to Operations and back: Security-only value is kept
moved = ok(c.put(f"/api/personnel/{p1['id']}", json={**{k: p1[k] for k in ["identifier","first_name","last_name","job_title","role","email","phone","status","start_date","notes"]}, "group_id": ops["id"], "extra": {"clearance_level": "L3", "badge_no": 7}}))
assert moved["extra"] == {"clearance_level": "L3", "radio_callsign": "Echo-4", "inducted": True, "badge_no": 7}, moved["extra"]

# list and search
assert len(ok(c.get("/api/personnel"))) == 3
assert [p["id"] for p in ok(c.get("/api/personnel?group=unassigned"))] == [p3["id"]]
assert len(ok(c.get(f"/api/personnel?group={ops['id']}"))) == 2
assert [p["id"] for p in ok(c.get("/api/personnel?q=echo-4 björk"))] == [p1["id"]]
assert [p["id"] for p in ok(c.get("/api/personnel?status=leave"))] == [p2["id"]]
assert c.get("/api/personnel?group=abc").status_code == 422

# CSV
r = c.get(f"/api/personnel/export.csv?group={ops['id']}")
assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
header = rows[0]
assert "Badge no." in header and "Radio callsign" not in header, header
zed = next(row for row in rows[1:] if row[2] == "Zed")
assert zed[1].startswith("'="), zed
ana = next(row for row in rows[1:] if row[2] == "Björk")
assert ana[7] == "+61 8 9000 0000" and ana[header.index("Inducted")] == "Yes"

# group counts
lst = ok(c.get("/api/groups"))
assert lst["total"] == 3 and lst["unassigned"] == 1
assert {g["name"]: g["member_count"] for g in lst["groups"]} == {"Security": 0, "Operations": 2}

# delete a field: values stripped
ok(c.delete(f"/api/fields/{inducted['id']}"), 204)
assert "inducted" not in ok(c.get(f"/api/personnel/{p1['id']}"))["extra"]

# delete Operations, move members to Security: Badge # field and values gone
r = c.delete(f"/api/groups/{ops['id']}?reassign_to={ops['id']}")
assert r.status_code == 422, r.text
ok(c.delete(f"/api/groups/{ops['id']}?reassign_to={sec['id']}"), 204)
a = ok(c.get(f"/api/personnel/{p1['id']}"))
assert a["group_id"] == sec["id"] and "badge_no" not in a["extra"] and a["extra"]["radio_callsign"] == "Echo-4", a
assert all(f["key"] != "badge_no" for f in ok(c.get("/api/fields")))
ok(c.delete(f"/api/groups/{sec['id']}"), 204)
assert ok(c.get(f"/api/personnel/{p1['id']}"))["group_id"] is None
assert "radio_callsign" not in ok(c.get(f"/api/personnel/{p1['id']}"))["extra"]

# users and sessions
r = c.post("/api/users", json={"username": "Bad Name", "password": "short"})
assert r.status_code == 422 and set(r.json()["detail"]["fields"]) == {"username", "password"}, r.text
bob = ok(c.post("/api/users", json={"username": "bob.smith", "password": "correct-horse-1"}), 201)
assert c.post("/api/users", json={"username": "BOB.SMITH", "password": "correct-horse-1"}).status_code == 409
me = ok(c.get("/api/auth/me"))
assert c.delete(f"/api/users/{me['id']}").status_code == 400
b = TestClient(app)
ok(b.post("/api/auth/login", json={"username": "bob.smith", "password": "correct-horse-1"}))
other = TestClient(app)
ok(other.post("/api/auth/login", json={"username": "bob.smith", "password": "correct-horse-1"}))
r = b.post("/api/auth/password", json={"current_password": "wrong", "new_password": "new-password-123"})
assert r.status_code == 422 and "current_password" in r.json()["detail"]["fields"]
ok(b.post("/api/auth/password", json={"current_password": "correct-horse-1", "new_password": "new-password-123"}), 204)
assert b.get("/api/auth/me").status_code == 200, "own session should survive"
assert other.get("/api/auth/me").status_code == 401, "other session should end"
ok(c.put(f"/api/users/{bob['id']}/password", json={"password": "admin-reset-123"}), 204)
assert b.get("/api/auth/me").status_code == 401
ok(c.delete(f"/api/users/{bob['id']}"), 204)
ok(c.delete(f"/api/personnel/{p2['id']}"), 204)
assert c.get(f"/api/personnel/{p2['id']}").status_code == 404

# throttle
t = TestClient(app)
for _ in range(10):
    t.post("/api/auth/login", json={"username": "admin", "password": "nope"})
assert t.post("/api/auth/login", json={"username": "admin", "password": os.environ["ADMIN_PASSWORD"]}).status_code == 429

ok(c.post("/api/auth/logout"), 204)
assert c.get("/api/auth/me").status_code == 401

# migrations: down and up again
from alembic import command
from alembic.config import Config
cfg = Config("alembic.ini"); cfg.attributes["skip_logging_config"] = True
command.downgrade(cfg, "base")
assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
command.upgrade(cfg, "head")
print("ALL CHECKS PASSED:", engine.dialect.name)
