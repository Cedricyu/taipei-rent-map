# -*- coding: utf-8 -*-
"""抓取捷運出入口 + YouBike 站點（台北市與新北市）"""
import json
import requests


def fetch_mrt():
    url = "https://data.taipei/api/v1/dataset/307a7f61-e302-4108-a817-877ccbfca7c1"
    out = []
    offset = 0
    while True:
        r = requests.get(url, params={"scope": "resourceAquire", "limit": 1000, "offset": offset}, timeout=30)
        r.raise_for_status()
        results = r.json()["result"]["results"]
        if not results:
            break
        out.extend(results)
        offset += len(results)
        if len(results) < 1000:
            break
    stations = []
    for row in out:
        try:
            lat = float(row.get("緯度") or row.get("lat"))
            lng = float(row.get("經度") or row.get("lon") or row.get("lng"))
            name = row.get("出入口名稱") or row.get("name") or ""
        except (TypeError, ValueError):
            continue
        stations.append({"name": name, "lat": lat, "lng": lng})
    print(f"捷運出入口: {len(stations)}")
    return stations


def fetch_youbike():
    pts = []
    # 台北市
    try:
        r = requests.get("https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json", timeout=30)
        for s in r.json():
            pts.append({"name": s["sna"].replace("YouBike2.0_", ""), "lat": float(s["latitude"]), "lng": float(s["longitude"])})
        print(f"台北 YouBike: {len(pts)}")
    except Exception as e:
        print(f"台北 YouBike 失敗: {e}")
    # 新北市（只留中永和）
    try:
        n = 0
        for page in range(20):
            r = requests.get(
                "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json",
                params={"page": page, "size": 1000}, timeout=30)
            rows = r.json()
            if not rows:
                break
            for s in rows:
                if s.get("sarea") in ("中和區", "永和區"):
                    pts.append({"name": s["sna"].replace("YouBike2.0_", ""), "lat": float(s["lat"]), "lng": float(s["lng"])})
                    n += 1
            if len(rows) < 1000:
                break
        print(f"中永和 YouBike: {n}")
    except Exception as e:
        print(f"新北 YouBike 失敗: {e}")
    return pts


if __name__ == "__main__":
    data = {"mrt": fetch_mrt(), "youbike": fetch_youbike()}
    with open("overlays.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("→ overlays.json")
