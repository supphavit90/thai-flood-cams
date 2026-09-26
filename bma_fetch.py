#!/usr/bin/env python3
"""BMA road-flood sensors, underpass tunnels and canal levels -> bma.json
(run by the GitHub Action every 20 min).

    curl -sf -A "$UA" -H "Accept: text/html" https://weather.bangkok.go.th/Flood -o flood.html
    curl -sf -A "$UA" -H "Accept: application/json" -d payload=x \
         https://weather.bangkok.go.th/water/PageMap/GoogleMap -o canals.json
    python3 bma_fetch.py flood.html canals.json


Roads + tunnels are JSON inside the /Flood page; canals come from the endpoint
BMA's own /water map polls. The
site sends no CORS header, so the map can't read it directly; this copies the
current readings into the repo, where the page can. Times are Bangkok local.

The download is curl's job: the site's firewall 403s Python's HTTP client even
with identical headers, but lets curl through with a browser UA + Accept: text/html.
"""
import json, re, sys
from datetime import datetime, timedelta, timezone


def grab(html, name):
    m = re.search(rf"const {name} = (\[.*?\]);\s*\n", html, re.S)
    if not m:
        raise ValueError(f"{name} not found - weather.bangkok.go.th/Flood changed shape (or 403 page)")
    return json.loads(m.group(1))


def bkk(ts):   # "2026/09/26 10:35" -> "2026-09-26T10:35"
    return (ts or "").replace("/", "-").replace(" ", "T")[:16]


def roads_and_tunnels(path):
    html = open(path, encoding="utf8", errors="replace").read()
    roads = [{"code": r["flood_code"], "th": r.get("flood_name"), "en": r.get("flood_name_en"),
              "y": r["latitude"], "x": r["longitude"], "cm": r.get("flood"),
              "max": r.get("flood_max"), "start": r.get("flood_start"),
              "ts": (r.get("site_timestamp") or "")[:16]}
             for r in grab(html, "floodData") if r.get("latitude") and r.get("longitude")]
    tunnels = [{"code": t["tunnel_code"], "th": t.get("tunnel_name"), "en": t.get("tunnel_name_en"),
                "y": t["latitude"], "x": t["longitude"],
                "sides": [{"dir": s.get("tunnel_sub_station_code"), "cm": s.get("flood"),
                           "ts": (s.get("site_timestamp") or "")[:16]}
                          for s in t.get("listTunnelSubLastDetail") or []]}
               for t in grab(html, "tunnelData") if t.get("latitude")]
    if len(roads) < 100:
        raise ValueError(f"only {len(roads)} road sensors")
    return roads, tunnels


def canals(path):
    out = [{"code": c.get("water_code"), "th": c.get("water_name"), "en": c.get("water_name_en"),
            "y": c["latitude"], "x": c["longitude"],
            # BMA's own status: 4 critical, 3 alert, 2 normal, 0-1 out of order
            "lvl": c.get("priorityStatus"), "m": c.get("wl_in"),
            "warn": c.get("warning"), "crit": c.get("critical"), "ts": bkk(c.get("site_timestampEN"))}
           for c in json.load(open(path, encoding="utf8")) if c.get("latitude") and c.get("longitude")]
    if len(out) < 100:
        raise ValueError(f"only {len(out)} canal stations")
    return out


def main():
    # BMA's firewall 403s /Flood now and then while /water still answers (or the
    # other way round). Whatever fails keeps its last good readings - they carry
    # their own timestamps, so the map ages them out on its own.
    try:
        prev = json.load(open("bma.json", encoding="utf8"))
    except (OSError, ValueError):
        prev = {}
    out, fresh = dict(prev), []
    try:
        out["roads"], out["tunnels"] = roads_and_tunnels(sys.argv[1]); fresh.append("roads")
    except (OSError, ValueError) as e:
        print(f"roads/tunnels: kept previous ({e})")
    try:
        out["canals"] = canals(sys.argv[2]); fresh.append("canals")
    except (OSError, ValueError) as e:
        print(f"canals: kept previous ({e})")
    if not fresh:
        sys.exit("both BMA sources failed - bma.json left as it was")
    out["fetched"] = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%dT%H:%M")
    json.dump(out, open("bma.json", "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
    print(f"bma.json: fresh {', '.join(fresh)} - {len(out.get('roads', []))} roads, "
          f"{len(out.get('tunnels', []))} tunnels, {len(out.get('canals', []))} canals, at {out['fetched']}")


if __name__ == "__main__":
    main()
