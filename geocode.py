# -*- coding: utf-8 -*-
"""將租屋地址轉經緯度：Nominatim + 本地快取，失敗退回區中心"""
import json
import re
import time
import os
import random
import requests

CACHE_FILE = "geocache.json"

# 各區中心點（查不到地址時的退路）
DISTRICT_CENTER = {
    "中正區": (25.0324, 121.5199),
    "大同區": (25.0627, 121.5113),
    "中山區": (25.0685, 121.5266),
    "松山區": (25.0500, 121.5574),
    "大安區": (25.0264, 121.5435),
    "萬華區": (25.0286, 121.4980),
    "信義區": (25.0308, 121.5716),
    "士林區": (25.0922, 121.5245),
    "北投區": (25.1321, 121.4987),
    "內湖區": (25.0692, 121.5904),
    "南港區": (25.0546, 121.6067),
    "文山區": (24.9880, 121.5700),
    "永和區": (25.0074, 121.5157),
    "中和區": (24.9994, 121.4990),
}

HEADERS = {"User-Agent": "rent-analysis-taipei/1.0 (personal study project)"}


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def nominatim_query(addr):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": addr, "format": "json", "limit": 1, "countrycodes": "tw"},
            headers=HEADERS, timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                # 大台北範圍檢查
                if 24.8 <= lat <= 25.3 and 121.3 <= lon <= 121.8:
                    return lat, lon
    except requests.RequestException as e:
        print(f"  nominatim error: {e}", flush=True)
    return None


def simplify(addr):
    """完整地址 → 巷 → 路段 逐步簡化的候選清單"""
    cands = [addr]
    a = re.sub(r"\d+(?:-\d+)?號.*$", "", addr)      # 去掉門牌號之後
    if a != cands[-1] and len(a) > 6:
        cands.append(a)
    a2 = re.sub(r"\d+弄$", "", a)
    if a2 != cands[-1] and len(a2) > 6:
        cands.append(a2)
    a3 = re.sub(r"\d+巷$", "", a2)                   # 去掉巷
    if a3 != cands[-1] and len(a3) > 6:
        cands.append(a3)
    return cands


def nominatim(addr):
    for i, cand in enumerate(simplify(addr)):
        res = nominatim_query(cand)
        if res:
            return res
        time.sleep(1.05)
    return None


def main():
    with open("listings_raw.json", encoding="utf-8") as f:
        listings = json.load(f)

    cache = load_cache()
    # 唯一地址（同一條街的物件共用座標）
    addrs = sorted({l["address"] for l in listings if l.get("address")})
    todo = [a for a in addrs if a not in cache]
    print(f"{len(addrs)} 個唯一地址, 需查詢 {len(todo)} 個", flush=True)

    for i, addr in enumerate(todo):
        res = nominatim(addr)
        cache[addr] = list(res) if res else None
        if (i + 1) % 20 == 0:
            save_cache(cache)
            print(f"  進度 {i+1}/{len(todo)}", flush=True)
        time.sleep(1.05)
    save_cache(cache)

    ok = miss = 0
    rng = random.Random(42)
    for l in listings:
        addr = l.get("address")
        coords = cache.get(addr) if addr else None
        if coords:
            l["lat"], l["lng"] = coords[0], coords[1]
            l["geo_approx"] = False
            ok += 1
        else:
            c = DISTRICT_CENTER[l["district"]]
            # 加一點抖動避免全部疊在同一點
            l["lat"] = c[0] + rng.uniform(-0.004, 0.004)
            l["lng"] = c[1] + rng.uniform(-0.004, 0.004)
            l["geo_approx"] = True
            miss += 1

    # 同一街道多筆 → 微幅散開，避免 marker 完全重疊
    from collections import defaultdict
    groups = defaultdict(list)
    for l in listings:
        groups[(round(l["lat"], 6), round(l["lng"], 6))].append(l)
    for coords, group in groups.items():
        if len(group) > 1:
            for j, l in enumerate(group[1:], start=1):
                ang = rng.uniform(0, 6.283)
                r = 0.0004 + 0.0003 * (j % 5)
                import math
                l["lat"] += r * math.sin(ang)
                l["lng"] += r * math.cos(ang)

    with open("listings.json", "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=1)
    print(f"完成: 精確 {ok} 筆, 退回區中心 {miss} 筆 → listings.json", flush=True)


if __name__ == "__main__":
    main()
