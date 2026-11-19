#!/usr/bin/env python3
"""Daily CHIP Store vs. BestCheck price report.

Collects live prices from chipstore.de, matches them to BestCheck offers by EAN,
and writes a self-contained HTML report plus a landscape A4 PDF printed by
headless Chrome. Usage: python3 preischeck.py [--out DIR]
"""
import argparse
import gzip
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
SITEMAP_INDEX = "https://www.chipstore.de/sitemap.xml"
BERLIN = ZoneInfo("Europe/Berlin")
CHIP_MERCHANT_ID = "1161"

# EAN conflicts that cannot be detected from the data alone.
KNOWN_CONFLICTS = {
    "4062983001135": "Die eigene EAN der Soundbox XL findet auf BestCheck keinen Artikel. "
                     "Die BestCheck-Seite „Die Soundbox XL“ ist mit der EAN der Soundbox M verschlagwortet.",
}


def fetch(url, timeout=40, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9"})
            with urlopen(req, timeout=timeout) as r:
                return r.read()
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise last


def euro_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    s = re.sub(r"[^\d,.\-]", "", str(value))
    if not s or s in {"-", ".", ","}:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def eur(n):
    if n is None:
        return "—"
    sign = "−" if n < 0 else ""
    whole, frac = f"{abs(n):.2f}".split(".")
    whole = re.sub(r"\B(?=(\d{3})+(?!\d))", ".", whole)
    return f"{sign}{whole},{frac} €"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def walk_products(node, acc):
    if isinstance(node, list):
        for x in node:
            walk_products(x, acc)
        return
    if not isinstance(node, dict):
        return
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    if "Product" in types and node.get("name") and node.get("offers"):
        acc.append(node)
    for v in node.values():
        if isinstance(v, (dict, list)):
            walk_products(v, acc)


def product_urls():
    index = fetch(SITEMAP_INDEX).decode("utf-8", "replace")
    maps = re.findall(r"<loc>(.*?)</loc>", index)
    urls = []
    for m in maps:
        raw = fetch(m)
        xml = gzip.decompress(raw).decode("utf-8", "replace") if m.endswith(".gz") else raw.decode("utf-8", "replace")
        for chunk in re.findall(r"<url>(.*?)</url>", xml, re.S):
            loc = re.search(r"<loc>(.*?)</loc>", chunk)
            freq = re.search(r"<changefreq>(.*?)</changefreq>", chunk)
            if loc and freq and freq.group(1) == "hourly":
                urls.append(loc.group(1))
    return urls


def parse_shop_page(url, raw):
    text = raw.decode("utf-8", "replace")
    found = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        try:
            walk_products(json.loads(block), found)
        except json.JSONDecodeError:
            continue
    out = []
    for p in found:
        offers = p.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = euro_value(offers.get("price"))
        if price is None:
            continue
        spec = offers.get("priceSpecification") or {}
        specs = spec if isinstance(spec, list) else [spec]
        list_price = None
        for sp in specs:
            if isinstance(sp, dict) and "Strikethrough" in str(sp.get("priceType", "")):
                list_price = euro_value(sp.get("price"))
        gtin = re.sub(r"\D", "", str(p.get("gtin13") or p.get("gtin") or p.get("gtin14") or p.get("gtin12") or ""))
        name = re.sub(r"\s+", " ", html.unescape(p.get("name") or "")).strip()
        cond = str(offers.get("itemCondition") or "")
        is_bware = "B-Ware" in name or "Refurbished" in cond or "Used" in cond
        out.append({
            "name": name,
            "sku": p.get("sku") or "",
            "gtin": gtin,
            "price": price,
            "list_price": list_price,
            "bware": is_bware,
            "url": p.get("url") or url,
        })
    return out


def bc_search(query):
    text = fetch("https://www.bestcheck.de/search?q=" + quote(query)).decode("utf-8", "replace")
    items, seen = [], set()
    for m in re.finditer(r'data-product-id="(\d{4,})"', text):
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        window = text[m.start(): m.start() + 2500]
        tm = re.search(r"<h[23][^>]*>(.*?)</h[23]>", window, re.S)
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", tm.group(1)))).strip() if tm else ""
        slug = re.search(r"https://www\.bestcheck\.de/" + pid + r"/([^\"?#]+)\.html", text)
        url = f"https://www.bestcheck.de/{pid}/{slug.group(1)}.html" if slug else f"https://www.bestcheck.de/{pid}/"
        items.append({"id": pid, "title": title, "url": url})
    return items


def confirm_frontend(item, gtin):
    """A hit counts only when the BestCheck product page shows this EAN and a price comparison."""
    text = fetch(f"https://www.bestcheck.de/{item['id']}/").decode("utf-8", "replace")
    if gtin not in text or "Preisvergleich zu" not in text:
        return None
    can = re.search(r'rel="canonical" href="([^"]+)"', text)
    return {**item, "url": can.group(1) if can else item["url"]}


def match(product):
    gtin = product["gtin"]
    if not gtin:
        return None
    for item in bc_search(gtin)[:6]:
        try:
            confirmed = confirm_frontend(item, gtin)
        except Exception:
            continue
        if confirmed:
            return confirmed
    return None


def is_display_offer(offer):
    """Floor models and demo units are not comparable to new CHIP Store goods."""
    text = " ".join(
        str(offer.get(key) or "")
        for key in ("description", "delivery_time", "retailer")
    ).lower()
    return bool(re.search(r"aussteller|ausstellung|vorf[uü]hr", text))


def bc_offers(pid):
    offers, offset = [], 0
    while offset < 200:
        data = json.loads(fetch(f"https://www.bestcheck.de/api/product/{pid}/offers/?offset={offset}").decode("utf-8", "replace"))
        if not isinstance(data, list) or not data:
            break
        offers.extend(data)
        if len(data) < 5:
            break
        offset += len(data)
    out = []
    for o in offers:
        if is_display_offer(o):
            continue
        price = euro_value(o.get("price"))
        ship = euro_value(o.get("shipping_costs"))
        if price is None:
            continue
        out.append({
            "merchant": o.get("merchant_name") or "",
            "chip": str(o.get("merchant_id") or "") == CHIP_MERCHANT_ID,
            "price": price,
            "shipping": ship or 0.0,
            "total": round(price + (ship or 0.0), 2),
            "delivery": (o.get("delivery_time") or "").strip(),
            "updated": o.get("last_import_time") or "",
        })
    out.sort(key=lambda x: x["total"])
    return out


def long_delivery(text):
    nums = [int(n) for n in re.findall(r"\d+", text or "")]
    return bool(nums) and max(nums) >= 10 and "Werktag" in (text or "")


def collect():
    urls = product_urls()
    products = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(lambda u: (u, fetch(u)), u) for u in urls]):
            try:
                u, raw = fut.result()
                products.extend(parse_shop_page(u, raw))
            except Exception as e:
                print("Shop-Seite übersprungen:", e, file=sys.stderr)
    unique = {}
    for p in products:
        key = p["sku"] or p["gtin"] or p["url"]
        if key not in unique or p["price"] < unique[key]["price"]:
            unique[key] = p
    products = list(unique.values())

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(match, p): p for p in products}
        for fut in as_completed(futs):
            try:
                futs[fut]["bc"] = fut.result()
            except Exception:
                futs[fut]["bc"] = None

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(bc_offers, p["bc"]["id"]): p for p in products if p.get("bc")}
        for fut in as_completed(futs):
            try:
                futs[fut]["offers"] = fut.result()
            except Exception:
                futs[fut]["offers"] = []
    for p in products:
        p.setdefault("offers", [])
    return products


def classify(products):
    by_gtin = {}
    for p in products:
        if p["gtin"]:
            by_gtin.setdefault(p["gtin"], []).append(p)

    groups = {k: [] for k in ("gap", "tie", "win", "exclusive", "missing", "conflict")}
    for p in products:
        offers = p["offers"]
        others = [o for o in offers if not o["chip"]]
        chip_offer = next((o for o in offers if o["chip"]), None)
        siblings = by_gtin.get(p["gtin"], [])
        cheaper_sibling = min((s["price"] for s in siblings if s is not p), default=None)

        if p["bware"]:
            groups["conflict"].append({**p, "kind": "bware", "cheapest_new": others[0] if others else None})
            continue
        if cheaper_sibling is not None and cheaper_sibling < p["price"] - 0.01:
            groups["conflict"].append({**p, "kind": "shared_ean", "siblings": siblings, "chip_offer": chip_offer})
            continue
        if chip_offer and abs(chip_offer["price"] - p["price"]) > 0.5:
            groups["conflict"].append({**p, "kind": "price_mismatch", "chip_offer": chip_offer})
            continue
        if p["gtin"] in KNOWN_CONFLICTS:
            groups["conflict"].append({**p, "kind": "known", "text": KNOWN_CONFLICTS[p["gtin"]]})
            continue
        if not p.get("bc"):
            reason = "Im BestCheck-Frontend nicht gelistet" if p["gtin"] else "Keine EAN, im Frontend nicht zuordenbar"
            groups["missing"].append({**p, "reason": reason})
            continue
        if not others:
            groups["exclusive"].append(p)
            continue
        best = others[0]
        diff = round(p["price"] - best["total"], 2)
        row = {**p, "best": best, "others": others, "diff": diff, "chip_listed": bool(chip_offer)}
        if diff > 0.01:
            groups["gap"].append(row)
        elif diff >= -0.01:
            groups["tie"].append(row)
        else:
            groups["win"].append(row)

    groups["gap"].sort(key=lambda r: -r["diff"])
    groups["win"].sort(key=lambda r: r["diff"])
    groups["exclusive"].sort(key=lambda r: -r["price"])
    groups["missing"].sort(key=lambda r: -r["price"])
    return groups


def gap_note(r):
    best = r["best"]
    parts = []
    if best["shipping"] > 0:
        parts.append(f"Artikelpreis {eur(best['price'])} plus {eur(best['shipping'])} Versand.")
    if long_delivery(best["delivery"]):
        parts.append(f"{best['merchant']} nennt {best['delivery']}.")
    more = [o for o in r["others"][1:4]]
    if more:
        parts.append("Weitere: " + ", ".join(f"{o['merchant']} {eur(o['total'])}" for o in more) + ".")
    return " ".join(parts)


def tie_note(r):
    same = [o for o in r["others"] if abs(o["total"] - r["price"]) <= 0.01]
    split = [o for o in same if o["shipping"] > 0]
    text = "Gleicher Endpreis bei " + ", ".join(o["merchant"] for o in same[:6]) + "."
    if split:
        o = split[0]
        text += f" {o['merchant']}: {eur(o['price'])} plus {eur(o['shipping'])} Versand."
    return text


def win_note(r):
    best = r["best"]
    parts = [best["merchant"]]
    if long_delivery(best["delivery"]):
        parts.append(f"Lieferzeit {best['delivery']}")
    if not r["chip_listed"]:
        parts.append("CHIP Store ist auf dieser BestCheck-Seite nicht gelistet")
    return ". ".join(parts)


def conflict_cards(conflicts):
    cards = []
    shared = {}
    for c in conflicts:
        if c["kind"] == "shared_ean":
            shared.setdefault(c["gtin"], c)
    for gtin, c in shared.items():
        sibs = sorted(c["siblings"], key=lambda s: s["price"])
        names = ", ".join(f"{s['name']} für {eur(s['price'])}" for s in sibs)
        offer = c.get("chip_offer")
        bc = f" BestCheck zeigt für den CHIP Store {eur(offer['price'])} (Import {offer['updated']})." if offer else ""
        cards.append(("Eine EAN, mehrere Shop-Preise",
                      [f"{names} tragen dieselbe EAN {gtin}.{bc}",
                       f"Die teureren Seiten liegen bis zu {eur(sibs[-1]['price'] - sibs[0]['price'])} über dem günstigsten eigenen Eintrag derselben EAN."]))
    mism = [c for c in conflicts if c["kind"] == "price_mismatch"]
    known = [c for c in conflicts if c["kind"] == "known"]
    if mism or known:
        paras = [f"{c['name']} kostet im Shop {eur(c['price'])}, EAN {c['gtin']}. Der CHIP-Store-Eintrag auf der BestCheck-Seite dieser EAN zeigt {eur(c['chip_offer']['price'])}."
                 for c in mism]
        paras += [f"{c['name']} ({eur(c['price'])}): {c['text']}" for c in known]
        cards.append(("Shop-Preis passt nicht zum BestCheck-Eintrag", paras))
    for c in conflicts:
        if c["kind"] == "bware":
            new = c.get("cheapest_new")
            tail = f" Neuware beginnt dort bei {eur(new['total'])} ({new['merchant']})." if new else ""
            cards.append((f"{c['name']} ist B-Ware",
                          [f"Der Shop verkauft die geprüfte B-Ware für {eur(c['price'])}. BestCheck führt das Angebot auf der Neuware-Seite.{tail} Ein Bestpreis für Neuware ist das nicht."]))
    return cards


def donut_svg(segments, total):
    r, c = 70, 2 * math.pi * 70
    offset, circles = 0.0, []
    for value, color in segments:
        if value <= 0:
            continue
        length = c * value / total
        circles.append(f'<circle cx="100" cy="100" r="{r}" stroke="{color}" stroke-dasharray="{length:.2f} {c - length:.2f}" stroke-dashoffset="{-offset:.2f}"/>')
        offset += length
    return (f'<svg viewBox="0 0 200 200" width="230" height="230"><g transform="rotate(-90 100 100)" fill="none" stroke-width="34">'
            + "".join(circles)
            + f'</g><text x="100" y="98" text-anchor="middle" font-size="26" font-weight="700" fill="#111">{total}</text>'
            f'<text x="100" y="118" text-anchor="middle" font-size="12" fill="#666">Total</text></svg>')


def short_name(name):
    name = re.sub(r"^(Fensterputzroboter|Saugroboter|ECOVACS|Ecovacs|SAMSUNG|Samsung|TP-Link|UNOLD|Unold)\s+", "", name)
    name = re.sub(r"^(ECOVACS|Ecovacs|Fensterputzroboter)\s+", "", name)
    return name if len(name) <= 22 else name[:21] + "…"


def link(text, url):
    return f'<a href="{esc(url)}">{esc(text)}</a>' if url else esc(text)


def report_summary(groups):
    gap, tie, win = groups["gap"], groups["tie"], groups["win"]
    exclusive, missing, conflict = groups["exclusive"], groups["missing"], groups["conflict"]
    total = sum(len(v) for v in groups.values())
    gap_sum = sum(r["diff"] for r in gap)
    top3 = ", ".join(short_name(r["name"]) for r in gap[:3])
    headline = (
        f"Bei {len(gap)} von {total} Artikeln seid ihr nicht der günstigste Anbieter"
        if gap
        else "Bei allen vergleichbaren Artikeln liegt der CHIP Store vorn"
    )
    body = (
        f"Sobald BestCheck mindestens einen anderen Händler führt, liegt der CHIP Store bei {len(win)} Artikeln darunter, "
        f"bei {len(tie)} gleichauf und bei {len(gap)} darüber. Die Abstände summieren sich ungewichtet auf {eur(gap_sum)}."
        + (f" Am weitesten oben liegen {top3}." if gap else "")
    )
    return {
        "gap": gap,
        "tie": tie,
        "win": win,
        "exclusive": exclusive,
        "missing": missing,
        "conflict": conflict,
        "total": total,
        "gap_sum": gap_sum,
        "headline": headline,
        "body": body,
        "top3": top3,
    }


TEAMS_MARK = {"red": "🔴", "yellow": "🟡", "green": "🟢", "gray": "⚪", "black": "⚫"}


def teams_clip(text, width):
    text = str(text or "")
    if len(text) <= width:
        return text + " " * (width - len(text))
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def row_key(r):
    return r.get("gtin") or r.get("sku") or r.get("url") or r["name"]


def teams_product_labels(rows):
    labels = [short_name(r["name"]) for r in rows]
    out = []
    for label, r in zip(labels, rows):
        if labels.count(label) > 1:
            label = f"{label[:14].rstrip()}… {eur(r['price'])}"
        out.append(label)
    return out


def gap_change_status(r, prev_gap):
    if not prev_gap:
        return "red"
    old = prev_gap.get(row_key(r))
    if not old:
        return "red"
    same = (
        abs(old.get("diff", 0) - r["diff"]) <= 0.01
        and abs(old.get("price", 0) - r["price"]) <= 0.01
        and abs(old.get("best_total", 0) - r["best"]["total"]) <= 0.01
    )
    return "yellow" if same else "red"


def build_teams_state(groups, generated):
    gap = {
        row_key(r): {"price": r["price"], "diff": r["diff"], "best_total": r["best"]["total"]}
        for r in groups["gap"]
    }
    win = {
        row_key(r): {
            "price": r["price"],
            "advantage": round(-r["diff"], 2),
            "next_total": r["best"]["total"],
        }
        for r in groups["win"]
    }
    return {"date": generated.strftime("%Y-%m-%d"), "gap": gap, "win": win}


def load_teams_state(state_dir, generated):
    today = generated.date()
    latest_path, latest_day = None, None
    if not os.path.isdir(state_dir):
        return None
    for name in os.listdir(state_dir):
        m = re.match(r"preischeck-(\d{4}-\d{2}-\d{2})\.state\.json$", name)
        if not m:
            continue
        day = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if day >= today:
            continue
        if latest_day is None or day > latest_day:
            latest_day = day
            latest_path = os.path.join(state_dir, name)
    if not latest_path:
        return None
    with open(latest_path, encoding="utf-8") as f:
        return json.load(f)


def teams_gap_table(gap_rows, markers):
    """Fixed-width table for Teams (Markdown tables are not rendered in channel chat)."""
    w_prod, w_chip, w_best, w_shop, w_diff = 30, 12, 12, 18, 10
    header = "  ".join(
        [
            teams_clip("Produkt", w_prod),
            teams_clip("CHIP", w_chip),
            teams_clip("Günstigst.", w_best),
            teams_clip("Händler", w_shop),
            teams_clip("+Abstand", w_diff),
        ]
    )
    sep = "-" * len(header)
    labels = teams_product_labels(gap_rows)
    body = []
    for label, r, mark in zip(labels, gap_rows, markers):
        label = f"{TEAMS_MARK[mark]} {label}"
        body.append(
            "  ".join(
                [
                    teams_clip(label, w_prod),
                    teams_clip(eur(r["price"]), w_chip),
                    teams_clip(eur(r["best"]["total"]), w_best),
                    teams_clip(r["best"]["merchant"], w_shop),
                    teams_clip(f"+{eur(r['diff'])}", w_diff),
                ]
            )
        )
    return header, sep, body


def teams_win_table(win_rows):
    w_prod, w_chip, w_next, w_adv, w_shop = 30, 12, 12, 11, 18
    header = "  ".join(
        [
            teams_clip("Produkt", w_prod),
            teams_clip("CHIP", w_chip),
            teams_clip("Nächster", w_next),
            teams_clip("Günstiger", w_adv),
            teams_clip("Händler", w_shop),
        ]
    )
    sep = "-" * len(header)
    labels = teams_product_labels(win_rows)
    body = []
    for label, r in zip(labels, win_rows):
        label = f"{TEAMS_MARK['green']} {label}"
        body.append(
            "  ".join(
                [
                    teams_clip(label, w_prod),
                    teams_clip(eur(r["price"]), w_chip),
                    teams_clip(eur(r["best"]["total"]), w_next),
                    teams_clip(eur(-r["diff"]), w_adv),
                    teams_clip(r["best"]["merchant"], w_shop),
                ]
            )
        )
    return header, sep, body


def teams_tie_table(tie_rows):
    """Gleicher Endpreis wie der günstigste andere Händler. Grauer Punkt, kein Tagesvergleich."""
    w_prod, w_price, w_shop = 30, 12, 42
    header = "  ".join(
        [
            teams_clip("Produkt", w_prod),
            teams_clip("Endpreis", w_price),
            teams_clip("Gleichauf mit", w_shop),
        ]
    )
    sep = "-" * len(header)
    labels = teams_product_labels(tie_rows)
    body = []
    for label, r in zip(labels, tie_rows):
        same = [o["merchant"] for o in r["others"] if abs(o["total"] - r["price"]) <= 0.01]
        label = f"{TEAMS_MARK['gray']} {label}"
        body.append(
            "  ".join(
                [
                    teams_clip(label, w_prod),
                    teams_clip(eur(r["price"]), w_price),
                    teams_clip(", ".join(same[:4]), w_shop),
                ]
            )
        )
    return header, sep, body


def teams_missing_table(rows):
    w_prod, w_price, w_why = 34, 12, 42
    header = "  ".join(
        [
            teams_clip("Produkt", w_prod),
            teams_clip("CHIP", w_price),
            teams_clip("Grund", w_why),
        ]
    )
    sep = "-" * len(header)
    labels = teams_product_labels(rows)
    body = []
    for label, r in zip(labels, rows):
        label = f"{TEAMS_MARK['black']} {label}"
        body.append(
            "  ".join(
                [
                    teams_clip(label, w_prod),
                    teams_clip(eur(r["price"]), w_price),
                    teams_clip(r.get("reason") or "Im BestCheck-Frontend nicht gelistet", w_why),
                ]
            )
        )
    return header, sep, body


def render_teams_text(groups, generated, prev_state=None):
    s = report_summary(groups)
    stamp = generated.strftime("%d.%m.%Y")
    prev_gap = (prev_state or {}).get("gap") or {}
    prev_day = (prev_state or {}).get("date")
    compare = f"Vergleich zum Vortag ({datetime.strptime(prev_day, '%Y-%m-%d').strftime('%d.%m.%Y')})." if prev_day else "Erster Lauf — alle Einträge in der Teurer-Tabelle gelten als neu."
    lines = [
        f"# Preischeck vom {stamp}",
        "",
        "## Kurzfassung",
        f"**{s['headline']}**",
        "",
        s["body"],
        "",
        f"## Kennzahlen ({s['total']} Artikel)",
        "",
        f"- **Teurer als BestCheck:** {len(s['gap'])}",
        f"- **Günstigstes Angebot:** {len(s['win'])}",
        f"- **Geteilter Bestpreis:** {len(s['tie'])}",
        f"- **Nur CHIP Store:** {len(s['exclusive'])}",
        f"- **Auf Bestcheck nicht gelistet:** {len(s['missing'])}",
        f"- **Datensätze prüfen:** {len(s['conflict'])}",
        f"- **Summe Abstände (teurer):** {eur(s['gap_sum'])}",
        "",
        f"_{compare} 🔴 neu/geändert · 🟡 unverändert · ⚪ geteilter Preis · 🟢 Bestpreis · ⚫ nicht gelistet_",
    ]
    if s["gap"]:
        markers = [gap_change_status(r, prev_gap) for r in s["gap"]]
        header, sep, rows = teams_gap_table(s["gap"], markers)
        lines += [
            "",
            "## Teurer als BestCheck",
            "",
            "```",
            header,
            sep,
            *rows,
            "```",
        ]
    if s["tie"]:
        header, sep, rows = teams_tie_table(s["tie"])
        lines += [
            "",
            "## Geteilter Preis",
            f"_{len(s['tie'])} Artikel. Der CHIP-Store-Endpreis ist der günstigste, andere Händler liegen auf demselben Betrag._",
            "",
            "```",
            header,
            sep,
            *rows,
            "```",
        ]
    if s["win"]:
        header, sep, rows = teams_win_table(s["win"])
        lines += [
            "",
            f"## Bestpreis, andere Händler sind teurer",
            f"_{len(s['win'])} Artikel, sortiert nach dem Abstand zum nächstgünstigeren Angebot._",
            "",
            "```",
            header,
            sep,
            *rows,
            "```",
        ]
    if s["missing"]:
        header, sep, rows = teams_missing_table(s["missing"])
        lines += [
            "",
            "## Auf Bestcheck nicht gelistet",
            f"_{len(s['missing'])} Artikel. Für sie gibt es keine sichtbare BestCheck-Produktseite mit dieser EAN._",
            "",
            "```",
            header,
            sep,
            *rows,
            "```",
        ]
    lines += [
        "",
        "---",
        f"_Quelle: chipstore.de & bestcheck.de · Stand {stamp} (Europe/Berlin) · Endpreis inkl. Versand_",
    ]
    return "\n".join(lines)


def render(groups, generated):
    s = report_summary(groups)
    gap, tie, win = s["gap"], s["tie"], s["win"]
    exclusive, missing, conflict = s["exclusive"], s["missing"], s["conflict"]
    total, gap_sum = s["total"], s["gap_sum"]
    headline, body, top3 = s["headline"], s["body"], s["top3"]
    pct = lambda n: f"{(100 * n / total):.0f} %" if total else "0 %"
    colors = {"gap": "#d1555b", "win": "#3fb68b", "tie": "#5aa9e6", "exclusive": "#8e8db5", "missing": "#f2a650", "conflict": "#eccb48"}
    segs = [(len(gap), colors["gap"]), (len(win), colors["win"]), (len(tie), colors["tie"]),
            (len(exclusive), colors["exclusive"]), (len(missing), colors["missing"]), (len(conflict), colors["conflict"])]
    legend = [("Nicht Bestpreis", len(gap), colors["gap"]), ("Bestpreis", len(win), colors["win"]),
              ("Gleichauf", len(tie), colors["tie"]), ("Nur CHIP Store", len(exclusive), colors["exclusive"]),
              ("Kein BestCheck-Eintrag", len(missing), colors["missing"]), ("Daten prüfen", len(conflict), colors["conflict"])]
    max_diff = max((r["diff"] for r in gap), default=1)

    labels = [short_name(r["name"]) for r in gap]
    labels = [f"{l[:14].rstrip()}… {eur(r['price'])}" if labels.count(l) > 1 else l for l, r in zip(labels, gap)]
    bars = "".join(
        f'<div class="bar"><span class="bl">{esc(label)}</span>'
        f'<span class="bt"><span class="bf" style="width:{max(1.2, 100 * r["diff"] / max_diff):.1f}%"></span>'
        f'<span class="bv">{eur(r["diff"])}</span></span></div>' for label, r in zip(labels, gap))

    gap_rows = "".join(
        f'<tr><td class="dot red">{link(r["name"], r["url"])}</td><td class="n">{eur(r["price"])}</td>'
        f'<td class="n">{link(eur(r["best"]["total"]) + " · " + r["best"]["merchant"], r["bc"]["url"])}</td>'
        f'<td class="n">+{eur(r["diff"])}</td><td class="n">{len(r["others"])}</td><td>{esc(gap_note(r))}</td></tr>' for r in gap)
    tie_rows = "".join(
        f'<tr><td class="dot blue">{link(r["name"], r["url"])}</td><td class="n">{eur(r["price"])}</td><td>{esc(tie_note(r))}</td></tr>' for r in tie)
    win_rows = "".join(
        f'<tr><td class="dot green">{esc(r["name"])}</td><td class="n">{eur(r["price"])}</td><td class="n">{eur(r["best"]["total"])}</td>'
        f'<td class="n">{eur(-r["diff"])}</td><td>{esc(win_note(r))}</td></tr>' for r in win)
    excl_rows = "".join(
        f'<tr><td>{esc(r["name"])}</td><td class="n">{eur(r["price"])}</td><td class="n">{eur(r["list_price"])}</td></tr>' for r in exclusive)
    miss_rows = "".join(
        f'<tr><td>{esc(r["name"])}</td><td class="n">{eur(r["price"])}</td><td>{esc(r["reason"])}</td></tr>' for r in missing)
    cards = "".join(
        f'<div class="card"><div class="ch">{esc(t)}</div>' + "".join(f"<p>{esc(x)}</p>" for x in paras) + "</div>"
        for t, paras in conflict_cards(conflict))

    stamp = generated.strftime("%d.%m.%Y, %H:%M Uhr")

    def section(title, intro, head, rows):
        if not rows:
            return ""
        return f'<h2>{title}</h2>' + (f'<p class="sub">{intro}</p>' if intro else "") + f'<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>CHIP Store gegen BestCheck – {esc(stamp)}</title>
<style>
@page {{ size: A4 landscape; margin: 10mm 12mm; }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1d1d1f; font-size: 11.5px; line-height: 1.45; background: #fff; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 18px 8px 24px; }}
h1 {{ font-size: 22px; margin: 0 0 6px; font-weight: 650; }}
h2 {{ font-size: 15px; margin: 22px 0 6px; font-weight: 650; break-after: avoid; }}
p {{ margin: 0 0 6px; }}
.lead {{ color: #555; max-width: 980px; }}
.callout {{ display: flex; gap: 10px; margin: 14px 0 10px; }}
.callout .ic {{ color: #e0a100; font-weight: 700; font-size: 14px; line-height: 1.2; }}
.callout b {{ display: block; margin-bottom: 2px; }}
.overview {{ display: flex; align-items: center; gap: 36px; margin: 6px 0 2px; break-inside: avoid; }}
.stats {{ display: flex; gap: 46px; margin-bottom: 12px; }}
.stat b {{ display: block; font-size: 26px; font-weight: 650; line-height: 1.1; }}
.stat span {{ color: #555; font-size: 11px; }}
.r {{ color: #d1555b; }} .g {{ color: #3fb68b; }} .bl2 {{ color: #5aa9e6; }}
.small {{ color: #555; font-size: 10.5px; max-width: 520px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 10.5px; color: #444; margin: 4px 0 8px 10px; }}
.legend i {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; vertical-align: 0; }}
.legend em {{ color: #888; font-style: normal; margin-left: 3px; }}
.bars {{ break-inside: avoid; margin-top: 4px; }}
.bar {{ display: flex; align-items: center; margin: 5px 0; }}
.bl {{ width: 135px; text-align: right; padding-right: 10px; color: #444; font-size: 10.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.bt {{ flex: 1; display: flex; align-items: center; gap: 6px; border-left: 1px solid #ddd; }}
.bf {{ display: block; height: 14px; background: #d1555b; border-radius: 0 2px 2px 0; }}
.bv {{ font-size: 10.5px; font-weight: 600; white-space: nowrap; }}
.cap {{ color: #777; font-size: 10px; margin: 4px 0 0; }}
.sub {{ color: #555; }}
table {{ width: 100%; border-collapse: collapse; border: 1px solid #e3e3e3; border-radius: 6px; font-size: 10.5px; }}
thead {{ display: table-header-group; }}
th {{ text-align: left; font-weight: 600; color: #555; background: #f6f6f6; padding: 6px 8px; border-bottom: 1px solid #e3e3e3; }}
td {{ padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }}
tr {{ break-inside: avoid; }}
tbody tr:nth-child(even) td {{ background: #fafafa; }}
td.n, th.n {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
td.dot::before {{ content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; }}
td.red::before {{ background: #d1555b; }} td.green::before {{ background: #3fb68b; }} td.blue::before {{ background: #5aa9e6; }}
a {{ color: #1d1d1f; text-decoration: underline; text-decoration-color: #bbb; }}
.two {{ display: flex; gap: 18px; align-items: flex-start; }}
.two > div {{ flex: 1; }}
.card {{ border: 1px solid #e3e3e3; border-radius: 6px; padding: 9px 12px; margin: 8px 0; break-inside: avoid; }}
.ch {{ font-weight: 600; margin-bottom: 4px; }}
.info {{ display: flex; gap: 10px; margin-top: 18px; color: #333; break-inside: avoid; }}
.info .ic {{ color: #5aa9e6; font-weight: 700; }}
.page2 {{ break-before: page; }}
</style></head><body><main>
<h1>CHIP Store gegen BestCheck</h1>
<p class="lead">Live-Preise von chipstore.de gegen die Händlerangebote auf bestcheck.de, zugeordnet über die EAN. Stand {esc(stamp)} (Europe/Berlin). Verglichen ist der Endpreis inklusive ausgewiesener Versandkosten. Der CHIP Store liefert versandfrei, der Artikelpreis ist dort der Endpreis.</p>
<div class="callout"><span class="ic">⚠</span><div><b>{esc(headline)}</b>{esc(body)}</div></div>
<div class="overview">
  <div>{donut_svg(segs, total)}</div>
  <div>
    <div class="stats">
      <div class="stat"><b class="r">{len(gap)}</b><span>Über dem günstigsten<br>Angebot</span></div>
      <div class="stat"><b class="g">{len(win)}</b><span>Günstigstes Angebot</span></div>
      <div class="stat"><b class="bl2">{len(tie)}</b><span>Geteilter Bestpreis</span></div>
    </div>
    <p class="small">{len(exclusive)} Produkte führt BestCheck nur beim CHIP Store, {len(missing)} Artikel haben dort keinen belastbaren Eintrag, {len(conflict)} Datensätze sind widersprüchlich und unten einzeln erklärt. Quelle: Produktseiten chipstore.de und Angebots-API bestcheck.de, {generated.strftime("%d.%m.%Y")}.</p>
  </div>
</div>
<div class="legend">{"".join(f'<span><i style="background:{c}"></i>{l}<em>{pct(n)}</em></span>' for l, n, c in legend)}</div>
{f'<h2>Abstand zum günstigsten BestCheck-Angebot</h2><div class="bars">{bars}</div><p class="cap">Differenz in Euro, Endpreis inklusive Versand. Quelle: BestCheck-Angebote vom {generated.strftime("%d.%m.%Y")}.</p>' if gap else ""}
<div class="page2">
{section("Diese Preise sind nicht der Bestpreis", "", '<th>Produkt</th><th class="n">CHIP Store</th><th class="n">Günstigster Endpreis</th><th class="n">Abstand</th><th class="n">Andere Händler</th><th>Hinweis</th>', gap_rows)}
{section("Geteilter Bestpreis", "Bei diesen Artikeln ist der CHIP-Store-Endpreis der günstigste, andere Händler liegen auf demselben Betrag.", '<th>Produkt</th><th class="n">Endpreis</th><th>Lage</th>', tie_rows)}
{section("Bestpreis, andere Händler sind teurer", f"{len(win)} Artikel, sortiert nach dem Abstand zum nächstgünstigeren Angebot.", '<th>Produkt</th><th class="n">CHIP Store</th><th class="n">Nächster Endpreis</th><th class="n">Günstiger um</th><th>Händler</th>', win_rows)}
<div class="two">
  <div>{section("Nur der CHIP Store auf BestCheck", "BestCheck zeigt keinen zweiten Händler. Der Preis ist dort das einzige Angebot, ein Marktvergleich fehlt.", '<th>Produkt</th><th class="n">Preis</th><th class="n">Streichpreis</th>', excl_rows)}</div>
  <div>{section("Kein belastbarer BestCheck-Eintrag", "Zu diesen Artikeln lässt sich auf BestCheck nichts sagen.", '<th>Produkt</th><th class="n">Preis</th><th>Grund</th>', miss_rows)}</div>
</div>
{f'<h2>{len(conflict)} Datensätze vor einer Preisentscheidung prüfen</h2>{cards}' if conflict else ""}
<div class="info"><span class="ic">ⓘ</span><div><b>Was der Vergleich abdeckt</b><br>BestCheck bündelt die angebundenen Shops, nicht den gesamten Markt. Marketplace-Angebote sind enthalten. Angebote mit sehr langer Lieferzeit zählen beim Preis mit und sind in der Zeile benannt.</div></div>
</div>
</main></body></html>"""


def find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def print_pdf(html_path, pdf_path):
    chrome = find_chrome()
    if not chrome:
        raise SystemExit("Kein Chrome/Chromium gefunden. Bitte installieren: apt-get install -y chromium")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    # Headless Chrome in containers often writes the PDF but never exits.
    proc = subprocess.Popen([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                             "--no-first-run", "--no-pdf-header-footer", "--user-data-dir=/tmp/preischeck-chrome",
                             f"--print-to-pdf={pdf_path}", f"file://{os.path.abspath(html_path)}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline, last_size, stable = time.time() + 120, -1, 0
    while time.time() < deadline:
        if proc.poll() is not None and os.path.exists(pdf_path):
            break
        size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else -1
        stable = stable + 1 if size > 0 and size == last_size else 0
        last_size = size
        if stable >= 3:
            break
        time.sleep(1)
    if proc.poll() is None:
        proc.kill()
        proc.wait()
    if not os.path.exists(pdf_path):
        raise SystemExit("PDF-Erzeugung fehlgeschlagen.")
    with open(pdf_path, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise SystemExit("PDF-Erzeugung fehlgeschlagen.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    ap.add_argument("--state-dir", default="state", help="Ordner für .state.json (Tagesvergleich, versioniert)")
    ap.add_argument("--no-pdf", action="store_true", help="Kein PDF erzeugen (nur HTML + Teams-Text)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.state_dir, exist_ok=True)
    generated = datetime.now(BERLIN)
    groups = classify(collect())
    stem = f"preischeck-{generated.strftime('%Y-%m-%d')}"
    html_path = os.path.join(args.out, stem + ".html")
    pdf_path = os.path.join(args.out, stem + ".pdf")
    teams_path = os.path.join(args.out, stem + ".teams.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render(groups, generated))
    prev_state = load_teams_state(args.state_dir, generated)
    teams_text = render_teams_text(groups, generated, prev_state)
    with open(teams_path, "w", encoding="utf-8") as f:
        f.write(teams_text)
    state_path = os.path.join(args.state_dir, stem + ".state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(build_teams_state(groups, generated), f, ensure_ascii=False, indent=2)
    if not args.no_pdf:
        print_pdf(html_path, pdf_path)
    summary = {k: len(v) for k, v in groups.items()}
    payload = {
        "html": html_path,
        "teams_text": teams_path,
        "state": state_path,
        "counts": summary,
    }
    if not args.no_pdf:
        payload["pdf"] = pdf_path
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
