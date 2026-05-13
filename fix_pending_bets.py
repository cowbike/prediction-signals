#!/usr/bin/env python3
"""Fix PENDING bets: re-check round winners, mark VOID if prices are 0."""
import json, os, sys
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whale_data.json')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from whale_tracker_incremental import get_round_winner

with open(OUT_FILE) as f:
    data = json.load(f)

bets = data['bets']
pending = [b for b in bets if b['result'] == 'PENDING']
print(f'Total bets: {len(bets)}, Pending: {len(pending)}')
fixed = 0

for i, b in enumerate(pending):
    ep = b['epoch']
    print(f'[{i+1}/{len(pending)}] Epoch {ep} ({b["dir"]})...', end=' ')
    winner, bull_amt, bear_amt = get_round_winner(ep)
    if winner == 'VOID':
        b['result'] = 'VOID'
        print('→ VOID (无效局)')
        fixed += 1
    elif winner:
        won = (b['dir'] == winner)
        b['result'] = 'WIN' if won else 'LOSE'
        print(f'→ {winner} → {b["result"]}')
        fixed += 1
    else:
        print('still PENDING (no round data available)')

data['bets'] = bets
settled = [b for b in bets if b['result'] in ('WIN', 'LOSE')]
wins = sum(1 for b in settled if b['result'] == 'WIN')
voids = sum(1 for b in bets if b['result'] == 'VOID')

data['stats'] = {
    'total_bets': len(bets),
    'wins': wins,
    'losses': len(settled) - wins,
    'win_rate': round(wins / len(settled) * 100, 1) if settled else 0,
    'total_wagered': round(sum(b['amount'] for b in bets), 4),
}

with open(OUT_FILE, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

still = sum(1 for b in bets if b['result'] == 'PENDING')
print(f'\nDone! {fixed} fixed, {still} still PENDING, {voids} VOID total')
print(f'Win rate: {data["stats"]["win_rate"]}% ({wins}/{len(settled)})')
