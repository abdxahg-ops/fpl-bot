"""
بوت نقاط الدفاع (DEF CON) لحساب @fanFpl11
يراقب موقع الفانتزي الرسمي وقت المباريات، وأي لاعب ياخذ +2 نقاط دفاع ينشر عنه تغريدة على طول عن طريق Typefully.
يشتغل كل جولة تلقائياً بدون أي تعديل.
"""
import calendar
import json
import os
import time

import requests

TYPEFULLY_KEY = os.environ.get("TYPEFULLY_API_KEY", "")
SOCIAL_SET_ID = os.environ.get("TYPEFULLY_SOCIAL_SET_ID", "346034")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
MAX_MINUTES = int(os.environ.get("MAX_MINUTES", "70"))  # أقصى مدة للتشغيل الواحد
POLL_SECONDS = 45
STATE_FILE = "defcon_state.json"
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


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"seen": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def tweet(text):
    if DRY_RUN or not TYPEFULLY_KEY:
        print("---- (تجربة) ----\n" + text + "\n")
        return True
    r = requests.post(
        f"https://api.typefully.com/v2/social-sets/{SOCIAL_SET_ID}/drafts",
        headers={"Authorization": f"Bearer {TYPEFULLY_KEY}"},
        json={"platforms": {"x": {"enabled": True, "posts": [{"text": text}]}}, "publish_at": "now"},
        timeout=30,
    )
    print("نشر:", r.status_code, text.splitlines()[2] if len(text.splitlines()) > 2 else "")
    return r.status_code < 300


def current_gw(bootstrap):
    for e in bootstrap["events"]:
        if e["is_current"]:
            return e["id"]
    for e in bootstrap["events"]:
        if e["is_next"]:
            return e["id"]
    return None


def window_active(fixtures, now):
    """فيه مباراة شغالة أو بتبدأ خلال ساعة؟"""
    for f in fixtures:
        if f["started"] and not f["finished_provisional"]:
            return True
        if f["kickoff_time"] and not f["started"]:
            ko = calendar.timegm(time.strptime(f["kickoff_time"], "%Y-%m-%dT%H:%M:%SZ"))
            if 0 <= ko - now <= 3600:
                return True
    return False


def achievements(gw):
    """كل (لاعب، مباراة) اللي ياخذ فيها نقاط دفاع."""
    out = {}
    for e in get(f"event/{gw}/live/")["elements"]:
        for ex in e["explain"]:
            for s in ex["stats"]:
                if s["identifier"] == "defensive_contribution" and s["points"] > 0:
                    out[f'{e["id"]}-{ex["fixture"]}'] = s["points"]
    return out


def main():
    bootstrap = get("bootstrap-static/")
    gw = current_gw(bootstrap)
    if not gw:
        print("ما فيه جولة")
        return
    players = {p["id"]: p for p in bootstrap["elements"]}
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    state = load_state()
    if state.get("gw") != gw:
        state = {"gw": gw, "seen": []}

    start = time.time()
    while time.time() - start < MAX_MINUTES * 60:
        try:
            if not tick(gw, players, teams, state):
                break
        except Exception as err:  # خطأ مؤقت من موقع الفانتزي (مثلاً وقت التحديث): نكمل
            print("خطأ مؤقت:", err)
        time.sleep(POLL_SECONDS)
    save_state(state)


def tick(gw, players, teams, state):
    """دورة وحدة: ترجع False إذا ما فيه مباريات شغالة."""
    fixtures = get(f"fixtures/?event={gw}")
    # بطاقة نهاية المباراة (بصور اللاعبين) للمباريات اللي خلصت توها
    for f in fixtures:
        key = f"ft-{f['id']}"
        if f["finished_provisional"] and key not in state["seen"] and recently_finished(f):
            try:
                if post_full_time(f, gw, players, teams):
                    state["seen"].append(key)
                    save_state(state)
            except Exception as err:
                print("خطأ في بطاقة النهاية:", err)
    if not window_active(fixtures, time.time()):
        print("ما فيه مباريات شغالة")
        return False
    fx = {f["id"]: f for f in fixtures}
    try:
        new = {k: v for k, v in achievements(gw).items() if k not in state["seen"]}
    except Exception as err:  # نكمل حتى لو صار خطأ مؤقت
        print("خطأ:", err)
        return True

    by_fixture = {}
    for key, pts in new.items():
        pid, fid = map(int, key.split("-"))
        if fx[fid]["finished_provisional"]:  # مباراة خلصت قبل ما نشتغل: ما نغرد عنها متأخر
            state["seen"].append(key)
            continue
        by_fixture.setdefault(fid, []).append((key, pid, pts))

    for fid, items in by_fixture.items():
        f = fx[fid]
        home, away = teams[f["team_h"]], teams[f["team_a"]]
        score = f'{TEAMS_AR.get(home, home)} {f["team_h_score"] or 0}-{f["team_a_score"] or 0} {TEAMS_AR.get(away, away)}'
        lines = []
        for _, pid, pts in items:
            name = players[pid]["web_name"]
            lines.append(f"🛡️ {PLAYERS_AR.get(name, name)} (+{pts})")
        text = "✅ | نقاط الدفاع DEF CON\n\n" + "\n".join(lines) + f"\n\n{score}\n\n#FPL #الفانتزي"
        if tweet(text):
            state["seen"] += [k for k, _, _ in items]
            save_state(state)

    # البونص المتوقع في الدقيقة 60 و80
    for f in fixtures:
        if not f["started"] or f["finished_provisional"]:
            continue
        for mark in BONUS_MARKS:
            key = f"bonus{mark}-{f['id']}"
            if f["minutes"] >= mark and key not in state["seen"]:
                text = bonus_tweet(f, mark, players, teams)
                if text and tweet(text):
                    state["seen"].append(key)
                    save_state(state)
    return True


BONUS_MARKS = (60, 80)


def recently_finished(f):
    if not f["kickoff_time"]:
        return False
    ko = calendar.timegm(time.strptime(f["kickoff_time"], "%Y-%m-%dT%H:%M:%SZ"))
    return time.time() - ko < 2.5 * 3600  # بدأت قبل أقل من ساعتين ونص (عشان ما نعيد مباريات قديمة)


def ar_name(players, pid):
    n = players[pid]["web_name"]
    return PLAYERS_AR.get(n, n)


def fixture_points(gw, fid):
    """نقاط كل لاعب في هذي المباراة بالذات."""
    pts = {}
    for e in get(f"event/{gw}/live/")["elements"]:
        for ex in e["explain"]:
            if ex["fixture"] == fid:
                mins = sum(s["value"] for s in ex["stats"] if s["identifier"] == "minutes")
                if mins > 0:
                    pts[e["id"]] = sum(s["points"] for s in ex["stats"])
    return pts


def post_full_time(f, gw, players, teams):
    import cards

    stat = {s["identifier"]: s["h"] + s["a"] for s in f["stats"]}
    home, away = teams[f["team_h"]], teams[f["team_a"]]
    home_ar, away_ar = TEAMS_AR.get(home, home), TEAMS_AR.get(away, away)
    hs, as_ = f["team_h_score"] or 0, f["team_a_score"] or 0

    def names(identifier, with_value=False):
        out = []
        for x in sorted(stat.get(identifier, []), key=lambda x: -x["value"]):
            n = ar_name(players, x["element"])
            if with_value:
                out.append(f"{n} {x['value']}")
            else:
                out.append(n + (f" ×{x['value']}" if x["value"] > 1 else ""))
        return out

    goals = names("goals_scored") + [f"{n} (عكسي)" for n in names("own_goals")]
    assists = names("assists")
    bonus = names("bonus", with_value=True)
    reds = names("red_cards")
    yellows = names("yellow_cards")

    pts = fixture_points(gw, f["id"])
    top_ids = sorted(pts, key=lambda pid: -pts[pid])[:6]
    top = [(ar_name(players, pid), pts[pid], cards.photo_url(players[pid])) for pid in top_ids]

    lines = [f"🏁 نهاية المباراة\n{home_ar} {hs}-{as_} {away_ar}", ""]
    if goals:
        lines.append("⚽ الأهداف: " + "، ".join(goals))
    if assists:
        lines.append("🅰️ الأسيست: " + "، ".join(assists))
    lines += ["", "📊 نقاط الفانتزي:"] + [f"{n} {p}" for n, p, _ in top]
    if bonus:
        lines += ["", "⭐ البونص: " + " | ".join(bonus)]
    if reds:
        lines.append("🟥 الطرد: " + "، ".join(reds))
    if yellows:
        lines.append("🟨 البطاقات: " + "، ".join(yellows))
    text = "\n".join(lines) + "\n\n#FPL #الفانتزي"

    card_items = (["🟥 " + n for n in reds]) + yellows
    page = cards.ft_card_html(hs, as_, home_ar, away_ar, goals, assists, top, bonus, card_items)
    path = cards.render_png(page, f"ft_{f['id']}.png")

    if DRY_RUN or not TYPEFULLY_KEY:
        print("---- (تجربة: بطاقة النهاية", path, ") ----\n" + text)
        return True
    media_id = cards.upload_media(path, SOCIAL_SET_ID, TYPEFULLY_KEY)
    r = requests.post(
        f"https://api.typefully.com/v2/social-sets/{SOCIAL_SET_ID}/drafts",
        headers={"Authorization": f"Bearer {TYPEFULLY_KEY}"},
        json={"platforms": {"x": {"enabled": True, "posts": [{"text": text, "media_ids": [media_id]}]}}, "publish_at": "now"},
        timeout=30,
    )
    print("نشر بطاقة النهاية:", r.status_code, home, away)
    return r.status_code < 300


def provisional_bonus(fixture):
    """يحسب البونص من نقاط BPS بنفس قانون الفانتزي (التعادل ياخذون نفس النقاط)."""
    bps = []
    for s in fixture["stats"]:
        if s["identifier"] == "bps":
            bps = s["h"] + s["a"]
    bps.sort(key=lambda x: -x["value"])
    out = []
    for p in bps:
        rank = 1 + sum(1 for q in bps if q["value"] > p["value"])
        if rank > 3:
            break
        out.append((p["element"], 4 - rank, p["value"]))
    return out


def bonus_tweet(f, mark, players, teams):
    bonus = provisional_bonus(f)
    if not bonus:
        return None
    home, away = teams[f["team_h"]], teams[f["team_a"]]
    score = f'{TEAMS_AR.get(home, home)} {f["team_h_score"] or 0}-{f["team_a_score"] or 0} {TEAMS_AR.get(away, away)}'
    lines = []
    for pid, pts, _ in bonus:
        name = players[pid]["web_name"]
        lines.append(f"{'🥇🥈🥉'[3 - pts]} {PLAYERS_AR.get(name, name)} +{pts}")
    return f"⭐ | البونص المتوقع (د{mark})\n\n" + "\n".join(lines) + f"\n\n{score}\n\n#FPL #الفانتزي"


if __name__ == "__main__":
    main()
