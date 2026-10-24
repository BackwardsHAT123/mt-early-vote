"""Fetch Montana unofficial election results (statewide + county) into data/results.json.

Source: the Secretary of State's results site, electionresults.mt.gov. Its
"Statewide and County Exports" page returns one xlsx with a sheet per contest and
a row per county. Exits quietly (code 0, file untouched) if results are not
posted yet, so it is safe to run on a schedule.

    python3 scripts/results.py                       # 2026 general, eid from config/probe
    python3 scripts/results.py --eid 450002785 --match "NOVEMBER 5, 2024" --out /tmp/r.json
"""
import argparse, html, io, json, pathlib, re, sys, time
import requests, openpyxl

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "results_config.json"
BASE = "https://electionresults.mt.gov/ResultsExport.aspx?eid="
SKIP = re.compile(r"^(JUDICIAL DISTRICT|STATE SENATE|STATE HOUSE|DISTRICT COURT|Shall Judge)", re.I)
PROBE_RANGE = range(450002929, 450003300)  # eids after the 2026 primary (450002928)


def get_form(session, eid):
    r = session.get(BASE + str(eid), timeout=60)
    if r.status_code != 200:
        return None, None
    f = {m.group(1): html.unescape(m.group(2)) for m in
         re.finditer(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', r.text)}
    return r.text, f


def find_eid(session, match):
    """Use the configured eid, else probe forward from the 2026 primary and cache the hit."""
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if cfg.get("eid"):
        return cfg["eid"]
    for eid in PROBE_RANGE:
        page, _ = get_form(session, eid)
        if page and match.lower() in page.lower():
            CONFIG.write_text(json.dumps({"eid": eid}, indent=1))
            return eid
        time.sleep(0.15)
    return None


def parse(xlsx_bytes):
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    contests, precincts = [], ""
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not precincts and len(rows) > 2 and rows[2][0]:
            precincts = str(rows[2][0])
        hdr = next((i for i, r in enumerate(rows) if len(r) > 1 and r[1] == "County"), None)
        if hdr is None:
            continue
        title = str(rows[hdr][0]).strip()
        if SKIP.match(title):
            continue
        choices = []
        for c in rows[hdr][2:]:
            parts = str(c).split("\n")
            choices.append({"name": parts[0].strip(), "party": parts[1].strip() if len(parts) > 1 else ""})
        counties, total = {}, None
        for r in rows[hdr + 1:]:
            if r[1] is None:
                continue
            votes = [int(v or 0) for v in r[2:2 + len(choices)]]
            if str(r[1]).upper() == "TOTALS":
                total = votes
            else:
                counties[str(r[1])] = votes
        if total is None:
            total = [sum(v[i] for v in counties.values()) for i in range(len(choices))]
        contests.append({"id": ws.title[:5], "title": title, "choices": choices,
                         "total": total, "counties": counties})
    return contests, precincts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eid", type=int)
    ap.add_argument("--match", default="GENERAL ELECTION - NOVEMBER 3, 2026")
    ap.add_argument("--out", default=str(ROOT / "data" / "results.json"))
    a = ap.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    eid = a.eid or find_eid(s, a.match)
    if not eid:
        print("No results posted yet for:", a.match)
        return 0
    page, form = get_form(s, eid)
    if not page or a.match.lower() not in page.lower():
        print("eid", eid, "is not", a.match)
        return 0
    form["__EVENTTARGET"], form["__EVENTARGUMENT"] = "ctl00$MainContent$Statewide", ""
    r = s.post(BASE + str(eid), data=form, timeout=180)
    if r.status_code != 200 or "spreadsheetml" not in r.headers.get("content-type", ""):
        print("Export failed:", r.status_code, r.headers.get("content-type"))
        return 1
    contests, precincts = parse(r.content)
    upd = re.search(r"Results last updated:\s*([^<\n]+?MT)", page)
    out = {"election": a.match, "eid": eid, "updated": upd.group(1) if upd else "",
           "precincts": precincts, "contests": contests}
    p = pathlib.Path(a.out)
    new = json.dumps(out, indent=1)
    if p.exists() and p.read_text() == new:
        print("unchanged")
        return 0
    p.write_text(new)
    print("saved", len(contests), "contests;", precincts, ";", out["updated"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
