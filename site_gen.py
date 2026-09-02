#!/usr/bin/env python3
"""
site_gen.py — 程序化加密数据站生成器（Phase 1 MVP）
=====================================================
本机 Binance 实时数据流 → 静态 SEO 页面（币种页 × Top50 + 首页 + sitemap + llms.txt）。

设计依据（2026 调研）：
  - 数据站模式算法免疫（CoinMarketCap/CoinGecko 模式，ICODA 2026）
  - AEO 答案块 134-167 词、问题式标题、FAQ schema（LuvKaizen 2026）
  - llms.txt 供 AI 爬虫（GPTBot/ClaudeBot/PerplexityBot 不执行 JS）
  - 返佣 CTA 全站嵌入（币安 90 天 cookie，Referral Pro）

用法：
  python3 site_gen.py                 # 全量生成到 public/
  python3 site_gen.py --top 20        # 只生成 Top20（快速测试）
  python3 site_gen.py --dry-run       # 只打印将生成哪些币页

输出：public/ 静态站（部署到 Cloudflare Pages / GitHub Pages）。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PUBLIC = BASE / "public"
TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
KLINE_URL = "https://api.binance.com/api/v3/klines?symbol={}&interval=1h&limit=24"

# 站点配置（部署后替换为真实域名；也可用环境变量 SITE_URL 覆盖）
import os as _os
SITE_URL = _os.environ.get("SITE_URL", "https://cryptodata.example.com")
SITE_NAME = "CryptoData Live"
SITE_DESC = ("Live cryptocurrency prices, 24h market data and coin guides. "
             "Real-time data from Binance, refreshed hourly.")

# 返佣资产
REF_URL = "https://web3.binance.com/referral?ref=ME8O8S1F"
REF_CODE = "ME8O8S1F"

# Google Search Console 验证（用户提供；meta 标签 + 验证文件双保险）
GSC_VERIFY = "googlea70d9f982413021c"
GSC_META = f'<meta name="google-site-verification" content="{GSC_VERIFY}" />'

# 稳定币/稳定币对：跳过（不生成页面）
STABLES = {"USDC", "FDUSD", "TUSD", "DAI", "USD1", "USDP", "EUR", "BUSD", "AEUR",
           "RLUSD", "U", "USDE", "USDS", "PYUSD", "GUSD", "USDY", "FRAX"}
# 代币化黄金/白银（非加密币，无推广价值）
GOLD_TOKENS = {"XAUT", "PAXG", "XAGX"}
# 杠杆代币后缀（跳过）
LEVERAGED_END = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")

# 知名币种全名（用于标题/H1 可读性；未知币用符号名）
COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB",
    "XRP": "XRP", "DOGE": "Dogecoin", "ADA": "Cardano", "AVAX": "Avalanche",
    "LINK": "Chainlink", "TRX": "TRON", "DOT": "Polkadot", "LTC": "Litecoin",
    "BCH": "Bitcoin Cash", "SHIB": "Shiba Inu", "SUI": "Sui", "APT": "Aptos",
    "ARB": "Arbitrum", "OP": "Optimism", "MATIC": "Polygon", "POL": "Polygon",
    "TON": "Toncoin", "NEAR": "NEAR Protocol", "ATOM": "Cosmos", "UNI": "Uniswap",
    "FIL": "Filecoin", "ETC": "Ethereum Classic", "XLM": "Stellar", "ICP": "Internet Computer",
    "HBAR": "Hedera", "CRO": "Cronos", "AAVE": "Aave", "MKR": "Maker",
    "LDO": "Lido DAO", "RNDR": "Render", "GRT": "The Graph", "STX": "Stacks",
    "INJ": "Injective", "SEI": "Sei", "PEPE": "Pepe", "WIF": "dogwifhat",
    "BONK": "Bonk", "FLOKI": "Floki", "ORDI": "Ordinals", "JUP": "Jupiter",
    "TIA": "Celestia", "DYDX": "dYdX", "ENA": "Ethena", "ONDO": "Ondo",
    "TAO": "Bittensor", "FET": "Fetch.ai", "AGIX": "SingularityNET", "RUNE": "THORChain",
}

def fetch_json(url: str) -> list | dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fmt_price(p: float) -> str:
    if p >= 1000: return f"{p:,.2f}"
    if p >= 1: return f"{p:,.4f}"
    if p >= 0.01: return f"{p:.5f}"
    return f"{p:.8f}"

def coin_name(sym: str) -> str:
    return COIN_NAMES.get(sym, sym)

def collect(top_n: int) -> list[dict]:
    """全量 24hr ticker → 过滤稳定币/杠杆 → 按成交额取 Top N。"""
    allt = fetch_json(TICKER_URL)
    rows = []
    for t in allt:
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        price = float(t["lastPrice"])
        pct = float(t["priceChangePercent"])
        # 过滤：已知稳定币、黄金代币、杠杆代币
        if base in STABLES or base in GOLD_TOKENS or any(s.endswith(x) for x in LEVERAGED_END):
            continue
        # 动态稳定币检测：价格≈$1 且 24h 几乎不动
        if 0.98 <= price <= 1.02 and abs(pct) < 0.3:
            continue
        rows.append({
            "sym": base,
            "price": price,
            "pct": pct,
            "high": float(t["highPrice"]),
            "low": float(t["lowPrice"]),
            "vol": float(t["volume"]),
            "qvol": float(t["quoteVolume"]),
        })
    rows.sort(key=lambda r: r["qvol"], reverse=True)
    return rows[:top_n]

def movers(rows: list[dict], n: int = 5) -> tuple[list[dict], list[dict]]:
    """从已采集数据中取 24h 涨幅榜/跌幅榜（过滤小成交额垃圾币）。"""
    liquid = [r for r in rows if r["qvol"] >= 5_000_000]
    gainers = sorted(liquid, key=lambda r: r["pct"], reverse=True)[:n]
    losers = sorted(liquid, key=lambda r: r["pct"])[:n]
    return gainers, losers

# ---- 对比页（买家词，转化最高的内容类型；数据基于 2026 调研，硬编码） ----
COMPARE_PAGES = [
    {
        "slug": "binance-vs-okx",
        "title": "Binance vs OKX: Which Exchange Is Better in 2026?",
        "h1": "Binance vs OKX (2026): Fees, Commissions & Features Compared",
        "ans": ("Binance and OKX are two of the largest cryptocurrency exchanges, but they differ in "
                "referral rewards, product depth and regional availability. Binance offers the longest "
                "affiliate attribution window in the industry at 90 days, versus 30 days on OKX, and "
                "operates the deepest spot and futures liquidity. OKX counters with a strong derivatives "
                "suite and its own Web3 wallet ecosystem. For most new traders, Binance wins on market "
                "depth, fee-referral terms and the range of listed assets; OKX is a solid alternative "
                "when Binance is unavailable in your region. This page compares both exchanges across "
                "fees, referral commissions, security and supported countries, updated for 2026."),
        "faq": [
            ("Is Binance better than OKX?",
             "Binance generally offers deeper liquidity, more listed assets and a 90-day referral cookie "
             "window (OKX: 30 days). If Binance is available in your region, most traders find it the "
             "better all-round choice for spot and futures trading."),
            ("Which exchange pays higher referral commissions?",
             "Binance pays up to 50% commission on spot fees for top affiliates (base 20-40%), plus a "
             "content creator bonus up to $3,000/month. OKX pays 20-40% depending on tier."),
            ("Can I use both Binance and OKX?",
             "Yes. Many traders hold accounts on both to compare liquidity and take advantage of each "
             "platform's promotions."),
        ],
        "table": [
            ("Referral cookie window", "90 days", "30 days"),
            ("Spot commission (affiliate)", "up to 50%", "up to 40%"),
            ("Futures commission", "up to 50%", "up to 40%"),
            ("Liquidity depth", "Highest", "High"),
            ("Web3 wallet", "Yes", "Yes"),
            ("Content creator bonus", "Up to $3,000/mo", "No"),
        ],
    },
    {
        "slug": "binance-vs-bybit",
        "title": "Binance vs Bybit: Fees, Referrals & Features Compared 2026",
        "h1": "Binance vs Bybit (2026): Which Crypto Exchange Should You Use?",
        "ans": ("Binance and Bybit are both top-tier crypto exchanges, but they target slightly different "
                "traders. Binance is the world's largest exchange with the broadest asset selection and a "
                "90-day referral attribution window. Bybit is a derivatives-first platform with a popular "
                "Web3 wallet and strong copy-trading features, but its referral cookie lasts only 30 days. "
                "For beginners Binance's larger ecosystem and educational resources are easier to grow "
                "into; for derivatives specialists Bybit's interface may feel more direct. Both support "
                "spot, futures, staking and a built-in Web3 wallet. This comparison focuses on the "
                "differences that matter: referral terms, fees, liquidity and regional availability."),
        "faq": [
            ("Is Bybit safer than Binance?",
             "Both are regulated in multiple jurisdictions and hold large trading volumes. Binance has "
             "the longer track record; Bybit is also a major exchange. Security practices are broadly "
             "comparable for mainstream users."),
            ("Which has better referral rewards, Binance or Bybit?",
             "Binance: 90-day cookie and up to 50% spot commission. Bybit: 30-day cookie and up to 30%. "
             "Binance's longer attribution window makes it better for content sites and reviews."),
            ("Which exchange has more coins?",
             "Binance lists significantly more assets than Bybit across spot and futures markets."),
        ],
        "table": [
            ("Referral cookie window", "90 days", "30 days"),
            ("Spot commission (affiliate)", "up to 50%", "up to 30%"),
            ("Futures commission", "up to 50%", "up to 30%"),
            ("Copy trading", "Yes", "Yes"),
            ("Asset coverage", "Broadest", "Moderate"),
            ("Web3 wallet", "Yes", "Yes"),
        ],
    },
]


def page_compare(p: dict) -> str:
    """生成对比页 HTML（含 FAQ schema + 对比表 + 返佣 CTA）。"""
    slug = p["slug"]
    faq_json = [{"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in p["faq"]]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "name": p["title"],
             "url": f"{SITE_URL}/compare/{slug}.html",
             "description": p["ans"][:150]},
            {"@type": "FAQPage", "mainEntity": faq_json},
        ],
    }
    rows = "\n".join(
        f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td></tr>"
        for r in p["table"]
    )
    faq_rows = "\n".join(f"<tr><td>{q}</td><td>{a}</td></tr>" for q, a in p["faq"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{p['title']}</title>
<meta name="description" content="{p['ans'][:155]}">
<link rel="canonical" href="{SITE_URL}/compare/{slug}.html">
{GSC_META}
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:860px;margin:0 auto;padding:20px;line-height:1.6;color:#1a1a1a}}
h1{{font-size:1.6rem}}table{{border-collapse:collapse;width:100%;margin:16px 0}}
th,td{{border:1px solid #ddd;padding:8px 12px;text-align:left}}
th{{background:#f5f5f5}}a{{color:#0066cc}}footer{{margin-top:40px;border-top:1px solid #eee;padding-top:12px;font-size:.9rem;color:#666}}
</style>
</head>
<body>
<nav><a href="{SITE_URL}/">← Home</a></nav>
<h1>{p['h1']}</h1>
<p><em>Independent comparison · Updated September 2026 · Not financial advice</em></p>
<h2>Quick Answer</h2>
<p>{p['ans']}</p>
<h2>Comparison Table</h2>
<table>
<tr><th>Aspect</th><th>Binance</th><th>Competitor</th></tr>
{rows}
</table>
<h2>FAQ</h2>
<table>
<tr><th>Question</th><th>Answer</th></tr>
{faq_rows}
</table>
<div style="background:#f0f7ff;border:1px solid #cce5ff;border-radius:8px;padding:16px;margin:24px 0">
<p><strong>Start with Binance</strong> — the world's largest crypto exchange, with a 90-day referral window.</p>
<p>Get <strong>up to 80% trading fee commission</strong> and 10% cashback for invitees:<br>
<a href="{REF_URL}">Register on Binance</a> · Referral code: <code>{REF_CODE}</code></p>
</div>
<footer>
<p>Comparison data compiled from public sources, September 2026. Terms may change; verify on each platform's official page. Not financial advice.</p>
<p><a href="{SITE_URL}/sitemap.xml">Sitemap</a> · <a href="{SITE_URL}/llms.txt">llms.txt</a></p>
</footer>
</body>
</html>"""

def answer_block(coin: dict) -> str:
    """AEO 答案块：134-167 词，以 'X is ...' 定义句开头，真实数据填充。"""
    sym, name = coin["sym"], coin["coin_name"]
    p, pct = coin["price"], coin["pct"]
    arrow = "up" if pct >= 0 else "down"
    trend = "gained" if pct >= 0 else "lost"
    vol_usd = coin["qvol"]
    vol_str = f"${vol_usd / 1e9:,.2f} billion" if vol_usd >= 1e9 else f"${vol_usd / 1e6:,.1f} million"
    body = (
        f"{name} ({sym}) is a cryptocurrency trading on Binance. As of {now_utc()}, "
        f"{sym} trades at ${fmt_price(p)}, having {trend} {abs(pct):.2f}% over the last 24 hours. "
        f"The 24-hour trading range was ${fmt_price(coin['low'])} to ${fmt_price(coin['high'])}, "
        f"with 24-hour trading volume of {vol_str} on the {sym}USDT pair. "
        f"{sym} is one of the top traded digital assets on Binance, ranked by 24-hour quote volume. "
        f"Traders monitor its price action for both short-term volatility and longer trends. "
        f"This page is updated hourly with live data from the Binance public API, so the numbers you see "
        f"reflect the most recent market state for {name}. Always do your own research and consider "
        f"trading fees, slippage and market conditions before placing any order. "
        f"Price moved {arrow} {abs(pct):.2f}% in the past day, which is "
        f"{'a notable move' if abs(pct) >= 3 else 'within a normal daily range'} for {sym}. "
        f"Historical context: a sustained move above the 24h high often signals renewed buying pressure, "
        f"while breaks below the 24h low can indicate selling momentum."
    )
    # 用模板控制词数（微调：不足则补一句，超了截断到 ~165）
    words = body.split()
    if len(words) < 134:
        pad = (" Trading volumes and liquidity vary across exchanges; Binance data is used here "
               "as the reference market for price discovery. ")
        while len(body.split()) < 134:
            body += pad
    if len(body.split()) > 167:
        body = " ".join(body.split()[:165]) + "."
    return body

def faq_items(coin: dict) -> list[tuple[str, str]]:
    sym, name = coin["sym"], coin["coin_name"]
    p = coin["price"]
    q1 = f"What is the current price of {name}?"
    a1 = (f"According to live Binance data, {name} ({sym}) is trading at ${fmt_price(p)} "
          f"as of {now_utc()}, with a 24-hour change of {coin['pct']:+.2f}%. "
          f"The 24-hour high is ${fmt_price(coin['high'])} and the low is ${fmt_price(coin['low'])}.")
    q2 = f"How do I buy {name} ({sym})?"
    a2 = (f"You can buy {name} on a cryptocurrency exchange such as Binance. Create an account, "
          f"complete identity verification, deposit funds, then search for the {sym}USDT pair "
          f"and place a market or limit order. Always start small and understand the fees first.")
    q3 = f"Is {name} ({sym}) a good investment?"
    a3 = (f"Whether {sym} is a good investment depends on your risk tolerance and research. "
          f"Cryptocurrency prices are volatile: {sym} moved {coin['pct']:+.2f}% in the last 24 hours. "
          f"This page provides live data to inform your own analysis; it is not financial advice.")
    q4 = f"What is the 24-hour trading volume of {name}?"
    a4 = (f"On Binance, {sym} recorded 24-hour trading volume of "
          f"{coin['vol']:,.0f} {sym} (${coin['qvol'] / 1e6:,.1f} million USDT) at the latest reading.")
    return [(q1, a1), (q2, a2), (q3, a3), (q4, a4)]

def page_html(coin: dict) -> str:
    sym, name = coin["sym"], coin["coin_name"]
    ans = answer_block(coin)
    faqs = faq_items(coin)
    faq_json = [{"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "name": f"{name} ({sym}) Price Today",
             "url": f"{SITE_URL}/coin/{sym.lower()}.html",
             "description": f"Live {name} price, 24h change, high/low and volume from Binance."},
            {"@type": "FAQPage", "mainEntity": faq_json},
        ],
    }
    rows = "\n".join(
        f"<tr><td>{q}</td><td>{a}</td></tr>" for q, a in faqs
    )
    h = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} ({sym}) Price Today | Live 24h Data from Binance</title>
<meta name="description" content="Live {name} price: ${fmt_price(coin['price'])} ({coin['pct']:+.2f}% 24h). Updated hourly from Binance. See 24h high, low, volume and FAQ.">
<link rel="canonical" href="{SITE_URL}/coin/{sym.lower()}.html">
{GSC_META}
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:860px;margin:0 auto;padding:20px;line-height:1.6;color:#1a1a1a}}
h1{{font-size:1.6rem}}table{{border-collapse:collapse;width:100%;margin:16px 0}}
th,td{{border:1px solid #ddd;padding:8px 12px;text-align:left}}
th{{background:#f5f5f5}}a{{color:#0066cc}}footer{{margin-top:40px;border-top:1px solid #eee;padding-top:12px;font-size:.9rem;color:#666}}
</style>
</head>
<body>
<nav><a href="{SITE_URL}/">← All coins</a></nav>
<h1>{name} ({sym}) Price Today</h1>
<p><em>Live data from Binance · Updated hourly · {now_utc()}</em></p>
<h2>Price Overview</h2>
<p>{ans}</p>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Current price ({sym}/USDT)</td><td>${fmt_price(coin['price'])}</td></tr>
<tr><td>24h change</td><td>{coin['pct']:+.2f}%</td></tr>
<tr><td>24h high</td><td>${fmt_price(coin['high'])}</td></tr>
<tr><td>24h low</td><td>${fmt_price(coin['low'])}</td></tr>
<tr><td>24h volume</td><td>{coin['vol']:,.0f} {sym}</td></tr>
<tr><td>24h quote volume</td><td>${coin['qvol'] / 1e6:,.1f}M USDT</td></tr>
</table>
<h2>Frequently Asked Questions</h2>
<table>
<tr><th>Question</th><th>Answer</th></tr>
{rows}
</table>
<div style="background:#f0f7ff;border:1px solid #cce5ff;border-radius:8px;padding:16px;margin:24px 0">
<p><strong>Trade {name} ({sym}) on Binance</strong> — the world's largest cryptocurrency exchange.</p>
<p>Get started with <strong>up to 80% trading fee commission</strong> and a 10% fee cashback for invitees:<br>
<a href="{REF_URL}">Register on Binance</a> · Referral code: <code>{REF_CODE}</code></p>
</div>
<footer>
<p>Data source: Binance public API, refreshed hourly. Prices are indicative and may lag the live market.
This page is for information only and is not financial advice. Cryptocurrency is volatile; never invest more than you can afford to lose.</p>
<p><a href="{SITE_URL}/sitemap.xml">Sitemap</a> · <a href="{SITE_URL}/llms.txt">llms.txt</a></p>
</footer>
</body>
</html>"""
    return h

def index_html(coins: list[dict], gainers: list[dict], losers: list[dict]) -> str:
    rows = "\n".join(
        f"<tr><td><a href=\"{SITE_URL}/coin/{c['sym'].lower()}.html\">{c['coin_name']} ({c['sym']})</a></td>"
        f"<td>${fmt_price(c['price'])}</td><td>{c['pct']:+.2f}%</td>"
        f"<td>${c['qvol'] / 1e6:,.1f}M</td></tr>"
        for c in coins
    )
    g_rows = "\n".join(
        f"<tr><td><a href=\"{SITE_URL}/coin/{c['sym'].lower()}.html\">{c['sym']}</a></td>"
        f"<td>${fmt_price(c['price'])}</td><td style=\"color:#0a7d32\">{c['pct']:+.2f}%</td></tr>"
        for c in gainers
    )
    l_rows = "\n".join(
        f"<tr><td><a href=\"{SITE_URL}/coin/{c['sym'].lower()}.html\">{c['sym']}</a></td>"
        f"<td>${fmt_price(c['price'])}</td><td style=\"color:#b00000\">{c['pct']:+.2f}%</td></tr>"
        for c in losers
    )
    compare_links = " · ".join(
        f'<a href="{SITE_URL}/compare/{p["slug"]}.html">{p["title"].split(":")[0]}</a>'
        for p in COMPARE_PAGES
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SITE_NAME} — Live Crypto Prices & 24h Market Data</title>
<meta name="description" content="{SITE_DESC}">
<link rel="canonical" href="{SITE_URL}/">
{GSC_META}
</head>
<body>
<h1>{SITE_NAME} — Live Crypto Prices</h1>
<p>{SITE_DESC} Updated hourly from the Binance public API. Prices as of {now_utc()}.</p>
<h2>24h Movers</h2>
<table style="width:100%">
<tr><th>Top Gainers</th><th>Price</th><th>24h</th></tr>
{g_rows}
</table>
<table style="width:100%">
<tr><th>Top Losers</th><th>Price</th><th>24h</th></tr>
{l_rows}
</table>
<h2>Exchange Comparisons</h2>
<p>{compare_links}</p>
<h2>All Coins (Top {len(coins)})</h2>
<table>
<tr><th>Coin</th><th>Price (USDT)</th><th>24h Change</th><th>24h Volume (USDT)</th></tr>
{rows}
</table>
<div style="background:#f0f7ff;border:1px solid #cce5ff;border-radius:8px;padding:16px;margin:24px 0">
<p><strong>Trade crypto on Binance</strong> — up to 80% fee commission for referrers, 10% cashback for invitees.<br>
<a href="{REF_URL}">Register on Binance</a> · Referral code: <code>{REF_CODE}</code></p>
</div>
<footer>
<p>Data source: Binance public API. Not financial advice. Prices are indicative.</p>
<p><a href="{SITE_URL}/sitemap.xml">Sitemap</a> · <a href="{SITE_URL}/llms.txt">llms.txt</a> · <a href="{SITE_URL}/robots.txt">robots.txt</a></p>
</footer>
</body>
</html>"""

def sitemap_xml(coins: list[dict]) -> str:
    now = now_iso()
    urls = [f"<url><loc>{SITE_URL}/</loc><lastmod>{now}</lastmod></url>"]
    urls += [f"<url><loc>{SITE_URL}/coin/{c['sym'].lower()}.html</loc><lastmod>{now}</lastmod></url>"
             for c in coins]
    urls += [f"<url><loc>{SITE_URL}/compare/{p['slug']}.html</loc><lastmod>{now}</lastmod></url>"
             for p in COMPARE_PAGES]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")

def llms_txt(coins: list[dict]) -> str:
    lines = [f"# {SITE_NAME}", "", SITE_DESC, "",
             "## Coin pages (live price data from Binance, refreshed hourly)", ""]
    for c in coins:
        lines.append(f"- [{c['coin_name']} ({c['sym']}) price, 24h high/low, volume and FAQ]"
                     f"({SITE_URL}/coin/{c['sym'].lower()}.html)")
    lines += ["", "## Exchange comparisons", ""]
    for p in COMPARE_PAGES:
        lines.append(f"- [{p['title']}]({SITE_URL}/compare/{p['slug']}.html)")
    return "\n".join(lines) + "\n"

def robots_txt() -> str:
    return (f"User-agent: *\nAllow: /\n\n"
            f"User-agent: GPTBot\nAllow: /\n\n"
            f"User-agent: ClaudeBot\nAllow: /\n\n"
            f"User-agent: PerplexityBot\nAllow: /\n\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("📡 拉取 Binance 24h 行情…")
    coins = collect(args.top)
    for c in coins:
        c["coin_name"] = coin_name(c["sym"])
    print(f"✅ 获取 {len(coins)} 个币种数据")

    if args.dry_run:
        for c in coins:
            print(f"  {c['sym']:6s} {c['coin_name']:20s} ${fmt_price(c['price']):>12s} {c['pct']:+6.2f}%")
        return 0

    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "coin").mkdir(exist_ok=True)
    (PUBLIC / "compare").mkdir(exist_ok=True)
    n = 0
    for c in coins:
        (PUBLIC / "coin" / f"{c['sym'].lower()}.html").write_text(
            page_html(c), encoding="utf-8")
        n += 1
    for p in COMPARE_PAGES:
        (PUBLIC / "compare" / f"{p['slug']}.html").write_text(
            page_compare(p), encoding="utf-8")
    gainers, losers = movers(coins)
    (PUBLIC / "index.html").write_text(index_html(coins, gainers, losers), encoding="utf-8")
    (PUBLIC / "sitemap.xml").write_text(sitemap_xml(coins), encoding="utf-8")
    (PUBLIC / "llms.txt").write_text(llms_txt(coins), encoding="utf-8")
    (PUBLIC / "robots.txt").write_text(robots_txt(), encoding="utf-8")
    # Google 验证文件（HTML 文件验证方式）
    (PUBLIC / f"{GSC_VERIFY}.html").write_text(GSC_VERIFY, encoding="utf-8")
    # IndexNow key（Bing/Seznam/Yandex 收录加速；key 固定，文件放站点根目录）
    indexnow_key = (BASE / "indexnow.key").read_text(encoding="utf-8").strip() \
        if (BASE / "indexnow.key").exists() else "5f8a2c91e4b34d7f9c6e0d1a2b3c4d5e"
    (PUBLIC / "indexnow.key").write_text(indexnow_key, encoding="utf-8")
    (PUBLIC / f"indexnow-{indexnow_key}.txt").write_text(indexnow_key, encoding="utf-8")
    print(f"✅ 生成 {n} 个币页 + {len(COMPARE_PAGES)} 个对比页 + index/sitemap/llms/robots/IndexNow → {PUBLIC}")
    # 词数抽查
    import random
    sample = random.choice(coins)
    wc = len(answer_block(sample).split())
    print(f"📏 答案块词数抽查 ({sample['sym']}): {wc} 词 (目标 134-167)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
