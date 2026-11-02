"""Build data/history.json: final 2022 and 2024 general-election turnout and county results.

One-off (re-run only to refresh). Uses the same Secretary of State export as results.py.
Per county it stores votes cast in the top race (2024: President; 2022: U.S. House, both
districts summed), the published turnout %, and the full county results for statewide
contests so the page can show 2026 vs. 2024 swing once results are posted.
"""
import json, pathlib, re, sys
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from results import BASE, get_form, parse

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "history.json"
ELECTIONS = {"2024": 450002785, "2022": 22}
CTY = "https://electionresults.mt.gov/ResultsSW.aspx?type=CTYALL&map=CTY&eid=%s&cty=%02d"
TOP = {"2024": [r"^PRESIDENT"], "2022": [r"^UNITED STATES REPRESENTATIVE"]}
TURN = "https://electionresults.mt.gov/VoterTurnoutDetails.aspx?map=TURN&eid="


def fetch(s, eid):
    page, form = get_form(s, eid)
    form["__EVENTTARGET"], form["__EVENTARGUMENT"] = "ctl00$MainContent$Statewide", ""
    r = s.post(BASE + str(eid), data=form, timeout=180)
    r.raise_for_status()
    return parse(r.content)[0]


def clean(h):
    h = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", h)
    return re.sub(r"(\| ?)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", h)))


def county_pages(s, eid, pattern):
    """Legacy elections have no working xlsx export: sum 'total votes' of matching contests per county page."""
    votes = {}
    for n in range(1, 57):
        t = clean(s.get(CTY % (eid, n), timeout=60).text)
        name = re.search(r"\|\s*([A-Za-z.&' ]+?) County Results", t).group(1).strip()
        votes[name] = sum(int(m.group(1).replace(",", "")) for m in
                          re.finditer(pattern + r"[^|]*\|[\s\S]*?total votes\s*\|\s*([\d,]+)", t))
    return votes


def turnout(s, eid):
    t = s.get(TURN + str(eid), timeout=60).text
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", t)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", t))
    tot = int(re.search(r"Total Turnout\s*\|*\s*([\d,]+)", t).group(1).replace(",", ""))
    reg = int(re.search(r"Registered Voters\s*\|*\s*([\d,]+)", t).group(1).replace(",", ""))
    pct = {m.group(1).strip(): float(m.group(2)) for m in
           re.finditer(r"([A-Z][A-Za-z.&' ]+?)[\s|]*(\d+\.\d+)%[\s|]*100\.0%", t)}
    return tot, reg, pct


def main():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    out = {}
    for year, eid in ELECTIONS.items():
        tot, reg, pct = turnout(s, eid)
        if year == "2024":
            contests = fetch(s, eid)
            votes = {}
            for c in contests:
                if re.match(TOP[year][0], c["title"], re.I):
                    for county, v in c["counties"].items():
                        votes[county] = votes.get(county, 0) + sum(v)
            keep = [c for c in contests if not re.match(r"^(CLERK|SUPREME|PUBLIC SERVICE)", c["title"], re.I)]
        else:
            votes = county_pages(s, eid, r"UNITED STATES REPRESENTATIVE")
            keep = []
        out[year] = {"eid": eid, "totalTurnout": tot, "registered": reg,
                     "countyVotes": votes, "countyTurnoutPct": pct, "contests": keep}
        print(year, tot, reg, len(votes), "counties;", sum(votes.values()), "votes in top race;", len(pct), "turnout pcts")
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print("saved", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
