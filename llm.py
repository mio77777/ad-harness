"""OpenAI互換 /chat/completions を叩く最小クライアント（依存なし）。
ai& Inference など OpenAI 互換APIなら Base URL を変えるだけで動く。
MOCK=1 のときはAPIを呼ばず、決定的な疑似応答を返す（オフライン確認用）。
"""
import json
import os
import random
import re
import time
import urllib.request
import zlib

BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
GEN_MODEL = os.environ.get("GEN_MODEL", "")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "") or GEN_MODEL
MOCK = os.environ.get("MOCK") == "1"


def chat(model, system, user, temperature=0.8, mock_ctx=None, retries=3):
    """戻り値: (text, total_tokens)"""
    if MOCK:
        return _mock(mock_ctx), 0
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            text = data["choices"][0]["message"]["content"] or ""
            return text, (data.get("usage") or {}).get("total_tokens", 0)
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"LLM call failed: {last}")


def extract_json(text):
    """推論モデルの<think>やコードフェンスを除去してJSONを取り出す"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


# ---------------- MOCK（オフライン動作確認用） ----------------
def _mock(ctx):
    kind, p = ctx["kind"], ctx["product"]
    # hash() は実行ごとに変わる（PYTHONHASHSEED）ので、crc32 で安定したシードを作る
    key = json.dumps([p["name"], kind, ctx.get("ad", {}), ctx.get("feedback", [])], ensure_ascii=False)
    rnd = random.Random(zlib.crc32(key.encode()))
    feat = p["features"]
    if kind == "generate":
        ads = []
        for i in range(ctx["n"]):
            f = rnd.choice(feat)
            r = rnd.random()
            if r < 0.2:      # 誇大表現
                h, c = f"最高の{p['name']}", f"{f}で毎日が絶対に変わる。今すぐ{p['name']}を試してみてください、きっと驚きます。"
            elif r < 0.4:    # 見出しが長すぎ
                h = f"{p['target']}のための、まったく新しい{p['name']}の体験がここに"
                c = f"{f}を実現した{p['name']}。忙しい毎日にちょうどいい相棒になります。"
            elif r < 0.55:   # 特徴に触れていない
                h, c = f"新しい毎日を{i}", "あなたの毎日を、もっと楽しく。新しい選択肢をぜひ一度体験してください。"
            else:
                h = f"{f}を、毎日に"
                c = f"{p['name']}は{f}を実現。{p['target']}の毎日を、静かに支えます。まずは公式サイトで。"
            ads.append({"headline": h[:40], "copy": c,
                        "image_prompt": f"product photo of {p['name_en']} on a clean desk, soft natural light, minimal style"})
        return json.dumps({"ads": ads}, ensure_ascii=False)
    if kind == "regenerate":
        f = rnd.choice(feat)
        return json.dumps({"headline": f"{f}で、軽やかに", "copy":
                           f"{p['name']}は{f}を実現。{p['target']}の毎日を、静かに支えます。詳しくは公式サイトへ。",
                           "image_prompt": f"lifestyle photo of {p['name_en']} used by a young professional, warm light, 35mm"},
                          ensure_ascii=False)
    if kind == "judge":
        from rules import check_ad
        out = []
        for ad in ctx["ads"]:
            v = check_ad(ad, p, ctx["ads"])
            s = max(2, 8 - 2 * len(v) + rnd.choice([-1, 0, 0, 1]))
            out.append({"specificity": s, "appeal": s, "fit": s, "comment": "具体性が弱い" if s < 7 else "良い"})
        return json.dumps({"scores": out}, ensure_ascii=False)
    raise ValueError(kind)
