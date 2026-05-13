#!/usr/bin/env python3
"""
Update whale bet results by querying chain data for epochs in whale_realtime.json.
Fixes the PENDING issue where realtime bets never get resolved.
"""
import json, os, time, urllib.request, ssl

PREDICTION_ADDR = '0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA'
REALTIME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whale_realtime.json')
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whale_data.json')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

RPC_SERVERS = [
    'https://bsc-dataseed.binance.org/',
    'https://bsc-dataseed1.binance.org/',
    'https://bsc-dataseed2.binance.org/',
]
_rpc_idx = 0

def rpc(method, params, timeout=10):
    global _rpc_idx
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

def get_round(epoch):
    """Get lock price, close price, bull/bear amounts for an epoch."""
    epoch_hex = hex(epoch)[2:].zfill(64)
    data = '0x8c65c81f' + epoch_hex
    result = rpc('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'], timeout=8)
    if not result or result == '0x' or len(result) < 64*11+2:
        return None, None, None, None, None, None
    h = result[2:]
    lock_raw = int(h[128:192], 16)
    close_raw = int(h[192:256], 16)
    if lock_raw >= 2**255: lock_raw -= 2**256
    if close_raw >= 2**255: close_raw -= 2**256
    bull_raw = int(h[576:640], 16)
    bear_raw = int(h[640:704], 16)

    winner = None
    if lock_raw == 0 and close_raw == 0:
        winner = 'VOID'
    elif lock_raw != 0 and close_raw != 0:
        winner = 'BULL' if close_raw > lock_raw else 'BEAR'
    
    bull_amt = bull_raw / 1e18
    bear_amt = bear_raw / 1e18
    total = bull_amt + bear_amt
    payout_pool = total * 0.97
    bull_odds = round(payout_pool / bull_amt, 2) if bull_amt > 0 else 0
    bear_odds = round(payout_pool / bear_amt, 2) if bear_amt > 0 else 0
    
    return winner, lock_raw/1e8, close_raw/1e8, bull_amt, bear_amt, bull_odds


def main():
    # Load realtime
    try:
        with open(REALTIME_FILE) as f:
            realtime_bets = json.load(f)
    except:
        print('No realtime file found')
        return

    # Load whale_data
    try:
        with open(DATA_FILE) as f:
            whale_data = json.load(f)
    except:
        whale_data = None

    current_epoch = get_current_epoch()
    if not current_epoch:
        print('ERROR: cannot get current epoch')
        return

    print(f'Current epoch: {current_epoch}')
    print(f'Realtime bets: {len(realtime_bets)}')
    
    # Also get all epochs from whale_data.json that are not resolved
    data_bets = []
    if whale_data:
        data_bets = {b['epoch']: b for b in whale_data.get('bets', [])}
    
    # Find all epochs that need result checking
    all_pending = []
    seen_epochs = set()
    
    # Check realtime bets first
    for b in realtime_bets:
        if b['result'] == 'PENDING' and b['epoch'] not in seen_epochs:
            all_pending.append(b)
            seen_epochs.add(b['epoch'])
    
    # Also check existing data bets that are PENDING
    if data_bets:
        for ep, b in data_bets.items():
            if b.get('result') == 'PENDING' and ep not in seen_epochs:
                all_pending.append(b)
                seen_epochs.add(ep)
    
    # Filter to only epochs that should be settled (at least 2 epochs old)
    pending_check = [b for b in all_pending if b['epoch'] <= current_epoch - 2]
    
    print(f'Checking results for {len(pending_check)} epochs...')
    
    fixed = 0
    for b in pending_check:
        epoch = b['epoch']
        winner, lock_p, close_p, bull_amt, bear_amt, _ = get_round(epoch)
        
        if winner is None:
            print(f'  #{epoch}: still OPEN (no close data)')
            continue
        
        if winner == 'VOID':
            new_result = 'VOID'
        elif b['dir'] == winner:
            new_result = 'WIN'
        else:
            new_result = 'LOSE'
            
        old_result = b['result']
        if old_result != new_result:
            print(f'  #{epoch}: {old_result} -> {new_result} (was {b["dir"]}, winner={winner})')
            b['result'] = new_result
            # Update odds if they were wrong
            if bull_amt > 0 and bear_amt > 0:
                total = bull_amt + bear_amt
                payout_pool = total * 0.97
                b['bull_odds'] = round(payout_pool / bull_amt, 2)
                b['bear_odds'] = round(payout_pool / bear_amt, 2)
                b['bull_amount'] = round(bull_amt, 4)
                b['bear_amount'] = round(bear_amt, 4)
            fixed += 1
        else:
            print(f'  #{epoch}: {old_result} (no change)')
    
    # Save realtime file back
    with open(REALTIME_FILE, 'w') as f:
        json.dump(realtime_bets, f, indent=2, ensure_ascii=False)
    
    # Update whale_data.json if it exists
    if whale_data:
        # Update existing bets
        for ep, b in data_bets.items():
            if b['result'] != 'PENDING' and any(bt['epoch'] == ep and bt['result'] != b['result'] for bt in all_pending):
                new_b = next((bt for bt in all_pending if bt['epoch'] == ep), None)
                if new_b:
                    b['result'] = new_b['result']
        
        # Add new bets from realtime that aren't in whale_data
        for b in realtime_bets:
            ep = b['epoch']
            if ep not in data_bets:
                whale_data['bets'].insert(0, {k: v for k, v in b.items()})
                data_bets[ep] = b
        
        whale_data['stats'] = {
            'total_bets': len(whale_data['bets']),
            'wins': sum(1 for b in whale_data['bets'] if b['result'] == 'WIN'),
            'losses': sum(1 for b in whale_data['bets'] if b['result'] == 'LOSE'),
            'win_rate': round(sum(1 for b in whale_data['bets'] if b['result'] == 'WIN') / max(1, sum(1 for b in whale_data['bets'] if b['result'] in ('WIN', 'LOSE'))) * 100, 1),
            'total_wagered': round(sum(b['amount'] for b in whale_data['bets']), 4),
        }
        whale_data['current_epoch'] = current_epoch
        
        with open(DATA_FILE, 'w') as f:
            json.dump(whale_data, f, indent=2, ensure_ascii=False)
    
    print(f'\nFixed {fixed} bets. Results saved.')

if __name__ == '__main__':
    main()
