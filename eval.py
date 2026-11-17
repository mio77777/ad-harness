"""評価: 同じ商品セットで baseline（1発生成）と harness（自己採点→再生成）を比較。
最終スコアは両方とも同じ審査員（temperature=0）で付け直すので公平。

python eval.py               # 全件
python eval.py --limit 3     # 3件だけ（時間がないとき）
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from agent import generate_ads, judge_ads
from harness import PASS_SCORE, run_baseline, run_harness
from rules import check_ad


def _score(p, mode, res):
    judged, _ = judge_ads(p, res["ads"])
    rows = []
    for ad, j in zip(res["ads"], judged):
        v = check_ad(ad, p, res["ads"])
        rows.append({"ad": ad, "score": j["score"], "violations": v,
                     "pass": (not v) and j["score"] >= PASS_SCORE})
    return {"product": p["name"], "mode": mode, "rows": rows,
            "calls": res["calls"], "tokens": res["tokens"], "trace": res["trace"]}


def evaluate(p):
    """同じ初期案から baseline と harness を走らせる（初期案の当たり外れを比較から除く）"""
    try:
        initial = generate_ads(p)
    except Exception as e:
        err = str(e)
        return [{"product": p["name"], "mode": m, "error": err} for m in ("baseline", "harness")]
    out = []
    for mode, run in (("baseline", run_baseline), ("harness", run_harness)):
        try:
            out.append(_score(p, mode, run(p, initial=initial)))
        except Exception as e:
            out.append({"product": p["name"], "mode": mode, "error": str(e)})
    return out


def summarize(results):
    ok = [r for r in results if "rows" in r]
    ads = [row for r in ok for row in r["rows"]]
    n = max(len(ads), 1)
    return {
        "products": len(ok), "errors": len(results) - len(ok), "ads": len(ads),
        "avg_score": round(sum(a["score"] for a in ads) / n, 2),
        "violation_rate": round(sum(1 for a in ads if a["violations"]) / n * 100, 1),
        "pass_rate": round(sum(1 for a in ads if a["pass"]) / n * 100, 1),
        "calls_per_product": round(sum(r["calls"] for r in ok) / max(len(ok), 1), 1),
        "tokens_per_product": round(sum(r["tokens"] for r in ok) / max(len(ok), 1)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()
    products = json.load(open("products.json", encoding="utf-8"))
    if a.limit:
        products = products[:a.limit]

    print(f"running baseline + harness on {len(products)} products (shared initial ads)...", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        pairs = list(ex.map(evaluate, products))
    out = {"baseline": [b for b, _ in pairs], "harness": [h for _, h in pairs]}

    sb, sh = summarize(out["baseline"]), summarize(out["harness"])
    lines = ["| 指標 | baseline（1発生成） | harness（自己採点＋再生成） |", "|---|---|---|"]
    for key, label in [("avg_score", "平均スコア（10点満点）"), ("pass_rate", "出稿OK率 %"),
                       ("violation_rate", "ルール違反率 %"), ("calls_per_product", "LLM呼び出し/商品"),
                       ("tokens_per_product", "tokens/商品"), ("errors", "エラー件数")]:
        lines.append(f"| {label} | {sb[key]} | {sh[key]} |")
    table = "\n".join(lines)

    # 改善例（デモ用）: harnessで違反→解消した案を1つ拾う
    example = ""
    for b, h in zip(out["baseline"], out["harness"]):
        if "rows" in h and h.get("trace") and h["trace"][0]["weak"]:
            example = f"\n\n### トレース例: {h['product']}\n" + "\n".join(
                f"- Round {t['round']}: scores={t['scores']} 作り直し対象={[i+1 for i in t['weak']]}"
                for t in h["trace"] if "round" in t)
            break

    md = f"# Ad Creative Harness Eval\n\n商品 {len(products)}件 × 5案\n\n{table}{example}\n"
    open("results.md", "w", encoding="utf-8").write(md)
    json.dump(out, open("results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n" + md)
    print("saved: results.md, results.json")


if __name__ == "__main__":
    main()
