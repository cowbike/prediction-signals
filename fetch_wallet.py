#!/usr/bin/env python3
"""Fetch PancakeSwap prediction bets via BSCScan API, generate HTML report."""
import json, time, sys, urllib.request, urllib.parse
from datetime import datetime
from collections import defaultdict

WALLET = "0xd8b53f94144b5bad90b156ecca28422c26c08e6c"
CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
BULL_TOPIC = "0x438122d8cff518d18388099a5181f0d17a12b4f1b55faedf6e4a6acee0060c12"
BEAR_TOPIC = "0x0d8c1fe3e67ab767116a81f122b83c2557a8c2564019cb7c4f83de1aeb1f1f0d"
CLAIM_TOPIC = "0x34fcbac0073d7c3d388e51312faf357774904998eeb8fca628b9e6f65ee1cbf7"
WALLET_PAD = "0x000000000000000000000000" + WALLET[2:].lower()

def bscscan_get_logs(topic0, label):
    """Fetch all logs for topic0 with wallet filter, ~2M block chunks."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/", request_kwargs={'timeout': 10}))
    cur = w3.eth.block_number
    start = cur - 10500000  # ~2y
    end = cur - 5250000     # ~1y
    
    all_logs = []
    chunk = 500000  # 500K blocks per request (well under 2M limit)
    
    for s in range(start, end, chunk):
        e = min(s + chunk - 1, end)
        url = (f"https://api.bscscan.com/api?module=logs&action=getLogs"
               f"&address={CONTRACT}&fromBlock={s}&toBlock={e}"
               f"&topic0={topic0}&topic1={WALLET_PAD}"
               f"&page=1&offset=1000")
        
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                
                if data['status'] == '1' and isinstance(data['result'], list):
                    all_logs.extend(data['result'])
                    print(f"  [{label}] {s}-{e}: +{len(data['result'])} (total: {len(all_logs)})", flush=True)
                elif data['status'] == '0' and 'No records found' in str(data.get('message','')):
                    pass  # normal, no events in this range
                else:
                    print(f"  [{label}] {s}-{e}: {data.get('message','?')}", flush=True)
                break
            except Exception as ex:
                if attempt < 2:
                    time.sleep(2*(attempt+1))
                else:
                    print(f"  [{label}] {s}-{e}: FAILED {str(ex)[:50]}", flush=True)
        time.sleep(0.25)  # 4 req/sec max
    return all_logs

print("=== Fetching BetBull ===", flush=True)
bull_logs = bscscan_get_logs(BULL_TOPIC, "BULL")
print(f"BetBull total: {len(bull_logs)}", flush=True)

time.sleep(1)
print("\n=== Fetching BetBear ===", flush=True)
bear_logs = bscscan_get_logs(BEAR_TOPIC, "BEAR")
print(f"BetBear total: {len(bear_logs)}", flush=True)

time.sleep(1)
print("\n=== Fetching Claims ===", flush=True)
claim_logs = bscscan_get_logs(CLAIM_TOPIC, "CLAIM")
print(f"Claims total: {len(claim_logs)}", flush=True)

# Parse bets
bets = []
for log in bull_logs:
    data = log['data'][2:] if log['data'].startswith('0x') else log['data']
    epoch = int(log['topics'][2], 16)
    amt = int(data[:64], 16) / 1e18
    blk = int(log['blockNumber'], 16)
    ts = int(log['timeStamp'], 16)
    bets.append({'epoch': epoch, 'dir': 'BULL', 'amt': round(amt, 8), 'block': blk, 'ts': ts})

for log in bear_logs:
    data = log['data'][2:] if log['data'].startswith('0x') else log['data']
    epoch = int(log['topics'][2], 16)
    amt = int(data[:64], 16) / 1e18
    blk = int(log['blockNumber'], 16)
    ts = int(log['timeStamp'], 16)
    bets.append({'epoch': epoch, 'dir': 'BEAR', 'amt': round(amt, 8), 'block': blk, 'ts': ts})

# Parse claims
claims_map = {}
for log in claim_logs:
    epoch = int(log['topics'][2], 16)
    data = log['data'][2:] if log['data'].startswith('0x') else log['data']
    amt = int(data[:64], 16) / 1e18
    claims_map[epoch] = round(amt, 8)

bets.sort(key=lambda x: x['block'])
print(f"\nTotal parsed bets: {len(bets)}", flush=True)

# Enrich
for b in bets:
    b['time'] = datetime.fromtimestamp(b['ts']).strftime('%Y-%m-%d %H:%M') if b['ts'] else '?'
    b['won'] = b['epoch'] in claims_map
    b['payout'] = claims_map.get(b['epoch'], 0)

# Take latest 20000
if len(bets) > 20000:
    bets = bets[-20000:]

# Stats
total = len(bets)
wins = sum(1 for b in bets if b['won'])
losses = total - wins
tb = sum(b['amt'] for b in bets)
tc = sum(b['payout'] for b in bets)
net = tc - tb
wr = (wins/total*100) if total else 0
bn = sum(1 for b in bets if b['dir']=='BULL')
ben = total - bn
amts = [b['amt'] for b in bets]

# Monthly
monthly = defaultdict(lambda:{'b':0,'w':0,'ba':0.0,'ca':0.0})
hourly = defaultdict(lambda:{'b':0,'w':0})
for b in bets:
    k = b['time'][:7]
    monthly[k]['b'] += 1
    if b['won']: monthly[k]['w'] += 1
    monthly[k]['ba'] += b['amt']
    monthly[k]['ca'] += b['payout']
    try:
        h = int(b['time'][11:13])
        hourly[h]['b'] += 1
        if b['won']: hourly[h]['w'] += 1
    except: pass

# Amount distribution
amt_dist = defaultdict(int)
for b in bets:
    a = b['amt']
    if a < 0.01: amt_dist['<0.01'] += 1
    elif a < 0.05: amt_dist['0.01-0.05'] += 1
    elif a < 0.1: amt_dist['0.05-0.1'] += 1
    elif a < 0.5: amt_dist['0.1-0.5'] += 1
    elif a < 1.0: amt_dist['0.5-1.0'] += 1
    else: amt_dist['>1.0'] += 1

result = {
    'wallet': WALLET,
    'period': f"{bets[0]['time']} ~ {bets[-1]['time']}" if bets else '?',
    'total': total, 'wins': wins, 'losses': losses, 'wr': round(wr, 2),
    'tb': round(tb, 4), 'tc': round(tc, 4), 'net': round(net, 4),
    'roi': round(net/tb*100, 2) if tb > 0 else 0,
    'bull': bn, 'bear': ben,
    'avg': round(sum(amts)/len(amts), 6) if amts else 0,
    'mn': round(min(amts), 6) if amts else 0,
    'mx': round(max(amts), 6) if amts else 0,
    'monthly': {k: v for k, v in sorted(monthly.items())},
    'hourly': {str(k): v for k, v in sorted(hourly.items())},
    'amt_dist': dict(amt_dist),
    'bets': [{'e':b['epoch'],'d':b['dir'],'a':b['amt'],'t':b['time'],'w':b['won'],'p':b['payout']} for b in bets[-500:]],
}

with open('/home/cowbike/prediction-signals/wallet_analysis.json', 'w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n{'='*40}", flush=True)
print(f"Bets: {total} | W:{wins} L:{losses} WR:{wr:.1f}%", flush=True)
print(f"Bet: {tb:.4f} | Claim: {tc:.4f} | PnL: {net:+.4f} BNB", flush=True)
print(f"ROI: {result['roi']:+.2f}% | BULL:{bn} BEAR:{ben}", flush=True)
print(f"Period: {result['period']}", flush=True)
print("Saved wallet_analysis.json!", flush=True)
