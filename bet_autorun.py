#!/usr/bin/env python3
"""
Cloud Auto-Bet Service for PancakeSwap BNB Prediction
Uses OKX Agentic Wallet (onchainos CLI) — no private keys stored.
Port: 5555 (localhost only, proxied via nginx)
"""

import json, time, threading, os, sys, signal, hmac, secrets, subprocess
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
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bet_config_v2.json')
BET_FN_SIGS = {'BULL': '57fb096f', 'BEAR': 'aa6b873a'}
MAX_WALLETS = 5
ONCHAINOS_BIN = 'onchainos'  # CLI binary path
BET_PIN = os.environ.get('BET_PIN', '')  # PIN protection

# ── Per-Wallet State ────────────────────────────────────────────────────
class WalletState:
    def __init__(self, addr):
        self.addr = addr.lower()
        self.auth_token = secrets.token_hex(16)
        self.mode = 'paused'       # 'paused', '0.003', '0.002', '0.001'
        self.direction = 'BULL'    # 'BULL' or 'BEAR'
        self.bet_after = 90        # seconds after round opens (90/120/150/180/210)
        self.paused = True
        self.last_bet_epoch = 0
        self.status = '已授权'
        self.last_error = None
        self.bet_count = 0         # successful bets placed
        self.bet_attempts = 0      # total attempts
        self.total_wagered = 0.0
        # Stats tracking
        self.wins = 0
        self.total_bets = 0        # resolved bets
        self._last_checked_epoch = 0
        self.bet_history = []      # all bet records: [{epoch, dir, amount, result, ts}]
        self.label = ''            # display label (e.g. "一号钱包")
        self.onchainos_account_id = ''  # for multi-account switching
        self.virtual_mode = False  # virtual betting mode (no real bets)

    def to_dict(self, include_token=False):
        d = {
            'wallet': self.addr,
            'mode': self.mode,
            'direction': self.direction,
            'bet_after': self.bet_after,
            'paused': self.paused,
            'status': self.status,
            'bet_count': self.bet_count,
            'bet_attempts': self.bet_attempts,
            'total_wagered': round(self.total_wagered, 4),
            'wins': self.wins,
            'total_bets': self.total_bets,
            'win_rate': round(self.wins / self.total_bets * 100, 1) if self.total_bets > 0 else 0,
            'last_error': self.last_error,
            'label': self.label,
            'onchainos_account_id': self.onchainos_account_id,
            'virtual_mode': self.virtual_mode,
        }
        if include_token:
            d['auth_token'] = self.auth_token
        return d

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

def check_claimable(epoch, addr):
    """Check if an epoch is claimable for the given address"""
    epoch_hex = hex(epoch)[2:].zfill(64)
    addr_hex = addr.lower().replace('0x', '').zfill(64)
    # claimable(uint256,address) selector: 0xa0c7f71c
    data = '0xa0c7f71c' + epoch_hex + addr_hex
    result = rpc_call('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'])
    if result and result != '0x':
        return int(result, 16) > 0
    return False

def get_ledger(epoch, addr):
    """Get user's bet info for a given epoch. Returns (position, amount_bnb, claimed)"""
    epoch_hex = hex(epoch)[2:].zfill(64)
    addr_hex = addr.lower().replace('0x', '').zfill(64)
    # ledger(uint256,address) selector: 0x7285c58b
    data = '0x7285c58b' + epoch_hex + addr_hex
    result = rpc_call('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'])
    if not result or result == '0x' or len(result) < 64*3+2:
        return None
    h = result[2:]
    position = int(h[0:64], 16)       # 0=Bull, 1=Bear (Solidity enum)
    amount_wei = int(h[64:128], 16)
    claimed = int(h[128:192], 16) > 0
    # Return data even when amount=0 (failed bet) so stats_loop can record it
    return (position, amount_wei / 1e18, claimed)

def get_round_winner(epoch):
    """Get the winner of a round. Returns 'BULL', 'BEAR', or None if not resolved."""
    epoch_hex = hex(epoch)[2:].zfill(64)
    # rounds(uint256) selector: 0x8c65c81f
    data = '0x8c65c81f' + epoch_hex
    result = rpc_call('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'])
    if not result or result == '0x' or len(result) < 64*6+2:
        return None
    h = result[2:]
    # [4] = lockPrice (int256), [5] = closePrice (int256)
    lock_raw = int(h[256:320], 16)
    close_raw = int(h[320:384], 16)
    # Handle signed int256
    if lock_raw >= 2**255:
        lock_raw -= 2**256
    if close_raw >= 2**255:
        close_raw -= 2**256
    if lock_raw == 0 or close_raw == 0:
        return None
    return 'BULL' if close_raw > lock_raw else 'BEAR'

def get_round_odds(epoch):
    """Get bull/bear odds for a round. Returns (bull_odds, bear_odds) or None."""
    epoch_hex = hex(epoch)[2:].zfill(64)
    data = '0x8c65c81f' + epoch_hex
    result = rpc_call('eth_call', [{'to': PREDICTION_ADDR, 'data': data}, 'latest'])
    if not result or result == '0x' or len(result) < 64*11+2:
        return None
    h = result[2:]
    bull_raw = int(h[576:640], 16)   # [9] bullAmount
    bear_raw = int(h[640:704], 16)   # [10] bearAmount
    if bull_raw == 0 and bear_raw == 0:
        return None
    total = bull_raw + bear_raw
    # 3% treasury fee → winners get 97% of total pool
    payout_pool = total * 0.97
    bull_odds = round(payout_pool / bull_raw, 2) if bull_raw else 0
    bear_odds = round(payout_pool / bear_raw, 2) if bear_raw else 0
    return (bull_odds, bear_odds)

def claim_winnings(epochs, account_id=''):
    """Claim winnings for multiple epochs using onchainos contract-call"""
    # Switch to correct account if needed
    if account_id:
        switch_onchainos_account(account_id)
    # claim(uint256[]) selector: 0x6ba4c138
    # ABI encode: offset(32) + length(32) + each epoch(32)
    selector = '6ba4c138'
    offset = '0000000000000000000000000000000000000000000000000000000000000020'
    length = hex(len(epochs))[2:].zfill(64)
    epoch_data = ''.join(hex(e)[2:].zfill(64) for e in epochs)
    input_data = '0x' + selector + offset + length + epoch_data

    cmd = [
        ONCHAINOS_BIN, 'wallet', 'contract-call',
        '--to', PREDICTION_ADDR,
        '--chain', 'bsc',
        '--input-data', input_data,
        '--amt', '0',
        '--force',
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise Exception(f'claim failed: {err[:120]}')

    try:
        out = json.loads(result.stdout)
        tx_hash = (
            out.get('data', {}).get('txHash') or
            out.get('data', {}).get('txHashHex') or
            out.get('txHash') or ''
        )
        return tx_hash or result.stdout.strip()[:66]
    except json.JSONDecodeError:
        return result.stdout.strip()[:66]

# ── Contract Call via onchainos CLI ─────────────────────────────────────
def switch_onchainos_account(account_id):
    """Switch active onchainos account. Returns True if ok."""
    if not account_id:
        return True
    cmd = [ONCHAINOS_BIN, 'wallet', 'switch', account_id]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.returncode == 0

def onchainos_bet(bet_dir, epoch, amount_bnb, account_id=''):
    """Place a bet using onchainos wallet contract-call. Returns tx hash or raises."""
    # Switch to correct account if needed
    if account_id:
        switch_onchainos_account(account_id)
    fn_sig = BET_FN_SIGS[bet_dir]
    epoch_hex = hex(epoch)[2:].zfill(64)
    input_data = '0x' + fn_sig + epoch_hex
    amt_wei = str(int(amount_bnb * 1e18))

    cmd = [
        ONCHAINOS_BIN, 'wallet', 'contract-call',
        '--to', PREDICTION_ADDR,
        '--chain', 'bsc',
        '--input-data', input_data,
        '--amt', amt_wei,
        '--force',
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise Exception(f'onchainos error: {err[:120]}')

    # Parse JSON output to extract tx hash
    try:
        out = json.loads(result.stdout)
        # Try common fields for tx hash
        tx_hash = (
            out.get('data', {}).get('txHash') or
            out.get('data', {}).get('txHashHex') or
            out.get('txHash') or
            out.get('tx') or
            ''
        )
        if not tx_hash:
            # Return raw output as fallback
            return result.stdout.strip()[:66]
        return tx_hash
    except json.JSONDecodeError:
        # Try to extract hash from raw output
        for line in result.stdout.strip().split('\n'):
            if '0x' in line and len(line.strip()) >= 64:
                return line.strip()[:66]
        return result.stdout.strip()[:66]

# ── Background Stats Checker ────────────────────────────────────────────
def stats_loop():
    """Periodically check recent epochs for bet results"""
    while _running:
        try:
            with _lock:
                active_wallets = [w for w in wallets.values() if not w.paused and w.mode != 'paused']
            if not active_wallets:
                time.sleep(30)
                continue

            epoch = get_current_epoch()
            if not epoch:
                time.sleep(30)
                continue

            for ws in active_wallets:
                if ws._last_checked_epoch == 0:
                    # First run: check last 100 epochs
                    start = max(1, epoch - 100)
                    ws._last_checked_epoch = start
                else:
                    start = ws._last_checked_epoch

                checked = 0
                for e in range(start, epoch):
                    ledger = get_ledger(e, ws.addr)
                    if not ledger:
                        continue
                    position, amount, claimed = ledger
                    pos_str = 'BULL' if position == 0 else 'BEAR'
                    # Skip epochs with no bet and no existing history (wallet never participated)
                    if amount <= 0:
                        existing = next((h for h in ws.bet_history if h['epoch'] == e), None)
                        if not existing:
                            # Check if round is resolved — if so, this is a missed bet
                            winner_quick = get_round_winner(e)
                            if winner_quick:
                                # Only mark FAILED if wallet has history before this epoch
                                min_hist_epoch = min((h['epoch'] for h in ws.bet_history), default=0) if ws.bet_history else 0
                                if e > min_hist_epoch:
                                    ws.bet_history.append({
                                        'epoch': e,
                                        'dir': ws.direction,
                                        'amount': 0,
                                        'result': 'FAILED',
                                        'claimed': False,
                                    })
                                    save_config()
                            continue
                    winner = get_round_winner(e)
                    odds = get_round_odds(e)
                    bull_odds = odds[0] if odds else 0
                    bear_odds = odds[1] if odds else 0
                    with _lock:
                        existing = next((h for h in ws.bet_history if h['epoch'] == e), None)
                        if not winner:
                            # Unsettled — add as PENDING if not already tracked
                            if not existing:
                                ws.bet_history.append({
                                    'epoch': e,
                                    'dir': pos_str,
                                    'amount': round(amount, 4),
                                    'result': 'PENDING',
                                    'claimed': False,
                                    'bull_odds': bull_odds,
                                    'bear_odds': bear_odds,
                                })
                            elif odds:
                                # Update odds for existing PENDING
                                existing['bull_odds'] = bull_odds
                                existing['bear_odds'] = bear_odds
                        else:
                            won = (pos_str == winner)
                            # Check if bet actually went through (amount > 0)
                            if amount <= 0:
                                # Bet never confirmed on-chain
                                if existing and existing['result'] == 'PENDING':
                                    existing['result'] = 'FAILED'
                                    existing['claimed'] = False
                                    existing['dir'] = pos_str
                                elif not existing:
                                    ws.bet_history.append({
                                        'epoch': e,
                                        'dir': pos_str,
                                        'amount': 0,
                                        'result': 'FAILED',
                                        'claimed': False,
                                        'bull_odds': bull_odds,
                                        'bear_odds': bear_odds,
                                    })
                            else:
                                if existing and existing['result'] == 'PENDING':
                                    existing['result'] = 'WIN' if won else 'LOSE'
                                    existing['claimed'] = claimed
                                    existing['bull_odds'] = bull_odds
                                    existing['bear_odds'] = bear_odds
                                    existing['dir'] = pos_str
                                elif existing and existing['result'] == 'WIN':
                                    # Sync claimed status from chain for existing WIN entries
                                    existing['claimed'] = claimed
                                elif not existing:
                                    ws.bet_history.append({
                                        'epoch': e,
                                        'dir': pos_str,
                                        'amount': round(amount, 4),
                                        'result': 'WIN' if won else 'LOSE',
                                        'claimed': claimed,
                                        'bull_odds': bull_odds,
                                        'bear_odds': bear_odds,
                                    })
                                ws.total_bets += 1
                                if won:
                                    ws.wins += 1
                    checked += 1

                ws._last_checked_epoch = epoch

                # Re-check all PENDING entries for settlement + sync claimed for WIN
                with _lock:
                    pending = [h for h in ws.bet_history if h['result'] in ('PENDING', 'WIN')]
                for h in pending:
                    winner = get_round_winner(h['epoch'])
                    ledger = get_ledger(h['epoch'], ws.addr)
                    if not winner:
                        # Also fix direction from chain even if unsettled
                        if ledger and ledger[0] in (0, 1):
                            chain_dir = 'BULL' if ledger[0] == 0 else 'BEAR'
                            if h['dir'] != chain_dir:
                                with _lock:
                                    h['dir'] = chain_dir
                        continue
                    chain_dir = 'BULL' if ledger and ledger[0] == 0 else 'BEAR'
                    odds = get_round_odds(h['epoch'])
                    won = (chain_dir == winner)
                    with _lock:
                        # Check if bet actually went through (amount > 0)
                        if ledger and ledger[1] <= 0:
                            # Bet never confirmed on-chain
                            if h['result'] == 'PENDING':
                                h['result'] = 'FAILED'
                                h['dir'] = chain_dir
                                h['claimed'] = False
                        elif h['result'] == 'PENDING':
                            h['result'] = 'WIN' if won else 'LOSE'
                            h['dir'] = chain_dir
                            ws.total_bets += 1
                            if won:
                                ws.wins += 1
                        # Sync claimed status from chain
                        if ledger and ledger[1] > 0:
                            h['claimed'] = ledger[2]
                        if odds:
                            h['bull_odds'] = odds[0]
                            h['bear_odds'] = odds[1]

            save_config()
            time.sleep(60)  # Check every minute
        except Exception:
            time.sleep(30)

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

            # Process each wallet with its own timing
            for ws in active:
                ba = ws.bet_after
                if elapsed < ba:
                    wait = ba - elapsed
                    with _lock:
                        ws.status = f'⏳ 等待下注 (E{epoch}, {wait:.0f}s后)'
                    continue

                # In the betting window (ba to ba+10s after round opens)
                if not (ba <= elapsed <= ba + 10):
                    continue

                if ws.last_bet_epoch == epoch:
                    continue

                amount = float(ws.mode) if ws.mode not in ('paused', '') else 0.002
                balance = get_balance(ws.addr)

                if balance < amount + 0.001:
                    with _lock:
                        ws.status = f'❌ 余额不足 ({balance:.4f} BNB)'
                        ws.paused = True
                    continue

                with _lock:
                    ws.bet_attempts += 1
                    ws.status = f'⚡ 下注中... E{epoch} {ws.direction} {amount}BNB'

                try:
                    tx_hash = onchainos_bet(ws.direction, epoch, amount, ws.onchainos_account_id)
                    # Verify on-chain direction after bet
                    time.sleep(2)
                    ledger = get_ledger(epoch, ws.addr)
                    chain_dir = 'BULL' if ledger and ledger[0] == 0 else 'BEAR' if ledger and ledger[0] == 1 else ws.direction
                    with _lock:
                        ws.last_bet_epoch = epoch
                        ws.bet_count += 1
                        ws.total_wagered += amount
                        ws.status = f'✅ E{epoch} {chain_dir} {amount}BNB | {tx_hash[:10]}...'
                        ws.last_error = None
                        # Add to history immediately as PENDING with real chain direction
                        ws.bet_history.append({
                            'epoch': epoch,
                            'dir': chain_dir,
                            'amount': round(amount, 4),
                            'result': 'PENDING',
                            'claimed': False,
                        })
                        save_config()
                except Exception as e:
                    err = str(e)[:120]
                    with _lock:
                        ws.status = f'❌ E{epoch} 失败: {err}'
                        ws.last_error = err
                        # Record failed attempt in history so stats_loop can mark it FAILED
                        existing_fail = next((h for h in ws.bet_history if h['epoch'] == epoch), None)
                        if not existing_fail:
                            ws.bet_history.append({
                                'epoch': epoch,
                                'dir': ws.direction,
                                'amount': 0,
                                'result': 'FAILED',
                                'claimed': False,
                            })
                            save_config()

                time.sleep(1)  # stagger between wallets

            time.sleep(5)

        except Exception as e:
            time.sleep(10)

# ── Config Persistence ──────────────────────────────────────────────────
def save_config():
    cfg = {}
    for addr, ws in wallets.items():
        cfg[addr] = {
            'auth_token': ws.auth_token,
            'mode': ws.mode,
            'direction': ws.direction,
            'bet_after': ws.bet_after,
            'paused': ws.paused,
            'bet_count': ws.bet_count,
            'bet_attempts': ws.bet_attempts,
            'total_wagered': ws.total_wagered,
            'wins': ws.wins,
            'total_bets': ws.total_bets,
            '_last_checked_epoch': ws._last_checked_epoch,
            'bet_history': ws.bet_history,
            'label': ws.label,
            'onchainos_account_id': ws.onchainos_account_id,
            'virtual_mode': ws.virtual_mode,
        }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)
    except:
        pass

def get_onchainos_wallet():
    """Get current wallet address from onchainos CLI."""
    try:
        result = subprocess.run(
            [ONCHAINOS_BIN, 'wallet', 'addresses', '--chain', 'bsc'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Try data.evm first (new format)
            evm = data.get('data', {}).get('evm', [])
            for a in evm:
                if a.get('address'):
                    return a['address'].lower()
            # Fallback: data.addresses (old format)
            addrs = data.get('data', {}).get('addresses', [])
            for a in addrs:
                if a.get('chainName') in ('bnb', 'bsc') and a.get('address'):
                    return a['address'].lower()
    except:
        pass
    return None

def load_config():
    # Auto-detect OKX wallet address
    okx_addr = get_onchainos_wallet()
    if okx_addr:
        print(f'[bet-autorun] Detected OKX wallet: {okx_addr}')

    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for addr, data in cfg.items():
            if not addr.startswith('0x') or len(addr) != 42:
                continue
            ws = WalletState(addr)
            ws.auth_token = data.get('auth_token', ws.auth_token)
            ws.mode = data.get('mode', 'paused')
            ws.direction = data.get('direction', 'BULL')
            ws.bet_after = data.get('bet_after', 90)
            ws.paused = data.get('paused', True)
            ws.bet_count = data.get('bet_count', 0)
            ws.bet_attempts = data.get('bet_attempts', 0)
            ws.total_wagered = data.get('total_wagered', 0)
            ws.wins = data.get('wins', 0)
            ws.total_bets = data.get('total_bets', 0)
            ws._last_checked_epoch = data.get('_last_checked_epoch', 0)
            ws.bet_history = data.get('bet_history', [])
            ws.label = data.get('label', '')
            ws.onchainos_account_id = data.get('onchainos_account_id', '')
            ws.virtual_mode = data.get('virtual_mode', False)
            wallets[ws.addr] = ws
    except:
        pass

    # Auto-register OKX wallet if not already in config
    if okx_addr and okx_addr not in wallets:
        ws = WalletState(okx_addr)
        wallets[okx_addr] = ws
        save_config()
        print(f'[bet-autorun] Auto-registered OKX wallet: {okx_addr}')

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

    def _get_wallet_token(self, data):
        """Extract wallet + auth_token from request, validate. Returns (ws, error_tuple)."""
        wallet = data.get('wallet', '').lower().strip()
        token = data.get('auth_token', '')
        if not wallet or wallet not in wallets:
            return None, ({'error': '钱包未授权'}, 400)
        ws = wallets[wallet]
        if not token or not hmac.compare_digest(token, ws.auth_token):
            return None, ({'error': '无权操作此钱包'}, 403)
        return ws, None

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/bet/wallet-info':
            # Require PIN if configured
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            pin = qs.get('pin', [''])[0]
            if BET_PIN and pin != BET_PIN:
                self._json({'ok': False, 'error': 'PIN_INCORRECT'})
                return

            # Return all registered wallets
            result = []
            for addr, ws in wallets.items():
                bal = get_balance(addr)
                result.append({
                    'wallet': addr,
                    'auth_token': ws.auth_token,
                    'balance': round(bal, 4),
                    'status': ws.status,
                    'label': ws.label,
                })
            if result:
                self._json({'ok': True, 'wallets': result})
            else:
                self._json({'ok': False, 'error': '未检测到 OKX 钱包'})
            return

        # ── Get wallet balance (no PIN needed, just auth_token) ──
        if path == '/api/bet/balance':
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            wallet = qs.get('wallet', [''])[0].lower()
            token = qs.get('token', [''])[0]
            if not wallet or wallet not in wallets:
                self._json({'ok': False, 'error': '钱包未授权'})
                return
            ws = wallets[wallet]
            if not token or not hmac.compare_digest(token, ws.auth_token):
                self._json({'ok': False, 'error': '无权操作'})
                return
            bal = get_balance(wallet)
            self._json({'ok': True, 'balance': round(bal, 4)})
            return

        # ── Claim winnings ──
        if path == '/api/bet/claim':
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            wallet = qs.get('wallet', [''])[0].lower()
            token = qs.get('token', [''])[0]
            epoch_param = qs.get('epoch', [''])[0]
            if not wallet or wallet not in wallets:
                self._json({'ok': False, 'error': '钱包未授权'})
                return
            ws = wallets[wallet]
            if not token or not hmac.compare_digest(token, ws.auth_token):
                self._json({'ok': False, 'error': '无权操作'})
                return

            # Switch to the correct onchainos account for this wallet
            if ws.onchainos_account_id:
                switch_onchainos_account(ws.onchainos_account_id)

            # Single epoch claim (指定单局)
            if epoch_param:
                try:
                    target_epoch = int(epoch_param)
                except ValueError:
                    self._json({'ok': False, 'error': '无效 epoch'})
                    return
                if not check_claimable(target_epoch, wallet):
                    self._json({'ok': False, 'error': f'Epoch {target_epoch} 不可提取（已提或未赢）'})
                    return
                try:
                    tx_hash = claim_winnings([target_epoch], ws.onchainos_account_id)
                    # Mark as claimed in history
                    for h in ws.bet_history:
                        if h.get('epoch') == target_epoch:
                            h['claimed'] = True
                            break
                    save_config()
                    self._json({'ok': True, 'message': f'提取 Epoch {target_epoch} 盈利', 'tx': tx_hash})
                except Exception as e:
                    self._json({'ok': False, 'error': str(e)[:120]})
                return

            # Batch claim all (扫描最近 20 局)
            epoch = get_current_epoch()
            if not epoch:
                self._json({'ok': False, 'error': '无法获取当前 epoch'})
                return

            claimable_epochs = []
            for e in range(max(1, epoch - 20), epoch):
                if check_claimable(e, wallet):
                    claimable_epochs.append(e)

            if not claimable_epochs:
                self._json({'ok': True, 'message': '没有可提取的盈利', 'epochs': 0})
                return

            try:
                tx_hash = claim_winnings(claimable_epochs, ws.onchainos_account_id)
                for ce in claimable_epochs:
                    for h in ws.bet_history:
                        if h.get('epoch') == ce:
                            h['claimed'] = True
                save_config()
                self._json({'ok': True, 'message': f'提取 {len(claimable_epochs)} 局盈利', 'tx': tx_hash})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)[:120]})
            return

        # ── Get bet stats (wins, total bets, win rate) ──
        if path == '/api/bet/stats':
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            wallet = qs.get('wallet', [''])[0].lower()
            token = qs.get('token', [''])[0]
            if not wallet or wallet not in wallets:
                self._json({'ok': False, 'error': '钱包未授权'})
                return
            ws = wallets[wallet]
            if not token or not hmac.compare_digest(token, ws.auth_token):
                self._json({'ok': False, 'error': '无权操作'})
                return

            # Return cached stats (updated by background thread)
            self._json({
                'ok': True,
                'wins': ws.wins,
                'total_bets': ws.total_bets,
                'win_rate': round(ws.wins / ws.total_bets * 100, 1) if ws.total_bets > 0 else 0,
                'total_wagered': round(ws.total_wagered, 4),
                'bet_count': ws.bet_count,
                'bet_attempts': ws.bet_attempts,
            })
            return

        # ── Get bet history (paginated) ──
        if path == '/api/bet/history':
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            wallet = qs.get('wallet', [''])[0].lower()
            token = qs.get('token', [''])[0]
            page = int(qs.get('page', ['1'])[0])
            per_page = int(qs.get('per_page', ['10'])[0])
            if not wallet or wallet not in wallets:
                self._json({'ok': False, 'error': '钱包未授权'})
                return
            ws = wallets[wallet]
            if not token or not hmac.compare_digest(token, ws.auth_token):
                self._json({'ok': False, 'error': '无权操作'})
                return

            # Newest first
            history = list(reversed(ws.bet_history))
            total = len(history)
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(1, min(page, total_pages))
            start = (page - 1) * per_page
            end = start + per_page
            items = history[start:end]

            self._json({
                'ok': True,
                'items': items,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages,
            })
            return

        if path == '/api/bet/status':
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            token_str = qs.get('tokens', [''])[0]
            auth_map = {}
            if token_str:
                for pair in token_str.split(','):
                    parts = pair.split(':')
                    if len(parts) == 2:
                        auth_map[parts[0].lower()] = parts[1]

            result = []
            for addr, ws in wallets.items():
                token = auth_map.get(addr, '')
                if not token or not hmac.compare_digest(token, ws.auth_token):
                    continue
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

        # ── Register a wallet (address only, no private key) ──
        if path == '/api/bet/authorize':
            addr = data.get('wallet', '').strip()
            if not addr or not addr.startswith('0x') or len(addr) != 42:
                self._json({'error': '地址格式错误 (需要 0x + 40位hex)'}, 400)
                return

            if len(wallets) >= MAX_WALLETS:
                self._json({'error': f'最多支持 {MAX_WALLETS} 个钱包'}, 400)
                return

            addr_lower = addr.lower()
            with _lock:
                ws = WalletState(addr)
                wallets[addr_lower] = ws
            save_config()
            self._json({'ok': True, 'wallet': addr, 'auth_token': ws.auth_token, 'count': len(wallets)})
            return

        # ── Set label for a wallet ──
        if path == '/api/bet/label':
            ws, err = self._get_wallet_token(data)
            if err:
                self._json(*err)
                return
            label = data.get('label', '').strip()
            with _lock:
                ws.label = label
            save_config()
            self._json({'ok': True, 'wallet': ws.addr, 'label': ws.label})
            return

        # ── Set mode/direction for a wallet ──
        if path == '/api/bet/mode':
            ws, err = self._get_wallet_token(data)
            if err:
                self._json(*err)
                return
            mode = data.get('mode', '')
            direction = data.get('direction', '')
            bet_after = data.get('bet_after')

            if mode and mode not in ('paused', '0.003', '0.002', '0.001'):
                self._json({'error': '无效模式'}, 400)
                return
            if direction and direction not in ('BULL', 'BEAR'):
                self._json({'error': '无效方向'}, 400)
                return
            if bet_after is not None and bet_after not in (90, 120, 150, 180, 210):
                self._json({'error': '无效时间'}, 400)
                return

            with _lock:
                if direction:
                    ws.direction = direction
                if bet_after is not None:
                    ws.bet_after = bet_after
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
            ws, err = self._get_wallet_token(data)
            if err:
                self._json(*err)
                return
            with _lock:
                ws.paused = True
                ws.mode = 'paused'
                ws.status = '⏸ 暂停中'
                ws.virtual_mode = False
            save_config()
            self._json({'ok': True, **ws.to_dict()})
            return

        # ── Toggle virtual mode ──
        if path == '/api/bet/virtual':
            ws, err = self._get_wallet_token(data)
            if err:
                self._json(*err)
                return
            enabled = data.get('enabled', None)
            if enabled is None:
                enabled = not ws.virtual_mode
            with _lock:
                ws.virtual_mode = bool(enabled)
                if ws.virtual_mode:
                    ws.status = '🎲 虚拟模式运行中'
                else:
                    ws.status = '⏸ 虚拟模式已关闭'
            save_config()
            self._json({'ok': True, 'virtual_mode': ws.virtual_mode, **ws.to_dict()})
            return

        # ── Remove a wallet ──
        if path == '/api/bet/remove':
            ws, err = self._get_wallet_token(data)
            if err:
                self._json(*err)
                return
            with _lock:
                del wallets[ws.addr]
            save_config()
            self._json({'ok': True, 'count': len(wallets)})
            return

        # ── Pause all ──
        if path == '/api/bet/pause-all':
            token = data.get('auth_token', '')
            if not token:
                self._json({'error': '需要认证'}, 403)
                return
            has_valid = any(hmac.compare_digest(token, ws.auth_token) for ws in wallets.values())
            if not has_valid:
                self._json({'error': '无权操作'}, 403)
                return
            with _lock:
                for ws in wallets.values():
                    ws.paused = True
                    ws.mode = 'paused'
                    ws.status = '⏸ 暂停中'
            save_config()
            self._json({'ok': True})
            return

        self._json({'error': 'not found'}, 404)

# ── Virtual Bet Loop ─────────────────────────────────────────────────────
def virtual_loop():
    """Virtual betting loop - records simulated bets every 60s, checks actual results."""
    while _running:
        try:
            with _lock:
                virtual_wallets = [w for w in wallets.values() if w.virtual_mode]
            if not virtual_wallets:
                time.sleep(10)
                continue

            epoch = get_current_epoch()
            if not epoch:
                time.sleep(30)
                continue

            for ws in virtual_wallets:
                # Skip if already recorded this epoch
                existing = next((h for h in ws.bet_history if h['epoch'] == epoch), None)
                if not existing:
                    # Record new virtual bet
                    odds = get_round_odds(epoch)
                    bull_odds = odds[0] if odds else 0
                    bear_odds = odds[1] if odds else 0
                    with _lock:
                        ws.bet_history.append({
                            'epoch': epoch,
                            'dir': 'BULL',
                            'amount': 0.001,
                            'result': 'VIRTUAL_PENDING',
                            'claimed': False,
                            'virtual': True,
                            'bull_odds': bull_odds,
                            'bear_odds': bear_odds,
                        })
                        ws.status = f'🎲 虚拟下注 E{epoch} BULL 0.001BNB (涨{bull_odds}x/跌{bear_odds}x)'
                        ws.bet_attempts += 1
                        ws.total_wagered += 0.001
                    save_config()

                # Update odds for ALL VIRTUAL_PENDING entries (real-time refresh)
                with _lock:
                    pending_virtuals = [h for h in ws.bet_history if h.get('result') == 'VIRTUAL_PENDING']
                for h in pending_virtuals:
                    odds = get_round_odds(h['epoch'])
                    if odds:
                        with _lock:
                            h['bull_odds'] = odds[0]
                            h['bear_odds'] = odds[1]
                    save_config()

            # Check previous epoch results for virtual bets
            prev_epoch = epoch - 1
            if prev_epoch > 0:
                for ws in virtual_wallets:
                    pending = [h for h in ws.bet_history
                               if h.get('epoch') == prev_epoch and h.get('result') == 'VIRTUAL_PENDING']
                    if not pending:
                        continue
                    winner = get_round_winner(prev_epoch)
                    if not winner:
                        continue
                    for h in pending:
                        h_dir = h.get('dir', 'BULL')
                        won = (h_dir == winner)
                        # Update odds from settled round
                        settled_odds = get_round_odds(prev_epoch)
                        with _lock:
                            h['result'] = '虚拟赢' if won else '虚拟输'
                            if settled_odds:
                                h['bull_odds'] = settled_odds[0]
                                h['bear_odds'] = settled_odds[1]
                            ws.total_bets += 1
                            if won:
                                ws.wins += 1
                        save_config()

            time.sleep(60)
        except Exception as e:
            print(f'[virtual-loop] Error: {e}')
            time.sleep(30)

# ── Main ────────────────────────────────────────────────────────────────
def main():
    load_config()

    t = threading.Thread(target=bet_loop, daemon=True)
    t.start()

    t2 = threading.Thread(target=stats_loop, daemon=True)
    t2.start()

    t3 = threading.Thread(target=virtual_loop, daemon=True)
    t3.start()

    port = 5555
    server = HTTPServer(('127.0.0.1', port), BetAPI)
    print(f'[bet-autorun] OKX Wallet auto-bet service started on :{port}')
    print(f'[bet-autorun] Loaded {len(wallets)} wallet(s)')
    print(f'[bet-autorun] Using onchainos CLI for contract calls')

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
