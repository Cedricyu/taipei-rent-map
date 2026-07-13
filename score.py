# -*- coding: utf-8 -*-
"""機器學習評分：行情價模型 + 子分數 → 寫回 listings.json

流程：build_data.py 產出 listings.json 後執行本腳本。
  1. 特徵工程（坪數/類型/行政區/樓層/屋齡/電梯/捷運距離/YouBike 密度/標籤）
  2. HistGradientBoosting 對 log(租金) 訓練行情模型（5-fold 交叉驗證的 out-of-fold 預測）
  3. CP 值 = 實際租金相對預估行情的殘差百分位（比行情便宜 → 高分）
  4. 子分數：s_value(CP值) / s_mrt(捷運) / s_bike(YouBike) / s_cond(屋況)
"""
import json
import sys

import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold

R_EARTH = 6371000.0


def haversine_matrix(lat1, lng1, lat2, lng2):
    """lat1/lng1: (n,1), lat2/lng2: (m,) → (n, m) 距離(公尺)"""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lng2) - np.radians(lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


def tri(v, true_val="可", false_val="不可"):
    """True/False/None → 1/0/NaN"""
    return 1.0 if v is True else (0.0 if v is False else np.nan)


def main():
    with open("listings.json", encoding="utf-8") as f:
        listings = json.load(f)
    with open("overlays.json", encoding="utf-8") as f:
        overlays = json.load(f)

    n = len(listings)
    lat = np.array([l["lat"] for l in listings])[:, None]
    lng = np.array([l["lng"] for l in listings])[:, None]

    # --- 捷運最近距離（公尺）---
    mrt_lat = np.array([s["lat"] for s in overlays.get("mrt", [])])
    mrt_lng = np.array([s["lng"] for s in overlays.get("mrt", [])])
    mrt_m = haversine_matrix(lat, lng, mrt_lat, mrt_lng).min(axis=1) if len(mrt_lat) else np.full(n, np.nan)

    # --- 500m 內 YouBike 站數（分塊避免大矩陣）---
    yb_lat = np.array([s["lat"] for s in overlays.get("youbike", [])])
    yb_lng = np.array([s["lng"] for s in overlays.get("youbike", [])])
    bike_n = np.zeros(n, dtype=int)
    if len(yb_lat):
        for i in range(0, n, 2000):
            d = haversine_matrix(lat[i:i + 2000], lng[i:i + 2000], yb_lat, yb_lng)
            bike_n[i:i + 2000] = (d <= 500).sum(axis=1)

    # --- 特徵矩陣 ---
    cats = sorted({l.get("kind") or "?" for l in listings})
    dists = sorted({l["district"] for l in listings})
    builds = sorted({l.get("building") or "?" for l in listings})
    cat_idx = {c: i for i, c in enumerate(cats)}
    dist_idx = {d: i for i, d in enumerate(dists)}
    build_idx = {b: i for i, b in enumerate(builds)}

    def feat(l, mrt_d, bike_c):
        tags = l.get("tags") or []
        return [
            l.get("area") or np.nan,
            l.get("rooms") if l.get("rooms") is not None else np.nan,
            l.get("halls") if l.get("halls") is not None else np.nan,
            l.get("floor_now") if l.get("floor_now") is not None else np.nan,
            l.get("floor_total") if l.get("floor_total") is not None else np.nan,
            l.get("age") if l.get("age") is not None else np.nan,
            tri(l.get("elevator")),
            tri(l.get("pet")),
            tri(l.get("cook")),
            tri(l.get("has_parking")),
            mrt_d,
            bike_c,
            1.0 if "屋主直租" in tags else 0.0,
            1.0 if "拎包入住" in tags else 0.0,
            1.0 if "近商圈" in tags else 0.0,
            1.0 if l.get("geo_approx") else 0.0,   # 座標不準的物件，位置特徵權重自然降低
            cat_idx[l.get("kind") or "?"],
            dist_idx[l["district"]],
            build_idx[l.get("building") or "?"],
        ]

    X = np.array([feat(l, mrt_m[i], bike_n[i]) for i, l in enumerate(listings)])
    price = np.array([l["price"] or 0 for l in listings], dtype=float)

    ok = price > 1000  # 排除異常價
    y = np.log(np.clip(price, 1, None))
    cat_features = [16, 17, 18]

    # --- out-of-fold 預測（避免模型看過自己 → 殘差失真）---
    pred = np.full(n, np.nan)
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    idx_ok = np.where(ok)[0]
    for tr, te in kf.split(idx_ok):
        tr_i, te_i = idx_ok[tr], idx_ok[te]
        model = HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.06, max_leaf_nodes=63,
            categorical_features=cat_features, random_state=42)
        model.fit(X[tr_i], y[tr_i])
        pred[te_i] = model.predict(X[te_i])

    resid = y - pred                     # >0 = 比行情貴, <0 = 比行情便宜
    r = resid[idx_ok]
    ss_res = float((r ** 2).sum())
    ss_tot = float(((y[idx_ok] - y[idx_ok].mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot
    mae_pct = float(np.mean(np.abs(np.expm1(resid[idx_ok] - 0))))  # 近似百分比誤差
    print(f"行情模型 5-fold R²(log) = {r2:.3f}, 中位殘差 = {np.median(np.abs(r)):.3f} (log)", flush=True)

    # 便宜到不合理（低於行情一半）多半是床位/共居/純登記等「單價非整戶」物件 → 標異常、不列入 CP 排名
    anomaly = np.zeros(n, dtype=bool)
    anomaly[idx_ok] = resid[idx_ok] < np.log(0.5)
    rank_ok = np.where(ok & ~anomaly)[0]

    # 殘差 → CP 值百分位（便宜端高分）
    order = np.argsort(np.argsort(resid[rank_ok]))
    pct = order / max(len(rank_ok) - 1, 1)
    s_value = np.full(n, 50.0)
    s_value[rank_ok] = np.round(100 * (1 - pct), 1)
    print(f"標記價格異常 {int(anomaly.sum())} 筆（低於行情一半）", flush=True)

    # --- 其他子分數 ---
    s_mrt = np.clip((1500 - mrt_m) / 1200, 0, 1) * 100 if len(mrt_lat) else np.full(n, 50.0)
    s_bike = np.clip(bike_n, 0, 5) / 5 * 100

    s_cond = np.full(n, 50.0)
    for i, l in enumerate(listings):
        parts = []
        if l.get("age") is not None:
            parts.append(max(0.0, min(1.0, (40 - l["age"]) / 40)) * 100)
        if l.get("elevator") is not None:
            parts.append(100.0 if l["elevator"] else 30.0)
        if parts:
            s_cond[i] = sum(parts) / len(parts)

    # --- 寫回 ---
    for i, l in enumerate(listings):
        l["mrt_m"] = int(round(mrt_m[i])) if np.isfinite(mrt_m[i]) else None
        l["bike_n"] = int(bike_n[i])
        l["pred_price"] = int(round(np.exp(pred[i]))) if np.isfinite(pred[i]) else None
        l["s_value"] = float(s_value[i])
        l["s_mrt"] = round(float(s_mrt[i]), 1)
        l["s_bike"] = round(float(s_bike[i]), 1)
        l["s_cond"] = round(float(s_cond[i]), 1)
        l["anomaly"] = bool(anomaly[i])

    with open("listings.json", "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False)

    cheap = sorted((l for l in listings if l.get("pred_price") and not l["anomaly"]),
                   key=lambda l: l["price"] / l["pred_price"])[:5]
    print(f"已寫回 {n} 筆評分 → listings.json", flush=True)
    print("最划算前 5 名（實際/行情）:", flush=True)
    for l in cheap:
        print(f"  {l['district']} {l['title'][:24]} {l['price']}/{l['pred_price']}", flush=True)


if __name__ == "__main__":
    main()
