#!/usr/bin/env python3
"""Genera assets/stats.svg con datos reales de GitHub (sin servicios de terceros).

Uso en GitHub Actions (modo normal, requiere GITHUB_TOKEN):
    USERNAME=Jhoansbr python scripts/generate_stats.py

Uso sin red (a partir de un JSON ya normalizado):
    python scripts/generate_stats.py --offline datos.json
"""
import argparse, collections, datetime as dt, json, os, sys, urllib.request
from xml.sax.saxutils import escape

OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "stats.svg")
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
HEAT = ["#21262D", "#0E4429", "#006D32", "#26A641", "#3FB950"]
LANG_COLORS = ["#58A6FF", "#3FB950", "#D29922", "#A371F7", "#F0883E", "#6E7681"]


def api(path, token, graphql=None):
    url = "https://api.github.com" + path
    data = json.dumps(graphql).encode() if graphql else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(user, token):
    q = {"query": """query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{
        totalContributions weeks{contributionDays{date contributionCount contributionLevel}}}}}}""",
         "variables": {"u": user}}
    cal = api("/graphql", token, q)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [[d["date"], d["contributionCount"], LEVELS[d["contributionLevel"]]]
            for w in cal["weeks"] for d in w["contributionDays"]]
    repos = api(f"/users/{user}/repos?per_page=100&type=owner", token)
    langs = collections.Counter()
    for r in repos:
        if r["fork"] or r["name"].lower() == user.lower():
            continue
        langs.update(api(f"/repos/{user}/{r['name']}/languages", token))
    return {"total": cal["totalContributions"], "days": days, "languages": dict(langs),
            "public_repos": len(repos)}


def streaks(days):
    days = sorted(days)
    today = dt.date.fromisoformat(days[-1][0])
    longest = run = 0
    for _, c, _ in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    cur, i = 0, len(days) - 1
    if days[i][1] == 0:  # el día en curso aún puede no tener actividad
        i -= 1
    while i >= 0 and days[i][1] > 0:
        cur += 1
        i -= 1
    return cur, longest, today


def render(d):
    days = sorted(d["days"])
    cur, longest, last = streaks(days)
    langs = sorted(d["languages"].items(), key=lambda kv: -kv[1])
    total_b = sum(b for _, b in langs) or 1
    top = langs[:5]
    other = sum(b for _, b in langs[5:])
    if other:
        top.append(("Otros", other))
    W, H, PAD = 640, 372, 28
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
         f'aria-labelledby="t d"><title id="t">Actividad en GitHub</title>'
         f'<desc id="d">{d["total"]} contribuciones en el último año, racha actual de {cur} días, '
         f'racha más larga de {longest} días.</desc>',
         '<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}'
         '.n{font-size:34px;font-weight:700;fill:#F0F6FC}.l{font-size:15px;fill:#8B949E}'
         '.s{font-size:14px;fill:#8B949E}.k{font-size:15px;fill:#F0F6FC}</style>',
         f'<rect width="{W}" height="{H}" rx="10" fill="#161B22" stroke="#30363D"/>']
    cols = [(PAD, d["total"], "contribuciones, último año", "#58A6FF"),
            (PAD + 258, cur, "días de racha actual", "#3FB950"),
            (PAD + 458, longest, "racha más larga", "#F0F6FC")]
    for x, v, label, color in cols:
        o.append(f'<text x="{x}" y="58" class="n" style="fill:{color}">{v}</text>'
                 f'<text x="{x}" y="82" class="l">{escape(label)}</text>')
    # mapa de calor
    weeks = collections.OrderedDict()
    for date, c, lvl in days:
        dd = dt.date.fromisoformat(date)
        key = dd - dt.timedelta(days=(dd.weekday() + 1) % 7)  # semanas que inician en domingo
        weeks.setdefault(key, {})[(dd.weekday() + 1) % 7] = lvl
    cell, gap, y0 = 9, 2, 112
    step = cell + gap
    x0 = PAD + (W - 2 * PAD - len(weeks) * step + gap) / 2
    for wi, (_, col) in enumerate(weeks.items()):
        for row, lvl in col.items():
            o.append(f'<rect x="{x0 + wi * step:.1f}" y="{y0 + row * step}" width="{cell}" height="{cell}" '
                     f'rx="2" fill="{HEAT[lvl]}"/>')
    # lenguajes
    ly = 218
    o.append(f'<text x="{PAD}" y="{ly}" class="k">lenguajes en repos públicos propios</text>')
    bx, bw, by = PAD, W - 2 * PAD, ly + 14
    o.append(f'<clipPath id="c"><rect x="{bx}" y="{by}" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#c)">')
    x = bx
    for i, (name, b) in enumerate(top):
        w = bw * b / total_b
        o.append(f'<rect x="{x:.1f}" y="{by}" width="{w:.1f}" height="10" fill="{LANG_COLORS[i]}"/>')
        x += w
    o.append('</g>')
    for i, (name, b) in enumerate(top):
        cx = PAD + (i % 3) * 200
        cy = by + 36 + (i // 3) * 26
        o.append(f'<circle cx="{cx + 5}" cy="{cy - 5}" r="5" fill="{LANG_COLORS[i]}"/>'
                 f'<text x="{cx + 18}" y="{cy}" class="k">{escape(name)} <tspan class="s">{b / total_b:.0%}</tspan></text>')
    o.append(f'<text x="{PAD}" y="{H - 16}" class="s">Datos al {last.isoformat()}. '
             f'{d["public_repos"]} repositorios públicos.</text>')
    o.append('</svg>')
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline")
    a = ap.parse_args()
    if a.offline:
        data = json.load(open(a.offline))
    else:
        token, user = os.environ.get("GITHUB_TOKEN"), os.environ.get("USERNAME", "Jhoansbr")
        if not token:
            sys.exit("Falta GITHUB_TOKEN")
        data = fetch(user, token)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(data))
    print("OK", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
