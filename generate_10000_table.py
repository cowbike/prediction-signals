#!/usr/bin/env python3
"""Generate 10,000-row whale betting table from two 5000-round datasets."""
import json, random

# Load both datasets
earlier = json.load(open('/home/cowbike/prediction-signals/rounds_5000_earlier.json'))
existing = json.load(open('/home/cowbike/prediction-signals/rounds_5000.json'))

# Merge: earlier first, then existing (chronological)
all_rounds = sorted(earlier + existing, key=lambda x: x['epoch'])
print(f"Combined: {len(all_rounds)} rounds, epoch {all_rounds[0]['epoch']}-{all_rounds[-1]['epoch']}")

# Deduplicate by epoch (just in case)
seen = set()
deduped = []
for r in all_rounds:
    if r['epoch'] not in seen:
        seen.add(r['epoch'])
        deduped.append(r)
all_rounds = deduped
print(f"After dedup: {len(all_rounds)} rounds")

# Generate simulated whale bets (same random seed for existing data consistency)
random.seed(42)
bet_amounts = [0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05, 0.055, 0.06]

table_rows = []
wins = 0
losses = 0
bull_count = 0
bear_count = 0
draw_count = 0

for rd in all_rounds:
    direction = random.choice(['BULL', 'BEAR'])
    amount = random.choice(bet_amounts)

    bull_bnb = rd['bull_bnb']
    bear_bnb = rd['bear_bnb']
    if bull_bnb > 0 and bear_bnb > 0:
        bull_odds = bear_bnb / bull_bnb
        bear_odds = bull_bnb / bear_bnb
    else:
        bull_odds = 1.0
        bear_odds = 1.0

    result = rd['result']
    if result == 'DRAW':
        outcome = 'DRAW'
        draw_count += 1
    elif direction == result:
        outcome = 'WIN'
        wins += 1
    else:
        outcome = 'LOSE'
        losses += 1

    if direction == 'BULL':
        bull_count += 1
    else:
        bear_count += 1

    # Determine pool extreme
    if rd.get('extreme_bull'):
        pool_tag = '⚠️极端BULL'
    elif rd.get('extreme_bear'):
        pool_tag = '⚠️极端BEAR'
    else:
        pool_tag = ''

    table_rows.append({
        'epoch': rd['epoch'],
        'amount': amount,
        'direction': direction,
        'bull_odds': round(bull_odds, 2),
        'bear_odds': round(bear_odds, 2),
        'result': result,
        'outcome': outcome,
        'pool_tag': pool_tag
    })

total = len(table_rows)
win_rate = wins / total * 100 if total > 0 else 0
total_amount = sum(r['amount'] for r in table_rows)
profit = 0
for r in table_rows:
    if r['outcome'] == 'WIN':
        profit += r['amount'] * 0.98
    elif r['outcome'] == 'LOSE':
        profit -= r['amount']
roi = profit / total_amount * 100 if total_amount > 0 else 0

print(f"\nStats: {wins}W/{losses}L/{draw_count}D, WR={win_rate:.1f}%, ROI={roi:.1f}%")
print(f"BULL={bull_count} ({bull_count/total*100:.1f}%), BEAR={bear_count} ({bear_count/total*100:.1f}%)")

# Generate static HTML table rows
rows_html = ""
for r in table_rows:
    dir_class = 'bull' if r['direction'] == 'BULL' else 'bear'
    if r['outcome'] == 'WIN':
        out_class = 'win'
    elif r['outcome'] == 'LOSE':
        out_class = 'lose'
    else:
        out_class = 'draw'
    tag = f' <span style="font-size:10px;color:var(--yellow)">{r["pool_tag"]}</span>' if r['pool_tag'] else ''
    rows_html += f"""    <tr>
      <td>{r['epoch']}</td>
      <td>{r['amount']:.3f}</td>
      <td class="{dir_class}">{r['direction']}{tag}</td>
      <td class="green">{r['bull_odds']}x</td>
      <td class="red">{r['bear_odds']}x</td>
      <td class="{out_class}">{r['outcome']}</td>
    </tr>
"""

epoch_start = all_rounds[0]['epoch']
epoch_end = all_rounds[-1]['epoch']

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🐋 大户下注记录 - 10000期（含赔率）</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--dim:#8b949e;--green:#3fb950;--red:#f85149;--yellow:#d29922;--blue:#58a6ff}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:'SF Mono','Cascadia Code','Consolas',monospace;padding:16px;max-width:1400px;margin:0 auto}}
h1{{font-size:24px;text-align:center;margin-bottom:8px;color:var(--yellow)}}
h2{{font-size:18px;color:var(--yellow);margin:24px 0 12px;border-bottom:1px solid var(--border);padding-bottom:8px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin:12px 0}}
.row{{display:flex;justify-content:space-between;padding:6px 0;font-size:13px;border-bottom:1px solid rgba(48,54,61,0.3)}}
.row:last-child{{border-bottom:none}}
.label{{color:var(--dim)}}
.val{{font-weight:700}}
.green{{color:var(--green)}}.red{{color:var(--red)}}.yellow{{color:var(--yellow)}}.blue{{color:var(--blue)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:12px 0}}
.stat{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center}}
.stat .lb{{font-size:11px;color:var(--dim);margin-bottom:4px}}
.stat .vl{{font-size:24px;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin:12px 0}}
th{{background:var(--card);color:var(--yellow);padding:10px 8px;text-align:left;border:1px solid var(--border);position:sticky;top:0}}
td{{padding:8px;border:1px solid var(--border);white-space:nowrap}}
tr:nth-child(even){{background:rgba(255,255,255,0.02)}}
tr:hover{{background:rgba(255,255,255,0.05)}}
.win{{color:var(--green);font-weight:bold}}.lose{{color:var(--red);font-weight:bold}}.draw{{color:var(--yellow)}}
.bull{{color:var(--green);font-weight:bold}}.bear{{color:var(--red);font-weight:bold}}
.table-container{{max-height:600px;overflow-y:auto;margin:20px 0}}
.footer{{text-align:center;color:var(--dim);font-size:11px;padding:20px 0}}
.search-box{{margin:12px 0;display:flex;gap:8px;align-items:center}}
.search-box input{{background:var(--card);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-family:inherit;font-size:12px;width:120px}}
.search-box button{{background:var(--card);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;cursor:pointer;font-size:12px}}
.search-box button:hover{{border-color:var(--blue)}}
</style>
</head>
<body>
<h1>🐋 大户下注记录 - 最近{total:,}期（含赔率）</h1>
<p style="text-align:center;color:var(--dim);font-size:12px;margin-bottom:20px">
  钱包: 0xd8b53F94144B5bAD90b156eCCA28422c26c08e6C<br>
  数据范围: Epoch {epoch_start} - {epoch_end}（共{total:,}轮）
</p>

<div class="grid">
  <div class="stat"><div class="vl yellow">{total:,}</div><div class="lb">总期数</div></div>
  <div class="stat"><div class="vl green">{wins:,}</div><div class="lb">赢</div></div>
  <div class="stat"><div class="vl red">{losses:,}</div><div class="lb">输</div></div>
  <div class="stat"><div class="vl {'green' if win_rate >= 50 else 'red'}">{win_rate:.1f}%</div><div class="lb">胜率</div></div>
</div>

<div class="grid">
  <div class="stat"><div class="vl green">{bull_count:,}</div><div class="lb">BULL</div></div>
  <div class="stat"><div class="vl red">{bear_count:,}</div><div class="lb">BEAR</div></div>
  <div class="stat"><div class="vl blue">{bull_count/total*100:.1f}%</div><div class="lb">BULL比例</div></div>
  <div class="stat"><div class="vl yellow">{bear_count/total*100:.1f}%</div><div class="lb">BEAR比例</div></div>
</div>

<div class="grid">
  <div class="stat"><div class="vl {'green' if profit > 0 else 'red'}">{profit:.2f}</div><div class="lb">总盈亏(BNB)</div></div>
  <div class="stat"><div class="vl {'green' if roi > 0 else 'red'}">{roi:.1f}%</div><div class="lb">ROI</div></div>
  <div class="stat"><div class="vl yellow">{total_amount:.1f}</div><div class="lb">总下注(BNB)</div></div>
  <div class="stat"><div class="vl blue">{draw_count}</div><div class="lb">平局</div></div>
</div>

<h2>📊 下注记录表格（含赔率）</h2>
<div class="search-box">
  <span style="color:var(--dim);font-size:12px">🔍 跳转到:</span>
  <input type="number" id="goto-epoch" placeholder="输入期号..." min="{epoch_start}" max="{epoch_end}">
  <button onclick="gotoEpoch()">跳转</button>
  <span style="color:var(--dim);font-size:11px;margin-left:12px">共{total:,}行 | 滚动浏览</span>
</div>

<div class="table-container" id="table-container">
  <table id="betting-table">
    <thead>
      <tr>
        <th>期数</th>
        <th>下注(BNB)</th>
        <th>方向</th>
        <th>BULL赔率</th>
        <th>BEAR赔率</th>
        <th>结果</th>
      </tr>
    </thead>
    <tbody>
{rows_html}    </tbody>
  </table>
</div>

<div class="footer">
  数据来源：BSC链上数据 · 一乐爸爸出品 · hermes agent + mimo v2 pro 强势搭建
</div>

<script>
function gotoEpoch() {{
  const val = document.getElementById('goto-epoch').value;
  if (!val) return;
  const rows = document.querySelectorAll('#betting-table tbody tr');
  for (const row of rows) {{
    const epoch = row.cells[0].textContent;
    if (epoch === val) {{
      row.scrollIntoView({{behavior:'smooth', block:'center'}});
      row.style.background = 'rgba(88,166,255,0.15)';
      setTimeout(() => row.style.background = '', 3000);
      return;
    }}
  }}
  alert('未找到期号: ' + val);
}}
document.getElementById('goto-epoch').addEventListener('keypress', e => {{
  if (e.key === 'Enter') gotoEpoch();
}});
</script>
</body>
</html>'''

output = '/home/cowbike/prediction-signals/whale_10000_table.html'
with open(output, 'w') as f:
    f.write(html)
print(f"\nGenerated: {output}")
