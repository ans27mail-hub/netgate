"""Create a v0.4-style database with sample data (run with the v0.4 code on PYTHONPATH),
so test_v05.py can check the upgrade. Usage: see tests/README.md."""
from app.auth import PERM_KEYS, hash_password
from app.db import Field, Group, Job, Record, SessionLocal, User, UserGroup, init_db, name_key

init_db()
with SessionLocal() as s:
    s.add(User(username="admin", password_hash=hash_password("secret123"), is_admin=True, role="Admin",
               perms=",".join(PERM_KEYS), all_groups=True, active=True, prefs={}))
    g = s.query(Group).filter_by(name="Manufacturers").one()
    m = s.query(Group).filter_by(name="Materials").one()
    s.add(User(username="worker1", password_hash=hash_password("secret123"), role="Editor",
               perms="view,request,keywords,edit", all_groups=True, active=True, prefs={}))
    s.add(User(username="viewer1", password_hash=hash_password("secret123"), role="Custom", perms="view,delete",
               all_groups=False, active=True, prefs={}, group_links=[UserGroup(group_id=m.id)]))
    g.fields.append(Field(name="Phone", key="phone", type="phone", words="phone, call", position=7, list=True))
    g.fields.append(Field(name="WhatsApp", key="whatsapp", type="text", words="whatsapp", position=8))
    g.fields.append(Field(name="Address", key="address", type="text", words="address", position=9))
    s.flush()
    j = Job(query="glove makers", group_id=g.id, kind="keyword", status="done", message="old run", stats={})
    s.add(j)
    s.flush()
    for i, (n, c) in enumerate([("Acme Leather (Pvt.) Ltd.", "Sialkot"), ("Old Gloves Co", "Lahore"),
                                ("Sialkot Sports Wear", "Sialkot"), ("Prime Leather Garments", "Sialkot")]):
        s.add(Record(job_id=j.id, group_id=g.id, topic="glove makers", title=n,
                     summary="Makes leather gloves and jackets." if i % 2 == 0 else "Sports wear factory.", facts="",
                     data={"city": c, "country": "Pakistan", "products": ["gloves"]}, sources={}, social={},
                     source_url="https://old.example/x", name_key=name_key(n)))
    s.add(Record(group_id=m.id, topic="leather", title="Hide Tannery", summary="Leather supplier", facts="",
                 data={"city": "Kasur", "country": "Pakistan"}, sources={}, social={},
                 source_url="https://old.example/y", name_key=name_key("Hide Tannery")))
    s.commit()
print("v0.4 database ready")
