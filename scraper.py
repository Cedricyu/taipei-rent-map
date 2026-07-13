# -*- coding: utf-8 -*-
"""爬取 591 租屋列表：台北市全區 + 新北市中和/永和"""
import requests
from bs4 import BeautifulSoup
import re
import json
import math
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.5',
    'Connection': 'close',
}

# (region, section, 區名, 城市名)
DISTRICTS = [
    (1, 1, "中正區", "台北市"),
    (1, 2, "大同區", "台北市"),
    (1, 3, "中山區", "台北市"),
    (1, 4, "松山區", "台北市"),
    (1, 5, "大安區", "台北市"),
    (1, 6, "萬華區", "台北市"),
    (1, 7, "信義區", "台北市"),
    (1, 8, "士林區", "台北市"),
    (1, 9, "北投區", "台北市"),
    (1, 10, "內湖區", "台北市"),
    (1, 11, "南港區", "台北市"),
    (1, 12, "文山區", "台北市"),
    (3, 37, "永和區", "新北市"),
    (3, 38, "中和區", "新北市"),
]

TARGET_DISTRICTS = {d[2] for d in DISTRICTS}
CITY_OF = {d[2]: d[3] for d in DISTRICTS}
PER_PAGE = 30


def txt(el):
    return el.get_text(" ", strip=True) if el else ""


def parse_items(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for it in soup.select("div.item[data-id]"):
        house_id = it.get("data-id", "")

        a = it.select_one("a[href]")
        href = a.get("href", "") if a else ""

        title = txt(it.select_one(".item-info-title"))

        cat = None            # 類別：整層住家/獨立套房/分租套房/雅房/車位...
        layout = None
        rooms = halls = None
        area = None
        floor_now = floor_total = None
        district = None
        address = None
        community = None
        update_date = None

        for line_el in it.select(".item-info-txt"):
            line = txt(line_el)
            if "坪" in line and cat is None:
                # 例："獨立套房 樓中樓 8.2坪 12F/13F"、"整層住家 2房1廳 27坪 8F/13F"
                cat = line.split()[0] if line.split() else None
                m = re.search(r"(\d+)房(\d+)廳(?:(\d+)衛)?", line)
                if m:
                    layout = m.group(0)
                    rooms, halls = int(m.group(1)), int(m.group(2))
                m = re.search(r"(\d+(?:\.\d+)?)\s*坪", line)
                if m:
                    area = float(m.group(1))
                m = re.search(r"(\S+)\s*/\s*(\d+)F", line)
                if m:
                    floor_total = int(m.group(2))
                    m2 = re.match(r"(\d+)F", m.group(1))
                    floor_now = int(m2.group(1)) if m2 else None
            elif "區-" in line and district is None:
                # 例："信義美學大樓 大安區-信義路二段"
                m = re.search(r"([一-鿿]{1,3}區)-(.+)$", line)
                if m:
                    district = m.group(1)
                    address = m.group(2).strip()
                    community = line[:m.start()].strip() or None
            elif "更新" in line:
                m = re.search(r"(\S+更新)", line)
                if m:
                    update_date = m.group(1)

        price = None
        m = re.search(r"([\d,]+)", txt(it.select_one(".item-info-price")))
        if m:
            price = int(m.group(1).replace(",", ""))

        tags = [txt(x) for x in it.select(".item-info-tag .tag")]
        tags = [t for t in tags if t]

        img_el = it.select_one("img.common-img")
        img_url = (img_el.get("data-src") or img_el.get("src", "")) if img_el else ""
        if img_url.startswith("data:"):
            img_url = ""

        rows.append({
            "house_id": house_id,
            "title": title,
            "address": address,
            "community": community,
            "district": district,
            "cat": cat,
            "price": price,
            "area": area,
            "floor_now": floor_now,
            "floor_total": floor_total,
            "layout": layout,
            "rooms": rooms,
            "halls": halls,
            "baths": None,
            "update_date": update_date,
            "tags": tags,
            "img_url": img_url,
            "href": href if href.startswith("http") else f"https://rent.591.com.tw/{house_id}",
        })
    return rows


def get_page(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code in (200, 202):
                return r.content
        except requests.RequestException as e:
            print(f"  retry {i+1}: {e}", flush=True)
        time.sleep(2)
    return None


def total_count(html):
    soup = BeautifulSoup(html, "html.parser")
    m = re.search(r"找到\s*([\d,]+)\s*間", soup.get_text())
    return int(m.group(1).replace(",", "")) if m else None


def scrape_district(region, section, district, city):
    base = f"https://rent.591.com.tw/list?region={region}&section={section}"
    html = get_page(base)
    if html is None:
        print(f"[{district}] 第一頁抓取失敗", flush=True)
        return []
    total = total_count(html)
    rows = parse_items(html)
    pages = math.ceil(total / PER_PAGE) if total else 1
    print(f"[{district}] 共 {total} 筆, {pages} 頁", flush=True)

    seen = {r["house_id"] for r in rows}
    for p in range(2, pages + 1):
        time.sleep(0.8)
        html = get_page(f"{base}&page={p}")
        if html is None:
            print(f"[{district}] 第 {p} 頁失敗, 略過", flush=True)
            continue
        page_rows = parse_items(html)
        new = [r for r in page_rows if r["house_id"] not in seen]
        if not page_rows:
            print(f"[{district}] 第 {p} 頁無資料, 提前結束", flush=True)
            break
        seen.update(r["house_id"] for r in new)
        rows.extend(new)
        if p % 10 == 0:
            print(f"  [{district}] 進度 {p}/{pages} 頁, 累計 {len(rows)} 筆", flush=True)

    print(f"[{district}] 抓到 {len(rows)} 筆", flush=True)
    return rows


def main():
    all_rows = []
    for region, section, district, city in DISTRICTS:
        all_rows.extend(scrape_district(region, section, district, city))
        time.sleep(1.5)

    # 去重（精選物件會跨頁/跨區重複出現）+ 只留目標區域
    seen = set()
    unique = []
    for r in all_rows:
        if not r["house_id"] or r["house_id"] in seen:
            continue
        if r["district"] not in TARGET_DISTRICTS:
            continue
        seen.add(r["house_id"])
        r["city"] = CITY_OF[r["district"]]
        # 給地理編碼用的完整地址
        if r["address"]:
            r["address"] = f'{r["city"]}{r["district"]}{r["address"]}'
        unique.append(r)

    with open("listings_raw.json", "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=1)
    print(f"總共 {len(unique)} 筆，已存 listings_raw.json", flush=True)


if __name__ == "__main__":
    main()
