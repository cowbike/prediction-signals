#!/usr/bin/env python3
"""Fetch 5000 earlier rounds (462743-467742) for whale analysis."""
import json, time, sys
from web3 import Web3

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

def connect():
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 30}))
            if w3.is_connected():
                print(f"Connected to {rpc}")
                return w3
        except:
            continue
    return None

def get_round_data(w3, epoch):
    selector = "0x8c65c81f"
    epoch_hex = hex(epoch)[2:].zfill(64)
    for attempt in range(3):
        try:
            result = w3.eth.call({'to': CONTRACT, 'data': selector + epoch_hex})
            result_bytes = bytes(result)
            lock_price = int.from_bytes(result_bytes[128:160], 'big', signed=True)
            close_price = int.from_bytes(result_bytes[160:192], 'big', signed=True)
            total_amount = int.from_bytes(result_bytes[256:288], 'big')
            bull_amount = int.from_bytes(result_bytes[288:320], 'big')
            bear_amount = int.from_bytes(result_bytes[320:352], 'big')
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
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                return None

def main():
    print(f"Fetching epochs {START_EPOCH} to {END_EPOCH} ({END_EPOCH - START_EPOCH + 1} rounds)")
    w3 = connect()
    if not w3:
        print("Cannot connect to BSC")
        sys.exit(1)

    all_data = []
    errors = 0

    for epoch in range(START_EPOCH, END_EPOCH + 1):
        data = get_round_data(w3, epoch)
        if data:
            all_data.append(data)
            errors = 0
            if len(all_data) % 200 == 0:
                print(f"  Fetched {len(all_data)}/{END_EPOCH - START_EPOCH + 1} (epoch {epoch})")
        else:
            errors += 1
            if errors > 10:
                print(f"  Too many errors, sleeping 5s...")
                time.sleep(5)
                errors = 0
        time.sleep(0.05)

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)
    print(f"\nDone! Saved {len(all_data)} rounds to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
