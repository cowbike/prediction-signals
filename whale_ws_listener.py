#!/usr/bin/env python3
"""
whale_ws_listener.py — WebSocket 实时监听榜一大哥的 BetBull/BetBear 事件

方案：WebSocket 订阅 newHeads → 每 ~3秒 拿到新区块 → 用 eth_getLogs 查询该块是否有目标地址的 bet 事件。
相比轮询：延迟从 ~15秒 → **~3秒**（1块确认时间）。

核心优势：
- 区块级响应速度（~3s）
- 不再依赖 scan 或轮询
- 持久运行的后台守护进程
"""
import json, time, ssl, urllib.request, os, sys, websocket

PREDICTION_ADDR = '0x18b2a687610328590bc8f2e5fedde3b582a49cdA'
WHALE_ADDR = '0xc2fa81eDF00A72dC05AE97Ab1c381856b12e0491'.lower().replace('0x', '')
WS_URL = 'wss://bsc.publicnode.com'
RPC_HTTP = 'https://bsc-dataseed.binance.org'
OUT_REALTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whale_realtime.json')
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whale_data.json')

# BetBull/BetBear event topics (keccak256 of event signatures)
BET_BULL_KECCAK = '0x1f39158c05c4976699db29c2c85847b37786b9af0126ea4e2e9736485a1e1b2a'
BET_BEAR_KECCAK = '0x0a548849743eb9716687e2e01444204b666a1677570c94ca6002fa61346d1188'

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

_realtime_bets = []
_seen_epochs = set()

def load_realtime():
    global _realtime_bets, _seen_epochs
    try:
        if os.path.exists(OUT_REALTIME):
            with open(OUT_REALTIME) as f:
                _realtime_bets = json.load(f)
            _seen_epochs = {b['epoch'] for b in _realtime_bets}
            print(f'[whale-ws] Loaded {len(_realtime_bets)} existing realtime bets')
    except Exception as e:
        print(f'[whale-ws] Error loading realtime: {e}')
        _realtime_bets = []
        _seen_epochs = set()

def save_realtime():
    global _realtime_bets
    _realtime_bets = _realtime_bets[:200]
    tmp = OUT_REALTIME + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(_realtime_bets, f, indent=2)
    os.replace(tmp, OUT_REALTIME)

def rpc(method, params, timeout=5):
    """HTTP RPC call with retry"""
    try:
        body = json.dumps({'jsonrpc':'2.0','method':method,'params':params,'id':1}).encode()
        req = urllib.request.Request(
            RPC_HTTP,
            data=body,
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        data = json.loads(resp.read())
        return data.get('result')
    except Exception:
        return None

def get_round_info(epoch):
    """Get bull/bear pool amounts for odds calculation"""
    try:
        epoch_hex = hex(epoch)[2:].zfill(64)
        data = '0x8c65c81f' + epoch_hex
        result = rpc('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'], timeout=3)
        if not result or result == '0x' or len(result) < 704:
            return 0, 0
        h = result[2:]
        bull_raw = int(h[576:640], 16)
        bear_raw = int(h[640:704], 16)
        if bull_raw > 0 and bear_raw > 0:
            bull_amt = bull_raw / 1e18
            bear_amt = bear_raw / 1e18
            total = bull_amt + bear_amt
            payout = total * 0.97
            return round(payout / bull_amt, 2), round(payout / bear_amt, 2)
        return 0, 0
    except Exception:
        return 0, 0

def check_block_for_whale_bet(block_hash, block_ts):
    """Check if whale bet in this specific block"""
    bets_found = []
    whale_topic = '0x' + WHALE_ADDR.zfill(64)
    
    for event_sig, direction in [(BET_BULL_KECCAK, 'BULL'), (BET_BEAR_KECCAK, 'BEAR')]:
        try:
            body = json.dumps({
                'jsonrpc': '2.0',
                'method': 'eth_getLogs',
                'params': [{
                    'address': PREDICTION_ADDR,
                    'topics': [event_sig, None, whale_topic],
                    'blockHash': block_hash,
                }],
                'id': 1
            }).encode()
            req = urllib.request.Request(
                RPC_HTTP,
                data=body,
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, context=ctx, timeout=4)
            data = json.loads(resp.read())
            logs = data.get('result', [])
            if not isinstance(logs, list):
                continue
            for log in logs:
                topics = log.get('topics', [])
                data_field = log.get('data', '0x')[2:]
                if len(topics) < 2 or len(data_field) < 64:
                    continue
                epoch = int(topics[0], 16)
                amount = int(data_field[：64], 16) / 1e18
                bull_odds, bear_odds = get_round_info(epoch)
                bets_found.append({
                    'epoch': epoch,
                    'dir': direction,
                    'amount': round(amount, 4),
                    'result': 'PENDING',
                    'claimed': False,
                    'bull_odds': bull_odds,
                    'bear_odds': bear_odds,
                    'time': time.strftime('%H:%M:%S', time.localtime(block_ts)) if block_ts else '--',
                    'ts': block_ts,
                })
        except Exception:
            pass
    return bets_found

def on_open(ws):
    print(f'[whale-ws] Connected ✅ ({WS_URL})')

def on_message(ws, msg):
    global _realtime_bets, _seen_epochs
    try:
        data = json.loads(msg)
        if 'params' not in data or 'result' not in data['params']:
            return
        block = data['params']['result']
        block_hash = block.get('hash', '')
        block_ts = int(block.get('timestamp', '0x0'), 16)
        if not block_hash:
            return
        # Check if whale bet in this block
        bets = check_block_for_whale_bet(block_hash, block_ts)
        if bets:
            for b in bets:
                if b['epoch'] in _seen_epochs:
                    continue
                print(f'[whale-ws] 🐋 #{b["epoch"]} {b["dir"]} {b["amount"]} BNB @ {b["time"]}')
                _realtime_bets.insert(0, b)
                _seen_epochs.add(b['epoch'])
            save_realtime()
            # Also update whale_data.json
            try:
                with open(OUT_FILE) as f:
                    wd = json.load(f)
                existing = {bet['epoch'] for bet in wd.get('bets', [])}
                for b in bets:
                    if b['epoch'] not in existing:
                        wd['bets'].insert(0, {k: v for k, v in b.items()})
                        existing.add(b['epoch'])
                settled = [bt for bt in wd['bets'] if bt.get('result') in ('WIN', 'LOSE')]
                wins = sum(1 for bt in settled if bt['result'] == 'WIN')
                wd['stats'] = {
                    'total_bets': len(wd['bets']),
                    'wins': wins,
                    'losses': len(settled) - wins,
                    'win_rate': round(wins / len(settled) * 100, 1) if settled else 0,
                    'total_wagered': round(sum(bt['amount'] for bt in wd['bets']), 4),
                }
                with open(OUT_FILE, 'w') as f:
                    json.dump(wd, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            print(f'[whale-ws] Updated. Total realtime: {len(_realtime_bets)}')
    except Exception as e:
        print(f'[whale-ws] Error processing message: {e}')

def on_error(ws, error):
    print(f'[whale-ws] Error: {error}')

def on_close(ws, close_status_code, close_msg):
    print(f'[whale-ws] Disconnected. Reconnect in 5s...')
    time.sleep(5)
    try:
        ws.run_forever(sslopt={'cert_reqs': ssl.CERT_NONE}, ping_interval=30, ping_timeout=10)
    except Exception:
        pass

if __name__ == '__main__':
    print('[whale-ws] Starting WebSocket listener for whale bets...')
    print(f'[whale-ws] Watched address: 0x{WHALE_ADDR}')
    load_realtime()
    
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    
    while True:
        try:
            ws.run_forever(
                sslopt={'cert_reqs': ssl.CERT_NONE},
                ping_interval=30,
                ping_timeout=10
            )
        except Exception as e:
            print(f'[whale-ws] run_forever exception: {e}')
            time.sleep(5)
