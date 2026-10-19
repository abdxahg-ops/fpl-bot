"""
FPL smart manager - Telegram alerts + Claude reports.
"""
import json, os, sys
from collections import Counter
from datetime import datetime, timezone
import requests

ENTRY = int(os.environ.get("FPL_ENTRY", "53586"))
LEAGUE = int(os.environ.get("FPL_LEAGUE", "1065708"))
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
FORCE = os.environ.get("FORCE_REPORT", "").strip().lower()
STATE_FILE = "manager_state.json"
H = {"User-Agent": "Mozilla/5.0 (fpl manager)"}
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

with open("arabic_names.json", encoding="utf-8") as f:
    AR = json.load(f)

SYSTEM = """أنت مدير فريق فانتزي الدوري الإنجليزي (FPL) لعبدالله، وتكلمه باللهجة السعودية بشكل ودي ومختصر.
مهمتك تكتب له رسالة تيليجرام فيها قرار واضح، مو كلام عام.
قواعد لازم تلتزم فيها:
- الحد الأقصى 3 لاعبين من نفس الفريق. لا تقترح تبديل يكسر هالقاعدة أبداً (احسب لاعبين كل فريق بعد التبديل).
- التبديل لازم يكون نفس المركز، وسعر اللاعب الجديد <= سعر اللي يطلع + البنك.
- كل تبديل زيادة عن التبديلات المجانية يخصم 4 نقاط، ولا تقترحه إلا إذا يستاهل بوضوح.
- خذ بالاعتبار الإصابات، والفورم، وصعوبة المباريات الجاية (FDR 1 سهل، 5 صعب)، ومنافسيه في دوري الأستراحة.
- الشرائح: اقترح استخدامها بس إذا الوقت مناسب فعلاً، واذكر ليش.
- استخدم أسماء اللاعبين بالعربي إذا موجودة.
- الرسالة لا تتجاوز 8000 حرف، واستخدم إيموجي بسيطة وأسطر قصيرة. لا تستخدم markdown مثل ** أو #.
"""


def ar(n): return AR.get(n, n)
def get(p): return requests.get("https://fantasy.premierleague.com/api/" + p, headers=H, timeout=30).json()


def send(text):
    if not TG_TOKEN:
        print("---- MESSAGE ----\n" + text + "\n"); return
    for i in range(0, len(text), 4000):
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN.strip()}/sendMessage",
                          json={"chat_id": TG_CHAT.strip(), "text": text[i:i + 4000]}, timeout=30)
        print("TELEGRAM:", r.status_code, r.text[:200])


def ask_claude(task, data):
    if not CLAUDE_KEY:
        return None
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": CLAUDE_KEY, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 8000, "system": SYSTEM,
                            "messages": [{"role": "user", "content":
                                          task + "\n\nDATA:\n" + json.dumps(data, ensure_ascii=False)}]},
                      timeout=120)
    print("CLAUDE:", r.status_code)
    if r.status_code != 200:
        print("Claude error:", r.text[:300]); return None
    return "".join(c.get("text", "") for c in r.json().get("content", []))


def load():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"news": {}, "prices": {}, "report_gw": 0, "summary_gw": 0}


def fixtures_by_team(T, start_gw, n=5):
    out = {t: [] for t in T}
    for gw in range(start_gw, min(start_gw + n, 39)):
        for f in get(f"fixtures/?event={gw}"):
            out[f["team_h"]].append(f"GW{gw} {T[f['team_a']]}(H) {f['team_h_difficulty']}")
            out[f["team_a"]].append(f"GW{gw} {T[f['team_h']]}(A) {f['team_a_difficulty']}")
    return out


def free_transfers(history):
    ft = 1
    chips = {c["event"]: c["name"] for c in history["chips"]}
    for r in history["current"][1:]:
        if chips.get(r["event"]) in ("wildcard", "freehit"):
            continue
        ft = min(5, max(1, ft - r["event_transfers"] + 1)) if r["event_transfers"] <= ft else 1
    return ft


def player_info(p, T, fx):
    return {"name": ar(p["web_name"]), "team": T[p["team"]], "pos": POS[p["element_type"]],
            "price": p["now_cost"] / 10, "form": p["form"], "total_pts": p["total_points"],
            "ep_next": p["ep_next"], "chance": p["chance_of_playing_next_round"],
            "news": p["news"], "owned_pct": p["selected_by_percent"],
            "next_fixtures": fx[p["team"]]}


def build_data(b, P, T, gw_for_picks, next_gw):
    fx = fixtures_by_team(T, next_gw)
    picks = get(f"entry/{ENTRY}/event/{gw_for_picks}/picks/")
    hist = get(f"entry/{ENTRY}/history/")
    squad = [x["element"] for x in picks["picks"]]
    all_chips = {"wildcard", "freehit", "bboost", "3xc"}
    used = [c["name"] for c in hist["chips"]]

    league = get(f"leagues-classic/{LEAGUE}/standings/")["standings"]["results"]
    own = Counter(); rivals = []
    for r in league:
        pk = get(f"entry/{r['entry']}/event/{gw_for_picks}/picks/")
        h = get(f"entry/{r['entry']}/history/")
        for x in pk["picks"]: own[x["element"]] += 1
        cap = next(x["element"] for x in pk["picks"] if x["is_captain"])
        rivals.append({"rank": r["rank"], "name": r["player_name"], "total": r["total"],
                       "captain": ar(P[cap]["web_name"]),
                       "chips_left": sorted(all_chips - {c["name"] for c in h["chips"]})})

    cands = []
    for pos in (1, 2, 3, 4):
        pool = [p for p in P.values() if p["element_type"] == pos and p["id"] not in squad
                and p["minutes"] >= 270 and p["chance_of_playing_next_round"] in (None, 100)]
        pool.sort(key=lambda p: -(float(p["form"]) + float(p["ep_next"] or 0)))
        cands += [player_info(p, T, fx) | {"league_owners": own[p["id"]]} for p in pool[:12]]

    return {
        "next_gameweek": next_gw,
        "my_team": [player_info(P[i], T, fx) | {"league_owners": own[i],
                    "starting": n < 11, "captain": x["is_captain"]}
                    for n, (i, x) in enumerate(zip(squad, picks["picks"]))],
        "bank": picks["entry_history"]["bank"] / 10,
        "free_transfers_estimate": free_transfers(hist),
        "chips_left": sorted(all_chips - set(used)),
        "my_rank_overall": hist["current"][-1]["overall_rank"],
        "league_table": rivals,
        "league_size": len(league),
        "transfer_candidates": cands,
    }


def main():
    print("FORCE:", repr(FORCE), "| TG token:", len(TG_TOKEN), "| chat:", len(TG_CHAT), "| claude key:", len(CLAUDE_KEY))
    st = load()
    b = get("bootstrap-static/")
    P = {p["id"]: p for p in b["elements"]}
    T = {t["id"]: t["short_name"] for t in b["teams"]}
    now = datetime.now(timezone.utc)
    cur = next((e for e in b["events"] if e["is_current"]), None)
    nxt = next((e for e in b["events"] if e["is_next"]), None)
    gw = cur["id"] if cur else 1
    squad = [x["element"] for x in get(f"entry/{ENTRY}/event/{gw}/picks/")["picks"]]

    alerts = []
    for i in squad:
        p = P[i]; k = str(i)
        news = f'{p["chance_of_playing_next_round"]}|{p["news"]}'
        if k in st["news"] and st["news"][k] != news:
            ch = p["chance_of_playing_next_round"]
            alerts.append(f"🚨 {ar(p['web_name'])}: " + (f"{ch}% — {p['news']}" if p["news"] else "✅ صار جاهز"))
        st["news"][k] = news
        if k in st["prices"] and st["prices"][k] != p["now_cost"]:
            arrow = "📈" if p["now_cost"] > st["prices"][k] else "📉"
            alerts.append(f"{arrow} {ar(p['web_name'])}: {st['prices'][k]/10} ← {p['now_cost']/10}")
        st["prices"][k] = p["now_cost"]
    if alerts:
        send("🔔 تنبيه فريقك\n\n" + "\n".join(alerts))

    if nxt:
        dl = datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
        due = 0 < (dl - now).total_seconds() / 3600 <= 30 and st["report_gw"] != nxt["id"]
        if due or FORCE == "deadline":
            data = build_data(b, P, T, gw, nxt["id"])
            text = ask_claude(
                f"اكتب تقرير الجولة {nxt['id']} قبل الديدلاين: التبديل (أو التوفير)، الكابتن ونائبه، "
                "التشكيلة الأساسية والدكة، الشرائح، وكيف يتقدم على منافسيه في دوري الأستراحة.", data)
            send(text or "📋 الديدلاين قرّب، وما قدرت أجهز التحليل الذكي هالمرة.")
            if not FORCE:
                st["report_gw"] = nxt["id"]

    if cur and ((cur["finished"] and cur["data_checked"] and st["summary_gw"] != cur["id"]) or FORCE == "summary"):
        live = {e["id"]: e["stats"]["total_points"] for e in get(f"event/{cur['id']}/live/")["elements"]}
        pk = get(f"entry/{ENTRY}/event/{cur['id']}/picks/")
        hist = get(f"entry/{ENTRY}/history/")["current"]
        league = get(f"leagues-classic/{LEAGUE}/standings/")["standings"]["results"]
        data = {"gameweek": cur["id"], "my_gw": next(r for r in hist if r["event"] == cur["id"]),
                "my_players": [{"name": ar(P[x["element"]]["web_name"]), "points": live.get(x["element"], 0),
                                "multiplier": x["multiplier"]} for x in pk["picks"]],
                "league": [{"rank": r["rank"], "last_rank": r["last_rank"], "name": r["player_name"],
                            "gw_points": r["event_total"], "total": r["total"]} for r in league]}
        text = ask_claude(f"اكتب ملخص الجولة {cur['id']}: نقاطه، أفضل وأسوأ لاعب عنده، حركته في دوري "
                          "الأستراحة، وكم بينه وبين اللي فوقه، ونصيحة وحدة للجولة الجاية.", data)
        if text:
            send(text)
        if not FORCE:
            st["summary_gw"] = cur["id"]

    json.dump(st, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    print("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e); sys.exit(0)
