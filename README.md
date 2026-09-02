# CryptoData Live — Programmatic Crypto Price Site

Live cryptocurrency prices and 24h market data, generated hourly from the Binance public API.

## 站点内容

- 50 coin pages: live price, 24h change/high/low/volume, FAQ schema (JSON-LD), AEO answer blocks
- `index.html` — market overview table
- `sitemap.xml` / `llms.txt` / `robots.txt` — SEO & AI crawler support

## 维护（本机）

```bash
cd /root/deepseek/work/crypto-site
SITE_URL="https://lumingze-56.github.io/cryptodata-site" python3 site_gen.py --top 50
cp public/*.html public/sitemap.xml public/llms.txt public/robots.txt public/.nojekyll .
cp public/coin/*.html coin/
git add -A && git commit -m "refresh $(date -u +%Y-%m-%d)" && git push
```

## 免责声明

Data source: Binance public API, refreshed hourly. Not financial advice.
