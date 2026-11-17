"""基本エージェント: 生成・再生成・採点"""
import json

import llm

GEN_SYSTEM = """あなたは日本語の広告コピーライターです。
出力はJSONのみ。形式: {"ads":[{"headline":"...","copy":"...","image_prompt":"..."}]}
- headline: 日本語の見出し
- copy: 日本語の本文コピー
- image_prompt: 画像生成用の英語プロンプト"""

REGEN_SYSTEM = """あなたは日本語の広告コピーライターです。指摘を全て直した改善案を1つ作ってください。
出力はJSONのみ。形式: {"headline":"...","copy":"...","image_prompt":"..."}"""

JUDGE_SYSTEM = """あなたは厳しい広告クリエイティブディレクターです。各案を1〜10で採点してください。
- specificity: 商品の特徴が具体的に伝わるか
- appeal: クリックしたくなるか
- fit: ターゲットとトーンに合っているか
7以上は「そのまま出稿できる」水準のときだけ。
出力はJSONのみ。形式: {"scores":[{"specificity":n,"appeal":n,"fit":n,"comment":"改善点を一文"}]}（案と同じ順・同じ数）"""


def _brief(p):
    return (f"商品名: {p['name']}\n概要: {p['summary']}\nターゲット: {p['target']}\n"
            f"特徴: {' / '.join(p['features'])}\nトーン: {p['tone']}")


def generate_ads(p, n=5):
    text, tok = llm.chat(llm.GEN_MODEL, GEN_SYSTEM, f"{_brief(p)}\n\n広告案を{n}つ作ってください。",
                         mock_ctx={"kind": "generate", "product": p, "n": n})
    return llm.extract_json(text)["ads"][:n], tok


def regenerate_ad(p, ad, feedback, other_headlines):
    user = (f"{_brief(p)}\n\n元の案:\n{json.dumps(ad, ensure_ascii=False)}\n\n指摘:\n- " + "\n- ".join(feedback)
            + f"\n\n他の案の見出し（重複禁止）: {' / '.join(other_headlines)}")
    text, tok = llm.chat(llm.GEN_MODEL, REGEN_SYSTEM, user,
                         mock_ctx={"kind": "regenerate", "product": p, "ad": ad, "feedback": feedback})
    new = llm.extract_json(text)
    missing = [k for k in ("headline", "copy", "image_prompt") if not isinstance(new.get(k), str)]
    if missing:
        raise ValueError(f"regenerated ad missing keys: {missing}")
    return new, tok


def judge_ads(p, ads):
    user = f"{_brief(p)}\n\n広告案:\n{json.dumps(ads, ensure_ascii=False, indent=1)}"
    text, tok = llm.chat(llm.JUDGE_MODEL, JUDGE_SYSTEM, user, temperature=0.0,
                         mock_ctx={"kind": "judge", "product": p, "ads": ads})
    scores = llm.extract_json(text)["scores"]
    out = []
    for s in scores[:len(ads)]:
        avg = round((s["specificity"] + s["appeal"] + s["fit"]) / 3, 2)
        out.append({"score": avg, "comment": s.get("comment", "")})
    while len(out) < len(ads):  # 採点漏れは0点扱い
        out.append({"score": 0, "comment": "採点漏れ"})
    return out, tok
