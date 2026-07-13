# -*- coding: utf-8 -*-
"""抓取 591 每筆物件詳細頁：型態/寵物/開伙/屋齡/電梯/車位/租期"""
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

CACHE_FILE = "enrich_cache.json"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

KINDS = {"電梯大樓", "公寓", "透天厝", "別墅", "住宅大樓", "華廈", "平房", "其他"}


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {}

    # 房屋資訊區：div.item > span.label / span.value（屋齡、電梯...）
    for item in soup.select("div.item"):
        lab = item.select_one("span.label")
        val = item.select_one("span.value")
        if not lab or not val:
            continue
        key = lab.get_text(strip=True)
        if key in ("屋齡", "電梯"):
            out[key] = val.get_text(" ", strip=True)

    # 租住說明區：desc-label / desc-value（養寵物、開伙、最短租期）
    for item in soup.select(".desc-item"):
        lab = item.select_one(".desc-label")
        val = item.select_one(".desc-value")
        if not lab or not val:
            continue
        key = lab.get_text(strip=True)
        v = val.get_text(" ", strip=True)
        if key == "養寵物":
            out["寵物"] = "不可" if "不可" in v else "可"
        elif key == "開伙":
            out["開伙"] = "不可" if "不可" in v else "可"
        elif key == "最短租期":
            out["租期"] = v

    # 型態（電梯大樓/公寓/透天厝...）：頁首資訊列的獨立 span
    for sp in soup.select("span"):
        t = sp.get_text(strip=True)
        if t in KINDS:
            out["型態"] = t
            break

    # 設備清單：dl 沒有 del class 表示有提供
    for dl in soup.select(".facility dl"):
        name = dl.get_text(strip=True)
        if name in ("車位", "電梯"):
            has = "del" not in (dl.get("class") or [])
            key = "車位" if name == "車位" else "電梯"
            # label/value 的電梯優先，設備清單當備援
            if key not in out:
                out[key] = "有" if has else "無"
    return out


def fetch_one(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return parse_detail(r.text)
            if r.status_code in (404, 410):
                return {}
        except requests.RequestException:
            pass
        time.sleep(2)
    return None  # 暫時失敗，下次再試


def main():
    with open("listings_raw.json", encoding="utf-8") as f:
        listings = json.load(f)

    cache = load_cache()
    todo = [l for l in listings if l["house_id"] not in cache and l.get("href")]
    print(f"共 {len(listings)} 筆, 需抓詳細頁 {len(todo)} 筆", flush=True)

    for i, l in enumerate(todo):
        res = fetch_one(l["href"])
        if res is not None:
            cache[l["house_id"]] = res
        if (i + 1) % 50 == 0:
            save_cache(cache)
            print(f"  進度 {i+1}/{len(todo)}", flush=True)
        time.sleep(0.4)

    save_cache(cache)
    print(f"完成，快取共 {len(cache)} 筆 → {CACHE_FILE}", flush=True)


if __name__ == "__main__":
    main()
