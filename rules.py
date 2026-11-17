"""決定的ルールチェック（LLMに依存しない客観指標）"""

BANNED = ["絶対", "100%", "１００％", "最高", "日本一", "No.1", "NO.1", "業界初", "必ず", "完璧", "世界一"]
HEADLINE_RANGE = (6, 20)   # 文字数
COPY_RANGE = (30, 80)


def check_ad(ad, product, all_ads=None):
    v = []
    h, c, ip = ad.get("headline", ""), ad.get("copy", ""), ad.get("image_prompt", "")
    if not (HEADLINE_RANGE[0] <= len(h) <= HEADLINE_RANGE[1]):
        v.append(f"見出しは{HEADLINE_RANGE[0]}〜{HEADLINE_RANGE[1]}文字にする（現在{len(h)}文字）")
    if not (COPY_RANGE[0] <= len(c) <= COPY_RANGE[1]):
        v.append(f"コピーは{COPY_RANGE[0]}〜{COPY_RANGE[1]}文字にする（現在{len(c)}文字）")
    hits = [w for w in BANNED if w in h + c]
    if hits:
        v.append(f"誇大表現を使わない: {', '.join(hits)}")
    if not any(f in h + c for f in product["features"]):
        v.append(f"商品の特徴のどれかに具体的に触れる: {' / '.join(product['features'])}")
    if len(ip.split()) < 8 or any(ord(ch) > 0x3000 for ch in ip):
        v.append("画像プロンプトは英語で8語以上にする")
    if all_ads and sum(1 for a in all_ads if a.get("headline") == h) > 1:
        v.append("他の案と見出しが重複している")
    return v
