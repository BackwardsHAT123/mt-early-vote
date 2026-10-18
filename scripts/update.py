"""Append today's Montana absentee counts to data/snapshots.json."""
import csv, io, json, datetime, urllib.request, pathlib

URL = "https://tableau-ext.mt.gov/t/SOS/views/AbsenteeBallots/AbsenteeDash.csv"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "snapshots.json"

req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")
by = {}
for r in csv.DictReader(io.StringIO(text)):
    by.setdefault(r["County"], {})[r["Measure Names"]] = int(r["Measure Values"].replace(",", "")) if "%" not in r["Measure Names"] else 0
rows = [[c, v["Ballots Sent"], v["Ballots Received"]] for c, v in by.items() if c != "All"]
tot = by["All"]
snap = {"asof": datetime.date.today().isoformat(), "electionDay": "2026-11-03",
        "rows": rows, "total": [tot["Ballots Sent"], tot["Ballots Received"]]}
data = json.loads(OUT.read_text()) if OUT.exists() else []
data = [d for d in data if d["asof"] != snap["asof"]] + [snap]
OUT.write_text(json.dumps(data, indent=1))
print("saved", snap["asof"], snap["total"])
