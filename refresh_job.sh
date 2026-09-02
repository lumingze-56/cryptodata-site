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
echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] refresh done" >> refresh.log
