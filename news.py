"""
بوت الأخبار لحساب @fanFpl11 — يشتغل كل ساعتين:
- تغير الأسعار (يرصد أي لاعب ارتفع أو نزل سعره من آخر مرة)
- الإصابات: تتجمع وتنزل تغريدة وحدة باليوم؛ ووقت الجولة الشغالة بس الإصابات الجديدة
"""
import json
import os

import requests

import buffer_api

TYPEFULLY_KEY = os.environ.get("TYPEFULLY_API_KEY", "")
SOCIAL_SET_ID = os.environ.get("TYPEFULLY_SOCIAL_SET_ID", "346034")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
SNAPSHOT = "news_state.json"
MIN_OWNERSHIP = 1.0  # الإصابات: نغرد بس عن اللاعبين اللي ملكيتهم 1% أو أكثر

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


def tweet(text):
    if DRY_RUN or not buffer_api.KEY:
        print("---- (تجربة) ----\n" + text + "\n")
        return True
    return buffer_api.post(text)


def label(p, teams):
    name = PLAYERS_AR.get(p["web_name"], p["web_name"])
    team = TEAMS_AR.get(teams[p["team"]], teams[p["team"]])
    return f"{name} ({team})"


def status_text(p):
    s, chance = p["status"], p["chance_of_playing_next_round"]
    if s == "a":
        return "🟢", "جاهز"
    if s == "d":
        return "🟡", f"نسبة المشاركة {chance}%" if chance is not None else "غير مؤكد يلعب"
    if s == "s":
        return "🔴", "موقوف"
    if s == "i":
        return "🔴", "مصاب"
    return "🔴", "غير متاح"


def chunks(header, lines, footer="\n\n#FPL #الفانتزي", limit=3500):
    """يقسم القائمة لعدة تغريدات إذا كانت طويلة."""
    posts, cur = [], []
    for line in lines:
        if len(header + "\n".join(cur + [line]) + footer) > limit:
            posts.append(header + "\n".join(cur) + footer)
            cur = []
        cur.append(line)
    if cur:
        posts.append(header + "\n".join(cur) + footer)
    return posts


INJ_STATE = "injuries_state.json"
POST_HOUR_KSA = 20  # تتجمع الإصابات طول اليوم وتنزل تغريدة وحدة بعد هالساعة


def gw_in_progress(data):
    """فيه جولة شغالة؟ (بدت مبارياتها وما خلصت)"""
    for e in data["events"]:
        if e["is_current"] and not e["finished"]:
            fx = requests.get(f"https://fantasy.premierleague.com/api/fixtures/?event={e['id']}", timeout=30).json()
            return any(f["started"] for f in fx)
    return False


def injury_daily(data, players, teams, now):
    from datetime import datetime, timedelta, timezone
    ksa = datetime.now(timezone.utc) + timedelta(hours=3)
    today = ksa.strftime("%Y-%m-%d")
    cur = {pid: [v["status"], v["chance"]] for pid, v in now.items()}
    if not os.path.exists(INJ_STATE):
        with open(INJ_STATE, "w") as f:
            json.dump({"date": today, "base": cur}, f)
        print("الإصابات: أول تشغيل، حفظت الوضع")
        return
    with open(INJ_STATE) as f:
        st = json.load(f)
    if st.get("date") == today or ksa.hour < POST_HOUR_KSA:
        print("الإصابات: مو وقت التغريدة اليومية")
        return
    base = st["base"]
    only_new = gw_in_progress(data)  # وقت المباريات: الإصابات الجديدة بس
    changes = []
    for pid, (status, chance) in cur.items():
        prev = base.get(pid)
        if not prev or prev == [status, chance]:
            continue
        p = players[pid]
        if float(p["selected_by_percent"]) < MIN_OWNERSHIP or status == "u":
            continue
        if only_new and not (prev[0] == "a" and status in ("d", "i", "s")):
            continue
        icon, text = status_text(p)
        changes.append((float(p["selected_by_percent"]), f"{icon} {label(p, teams)} — {text}"))
    ok = True
    if changes:
        lines = [l for _, l in sorted(changes, reverse=True)]
        header = "🚑 | إصابات جديدة\n\n" if only_new else "🚑 | تحديث الإصابات اليومي\n\n"
        for post in chunks(header, lines):
            ok = tweet(post) and ok
    else:
        print("الإصابات: ما فيه جديد اليوم")
    if ok:
        with open(INJ_STATE, "w") as f:
            json.dump({"date": today, "base": cur}, f)


def main():
    data = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=30).json()
    teams = {t["id"]: t["short_name"] for t in data["teams"]}
    now = {
        str(p["id"]): {"cost": p["now_cost"], "status": p["status"], "chance": p["chance_of_playing_next_round"]}
        for p in data["elements"]
    }
    players = {str(p["id"]): p for p in data["elements"]}

    if not os.path.exists(SNAPSHOT):  # أول تشغيل: نحفظ الوضع الحالي بس
        with open(SNAPSHOT, "w") as f:
            json.dump(now, f)
        print("أول تشغيل: حفظت الأسعار والإصابات")
        return
    with open(SNAPSHOT) as f:
        old = json.load(f)

    # تغير الأسعار
    up, down = [], []
    for pid, cur in now.items():
        prev = old.get(pid)
        if not prev or prev["cost"] == cur["cost"]:
            continue
        p = players[pid]
        diff = (cur["cost"] - prev["cost"]) / 10
        line = f"{label(p, teams)} {cur['cost'] / 10:.1f} ({diff:+.1f})"
        (up if cur["cost"] > prev["cost"] else down).append((float(p["selected_by_percent"]), line))
    price_ok = True
    if up or down:
        lines = []
        if up:
            lines += ["📈 ارتفع:"] + [l for _, l in sorted(up, reverse=True)]
        if down:
            lines += ([""] if up else []) + ["📉 نزل:"] + [l for _, l in sorted(down, reverse=True)]
        for post in chunks("💰 | تغير الأسعار\n\n", lines):
            price_ok = tweet(post) and price_ok

    # الإصابات: تغريدة وحدة باليوم (بعد الساعة 8 المسا بتوقيت السعودية)
    injury_daily(data, players, teams, now)

    # نحفظ الوضع الجديد بس إذا النشر نجح (عشان ما يضيع خبر)
    for pid, cur in now.items():
        prev = old.get(pid, cur)
        if not price_ok:
            cur["cost"] = prev["cost"]
    with open(SNAPSHOT, "w") as f:
        json.dump(now, f)


if __name__ == "__main__":
    main()
