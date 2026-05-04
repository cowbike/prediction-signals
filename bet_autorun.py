#!/usr/bin/env python3
"""
Cloud Auto-Bet Service for PancakeSwap BNB Prediction
Multi-wallet support: each wallet independently authorized and controlled.
Port: 5555 (localhost only, proxied via nginx)
"""

import json, time, threading, os, sys, signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

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
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_config.json')
GAS_LIMIT = 300000
GAS_PRICE = 1_000_000_000  # 1 gwei
BET_FN_SIGS = {'BULL': '57fb096f', 'BEAR': 'aa6b873a'}
MAX_WALLETS = 5

# ── Per-Wallet State ────────────────────────────────────────────────────
class WalletState:
    def __init__(self, addr, private_key):
        self.addr = addr.lower()
        self.private_key = private_key
        self.mode = 'paused'       # 'paused', '0.003', '0.002'
        self.direction = 'BULL'    # 'BULL' or 'BEAR'
        self.paused = True
        self.last_bet_epoch = 0
        self.status = '已授权'
        self.last_error = None
        self.bet_count = 0
        self.total_wagered = 0.0

    def to_dict(self):
        return {
            'wallet': self.addr,
            'mode': self.mode,
            'direction': self.direction,
            'paused': self.paused,
            'status': self.status,
            'bet_count': self.bet_count,
            'total_wagered': round(self.total_wagered, 4),
            'last_error': self.last_error,
        }

# ── Global State ────────────────────────────────────────────────────────
wallets = {}  # addr -> WalletState
_running = True
_lock = threading.Lock()

# ── RPC Helpers ─────────────────────────────────────────────────────────
def rpc_call(method, params, timeout=10):
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
    result = rpc_call('eth_sendRawTransaction', [raw_hex], timeout=15)
    return result

# ── Transaction Signing ─────────────────────────────────────────────────
def sign_and_send(ws, bet_dir, epoch, amount_bnb):
    from eth_account import Account

    fn_sig = BET_FN_SIGS[bet_dir]
    epoch_hex = hex(epoch)[2:].zfill(64)
    call_data = '0x' + fn_sig + epoch_hex

    nonce = get_nonce(ws.addr)
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

    signed = Account.sign_transaction(tx, ws.private_key)
    tx_hash = send_raw_tx(signed.raw_transaction.hex())
    if not tx_hash:
        raise Exception('广播失败: 所有 RPC 均不可用')
    return tx_hash

# ── Background Betting Loop ─────────────────────────────────────────────
def bet_loop():
    global _running
    while _running:
        try:
            # Get active wallets
            with _lock:
                active = [w for w in wallets.values() if not w.paused and w.mode != 'paused']

            if not active:
                time.sleep(5)
                continue

            epoch = get_current_epoch()
            if not epoch:
                time.sleep(10)
                continue

            lock_ts = get_round_lock_ts(epoch)
            if not lock_ts:
                time.sleep(10)
                continue

            now = time.time()
            round_start = lock_ts - ROUND_INTERVAL
            elapsed = now - round_start

            # Wait if too early
            if elapsed < BET_AFTER_OPEN:
                wait = BET_AFTER_OPEN - elapsed
                for ws in active:
                    with _lock:
                        ws.status = f'⏳ 等待下注 (E{epoch}, {wait:.0f}s后)'
                time.sleep(min(wait, 5))
                continue

            # In the betting window (90-100s after round opens)
            if BET_AFTER_OPEN <= elapsed <= BET_AFTER_OPEN + 10:
                for ws in active:
                    if ws.last_bet_epoch == epoch:
                        continue

                    amount = 0.003 if ws.mode == '0.003' else 0.002
                    balance = get_balance(ws.addr)

                    if balance < amount + 0.001:
                        with _lock:
                            ws.status = f'❌ 余额不足 ({balance:.4f} BNB)'
                            ws.paused = True
                        continue

                    with _lock:
                        ws.status = f'⚡ 下注中... E{epoch} {ws.direction} {amount}BNB'

                    try:
                        tx_hash = sign_and_send(ws, ws.direction, epoch, amount)
                        with _lock:
                            ws.last_bet_epoch = epoch
                            ws.bet_count += 1
                            ws.total_wagered += amount
                            ws.status = f'✅ E{epoch} {ws.direction} {amount}BNB | {tx_hash[:10]}...'
                            ws.last_error = None
                    except Exception as e:
                        err = str(e)[:120]
                        with _lock:
                            ws.status = f'❌ E{epoch} 失败: {err}'
                            ws.last_error = err

                    time.sleep(1)  # stagger between wallets

            time.sleep(5)

        except Exception as e:
            time.sleep(10)

# ── Config Persistence ──────────────────────────────────────────────────
def save_config():
    cfg = {}
    for addr, ws in wallets.items():
        cfg[addr] = {
            'private_key': ws.private_key,
            'mode': ws.mode,
            'direction': ws.direction,
            'paused': ws.paused,
            'bet_count': ws.bet_count,
            'total_wagered': ws.total_wagered,
        }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)
    except:
        pass

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for addr, data in cfg.items():
            from eth_account import Account
            try:
                acct = Account.from_key(data['private_key'])
                ws = WalletState(acct.address, data['private_key'])
                ws.mode = data.get('mode', 'paused')
                ws.direction = data.get('direction', 'BULL')
                ws.paused = data.get('paused', True)
                ws.bet_count = data.get('bet_count', 0)
                ws.total_wagered = data.get('total_wagered', 0)
                wallets[ws.addr] = ws
            except:
                continue
    except:
        pass

# ── HTTP API ────────────────────────────────────────────────────────────
class BetAPI(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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

    def _read_body(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode() if content_len else '{}'
        try:
            return json.loads(body)
        except:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/bet/status':
            result = []
            for addr, ws in wallets.items():
                bal = get_balance(addr)
                d = ws.to_dict()
                d['balance'] = round(bal, 4)
                result.append(d)
            self._json({'wallets': result, 'count': len(result)})
            return

        self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_body()

        # ── Authorize a new wallet ──
        if path == '/api/bet/authorize':
            pk = data.get('private_key', '').strip()
            if not pk or (not pk.startswith('0x') and len(pk) != 64):
                self._json({'error': '私钥格式错误'}, 400)
                return
            clean_pk = pk if pk.startswith('0x') else '0x' + pk

            if len(wallets) >= MAX_WALLETS:
                self._json({'error': f'最多支持 {MAX_WALLETS} 个钱包'}, 400)
                return

            try:
                from eth_account import Account
                acct = Account.from_key(clean_pk)
                addr = acct.address.lower()
                with _lock:
                    ws = WalletState(acct.address, clean_pk)
                    wallets[addr] = ws
                save_config()
                self._json({'ok': True, 'wallet': acct.address, 'count': len(wallets)})
            except Exception as e:
                self._json({'error': f'私钥无效: {str(e)[:60]}'}, 400)
            return

        # ── Set mode/direction for a wallet ──
        if path == '/api/bet/mode':
            wallet = data.get('wallet', '').lower().strip()
            mode = data.get('mode', '')
            direction = data.get('direction', '')

            if not wallet or wallet not in wallets:
                self._json({'error': '钱包未授权'}, 400)
                return
            if mode and mode not in ('paused', '0.003', '0.002'):
                self._json({'error': '无效模式'}, 400)
                return
            if direction and direction not in ('BULL', 'BEAR'):
                self._json({'error': '无效方向'}, 400)
                return

            ws = wallets[wallet]
            with _lock:
                if direction:
                    ws.direction = direction
                if mode:
                    ws.mode = mode
                    ws.paused = (mode == 'paused')
                    if mode == 'paused':
                        ws.status = '⏸ 暂停中'
                    else:
                        ws.status = f'🚀 {mode} BNB ({ws.direction})'
                    ws.last_bet_epoch = 0
            save_config()
            self._json({'ok': True, **ws.to_dict()})
            return

        # ── Pause a wallet ──
        if path == '/api/bet/pause':
            wallet = data.get('wallet', '').lower().strip()
            if not wallet or wallet not in wallets:
                self._json({'error': '钱包未授权'}, 400)
                return
            ws = wallets[wallet]
            with _lock:
                ws.paused = True
                ws.mode = 'paused'
                ws.status = '⏸ 暂停中'
            save_config()
            self._json({'ok': True, **ws.to_dict()})
            return

        # ── Remove a wallet ──
        if path == '/api/bet/remove':
            wallet = data.get('wallet', '').lower().strip()
            if not wallet or wallet not in wallets:
                self._json({'error': '钱包未找到'}, 400)
                return
            with _lock:
                del wallets[wallet]
            save_config()
            self._json({'ok': True, 'count': len(wallets)})
            return

        # ── Pause all ──
        if path == '/api/bet/pause-all':
            with _lock:
                for ws in wallets.values():
                    ws.paused = True
                    ws.mode = 'paused'
                    ws.status = '⏸ 暂停中'
            save_config()
            self._json({'ok': True})
            return

        self._json({'error': 'not found'}, 404)

# ── Main ────────────────────────────────────────────────────────────────
def main():
    load_config()

    t = threading.Thread(target=bet_loop, daemon=True)
    t.start()

    port = 5555
    server = HTTPServer(('127.0.0.1', port), BetAPI)
    print(f'[bet-autorun] Cloud auto-bet service started on :{port}')
    print(f'[bet-autorun] Loaded {len(wallets)} wallet(s)')

    def shutdown(sig, frame):
        global _running
        _running = False
        save_config()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    server.serve_forever()

if __name__ == '__main__':
    main()
