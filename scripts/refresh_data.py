#!/usr/bin/env python3
"""
Refresh data/combined.json and rebuild index.html for Hormuz Watch.

Sources (both free, no API key required):
  - IMF PortWatch, Daily Chokepoint Transit Calls (chokepoint6 = Strait of Hormuz),
    served from an ArcGIS FeatureServer.
  - FRED (Federal Reserve Economic Data), series DCOILBRENTEU
    (Europe Brent Spot Price FOB, $/barrel), sourced from the US EIA.

Run with: python scripts/refresh_data.py
Exits with code 0 always. index.html is rebuilt from the current template on
EVERY run (so template edits and the "last updated" timestamp always show up),
even on days the two sources haven't published anything new.

data/combined.json holds the rolling WINDOW_DAYS window shown on the page.
data/archive.json holds the FULL history ever fetched, so trimming/extending
the window later doesn't lose data.
data/status.json tracks consecutive fetch failures, so the workflow can open
a GitHub Issue if the sources have been down for multiple days running.
"""
import csv
import io
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "combined.json")
ARCHIVE_PATH = os.path.join(ROOT, "data", "archive.json")
STATUS_PATH = os.path.join(ROOT, "data", "status.json")
TEMPLATE_PATH = os.path.join(ROOT, "scripts", "template.html")
INDEX_PATH = os.path.join(ROOT, "index.html")

WINDOW_DAYS = 120  # rolling window shown on the page
FAILURE_THRESHOLD = 3  # consecutive failed runs before the workflow should flag it

# Used for canonical link + Open Graph/Twitter image URLs in the page <head>.
# UPDATE THIS once your custom domain is live (e.g. "https://hormuzwatch.org").
# No trailing slash.
SITE_URL = "https://eshaaalali.github.io/hormuz-watch-repo"

PORTWATCH_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"

UA = {"User-Agent": "hormuz-watch-refresh/1.0 (+https://github.com/)"}


def fetch(url, params=None, timeout=30):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_transits():
    """Return {iso_date: {"transits": int, "tankers": int}} from IMF PortWatch."""
    params = {
        "where": "portname='Strait of Hormuz'",
        "outFields": "date,n_tanker,n_cargo,n_container,n_dry_bulk,n_general_cargo,n_roro",
        "orderByFields": "date DESC",
        "resultRecordCount": str(WINDOW_DAYS + 30),
        "f": "json",
    }
    raw = fetch(PORTWATCH_URL, params)
    payload = json.loads(raw)
    out = {}
    for feat in payload.get("features", []):
        attrs = feat["attributes"]
        ts_ms = attrs.get("date")
        if ts_ms is None:
            continue
        d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
        counts = [
            attrs.get("n_tanker") or 0,
            attrs.get("n_cargo") or 0,
            attrs.get("n_container") or 0,
            attrs.get("n_dry_bulk") or 0,
            attrs.get("n_general_cargo") or 0,
            attrs.get("n_roro") or 0,
        ]
        out[d] = {"transits": int(sum(counts)), "tankers": int(attrs.get("n_tanker") or 0)}
    return out


def fetch_brent():
    """Return {iso_date: float} from FRED, skipping missing ('.') values."""
    raw = fetch(FRED_URL).decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(raw))
    header = next(reader, None)
    out = {}
    for row in reader:
        if len(row) < 2:
            continue
        d, v = row[0].strip(), row[1].strip()
        if not d or v in ("", "."):
            continue
        try:
            out[d] = float(v)
        except ValueError:
            continue
    return out


def build_combined(transits, brent):
    dates = sorted(set(transits) & set(brent))
    if not dates:
        return []
    rows = []
    for d in dates:
        t = transits[d]
        rows.append({
            "date": d,
            "transits": t["transits"],
            "tankers": t["tankers"],
            "brent": round(brent[d], 2),
            "brentReal": True,
        })
    return rows


def validate_rows(rows):
    """Raise ValueError if rows don't look like well-formed data. Returns rows unchanged."""
    if not isinstance(rows, list):
        raise ValueError("rows is not a list")
    seen_dates = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ValueError("row %d is not an object" % i)
        for key in ("date", "transits", "tankers", "brent", "brentReal"):
            if key not in r:
                raise ValueError("row %d missing key %r" % (i, key))
        d = r["date"]
        if not isinstance(d, str) or len(d) != 10 or d[4] != "-" or d[7] != "-":
            raise ValueError("row %d has malformed date %r" % (i, d))
        if d in seen_dates:
            raise ValueError("duplicate date %r in rows" % d)
        seen_dates.add(d)
        if not isinstance(r["transits"], int) or r["transits"] < 0:
            raise ValueError("row %d has bad transits value %r" % (i, r["transits"]))
        if not isinstance(r["tankers"], int) or r["tankers"] < 0:
            raise ValueError("row %d has bad tankers value %r" % (i, r["tankers"]))
        if not isinstance(r["brent"], (int, float)) or r["brent"] <= 0:
            raise ValueError("row %d has bad brent value %r" % (i, r["brent"]))
        if r["tankers"] > r["transits"]:
            raise ValueError("row %d has tankers > transits" % i)
    return rows


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")


def merge_archive(archive_rows, new_rows):
    """Merge new_rows into the full archive, deduped by date, sorted ascending."""
    by_date = {r["date"]: r for r in archive_rows}
    for r in new_rows:
        by_date[r["date"]] = r
    return [by_date[d] for d in sorted(by_date)]


def render_index(rows):
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        tpl = f.read()
    data_json = json.dumps(rows, separators=(",", ":"))
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = tpl.replace("__DATA_JSON__", data_json)
    html = html.replace("__DAY_COUNT__", str(len(rows)))
    html = html.replace("__AS_OF__", as_of)
    html = html.replace("__SITE_URL__", SITE_URL)
    return html


def main():
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = load_json(STATUS_PATH, {"consecutive_failures": 0, "last_success": None, "last_run": None})
    old_combined = load_json(DATA_PATH, [])
    archive = load_json(ARCHIVE_PATH, old_combined)  # bootstrap archive from combined.json the first time

    rows = old_combined
    note = "no new data fetched"
    fetch_ok = False

    try:
        transits = fetch_transits()
        brent = fetch_brent()
        fetched_rows = build_combined(transits, brent)
        if fetched_rows:
            validate_rows(fetched_rows)
            archive = merge_archive(archive, fetched_rows)
            rows = archive[-WINDOW_DAYS:]
            note = "fetched OK"
            fetch_ok = True
        else:
            note = "fetch returned no overlapping dates; kept previous data"
    except Exception as e:
        note = "fetch failed (%s); kept previous data" % e

    status["last_run"] = now_iso
    if fetch_ok:
        status["consecutive_failures"] = 0
        status["last_success"] = now_iso
    else:
        status["consecutive_failures"] = status.get("consecutive_failures", 0) + 1
    write_json(STATUS_PATH, status)

    if not rows:
        print("refresh: no data available yet (%s); index.html not built." % note)
        return 0

    if rows != old_combined:
        write_json(DATA_PATH, rows)
    if fetch_ok:
        write_json(ARCHIVE_PATH, archive)

    html = render_index(rows)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    last = rows[-1]
    print(
        "refresh: %s. Page rebuilt through %s — %d transits (%d tankers), Brent $%.2f. "
        "%d days in window, %d in archive. consecutive_failures=%d"
        % (note, last["date"], last["transits"], last["tankers"], last["brent"],
           len(rows), len(archive), status["consecutive_failures"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
