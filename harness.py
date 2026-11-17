"""ハーネス本体: 生成 → (ルール検査 + LLM採点) → 弱い案だけ再生成、を繰り返す。

python harness.py            # products.json の1件目でトレースを表示
python harness.py 3          # 4件目
"""
import json
import sys

from agent import generate_ads, judge_ads, regenerate_ad
from rules import check_ad

PASS_SCORE = 7.0
MAX_ROUNDS = 2
REWRITE_ATTEMPTS = 2  # 作り直し案がルール違反なら、違反内容を渡してもう1回だけやり直す


def run_baseline(p, initial=None):
    """initial=(ads, tokens) を渡すと、harness と同じ初期案を使う（公平な比較用）"""
    ads, tok = initial if initial else generate_ads(p)
    return {"ads": [dict(a) for a in ads], "calls": 1, "tokens": tok, "trace": []}


def _rewrite(p, ads, i, feedback):
    """案iを作り直す。作り直し案もルール検査し、違反があれば違反内容を足して再挑戦。
    最終的に違反が一番少ない案を採用（同数なら新しい方）。戻り値: (採用案, 違反, calls, tokens, errors)"""
    calls = tok = 0
    errors = []
    best, best_v = ads[i], check_ad(ads[i], p, ads)
    fb = list(feedback)
    for _ in range(REWRITE_ATTEMPTS):
        others = [a.get("headline", "") for k, a in enumerate(ads) if k != i]
        try:
            new, t = regenerate_ad(p, ads[i], fb, others)
        except Exception as e:  # 再生成失敗時はそれまでの最良案を残す
            errors.append(str(e))
            continue
        calls += 1; tok += t
        v = check_ad(new, p, ads[:i] + [new] + ads[i + 1:])
        if len(v) <= len(best_v):
            best, best_v = new, v
        if not v:
            break
        fb = list(feedback) + [f"（作り直し案のルール違反）{x}" for x in v]
    return best, best_v, calls, tok, errors


def run_harness(p, max_rounds=MAX_ROUNDS, pass_score=PASS_SCORE, verbose=False, initial=None):
    ads, tok = initial if initial else generate_ads(p)
    ads = [dict(a) for a in ads]  # baseline と初期案を共有しても壊さないようコピー
    calls, trace = 1, []
    for rnd in range(1, max_rounds + 1):
        judged, t = judge_ads(p, ads)
        calls += 1; tok += t
        weak = []
        for i, (ad, j) in enumerate(zip(ads, judged)):
            viol = check_ad(ad, p, ads)
            if viol or j["score"] < pass_score:
                weak.append((i, viol + ([f"審査員コメント({j['score']}点): {j['comment']}"] if j["score"] < pass_score else [])))
        trace.append({"round": rnd, "scores": [j["score"] for j in judged], "weak": [i for i, _ in weak]})
        if verbose:
            _print_round(rnd, ads, judged, weak)
        if not weak:
            break
        for i, fb in weak:
            old = ads[i].get("headline")
            new, v, c, t, errs = _rewrite(p, ads, i, fb)
            calls += c; tok += t
            if errs:
                trace[-1].setdefault("errors", []).extend(errs)
            if verbose:
                kept = "（元の案を維持）" if new is ads[i] else ""
                print(f"   ↻ 案{i+1} 作り直し: {old}  →  {new.get('headline')}{kept}"
                      + (f"  ⚠ 残る違反: {'; '.join(v)}" if v else ""))
            ads[i] = new
    # 最終ラウンドの作り直し案は採点されないので、ルール違反だけは記録しておく
    trace.append({"final_violations": [check_ad(a, p, ads) for a in ads]})
    return {"ads": ads, "calls": calls, "tokens": tok, "trace": trace}


def _print_round(rnd, ads, judged, weak):
    weak_ids = {i for i, _ in weak}
    print(f"\n=== Round {rnd} ===")
    for i, (ad, j) in enumerate(zip(ads, judged)):
        mark = "✗" if i in weak_ids else "✓"
        print(f" {mark} 案{i+1} [{j['score']:>4}] {ad.get('headline')}")
    for i, fb in weak:
        for f in fb:
            print(f"     - 案{i+1}: {f}")


if __name__ == "__main__":
    products = json.load(open("products.json", encoding="utf-8"))
    p = products[int(sys.argv[1]) if len(sys.argv) > 1 else 0]
    print(f"商品: {p['name']}")
    res = run_harness(p, verbose=True)
    print("\n=== 最終案 ===")
    for i, ad in enumerate(res["ads"]):
        print(f"{i+1}. {ad.get('headline')}\n   {ad.get('copy')}\n   🎨 {ad.get('image_prompt')}")
    left = [i + 1 for i, v in enumerate(res["trace"][-1]["final_violations"]) if v]
    if left:
        print(f"\n⚠ ルール違反が残っている案: {left}")
    print(f"\nLLM呼び出し {res['calls']}回 / tokens {res['tokens']}")
