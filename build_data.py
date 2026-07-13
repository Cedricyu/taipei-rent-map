# -*- coding: utf-8 -*-
"""合併 listings_raw + geocache + enrich_cache → listings.json（排除車位出租）"""
import json
import math
import os
import random
import re

from geocode import DISTRICT_CENTER


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def main():
    listings = load("listings_raw.json", [])
    geocache = load("geocache.json", {})
    enrich = load("enrich_cache.json", {})

    out = []
    n_parking = 0
    for l in listings:
        e = enrich.get(l["house_id"], {})
        cat = l.get("cat") or ""
        tags = l.get("tags") or []

        # 排除車位出租（類別標車位，或標題寫車位出租但沒有房間資訊）
        title = l.get("title") or ""
        if "車位" in cat or ("車位出租" in title and l.get("rooms") is None):
            n_parking += 1
            continue

        # kind = 591 的類別（整層住家/獨立套房/分租套房/雅房），building = 建物型態
        l["kind"] = cat or None
        l["building"] = e.get("型態")

        # 詳細頁資料優先，列表 tag 當備援（tag 只有正面標示，沒有≠不可）
        pet = e.get("寵物")
        l["pet"] = True if pet == "可" else (False if pet == "不可" else
                   (True if "可養寵物" in tags else None))
        cook = e.get("開伙")
        l["cook"] = True if cook == "可" else (False if cook == "不可" else
                    (True if "可開伙" in tags else None))
        elev = e.get("電梯")
        l["elevator"] = True if elev == "有" else (False if elev == "無" else
                        (True if ("有電梯" in tags or e.get("型態") == "電梯大樓") else None))
        park = e.get("車位")
        l["has_parking"] = True if park == "有" else (False if park == "無" else None)

        age = None
        m = re.search(r"(\d+(?:\.\d+)?)", e.get("屋齡", "") or "")
        if m:
            age = float(m.group(1))
        l["age"] = age

        out.append(l)

    # 座標
    ok = miss = 0
    rng = random.Random(42)
    for l in out:
        coords = geocache.get(l.get("address") or "")
        if coords:
            l["lat"], l["lng"] = coords[0], coords[1]
            l["geo_approx"] = False
            ok += 1
        else:
            c = DISTRICT_CENTER[l["district"]]
            l["lat"] = c[0] + rng.uniform(-0.004, 0.004)
            l["lng"] = c[1] + rng.uniform(-0.004, 0.004)
            l["geo_approx"] = True
            miss += 1

    # 同座標微幅散開
    from collections import defaultdict
    groups = defaultdict(list)
    for l in out:
        groups[(round(l["lat"], 6), round(l["lng"], 6))].append(l)
    for coords, group in groups.items():
        if len(group) > 1:
            for j, l in enumerate(group[1:], start=1):
                ang = rng.uniform(0, 2 * math.pi)
                r = 0.0004 + 0.0003 * (j % 5)
                l["lat"] += r * math.sin(ang)
                l["lng"] += r * math.cos(ang)

    with open("listings.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    n_pet = sum(1 for l in out if l["pet"] is True)
    n_enriched = sum(1 for l in out if l["house_id"] in enrich)
    print(f"輸出 {len(out)} 筆（排除車位 {n_parking} 筆，詳細頁已補 {n_enriched} 筆）", flush=True)
    print(f"座標: 精確 {ok} / 區中心 {miss}；可養寵物 {n_pet} 筆", flush=True)


if __name__ == "__main__":
    main()
