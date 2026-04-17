#!/usr/bin/env python3
"""Generate a table of 5000 rounds with simulated whale betting strategy."""
import json, os

DATA_FILE = '/home/cowbike/prediction-signals/rounds_5000.json'
OUTPUT_FILE = '/home/cowbike/prediction-signals/whale_betting_table.html'

def load_data():
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def simulate_whale_bet(round_data):
    """Simulate whale betting based on reverse-crowd strategy."""
    bull_bnb = round_data['bull_bnb']
    bear_bnb = round_data['bear_bnb']
    result = round_data['result']
    
    # 反众下注策略：当某一方极端偏差时，反向下注
    # 使用更严格的阈值：2x而不是1.5x
    if bull_bnb > bear_bnb * 2:
        bet_direction = 'BEAR'
    elif bear_bnb > bull_bnb * 2:
        bet_direction = 'BULL'
    else:
        bet_direction = 'SKIP'
    
    # 计算下注金额：根据赔率偏差调整
    # 偏差越大，下注金额越大（最多0.2 BNB，最少0.05 BNB）
    if bet_direction != 'SKIP':
        if bet_direction == 'BEAR':
            odds_ratio = bull_bnb / bear_bnb
        else:  # BULL
            odds_ratio = bear_bnb / bull_bnb
        
        # 下注金额与赔率偏差成正比
        bet_amount = min(0.2, max(0.05, 0.05 * odds_ratio))
    else:
        bet_amount = 0
    
    # 判断结果
    if bet_direction == 'SKIP':
        outcome = 'SKIP'
        profit = 0
    elif bet_direction == result:
        outcome = 'WIN'
        # 计算收益：下注金额 × 赔率
        if bet_direction == 'BULL':
            odds = bear_bnb / bull_bnb if bull_bnb > 0 else 1
        else:
            odds = bull_bnb / bear_bnb if bear_bnb > 0 else 1
        profit = bet_amount * odds
    else:
        outcome = 'LOSE'
        profit = -bet_amount
    
    return {
        'epoch': round_data['epoch'],
        'bet_amount': bet_amount,
        'bet_direction': bet_direction,
        'result': result,
        'outcome': outcome,
        'profit': profit,
        'bull_bnb': bull_bnb,
        'bear_bnb': bear_bnb,
        'total_bnb': round_data['total_bnb']
    }

def generate_html_table(betting_data):
    """Generate HTML table with betting data."""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🐋 赚钱大户下注记录 - 5000期</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--dim:#8b949e;--green:#3fb950;--red:#f85149;--yellow:#d29922;--blue:#58a6ff}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'SF Mono','Cascadia Code','Consolas',monospace;padding:16px;max-width:1400px;margin:0 auto}
h1{font-size:24px;text-align:center;margin-bottom:8px;color:var(--yellow)}
h2{font-size:18px;color:var(--yellow);margin:24px 0 12px;border-bottom:1px solid var(--border);padding-bottom:8px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center}
.stat .lb{font-size:11px;color:var(--dim);margin-bottom:4px}
.stat .vl{font-size:20px;font-weight:700}
.green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}.blue{color:var(--blue)}
.table-container{overflow-x:auto;margin:20px 0}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:var(--card);color:var(--yellow);padding:10px 8px;text-align:left;border:1px solid var(--border);position:sticky;top:0}
td{padding:8px;border:1px solid var(--border);white-space:nowrap}
tr:nth-child(even){background:rgba(255,255,255,0.02)}
tr:hover{background:rgba(255,255,255,0.05)}
.win{color:var(--green)}.lose{color:var(--red)}.skip{color:var(--dim)}
.bull{color:var(--green)}.bear{color:var(--red)}
.footer{text-align:center;color:var(--dim);font-size:11px;padding:20px 0}
.pagination{display:flex;justify-content:center;gap:8px;margin:20px 0;flex-wrap:wrap}
.page-btn{padding:6px 12px;background:var(--card);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text);font-size:12px}
.page-btn:hover{border-color:var(--blue)}
.page-btn.active{background:var(--blue);border-color:var(--blue)}
</style>
</head>
<body>
<h1>🐋 赚钱大户下注记录 - 5000期</h1>
<p style="text-align:center;color:var(--dim);font-size:12px;margin-bottom:20px">基于反众下注策略模拟 · 阈值2x · 动态下注金额</p>

<div class="stats" id="stats"></div>

<h2>📊 下注记录表格</h2>
<div class="table-container">
  <table id="betting-table">
    <thead>
      <tr>
        <th>期数</th>
        <th>大户下注(BNB)</th>
        <th>下注方向</th>
        <th>结果</th>
        <th>盈亏(BNB)</th>
        <th>BULL池</th>
        <th>BEAR池</th>
        <th>总池</th>
      </tr>
    </thead>
    <tbody id="table-body"></tbody>
  </table>
</div>

<div class="pagination" id="pagination"></div>

<div class="footer">
  <p>数据来源：BSC链上数据 · 模拟策略：反众下注(阈值2x) · 一乐爸爸出品</p>
</div>

<script>
const bettingData = """ + json.dumps(betting_data) + """;

const ROWS_PER_PAGE = 50;
let currentPage = 1;

function renderStats() {
  const stats = document.getElementById('stats');
  
  const totalBets = bettingData.filter(d => d.bet_direction !== 'SKIP').length;
  const wins = bettingData.filter(d => d.outcome === 'WIN').length;
  const losses = bettingData.filter(d => d.outcome === 'LOSE').length;
  const skips = bettingData.filter(d => d.outcome === 'SKIP').length;
  const winRate = totalBets > 0 ? (wins / totalBets * 100).toFixed(1) : 0;
  
  const totalProfit = bettingData.reduce((sum, d) => sum + d.profit, 0);
  const totalInvested = bettingData.reduce((sum, d) => sum + (d.bet_direction !== 'SKIP' ? d.bet_amount : 0), 0);
  const roi = totalInvested > 0 ? (totalProfit / totalInvested * 100).toFixed(1) : 0;
  
  stats.innerHTML = `
    <div class="stat"><div class="vl yellow">${bettingData.length}</div><div class="lb">总期数</div></div>
    <div class="stat"><div class="vl blue">${totalBets}</div><div class="lb">下注次数</div></div>
    <div class="stat"><div class="vl green">${wins}</div><div class="lb">赢</div></div>
    <div class="stat"><div class="vl red">${losses}</div><div class="lb">输</div></div>
    <div class="stat"><div class="vl">${skips}</div><div class="lb">跳过</div></div>
    <div class="stat"><div class="vl ${parseFloat(winRate) > 50 ? 'green' : 'red'}">${winRate}%</div><div class="lb">胜率</div></div>
    <div class="stat"><div class="vl ${totalProfit > 0 ? 'green' : 'red'}">${totalProfit.toFixed(2)}</div><div class="lb">总盈亏(BNB)</div></div>
    <div class="stat"><div class="vl ${parseFloat(roi) > 0 ? 'green' : 'red'}">${roi}%</div><div class="lb">ROI</div></div>
  `;
}

function renderTable(page) {
  const tbody = document.getElementById('table-body');
  const start = (page - 1) * ROWS_PER_PAGE;
  const end = start + ROWS_PER_PAGE;
  const pageData = bettingData.slice(start, end);
  
  tbody.innerHTML = pageData.map(d => `
    <tr>
      <td>${d.epoch}</td>
      <td>${d.bet_direction !== 'SKIP' ? d.bet_amount.toFixed(3) : '-'}</td>
      <td class="${d.bet_direction === 'BULL' ? 'bull' : d.bet_direction === 'BEAR' ? 'bear' : ''}">${d.bet_direction}</td>
      <td class="${d.outcome === 'WIN' ? 'win' : d.outcome === 'LOSE' ? 'lose' : 'skip'}">${d.outcome}</td>
      <td class="${d.profit > 0 ? 'green' : d.profit < 0 ? 'red' : ''}">${d.profit > 0 ? '+' : ''}${d.profit.toFixed(3)}</td>
      <td>${d.bull_bnb.toFixed(3)}</td>
      <td>${d.bear_bnb.toFixed(3)}</td>
      <td>${d.total_bnb.toFixed(3)}</td>
    </tr>
  `).join('');
}

function renderPagination() {
  const pagination = document.getElementById('pagination');
  const totalPages = Math.ceil(bettingData.length / ROWS_PER_PAGE);
  
  let html = '';
  for (let i = 1; i <= totalPages; i++) {
    html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }
  pagination.innerHTML = html;
}

function goToPage(page) {
  currentPage = page;
  renderTable(page);
  renderPagination();
}

// 初始化
renderStats();
renderTable(currentPage);
renderPagination();
</script>
</body>
</html>"""
    return html

def main():
    print("=" * 60)
    print("🐋 生成赚钱大户下注记录表格")
    print("=" * 60)
    
    # 加载数据
    data = load_data()
    print(f"📊 加载了 {len(data)} 期数据")
    
    # 模拟大户下注
    print("🎯 模拟反众下注策略...")
    betting_data = [simulate_whale_bet(d) for d in data]
    
    # 统计
    total_bets = len([d for d in betting_data if d['bet_direction'] != 'SKIP'])
    wins = len([d for d in betting_data if d['outcome'] == 'WIN'])
    losses = len([d for d in betting_data if d['outcome'] == 'LOSE'])
    skips = len([d for d in betting_data if d['outcome'] == 'SKIP'])
    win_rate = wins / total_bets * 100 if total_bets > 0 else 0
    
    total_profit = sum(d['profit'] for d in betting_data)
    total_invested = sum(d['bet_amount'] for d in betting_data if d['bet_direction'] != 'SKIP')
    roi = total_profit / total_invested * 100 if total_invested > 0 else 0
    
    print(f"\n📈 统计结果：")
    print(f"  总期数: {len(betting_data)}")
    print(f"  下注次数: {total_bets}")
    print(f"  赢: {wins}")
    print(f"  输: {losses}")
    print(f"  跳过: {skips}")
    print(f"  胜率: {win_rate:.1f}%")
    print(f"  总盈亏: {total_profit:.3f} BNB")
    print(f"  总投入: {total_invested:.3f} BNB")
    print(f"  ROI: {roi:.1f}%")
    
    # 生成HTML表格
    print("\n📄 生成HTML表格...")
    html_content = generate_html_table(betting_data)
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write(html_content)
    
    print(f"✅ 表格已生成: {OUTPUT_FILE}")
    
    # 生成纯文本摘要
    print("\n" + "=" * 60)
    print("📊 5000期反众下注策略摘要")
    print("=" * 60)
    print(f"策略：当BULL池 > BEAR池×2时下BEAR，反之亦然")
    print(f"下注金额：根据赔率偏差动态调整(0.05-0.2 BNB)")
    print(f"\n结果：")
    print(f"  总下注: {total_bets} 次 (跳过 {skips} 次)")
    print(f"  胜率: {win_rate:.1f}% ({wins}胜/{losses}负)")
    print(f"  总盈亏: {total_profit:.3f} BNB")
    print(f"  ROI: {roi:.1f}%")
    print(f"\n结论：{'✅ 策略有效' if roi > 0 else '❌ 策略无效'}")
    print("=" * 60)

if __name__ == "__main__":
    main()