"""
تصميم بطاقة نهاية المباراة بصور اللاعبين الحقيقية (من موقع الفانتزي الرسمي).
يرسم البطاقة بـ HTML ويصورها بـ Playwright، وبعدين يرفعها لـ Typefully.
"""
import html
import os
import time

import requests

PHOTO = "https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png"


FALLBACK = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<rect width='100' height='100' fill='%234c8bff'/><circle cx='50' cy='38' r='18' fill='%23ffffffcc'/>"
    "<path d='M18 95c4-22 18-32 32-32s28 10 32 32z' fill='%23ffffffcc'/></svg>"
)


def photo_url(player):
    """صورة اللاعب بلبس هالموسم، وإذا ما لقيناها نجرب الصورة القديمة، وآخر شي شكل بديل."""
    for url in (
        f"https://resources.premierleague.com/premierleague25/photos/players/110x140/{player['code']}.png",
        PHOTO.format(code=player["code"]),
    ):
        try:
            if requests.head(url, timeout=10).status_code == 200:
                return url
        except Exception:
            pass
    return FALLBACK


def esc(s):
    return html.escape(str(s))


def ft_card_html(score_home, score_away, home, away, goals, assists, top, bonus, cards):
    """top: [(اسم, نقاط, رابط الصورة)] أعلى اللاعبين نقاطاً، أول واحد هو نجم المباراة."""
    hero = top[0]
    rest = top[1:6]
    tiles = "".join(
        f'<div class="tile"><img src="{esc(u)}"><div class="tn">{esc(n)}</div><div class="tp">{p}</div></div>'
        for n, p, u in rest
    )

    def row(icon, title, items):
        if not items:
            return ""
        return f'<div class="row"><span class="ri">{icon}</span><span class="rt">{esc(title)}</span><span class="rv">{esc("، ".join(items))}</span></div>'

    rows = (
        row("⚽", "الأهداف", goals)
        + row("🅰️", "الأسيست", assists)
        + row("⭐", "البونص", bonus)
        + row("🟨", "البطاقات", cards)
    )
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@600;800;900&family=Barlow+Condensed:wght@700;800&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1350px;font-family:'Cairo',sans-serif;color:#fff;
background:radial-gradient(circle at 20% 0%,#4c8bff55,transparent 45%),radial-gradient(circle at 100% 100%,#7a3cff66,transparent 50%),#2b0a3d;
display:flex;flex-direction:column;padding:46px 56px;gap:22px}}
.top{{display:flex;justify-content:space-between;align-items:center}}
.badge{{background:linear-gradient(90deg,#05f0ff,#4c8bff,#7a3cff);padding:10px 28px;border-radius:40px;font-weight:900;font-size:34px}}
.handle{{font-family:'Barlow Condensed';font-size:38px;opacity:.85;direction:ltr}}
.score{{display:flex;align-items:center;justify-content:space-between;background:#ffffff10;border:2px solid #ffffff22;border-radius:28px;padding:18px 30px}}
.team{{font-size:46px;font-weight:900;width:330px;text-align:center;line-height:1.25}}
.nums{{white-space:nowrap;flex-shrink:0;font-family:'Barlow Condensed';font-size:120px;font-weight:800;direction:ltr;
background:linear-gradient(90deg,#05f0ff,#7a3cff);-webkit-background-clip:text;color:transparent;line-height:1}}
.hero{{display:flex;align-items:center;gap:30px;background:linear-gradient(90deg,#05f0ff22,#7a3cff33);border-radius:28px;padding:20px 34px}}
.hero img{{width:190px;height:190px;object-fit:cover;object-position:top;border-radius:50%;background:#ffffff18;border:5px solid #05f0ff}}
.hl{{font-size:30px;opacity:.8}}.hn{{font-size:56px;font-weight:900;line-height:1.2}}
.hp{{font-family:'Barlow Condensed';font-size:90px;font-weight:800;color:#05f0ff;margin-right:auto;direction:ltr}}
.tiles{{display:flex;gap:18px}}
.tile{{flex:1;background:#ffffff10;border-radius:22px;padding:14px 8px;text-align:center}}
.tile img{{width:116px;height:116px;object-fit:cover;object-position:top;border-radius:50%;background:#ffffff18}}
.tn{{font-size:26px;font-weight:800;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tp{{font-family:'Barlow Condensed';font-size:46px;font-weight:800;color:#05f0ff}}
.rows{{display:flex;flex-direction:column;gap:12px}}
.row{{display:flex;gap:14px;align-items:baseline;font-size:27px;background:#ffffff0c;border-radius:16px;padding:9px 20px;line-height:1.5}}
.ri{{font-size:30px}}.rt{{font-weight:900;white-space:nowrap}}.rv{{opacity:.9}}
</style></head><body>
<div class="top"><div class="badge">🏁 نهاية المباراة</div><div class="handle">@fanFpl11</div></div>
<div class="score"><div class="team">{esc(home)}</div><div class="nums">{score_away} - {score_home}</div><div class="team">{esc(away)}</div></div>
<div class="hero"><img src="{esc(hero[2])}"><div><div class="hl">نجم المباراة في الفانتزي</div><div class="hn">{esc(hero[0])}</div></div><div class="hp">{hero[1]}</div></div>
<div class="tiles">{tiles}</div>
<div class="rows">{rows}</div>
</body></html>"""


def render_png(page_html, out_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # أول مرة على GitHub: نثبت المتصفح
            import subprocess
            import sys

            subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True)
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        page.set_content(page_html, wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=out_path, full_page=False)
        browser.close()
    return out_path


def upload_media(path, social_set_id, key):
    """يرفع الصورة لـ Typefully ويرجع media_id."""
    r = requests.post(
        f"https://api.typefully.com/v2/social-sets/{social_set_id}/media/upload",
        headers={"Authorization": f"Bearer {key}"},
        json={"file_name": os.path.basename(path)},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    with open(path, "rb") as f:
        requests.put(data["upload_url"], data=f.read(), timeout=60).raise_for_status()
    media_id = data["media_id"]
    for _ in range(15):  # ننتظر لين تجهز الصورة
        s = requests.get(
            f"https://api.typefully.com/v2/social-sets/{social_set_id}/media/{media_id}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        if s.ok and s.json().get("status") == "ready":
            break
        time.sleep(2)
    return media_id
