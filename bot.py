"""
بوت @fanFpl11 — يقرأ بيانات الفانتزي الرسمية وينشر على X عن طريق Typefully.
"""
import json
import os
import sys

import requests

TYPEFULLY_KEY = os.environ.get("TYPEFULLY_API_KEY", "")
SOCIAL_SET_ID = os.environ.get("TYPEFULLY_SOCIAL_SET_ID", "346034")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"

FPL = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (fanFpl11 bot)"}
STATE_FILE = "state.json"
HASHTAGS = "#FPL #الفانتزي"

GOAL_POINTS = {1: 10, 2: 6, 3: 5, 4: 4}
ASSIST_POINTS = 3

with open("arabic_names.json", encoding="utf-8") as f:
    ARABIC = json.load(f)


def ar(name):
    return ARABIC.get(name, name)


def get(path):
    r = requests.get(f"{FPL}/{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def tweet(text):
    if DRY_RUN:
        print("---- TEST ----\n" + text + "\n")
        return
    r = requests.post(
        f"https://api.typefully.com/v2/social-sets/{SOCIAL_SET_ID}/drafts",
        headers={"Authorization": f"Bearer {TYPEFULLY_KEY}"},
        json={"platforms": {"x": {"enabled": True, "posts": [{"text": text}]}},
              "publish_at": "now"},
        timeout=30,
    )
    print("POST:", r.status_code, text.splitlines()[0])


def stat(fx, identifier):
    out = {}
    for s in fx.get("stats", []):
        if s["identifier"] == identifier:
            for side in ("h", "a"):
                for row in s[side]:
                    out[str(row["element"])] = [row["value"], side]
    return out


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"initialized": False, "fixtures": {}}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def main():
    boot = get("bootstrap-static/")
    current = next((e for e in boot["events"] if e["is_current"]), None)
    if not current:
        print("no current gameweek")
        return
    players = {str(p["id"]): p for p in boot["elements"]}
    teams = {t["id"]: t["name"] for t in boot["teams"]}

    fixtures = get(f"fixtures/?event={current['id']}")
    state = load_state()
    first_run = not state["initialized"]

    def team_name(fx, side):
        return ar(teams[fx["team_h"] if side == "h" else fx["team_a"]])

    def score_line(fx):
        return (f'{ar(teams[fx["team_h"]])} {fx["team_h_score"] or 0}-'
                f'{fx["team_a_score"] or 0} {ar(teams[fx["team_a"]])}')

    def name(pid):
        return ar(players[pid]["web_name"])

    def goal_pts(pid):
        return GOAL_POINTS.get(players[pid]["element_type"], 0)

    for fx in fixtures:
        if not fx["started"]:
            continue
        fid = str(fx["id"])
        goals = stat(fx, "goals_scored")
        assists = stat(fx, "assists")
        own = stat(fx, "own_goals")
        old = state["fixtures"].get(fid, {"goals": {}, "assists": {}, "own": {}, "done": False})

        if first_run:
            state["fixtures"][fid] = {"goals": goals, "assists": assists, "own": own,
                                      "done": fx["finished_provisional"]}
            continue

        new_goals = [(pid, side) for pid, (v, side) in goals.items()
                     for _ in range(v - old["goals"].get(pid, [0])[0])]
        new_assists = [(pid, side) for pid, (v, side) in assists.items()
                       for _ in range(v - old["assists"].get(pid, [0])[0])]
        new_own = [(pid, side) for pid, (v, side) in own.items()
                   for _ in range(v - old["own"].get(pid, [0])[0])]

        running = {pid: old["goals"].get(pid, [0])[0] for pid, _ in new_goals}
        for pid, side in new_goals:
            lines = [f"⚽ هدف! {score_line(fx)}", f"🎯 {name(pid)} +{goal_pts(pid)}"]
            running[pid] += 1
            total = running[pid]
            if total > 1:
                lines.append(f"📊 المجموع: {total} أهداف = +{total * goal_pts(pid)}")
            match = next((a for a in new_assists if a[1] == side), None)
            if match:
                new_assists.remove(match)
                lines.append(f"🅰️ {name(match[0])} +{ASSIST_POINTS}")
            tweet("\n".join(lines + ["", HASHTAGS]))

        for pid, side in new_own:
            tweet("\n".join([f"⚽ هدف عكسي! {score_line(fx)}",
                             f"😬 {name(pid)} (هدف عكسي)", "", HASHTAGS]))

        for pid, side in new_assists:
            tweet("\n".join([f"🅰️ تحديث أسيست | {score_line(fx)}",
                             f"أسيست هدف {team_name(fx, side)}: {name(pid)} +{ASSIST_POINTS}",
                             "", HASHTAGS]))

        if fx["finished_provisional"] and not old["done"]:
            lines = ["🏁 نهاية المباراة", score_line(fx), ""]
            for pid, (v, _) in goals.items():
                lines.append(f'{"⚽" * v} {name(pid)} +{v * goal_pts(pid)}')
            for pid, (v, _) in assists.items():
                lines.append(f'{"🅰️" * v} {name(pid)} +{v * ASSIST_POINTS}')
            tweet("\n".join(lines + ["", HASHTAGS]))

        state["fixtures"][fid] = {"goals": goals, "assists": assists, "own": own,
                                  "done": fx["finished_provisional"]}

    state["initialized"] = True
    save_state(state)
    print("DONE", "(first run: saved baseline, no posts)" if first_run else "")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("ERROR:", err)
        sys.exit(0)
