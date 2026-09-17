#!/usr/bin/env python3
"""
Refresh data/combined.json and rebuild index.html for Hormuz Watch.

Sources (both free, no API key required):
  - IMF PortWatch, Daily Chokepoint Transit Calls (chokepoint6 = Strait of Hormuz),
    served from an ArcGIS FeatureServer.
  - FRED (Federal Reserve Economic Data), series DCOILBRENTEU
    (Europe Brent Spot Price FOB, $/barrel), sourced from the US EIA.

Run with: python scripts/refresh_data.py
Exits with code 0 always; writes data/combined.json and index.html only if
something changed, and prints a one-line summary either way.
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
TEMPLATE_PATH = os.path.join(ROOT, "scripts", "template.html")
INDEX_PATH = os.path.join(ROOT, "index.html")

WINDOW_DAYS = 120  # rolling window shown on the page

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
    dates = dates[-WINDOW_DAYS:]
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


def render_index(rows):
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        tpl = f.read()
    data_json = json.dumps(rows, separators=(",", ":"))
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = tpl.replace("__DATA_JSON__", data_json)
    html = html.replace("__DAY_COUNT__", str(len(rows)))
    html = html.replace("__AS_OF__", as_of)
    return html


def main():
    try:
        transits = fetch_transits()
    except Exception as e:
        print("refresh: could not fetch IMF PortWatch data (%s); leaving site unchanged." % e)
        return 0
    try:
        brent = fetch_brent()
    except Exception as e:
        print("refresh: could not fetch FRED Brent data (%s); leaving site unchanged." % e)
        return 0

    rows = build_combined(transits, brent)
    if not rows:
        print("refresh: no overlapping dates between sources; leaving site unchanged.")
        return 0

    old_rows = []
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                old_rows = json.load(f)
        except Exception:
            old_rows = []

    if rows == old_rows:
        print("refresh: no new data since last run (latest %s). No changes made." % rows[-1]["date"])
        return 0

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
        f.write("\n")

    html = render_index(rows)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    last = rows[-1]
    print(
        "refresh: updated through %s — %d transits (%d tankers), Brent $%.2f. %d days in window."
        % (last["date"], last["transits"], last["tankers"], last["brent"], len(rows))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
