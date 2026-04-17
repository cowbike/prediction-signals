#!/usr/bin/env python3
"""Fetch 5000 earlier rounds (462743-467742). Uses curl for RPC calls (avoids web3 output buffering)."""
import json, time, sys, subprocess, os

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
    "https://bsc-dataseed4.binance.org/",
]

OUTPUT_FILE = '/home/cowbike/prediction-signals/rounds_5000_earlier.json'
START_EPOCH = 462743
END_EPOCH = 467742

def rpc_call(rpc_url, data):
    """Make JSON-RPC call via curl."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": CONTRACT, "data": data}, "latest"],
        "id": 1
    })
    try:
        result = subprocess.run(
            ['curl', '-s', '-X', 'POST', '-H', 'Content-Type: application/json',
             '-d', payload, '--max-time', '15', rpc_url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0 and result.stdout:
            resp = json.loads(result.stdout)
            if 'result' in resp:
                return resp['result']
    except:
        pass
    return None

def get_round_data(epoch):
    selector = "0x8c65c81f"
    epoch_hex = hex(epoch)[2:].zfill(64)
    call_data = selector + epoch_hex

    for rpc in RPCS:
        result = rpc_call(rpc, call_data)
        if result and result != '0x':
            try:
                b = bytes.fromhex(result[2:])
                lock_price = int.from_bytes(b[128:160], 'big', signed=True)
                close_price = int.from_bytes(b[160:192], 'big', signed=True)
                total_amount = int.from_bytes(b[256:288], 'big')
                bull_amount = int.from_bytes(b[288:320], 'big')
                bear_amount = int.from_bytes(b[320:352], 'big')

                if close_price > lock_price:
                    result_dir = "BULL"
                elif close_price < lock_price:
                    result_dir = "BEAR"
                else:
                    result_dir = "DRAW"

                if bull_amount > 0 and bear_amount > 0:
                    bull_ratio = bull_amount / bear_amount
                    bear_ratio = bear_amount / bull_amount
                else:
                    bull_ratio = 0
                    bear_ratio = 0

                return {
                    'epoch': epoch,
                    'lock_price': lock_price / 1e8,
                    'close_price': close_price / 1e8,
                    'result': result_dir,
                    'total_bnb': total_amount / 1e18,
                    'bull_bnb': bull_amount / 1e18,
                    'bear_bnb': bear_amount / 1e18,
                    'bull_ratio': bull_ratio,
                    'bear_ratio': bear_ratio,
                    'extreme_bull': bull_ratio > 1.5,
                    'extreme_bear': bear_ratio > 1.5
                }
            except:
                pass
        time.sleep(0.5)
    return None

def main():
    total = END_EPOCH - START_EPOCH + 1
    sys.stdout.write(f"Fetching epochs {START_EPOCH} to {END_EPOCH} ({total} rounds)\n")
    sys.stdout.flush()

    # Resume support
    all_data = []
    if os.path.exists(OUTPUT_FILE):
        try:
            all_data = json.load(open(OUTPUT_FILE))
            fetched = {d['epoch'] for d in all_data}
            sys.stdout.write(f"Resuming: {len(all_data)} already fetched\n")
            sys.stdout.flush()
        except:
            all_data = []
            fetched = set()
    else:
        fetched = set()

    errors = 0
    for epoch in range(START_EPOCH, END_EPOCH + 1):
        if epoch in fetched:
            continue

        data = get_round_data(epoch)
        if data:
            all_data.append(data)
            fetched.add(epoch)
            errors = 0
            count = len(all_data)
            if count % 100 == 0:
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(all_data, f)
                sys.stdout.write(f"  {count}/{total} done (epoch {epoch})\n")
                sys.stdout.flush()
        else:
            errors += 1
            if errors > 5:
                sys.stdout.write(f"  errors at epoch {epoch}, sleeping 5s\n")
                sys.stdout.flush()
                time.sleep(5)
                errors = 0

        time.sleep(0.08)

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)
    sys.stdout.write(f"\nDone! {len(all_data)} rounds saved\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
