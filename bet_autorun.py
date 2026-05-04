#!/usr/bin/env python3
"""
Cloud Auto-Bet Service for PancakeSwap BNB Prediction
Runs on VPS, bets automatically every round based on mode.
Port: 5555 (localhost only, proxied via nginx)
"""

import json, time, threading, os, sys, signal, hashlib, hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    import requests as req_lib
except ImportError:
    req_lib = None

# ── Config ──────────────────────────────────────────────────────────────
PREDICTION_ADDR = '0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA'
CHAIN_ID = 56
RPC_LIST = [
    'https://bsc-dataseed.binance.org/',
    'https://bsc-dataseed1.binance.org/',
    'https://bsc-dataseed2.binance.org/',
    'https://1rpc.io/bnb',
]
BET_AFTER_OPEN = 90   # seconds after round opens to bet
ROUND_INTERVAL = 300   # 5 minutes per round
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'bet_config.json')
PRIVATE_KEY_FILE = os.path.join(os.path.dirname(__file__), 'bet_key.enc')
GAS_LIMIT = 300000
GAS_PRICE = 1_000_000_000  # 1 gwei
BET_FN_SIGS = {'BULL': '57fb096f', 'BEAR': 'aa6b873a'}

# ── State ───────────────────────────────────────────────────────────────
class BetState:
    def __init__(self):
        self.mode = 'paused'  # 'paused', '0.003', '0.002'
        self.direction = 'BULL'  # 'BULL' or 'BEAR' (user picks)
        self.paused = True
        self.last_bet_epoch = 0
        self.wallet_addr = None
        self.private_key = None
        self.status = '未授权'
        self.last_error = None
        self.bet_count = 0
        self.total_wagered = 0.0
        self.running = True
        self._lock = threading.Lock()
        self._authorized = False

state = BetState()

# ── RPC Helpers ─────────────────────────────────────────────────────────
def rpc_call(method, params, timeout=10):
    """Try all RPCs, return first success."""
    payload = json.dumps({'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}).encode()
    headers = {'Content-Type': 'application/json'}
    last_err = None
    for rpc in RPC_LIST:
        try:
            r = req_lib.post(rpc, data=payload, headers=headers, timeout=timeout)
            j = r.json()
            if 'result' in j:
                return j['result']
            if 'error' in j:
                last_err = j['error'].get('message', str(j['error']))
        except Exception as e:
            last_err = str(e)[:80]
    return None

def get_current_epoch():
    result = rpc_call('eth_call', [{'to': PREDICTION_ADDR, 'data': '0x76671808'}, 'latest'])
    if result and result != '0x':
        return int(result, 16)
    return None

def get_round_lock_ts(epoch):
    epoch_hex = hex(epoch)[2:].zfill(64)
    result = rpc_call('eth_call', [{'to': PREDICTION_ADDR, 'data': '0x8c65c81f' + epoch_hex}, 'latest'])
    if not result or result == '0x' or len(result) < 64*3+2:
        return None
    h = result[2:]
    # Fields: [0]=epoch, [1]=startTs, [2]=lockTs, [3]=closeTs
    lock_ts = int(h[128:192], 16)
    return lock_ts if lock_ts > 1e9 else None

def get_balance(addr):
    result = rpc_call('eth_getBalance', [addr, 'latest'])
    if result:
        return int(result, 16) / 1e18
    return 0

def get_nonce(addr):
    result = rpc_call('eth_getTransactionCount', [addr, 'pending'])
    if result:
        return int(result, 16)
    return None

def send_raw_tx(raw_hex):
    """Broadcast signed transaction. Returns tx hash or None."""
    result = rpc_call('eth_sendRawTransaction', [raw_hex], timeout=15)
    return result  # tx hash hex string

# ── Transaction Signing ─────────────────────────────────────────────────
def sign_and_send(bet_dir, epoch, amount_bnb):
    """Sign and broadcast a bet transaction. Returns tx hash."""
    from eth_account import Account

    fn_sig = BET_FN_SIGS[bet_dir]
    epoch_hex = hex(epoch)[2:].zfill(64)
    call_data = '0x' + fn_sig + epoch_hex

    addr = state.wallet_addr
    nonce = get_nonce(addr)
    if nonce is None:
        raise Exception('无法获取 nonce')

    value_wei = int(amount_bnb * 1e18)

    tx = {
        'nonce': nonce,
        'to': PREDICTION_ADDR,
        'value': value_wei,
        'data': bytes.fromhex(call_data[2:]),
        'gas': GAS_LIMIT,
        'gasPrice': GAS_PRICE,
        'chainId': CHAIN_ID,
    }

    signed = Account.sign_transaction(tx, state.private_key)
    tx_hash = send_raw_tx(signed.raw_transaction.hex())
    if not tx_hash:
        raise Exception('广播失败: 所有 RPC 均不可用')
    return tx_hash

# ── Bet Timing Logic ────────────────────────────────────────────────────
def get_bet_amount():
    if state.mode == '0.003':
        return 0.003
    elif state.mode == '0.002':
        return 0.002
    return 0

def should_bet_now(lock_ts):
    """Returns True if current time is BET_AFTER_OPEN seconds into the round."""
    now = time.time()
    round_start = lock_ts - ROUND_INTERVAL
    elapsed = now - round_start
    # Bet when we're 90s into the round (between 90-100s window)
    return BET_AFTER_OPEN <= elapsed <= BET_AFTER_OPEN + 10

# ── Background Betting Loop ─────────────────────────────────────────────
def bet_loop():
    """Background thread: check every 5s, bet at the right time."""
    while state.running:
        try:
            if state.paused or not state._authorized or state.mode == 'paused':
                time.sleep(5)
                continue

            epoch = get_current_epoch()
            if not epoch:
                time.sleep(10)
                continue

            # Skip if already bet this epoch
            if epoch == state.last_bet_epoch:
                time.sleep(5)
                continue

            lock_ts = get_round_lock_ts(epoch)
            if not lock_ts:
                time.sleep(10)
                continue

            now = time.time()
            round_start = lock_ts - ROUND_INTERVAL

            # If round just started (< 90s), wait
            elapsed = now - round_start
            if elapsed < BET_AFTER_OPEN:
                wait = BET_AFTER_OPEN - elapsed
                with state._lock:
                    state.status = f'⏳ 等待下注 (E{epoch}, {wait:.0f}s后)'
                time.sleep(min(wait, 5))
                continue

            # If we're in the 90-100s window, bet!
            if BET_AFTER_OPEN <= elapsed <= BET_AFTER_OPEN + 10:
                amount = get_bet_amount()
                if amount <= 0:
                    time.sleep(5)
                    continue

                balance = get_balance(state.wallet_addr)
                if balance < amount + 0.001:  # need gas buffer
                    with state._lock:
                        state.status = f'❌ 余额不足 ({balance:.4f} BNB)'
                        state.paused = True
                    continue

                with state._lock:
                    state.status = f'⚡ 下注中... E{epoch} {state.direction} {amount}BNB'

                try:
                    tx_hash = sign_and_send(state.direction, epoch, amount)
                    with state._lock:
                        state.last_bet_epoch = epoch
                        state.bet_count += 1
                        state.total_wagered += amount
                        state.status = f'✅ E{epoch} {state.direction} {amount}BNB | {tx_hash[:10]}...'
                        state.last_error = None
                except Exception as e:
                    err = str(e)[:120]
                    with state._lock:
                        state.status = f'❌ E{epoch} 下注失败: {err}'
                        state.last_error = err
                    # Don't set last_bet_epoch so it retries
                    time.sleep(5)
                    continue

            # After 100s into round, just wait for next epoch
            time.sleep(5)

        except Exception as e:
            with state._lock:
                state.status = f'❌ 循环错误: {str(e)[:80]}'
            time.sleep(10)

# ── Config Persistence ──────────────────────────────────────────────────
def save_config():
    cfg = {
        'mode': state.mode,
        'direction': state.direction,
        'paused': state.paused,
        'bet_count': state.bet_count,
        'total_wagered': state.total_wagered,
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f)
    except:
        pass

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        state.mode = cfg.get('mode', 'paused')
        state.direction = cfg.get('direction', 'BULL')
        state.paused = cfg.get('paused', True)
        state.bet_count = cfg.get('bet_count', 0)
        state.total_wagered = cfg.get('total_wagered', 0)
    except:
        pass

def save_key(pk):
    """Save private key to file with 600 permissions."""
    with open(PRIVATE_KEY_FILE, 'w') as f:
        f.write(pk)
    os.chmod(PRIVATE_KEY_FILE, 0o600)

def load_key():
    try:
        with open(PRIVATE_KEY_FILE) as f:
            return f.read().strip()
    except:
        return None

def init_wallet():
    """Load private key and derive address."""
    pk = load_key()
    if not pk:
        return False
    from eth_account import Account
    acct = Account.from_key(pk)
    state.private_key = pk
    state.wallet_addr = acct.address
    state._authorized = True
    state.status = f'✅ 已授权 {acct.address[:6]}...{acct.address[-4:]}'
    return True

# ── HTTP API ────────────────────────────────────────────────────────────
class BetAPI(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress access logs

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/bet/status':
            balance = 0
            if state.wallet_addr:
                balance = get_balance(state.wallet_addr)
            with state._lock:
                self._json({
                    'authorized': state._authorized,
                    'wallet': state.wallet_addr,
                    'balance': round(balance, 4),
                    'mode': state.mode,
                    'direction': state.direction,
                    'paused': state.paused,
                    'status': state.status,
                    'bet_count': state.bet_count,
                    'total_wagered': round(state.total_wagered, 4),
                    'last_error': state.last_error,
                })
            return

        self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode() if content_len else '{}'
        try:
            data = json.loads(body)
        except:
            data = {}

        if path == '/api/bet/authorize':
            pk = data.get('private_key', '').strip()
            if not pk or (not pk.startswith('0x') and len(pk) != 64):
                self._json({'error': '私钥格式错误'}, 400)
                return
            clean_pk = pk if pk.startswith('0x') else '0x' + pk
            try:
                from eth_account import Account
                acct = Account.from_key(clean_pk)
                save_key(clean_pk)
                state.private_key = clean_pk
                state.wallet_addr = acct.address
                state._authorized = True
                state.status = f'✅ 已授权 {acct.address[:6]}...{acct.address[-4:]}'
                self._json({'ok': True, 'wallet': acct.address})
            except Exception as e:
                self._json({'error': f'私钥无效: {str(e)[:60]}'}, 400)
            return

        if path == '/api/bet/mode':
            mode = data.get('mode', '')
            direction = data.get('direction', '')
            if mode not in ('paused', '0.003', '0.002'):
                self._json({'error': '无效模式'}, 400)
                return
            if direction and direction not in ('BULL', 'BEAR'):
                self._json({'error': '无效方向'}, 400)
                return
            if not state._authorized:
                self._json({'error': '请先授权钱包'}, 400)
                return
            with state._lock:
                if direction:
                    state.direction = direction
                state.mode = mode
                state.paused = (mode == 'paused')
                if mode == 'paused':
                    state.status = '⏸ 暂停中'
                else:
                    state.status = f'🚀 {mode} BNB 自动下注 ({state.direction})'
                state.last_bet_epoch = 0  # reset so next round can bet
            save_config()
            self._json({'ok': True, 'mode': state.mode, 'direction': state.direction})
            return

        if path == '/api/bet/pause':
            with state._lock:
                state.paused = True
                state.mode = 'paused'
                state.status = '⏸ 暂停中'
            save_config()
            self._json({'ok': True})
            return

        if path == '/api/bet/reset':
            with state._lock:
                state.mode = 'paused'
                state.paused = True
                state.last_bet_epoch = 0
                state.bet_count = 0
                state.total_wagered = 0
                state.last_error = None
                state.status = '🔄 已重置'
            save_config()
            self._json({'ok': True})
            return

        self._json({'error': 'not found'}, 404)

# ── Main ────────────────────────────────────────────────────────────────
def main():
    load_config()
    init_wallet()

    # Start background betting thread
    t = threading.Thread(target=bet_loop, daemon=True)
    t.start()

    port = 5555
    server = HTTPServer(('127.0.0.1', port), BetAPI)
    print(f'[bet-autorun] Cloud auto-bet service started on :{port}')
    print(f'[bet-autorun] Wallet: {state.wallet_addr or "未授权"}')
    print(f'[bet-autorun] Mode: {state.mode} | Direction: {state.direction}')

    def shutdown(sig, frame):
        state.running = False
        save_config()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()

if __name__ == '__main__':
    main()
