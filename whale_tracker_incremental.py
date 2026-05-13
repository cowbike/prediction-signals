#!/usr/bin/env python3
"""Incremental whale tracker - only scans new rounds since last update."""
import json, os, sys, time, urllib.request, ssl

PREDICTION_ADDR = '0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA'
WHALE_ADDR = '0xc2fa81eDF00A72dC05AE97Ab1c381856b12e0491'.lower()
RPC_SERVERS = [
    'https://bsc-dataseed.binance.org/',
    'https://bsc-dataseed1.binance.org/',
    'https://bsc-dataseed2.binance.org/',
    'https://bsc-dataseed3.binance.org/',
]
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whale_data.json')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

_rpc_idx = 0

def rpc(method, params, timeout=15):
    global _rpc_idx
    last_err = None
    for i in range(len(RPC_SERVERS)):
        url = RPC_SERVERS[(_rpc_idx + i) % len(RPC_SERVERS)]
        try:
            body = json.dumps({'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}).encode()
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
            data = json.loads(resp.read())
            if 'result' in data:
                _rpc_idx = (_rpc_idx + i) % len(RPC_SERVERS)
                return data['result']
            last_err = data.get('error', 'no result')
        except Exception as e:
            last_err = str(e)
            continue
    return None

def get_current_epoch():
    result = rpc('eth_call', [{'to': PREDICTION_ADDR, 'data': '0x76671808'}, 'latest'])
    if result and result != '0x':
        return int(result, 16)
    return None

def get_balance(addr):
    result = rpc('eth_getBalance', [addr, 'latest'])
    if result:
        return int(result, 16) / 1e18
    return 0

def get_ledger(epoch, addr):
    epoch_hex = hex(epoch)[2:].zfill(64)
    addr_hex = addr.lower().replace('0x', '').zfill(64)
    data = '0x7285c58b' + epoch_hex + addr_hex
    result = rpc('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'])
    if not result or result == '0x' or len(result) < 194:
        return None
    h = result[2:]
    position = int(h[0:64], 16)
    amount_wei = int(h[64:128], 16)
    claimed = int(h[128:192], 16) > 0
    return (position, amount_wei / 1e18, claimed)

def get_round_winner(epoch):
    epoch_hex = hex(epoch)[2:].zfill(64)
    data = '0x8c65c81f' + epoch_hex
    result = rpc('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'])
    if not result or result == '0x' or len(result) < 64*11+2:
        return None, None, None
    h = result[2:]
    lock_raw = int(h[256:320], 16)
    close_raw = int(h[320:384], 16)
    if lock_raw >= 2**255: lock_raw -= 2**256
    if close_raw >= 2**255: close_raw -= 2**256
    bull_raw = int(h[576:640], 16)
    bear_raw = int(h[640:704], 16)
    winner = None
    if lock_raw != 0 and close_raw != 0:
        winner = 'BULL' if close_raw > lock_raw else 'BEAR'
    return winner, bull_raw / 1e18, bear_raw / 1e18

def calc_odds(bull_amount, bear_amount):
    total = bull_amount + bear_amount
    if total == 0 or bull_amount == 0 or bear_amount == 0:
        return 0, 0
    payout_pool = total * 0.97
    bull_odds = round(payout_pool / bull_amount, 2)
    bear_odds = round(payout_pool / bear_amount, 2)
    return bull_odds, bear_odds

def main():
    print(f'[whale-tracker] Incremental scan of {WHALE_ADDR[:10]}...')
    current_epoch = get_current_epoch()
    if not current_epoch:
        print('[whale-tracker] ERROR: cannot get current epoch')
        sys.exit(1)

    balance = get_balance(WHALE_ADDR)
    print(f'[whale-tracker] Current epoch: {current_epoch}, Balance: {balance:.4f} BNB')

    # Load existing data
    with open(OUT_FILE) as f:
        existing = json.load(f)
    existing_bets = {b['epoch']: b for b in existing.get('bets', [])}
    last_epoch = max(existing_bets.keys()) if existing_bets else 0
    print(f'[whale-tracker] Last known epoch in data: {last_epoch}')
    print(f'[whale-tracker] Scanning {current_epoch - last_epoch} new epochs...')

    # Only scan from current_epoch down to last_epoch (new rounds)
    new_bets = []
    for ep in range(current_epoch, last_epoch, -1):
        ledger = get_ledger(ep, WHALE_ADDR)
        if not ledger:
            continue
        pos, amount, claimed = ledger
        if amount <= 0:
            continue
        direction = 'BULL' if pos == 0 else 'BEAR'
        winner, bull_amt, bear_amt = get_round_winner(ep)
        bull_odds, bear_odds = calc_odds(bull_amt, bear_amt)
        if winner:
            won = (direction == winner)
            result = 'WIN' if won else 'LOSE'
        else:
            result = 'PENDING'
        new_bets.append({
            'epoch': ep, 'dir': direction, 'amount': round(amount, 4),
            'result': result, 'claimed': claimed, 'bull_odds': bull_odds,
            'bear_odds': bear_odds, 'bull_amount': round(bull_amt, 4),
            'bear_amount': round(bear_amt, 4),
        })

    print(f'[whale-tracker] Incremental scan done: {len(new_bets)} new bets found')

    # Add new bets to existing
    all_bets_dict = existing_bets.copy()
    for b in new_bets:
        all_bets_dict[b['epoch']] = b

    all_bets = sorted(all_bets_dict.values(), key=lambda x: x['epoch'], reverse=True)
    settled = [b for b in all_bets if b['result'] in ('WIN', 'LOSE')]
    wins = sum(1 for b in settled if b['result'] == 'WIN')
    total_wagered = sum(b['amount'] for b in all_bets)

    output = {
        'address': WHALE_ADDR,
        'balance': round(balance, 4),
        'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
        'scan_range': existing.get('scan_range', 16500),
        'current_epoch': current_epoch,
        'stats': {
            'total_bets': len(all_bets),
            'wins': wins,
            'losses': len(settled) - wins,
            'win_rate': round(wins / len(settled) * 100, 1) if settled else 0,
            'total_wagered': round(total_wagered, 4),
        },
        'bets': all_bets,
    }

    with open(OUT_FILE, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f'[whale-tracker] Done! {len(all_bets)} total bets')
    print(f'[whale-tracker] Win rate: {output["stats"]["win_rate"]}% ({wins}/{len(settled)})')
    print(f'[whale-tracker] Total wagered: {total_wagered:.4f} BNB')

if __name__ == '__main__':
    main()
