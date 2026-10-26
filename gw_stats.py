"""
تغريدات أرقام نهاية الجولة لحساب @fanFpl11 (تنزل مرة وحدة بعد ما يثبت موقع الفانتزي نقاط الجولة):
1) باعوه وتألق: أكثر لاعب باعوه الناس قبل الجولة وجاب نقاط عالية
2) نتيجة الكابتنية: الكابتن الأكثر اختياراً كم جاب، ومين أفضل كابتن
3) مقارنة صادمة: لاعب رخيص جاب نقاط أكثر من لاعب غالي
"""
import datetime
import json
import os

import requests

TYPEFULLY_KEY = os.environ.get("TYPEFULLY_API_KEY", "")
SOCIAL_SET_ID = os.environ.get("TYPEFULLY_SOCIAL_SET_ID", "346034")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
FORCE = os.environ.get("FORCE", "0") == "1"  # للتجربة: يتجاهل شرط تثبيت النقاط
STATE_FILE = "gw_stats_state.json"
API = "https://fantasy.premierleague.com/api"

TEAMS_AR = {
    "ARS": "آرسنال", "AVL": "أستون فيلا", "BOU": "بورنموث", "BRE": "برينتفورد", "BHA": "برايتون",
    "CHE": "تشيلسي", "COV": "كوفنتري", "CRY": "كريستال بالاس", "EVE": "إيفرتون", "FUL": "فولهام",
    "HUL": "هال", "IPS": "إبسويتش", "LEE": "ليدز", "LIV": "ليفربول", "MCI": "مان سيتي",
    "MUN": "مان يونايتد", "NEW": "نيوكاسل", "NFO": "نوتنغهام", "TOT": "توتنهام", "SUN": "سندرلاند",
    "WHU": "وست هام", "WOL": "وولفز", "BUR": "بيرنلي", "SOU": "ساوثهامبتون", "LEI": "ليستر",
}

try:
    with open("arabic_names.json", encoding="utf-8") as f:
        PLAYERS_AR = json.load(f)
except FileNotFoundError:
    PLAYERS_AR = {}


def get(path):
    return requests.get(f"{API}/{path}", timeout=30).json()


def tweet(text, when="now"):
    if DRY_RUN or not TYPEFULLY_KEY:
        print("---- (تجربة) ----\n" + text + "\n")
        return True
    r = requests.post(
        f"https://api.typefully.com/v2/social-sets/{SOCIAL_SET_ID}/drafts",
        headers={"Authorization": f"Bearer {TYPEFULLY_KEY}"},
        json={"platforms": {"x": {"enabled": True, "posts": [{"text": text}]}}, "publish_at": when},
        timeout=30,
    )
    print("نشر:", r.status_code, text.splitlines()[0])
    return r.status_code < 300


def nq(n):
    """صيغة كلمة نقطة حسب العدد."""
    if n == 1:
        return "نقطة وحدة"
    if n == 2:
        return "نقطتين"
    if 3 <= n <= 10:
        return f"{n} نقاط"
    return f"{n} نقطة"


def main():
    data = get("bootstrap-static/")
    event = next((e for e in data["events"] if e["is_current"]), None)
    if not event:
        return
    gw = event["id"]
    if not FORCE and not (event["finished"] and event["data_checked"]):
        print("الجولة لسا ما انتهت أو النقاط ما ثبتت")
        return
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {"done": []}
    if gw in state["done"] and not FORCE:
        print("تغريدات الجولة نزلت قبل")
        return

    players = {p["id"]: p for p in data["elements"]}
    teams = {t["id"]: t["short_name"] for t in data["teams"]}
    pts = {e["id"]: e["stats"]["total_points"] for e in get(f"event/{gw}/live/")["elements"]
           if e["stats"]["minutes"] > 0}

    def name(pid):
        n = players[pid]["web_name"]
        return PLAYERS_AR.get(n, n)

    def team(pid):
        t = teams[players[pid]["team"]]
        return TEAMS_AR.get(t, t)

    def price(pid):
        return players[pid]["now_cost"] / 10

    tweets = []

    # 1) باعوه وتألق: من اللي جابوا 8 نقاط أو أكثر، مين أكثر واحد انباع قبل الجولة
    best = None
    for pid in [p for p, v in pts.items() if v >= 8]:
        hist = get(f"element-summary/{pid}/")["history"]
        out = sum(h["transfers_out"] for h in hist if h["round"] == gw)
        if out > 0 and (best is None or out > best[1]):
            best = (pid, out)
    if best and best[1] >= 10000:
        pid, out = best
        tweets.append(
            f"😬 | باعوه وتألق — الجولة {gw}\n\n"
            f"{name(pid)} ({team(pid)})\n"
            f"📤 باعه {out:,} مدرب قبل الجولة\n"
            f"📊 وجاب {nq(pts[pid])}\n\n#FPL #الفانتزي"
        )

    # 2) نتيجة الكابتنية
    cap, top = event.get("most_captained"), event.get("top_element")
    if cap and top and cap in pts:
        lines = [f"©️ | نتيجة الكابتنية — الجولة {gw}", ""]
        lines.append(f"👑 الكابتن الأكثر اختياراً: {name(cap)}")
        lines.append(f"جاب {nq(pts[cap])} ({nq(pts[cap] * 2)} بالشارة)")
        if top != cap:
            lines += ["", f"🏆 أفضل كابتن في الجولة: {name(top)} ({team(top)})",
                      f"جاب {nq(pts[top])} ({nq(pts[top] * 2)} بالشارة)"]
        else:
            lines += ["", "🏆 وكان هو أفضل لاعب في الجولة كلها"]
        tweets.append("\n".join(lines) + "\n\n#FPL #الفانتزي")

    # 3) مقارنة صادمة: أفضل لاعب سعره 5.0 أو أقل ضد أغلى لاعب جاب أقل منه
    cheap = [p for p in pts if price(p) <= 5.0]
    if cheap:
        c = max(cheap, key=lambda p: pts[p])
        pricey = sorted((p for p in pts if price(p) >= 10.0 and pts[p] < pts[c]), key=lambda p: -price(p))
        if pricey and pts[c] >= 6:
            e = pricey[0]
            tweets.append(
                f"🤯 | مقارنة الجولة {gw}\n\n"
                f"💸 {name(c)} ({team(c)}) — سعره {price(c):.1f}\n"
                f"جاب {nq(pts[c])}\n\n"
                f"💰 {name(e)} ({team(e)}) — سعره {price(e):.1f}\n"
                f"جاب {nq(pts[e])}\n\n"
                f"فرق السعر {price(e) - price(c):.1f} مليون 👀\n\n#FPL #الفانتزي"
            )

    # تنزل بفرق ساعة بين كل تغريدة والثانية (Typefully يجدولها)
    now = datetime.datetime.now(datetime.timezone.utc)
    ok = all(
        tweet(t, "now" if i == 0 else (now + datetime.timedelta(hours=i)).isoformat(timespec="seconds"))
        for i, t in enumerate(tweets)
    )
    if ok and not FORCE:
        state["done"].append(gw)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)


if __name__ == "__main__":
    main()
