#!/usr/bin/env bash
# crypto-site 每小时刷新：重新生成 → 推送到 GitHub Pages
set -euo pipefail
cd /root/deepseek/work/crypto-site
set -a; source /root/.dsh/.github-env; set +a
SITE_URL="https://lumingze-56.github.io/cryptodata-site" python3 site_gen.py --top 50 >> refresh.log 2>&1
cp public/*.html public/sitemap.xml public/llms.txt public/robots.txt public/.nojekyll . 2>/dev/null
cp public/coin/*.html coin/ 2>/dev/null
mkdir -p compare && cp public/compare/*.html compare/ 2>/dev/null
cp public/indexnow* . 2>/dev/null
git add -A >> refresh.log 2>&1
git -c user.email="lumingze-56@users.noreply.github.com" -c user.name="lumingze-56" commit -m "refresh $(date -u +%Y-%m-%d-%H:%M)" >> refresh.log 2>&1 || true
git push origin main >> refresh.log 2>&1
# IndexNow 提交（Bing 等收录加速；202=接受）
KEY="5f8a2c91e4b34d7f9c6e0d1a2b3c4d5e"
curl -s -m 10 -X POST "https://api.indexnow.org/indexnow" \
  -H "Content-Type: application/json" \
  -d "{\"host\":\"lumingze-56.github.io\",\"key\":\"$KEY\",\"keyLocation\":\"https://lumingze-56.github.io/cryptodata-site/indexnow-$KEY.txt\",\"urlList\":[\"https://lumingze-56.github.io/cryptodata-site/\",\"https://lumingze-56.github.io/cryptodata-site/compare/binance-vs-okx.html\",\"https://lumingze-56.github.io/cryptodata-site/compare/binance-vs-bybit.html\"]}" \
  -o /dev/null -w "indexnow HTTP %{http_code}\n" >> refresh.log 2>&1 || true
echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] refresh done" >> refresh.log
