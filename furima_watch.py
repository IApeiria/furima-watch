"""フリマ横断ウォッチャー（furima-watch）.

メルカリ・ヤフオク・PayPayフリマ・ラクマ・じゃんぱら・ソフマップ・ハードオフを巡回し、
条件に合う出品を見つけたら Windows 通知（任意で ntfy.sh 経由のスマホ通知）を出す。
監視対象は config.toml に書く（なければ config.example.toml を使う）。
一度通知した出品は seen.json に記録し、再通知しない（値下げで再び条件を満たした場合は再通知）。

使い方:
    python furima_watch.py            # 1 回巡回（タスクスケジューラから定期実行）
    python furima_watch.py --dry-run  # 通知・記録せず、該当候補を表示するだけ
    python furima_watch.py --test-notify
    python furima_watch.py --config my.toml
"""
import argparse
import asyncio
import json
import logging
import re
import sys
import time
import tomllib
import traceback
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "seen.json"
LOG_FILE = HERE / "furima_watch.log"
JST = timezone(timedelta(hours=9))

# どの商品でも共通で除外するもの（空箱・買取広告など）
COMMON_EXCLUDE = ["箱のみ", "空箱", "外箱", "化粧箱のみ", "買取", "求む", "探して", "レンタル", "代行"]
JUNK_RE = re.compile(r"ジャンク|junk|故障|不動|動作不良|訳あり")

log = logging.getLogger("furima_watch")


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def any_re(patterns):
    # タイトルは norm() 済み（全角→半角・小文字）なので、パターンも半角で書く
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I) if patterns else None


@dataclass
class Item:
    source: str
    id: str
    title: str
    price: int
    url: str
    note: str = ""


@dataclass
class Watch:
    name: str
    queries: list
    max_price: int
    min_price: int = 0
    shop_query: str = ""       # 中古ショップ（じゃんぱら等）用の検索語。空なら queries[0]
    target: list = field(default_factory=list)   # タイトルがどれか 1 つに一致すれば対象（空なら全部）
    exclude: list = field(default_factory=list)  # どれか 1 つに一致すれば除外
    include_junk: bool = False

    def __post_init__(self):
        self.target_re = any_re(self.target)
        self.exclude_re = any_re(COMMON_EXCLUDE + self.exclude)

    @property
    def shop_q(self):
        return self.shop_query or self.queries[0]

    def matches(self, it: Item) -> bool:
        if not self.min_price <= it.price <= self.max_price:
            return False
        t = norm(it.title)
        if self.target_re and not self.target_re.search(t):
            return False
        if self.exclude_re.search(t):
            return False
        return self.include_junk or not JUNK_RE.search(t)


@dataclass
class Settings:
    auction_ending_hours: int = 12   # ヤフオク: 即決なしでも、現在価格が条件内かつ残りこの時間以内なら通知
    ntfy_topic: str = ""             # スマホにも飛ばしたい場合、ntfy.sh のトピック名（空なら無効）
    fail_alert_after: int = 6        # 同じサイトがこの回数連続で失敗したら一度だけ通知


def load_config(path=None):
    if path is None:
        path = HERE / "config.toml"
        if not path.exists():
            path = HERE / "config.example.toml"
    cfg = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    watches = [Watch(**w) for w in cfg.get("watch", [])]
    if not watches:
        sys.exit(f"{path} に [[watch]] がありません")
    return watches, Settings(**cfg.get("settings", {}))


def price_int(s) -> int:
    d = re.sub(r"[^\d]", "", str(s))
    return int(d) if d else 0


def get(url, allow_404=False, **kw):
    r = requests.get(url, impersonate="chrome", timeout=25, **kw)
    if r.status_code >= 500:  # 一時的な混雑はもう一度だけ試す
        time.sleep(5)
        r = requests.get(url, impersonate="chrome", timeout=25, **kw)
    if not (allow_404 and r.status_code == 404):
        r.raise_for_status()
    return r


# ---- 各サイト -------------------------------------------------------------
def src_mercari(w: Watch, cfg: Settings):
    from mercapi import Mercapi
    from mercapi.requests import SearchRequestData as S

    async def run():
        m = Mercapi()
        out = []
        for q in w.queries:
            res = await m.search(
                q, price_min=w.min_price or None, price_max=w.max_price,
                status=[S.Status.STATUS_ON_SALE],
                sort_by=S.SortBy.SORT_CREATED_TIME, sort_order=S.SortOrder.ORDER_DESC,
            )
            for it in res.items:
                url = (f"https://jp.mercari.com/item/{it.id_}" if it.id_.startswith("m")
                       else f"https://jp.mercari.com/shops/product/{it.id_}")
                out.append(Item("メルカリ", it.id_, it.name, it.price, url))
        return out

    return asyncio.run(run())


def _next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}


def src_yahoo_auction(w: Watch, cfg: Settings):
    out = []
    now = datetime.now(JST)
    for q in w.queries:
        url = (f"https://auctions.yahoo.co.jp/search/search?p={quote_plus(q)}"
               f"&va={quote_plus(q)}&exflg=1&b=1&n=100&s1=new&o1=d")
        d = _next_data(get(url, allow_404=True).text)  # 検索結果 0 件だと 404 が返る
        items = (d.get("props", {}).get("pageProps", {}).get("initialState", {})
                 .get("search", {}).get("items", {}).get("listing", {}).get("items", []))
        for o in items:
            aid, title = o["auctionId"], o.get("title", "")
            link = f"https://auctions.yahoo.co.jp/jp/auction/{aid}"
            buy, cur = o.get("buyNowPrice"), o.get("price") or 0
            if buy and w.min_price <= buy <= w.max_price:
                out.append(Item("ヤフオク", aid, title, buy, link, "即決"))
                continue
            try:
                end = datetime.fromisoformat(o["endTime"])
            except (KeyError, ValueError):
                continue
            left = end - now
            if w.min_price <= cur <= w.max_price and left <= timedelta(hours=cfg.auction_ending_hours):
                hrs = max(0, int(left.total_seconds() // 3600))
                # 現在価格で ID を分け、値上がり後に再び条件を満たしても重複しないよう auction ID 単位にする
                out.append(Item("ヤフオク", aid + ":bid", title, cur, link,
                                f"入札{o.get('bidCount', 0)}件・残り約{hrs}時間"))
    return out


def src_paypay(w: Watch, cfg: Settings):
    out = []
    for q in w.queries:
        url = ("https://paypayfleamarket.yahoo.co.jp/api/v1/search?"
               f"query={quote_plus(q)}&results=100&sort=openTime&order=desc&itemStatus=open"
               f"&minPrice={w.min_price}&maxPrice={w.max_price}")
        d = get(url, headers={"Referer": "https://paypayfleamarket.yahoo.co.jp/"}).json()
        for it in d.get("items", []):
            if it.get("itemStatus") != "OPEN":
                continue
            out.append(Item("PayPayフリマ", it["id"], it["title"], it["price"],
                            f"https://paypayfleamarket.yahoo.co.jp/item/{it['id']}"))
    return out


def src_rakuma(w: Watch, cfg: Settings):
    out = []
    for q in w.queries:
        url = (f"https://fril.jp/s?query={quote_plus(q)}&min={w.min_price}&max={w.max_price}"
               "&transaction=selling&sort=created_at&order=desc")
        s = BeautifulSoup(get(url).text, "html.parser")
        for a in s.select("div.item a.link_search_image[data-rat-item_name]"):
            href = a["href"]
            out.append(Item("ラクマ", href.rsplit("/", 1)[-1], a["data-rat-item_name"],
                            price_int(a.get("data-rat-price")), href))
    return out


def src_janpara(w: Watch, cfg: Settings):
    out = []
    url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={quote_plus(w.shop_q)}"
    s = BeautifulSoup(get(url).text, "html.parser")
    for div in s.select("div.search_item_s"):
        a = div.select_one("a.search_itemlink")
        name = div.select_one(".search_itemname")
        price = div.select_one(".item_amount")
        cond = div.select_one(".search_itemcondition")
        if not (a and name and price):
            continue
        code = re.search(r"ITMCODE=(\d+)", a["href"])
        p = price_int(price.get_text())
        # 同一型番の最安値表示なので、価格込みで ID 化（さらに安い在庫が出たら再通知）
        out.append(Item("じゃんぱら", f"{code.group(1) if code else a['href']}@{p}",
                        name.get_text(" ", strip=True), p,
                        "https://www.janpara.co.jp" + a["href"].split("&")[0],
                        cond.get_text(strip=True) if cond else ""))
    return out


def src_sofmap(w: Watch, cfg: Settings):
    out = []
    url = ("https://www.sofmap.com/product_list_parts.aspx?gid=&is_page=serch_result&pno=1"
           f"&keyword={quote_plus(w.shop_q)}&product_type=USED&dispcnt=100&styp=p_page")
    s = BeautifulSoup(get(url).text, "html.parser")
    for li in s.select("ul.product_list > li"):
        a = li.select_one("a.product_name")
        price = li.select_one("span.price")
        if not (a and price):
            continue
        sku = re.search(r"sku=(\d+)", a["href"])
        shop = li.select_one("dl.used_link dd")
        out.append(Item("ソフマップ", sku.group(1) if sku else a["href"], a.get_text(strip=True),
                        price_int(price.find("strong").contents[0] if price.find("strong") else price.get_text()),
                        a["href"], shop.get_text(strip=True) if shop else ""))
    return out


def src_hardoff(w: Watch, cfg: Settings):
    out = []
    url = f"https://netmall.hardoff.co.jp/search/?q={quote_plus(w.shop_q)}&s=1"
    s = BeautifulSoup(get(url).text, "html.parser")
    for div in s.select("div.itemcolmn_item"):
        if "itemcolmn_item--soldout" in (div.get("class") or []):
            continue
        a = div.find("a", href=True)
        price = div.select_one(".item-price-en")
        if not (a and price):
            continue
        title = " ".join(x.get_text(strip=True) for x in div.select(".item-brand-name, .item-name, .item-code"))
        pid = re.search(r"/product/(\d+)", a["href"])
        out.append(Item("ハードオフ", pid.group(1) if pid else a["href"], title,
                        price_int(price.contents[0]), a["href"]))
    return out


SOURCES = {
    "メルカリ": src_mercari,
    "ヤフオク": src_yahoo_auction,
    "PayPayフリマ": src_paypay,
    "ラクマ": src_rakuma,
    "じゃんぱら": src_janpara,
    "ソフマップ": src_sofmap,
    "ハードオフ": src_hardoff,
}


# ---- 通知・状態 -----------------------------------------------------------
def notify(cfg: Settings, title, msg, url=None):
    try:
        from winotify import Notification, audio
        n = Notification(app_id="furima-watch", title=title, msg=msg, duration="long")
        n.set_audio(audio.Default, loop=False)
        if url:
            n.add_actions(label="開く", launch=url)
            n.launch = url
        n.show()
    except Exception:
        log.error("toast failed:\n%s", traceback.format_exc())
    if cfg.ntfy_topic:
        try:
            headers = {"Title": title.encode("utf-8"), "Tags": "moneybag"}
            if url:
                headers["Click"] = url
            requests.post(f"https://ntfy.sh/{cfg.ntfy_topic}", data=msg.encode("utf-8"),
                          headers=headers, timeout=15)
        except Exception:
            log.error("ntfy failed:\n%s", traceback.format_exc())


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": {}, "fails": {}}


def save_state(st):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


def run(watches, cfg: Settings, dry_run=False):
    st = load_state()
    st.setdefault("seen", {})
    st.setdefault("fails", {})
    hits = {}
    failed = set()
    for w in watches:
        for name, fn in SOURCES.items():
            try:
                items = fn(w, cfg)
            except Exception:
                failed.add(name)
                log.error("%s / %s failed:\n%s", w.name, name, traceback.format_exc())
                continue
            found = [it for it in items if w.matches(it)]
            log.info("%s / %s: %d listings, %d match", w.name, name, len(items), len(found))
            for it in found:
                hits.setdefault(f"{w.name}|{it.source}:{it.id}", (w, it))

    for name in SOURCES:
        n = st["fails"].get(name, 0) + 1 if name in failed else 0
        st["fails"][name] = n
        if n == cfg.fail_alert_after and not dry_run:
            notify(cfg, "furima-watch: 取得エラー", f"{name} が {n} 回連続で取得失敗。サイト構成が変わったかも。")

    new = [(k, w, it) for k, (w, it) in hits.items() if k not in st["seen"]]
    for k, w, it in sorted(new, key=lambda x: x[2].price):
        line = f"[{w.name}] ¥{it.price:,} [{it.source}] {it.title} {it.note} {it.url}"
        log.info("NEW %s", line)
        print(line)
        if not dry_run:
            notify(cfg, f"{w.name} ¥{it.price:,}（{it.source}）", f"{it.title}\n{it.note}".strip(), it.url)
            st["seen"][k] = {"t": datetime.now(JST).isoformat(timespec="seconds"),
                             "price": it.price, "title": it.title, "url": it.url}
    # 30 日以上前の記録は掃除
    cutoff = (datetime.now(JST) - timedelta(days=30)).isoformat()
    st["seen"] = {k: v for k, v in st["seen"].items() if v.get("t", "") >= cutoff}
    if not dry_run:
        save_state(st)
    log.info("run done: %d matches, %d new", len(hits), len(new))
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, help="設定ファイル（既定: config.toml → config.example.toml）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    args = ap.parse_args()
    handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stdout and sys.stdout.isatty() or args.dry_run:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    watches, cfg = load_config(args.config)
    if args.test_notify:
        q = quote_plus(watches[0].queries[0])
        notify(cfg, "furima-watch テスト", "通知はこんな感じで届きます（クリックでメルカリ検索を開く）",
               f"https://jp.mercari.com/search?keyword={q}")
        return
    run(watches, cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
