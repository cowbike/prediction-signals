#!/usr/bin/env python3
"""
Analyze PancakeSwap V2 Prediction history for a specific wallet.
Fetches betBull/betBear + claim events, computes P&L, generates HTML report.
"""
import json, time, sys, os
from datetime import datetime, timedelta
from web3 import Web3
from collections import defaultdict

WALLET = "0xd8b53f94144b5bad90b156ecca28422c26c08e6c"
CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"

RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
    "https://bsc-dataseed4.binance.org/",
]

# Event signatures
# betBull(uint256 indexed epoch, address indexed sender, uint256 amount)
BET_BULL_TOPIC = "0x5c7b7b683048b1b10e166dd0d3c3e4a8b64fe5c31c6f34e7f7c6e79e30a6a7ae"
# betBear(uint256 indexed epoch, address indexed sender, uint256 amount)
BET_BEAR_TOPIC = "0x5c7b7b683048b1b10e166dd0d3c3e4a8b64fe5c31c6f34e7f7c6e79e30a6a7af"
# Claim(address indexed sender, uint256 indexed epoch, uint256 amount)
CLAIM_TOPIC = "0x4a8b0b2e0d4c7d5e1f3a9c6b8d2e4f0a1c3b5d7e9f1a3c5b7d9e1f3a5c7b9d1e"

# Actually let me use the correct topic hashes
# These are keccak256 of the event signatures
import hashlib

def keccak(text):
    from web3 import Web3
    return Web3.keccak(text=text).hex()

BET_BULL_TOPIC = keccak("betBull(uint256,address,uint256)")
BET_BEAR_TOPIC = keccak("betBear(uint256,address,uint256)")
CLAIM_TOPIC = keccak("Claim(address,uint256,uint256)")

print(f"BetBull topic: {BET_BULL_TOPIC}")
print(f"BetBear topic: {BET_BEAR_TOPIC}")
print(f"Claim topic: {CLAIM_TOPIC}")

def connect():
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 30}))
            if w3.is_connected():
                block = w3.eth.block_number
                print(f"Connected to {rpc}, block: {block}")
                return w3
        except Exception as e:
            print(f"  {rpc} failed: {e}")
    return None

w3 = connect()
if not w3:
    print("ERROR: Cannot connect to BSC")
    sys.exit(1)

# Current block and time estimation
current_block = w3.eth.block_number
# BSC ~3s per block
BLOCKS_PER_DAY = 28800
current_time = datetime.now()

# We want 1-2 years ago
two_years_ago = current_time - timedelta(days=730)
one_year_ago = current_time - timedelta(days=365)

# Estimate blocks
seconds_ago_2y = (current_time - two_years_ago).total_seconds()
seconds_ago_1y = (current_time - one_year_ago).total_seconds()
block_2y_ago = current_block - int(seconds_ago_2y / 3)
block_1y_ago = current_block - int(seconds_ago_1y / 3)

print(f"\nCurrent block: {current_block}")
print(f"~2 years ago block: {block_2y_ago}")
print(f"~1 year ago block: {block_1y_ago}")

wallet_addr = Web3.to_checksum_address(WALLET)
wallet_topic = "0x" + wallet_addr[2:].lower().zfill(64)

contract_addr = Web3.to_checksum_address(CONTRACT)

# Query betBull events
print("\n--- Querying betBull events ---")
betbull_logs = []
chunk_size = 50000
for start in range(block_2y_ago, block_1y_ago, chunk_size):
    end = min(start + chunk_size - 1, block_1y_ago)
    try:
        logs = w3.eth.get_logs({
            'address': contract_addr,
            'topics': [BET_BULL_TOPIC, None, wallet_topic],
            'fromBlock': start,
            'toBlock': end,
        })
        betbull_logs.extend(logs)
        if logs:
            print(f"  blocks {start}-{end}: {len(logs)} betBull events")
    except Exception as e:
        print(f"  blocks {start}-{end}: error - {str(e)[:80]}")
    time.sleep(0.1)

print(f"Total betBull: {len(betbull_logs)}")

# Query betBear events
print("\n--- Querying betBear events ---")
betbear_logs = []
for start in range(block_2y_ago, block_1y_ago, chunk_size):
    end = min(start + chunk_size - 1, block_1y_ago)
    try:
        logs = w3.eth.get_logs({
            'address': contract_addr,
            'topics': [BET_BEAR_TOPIC, None, wallet_topic],
            'fromBlock': start,
            'toBlock': end,
        })
        betbear_logs.extend(logs)
        if logs:
            print(f"  blocks {start}-{end}: {len(logs)} betBear events")
    except Exception as e:
        print(f"  blocks {start}-{end}: error - {str(e)[:80]}")
    time.sleep(0.1)

print(f"Total betBear: {len(betbear_logs)}")

# Query claim events
print("\n--- Querying claim events ---")
claim_logs = []
# Claims can be from any sender to our wallet, or from our wallet
# Claim topic[1] is epoch (indexed), topic[0] is sender (indexed)
# We need: topics[0]=CLAIM_TOPIC, topics[2]=wallet_topic (sender)
for start in range(block_2y_ago, block_1y_ago, chunk_size):
    end = min(start + chunk_size - 1, block_1y_ago)
    try:
        logs = w3.eth.get_logs({
            'address': contract_addr,
            'topics': [CLAIM_TOPIC, None, wallet_topic],
            'fromBlock': start,
            'toBlock': end,
        })
        claim_logs.extend(logs)
        if logs:
            print(f"  blocks {start}-{end}: {len(logs)} claim events")
    except Exception as e:
        print(f"  blocks {start}-{end}: error - {str(e)[:80]}")
    time.sleep(0.1)

print(f"Total claims: {len(claim_logs)}")

# Parse bet events
bets = []
for log in betbull_logs:
    data = log['data'].hex() if isinstance(log['data'], bytes) else log['data']
    if data.startswith('0x'):
        data = data[2:]
    epoch = int(log['topics'][1].hex(), 16) if isinstance(log['topics'][1], bytes) else int(log['topics'][1], 16)
    amount_wei = int(data[:64], 16) if len(data) >= 64 else 0
    amount_bnb = amount_wei / 1e18
    bets.append({
        'epoch': epoch,
        'direction': 'BULL',
        'amount': amount_bnb,
        'block': log['blockNumber'],
    })

for log in betbear_logs:
    data = log['data'].hex() if isinstance(log['data'], bytes) else log['data']
    if data.startswith('0x'):
        data = data[2:]
    epoch = int(log['topics'][1].hex(), 16) if isinstance(log['topics'][1], bytes) else int(log['topics'][1], 16)
    amount_wei = int(data[:64], 16) if len(data) >= 64 else 0
    amount_bnb = amount_wei / 1e18
    bets.append({
        'epoch': epoch,
        'direction': 'BEAR',
        'amount': amount_bnb,
        'block': log['blockNumber'],
    })

# Parse claim events
claimed_epochs = set()
claim_amounts = {}
for log in claim_logs:
    topics = log['topics']
    epoch = int(topics[1].hex(), 16) if isinstance(topics[1], bytes) else int(topics[1], 16)
    data = log['data'].hex() if isinstance(log['data'], bytes) else log['data']
    if data.startswith('0x'):
        data = data[2:]
    amount_wei = int(data[:64], 16) if len(data) >= 64 else 0
    amount_bnb = amount_wei / 1e18
    claimed_epochs.add(epoch)
    claim_amounts[epoch] = amount_bnb

# Sort bets by block
bets.sort(key=lambda x: x['block'])

# Get block timestamps (sample every 1000th block for efficiency)
print("\n--- Getting block timestamps ---")
block_timestamps = {}
blocks_needed = set()
for b in bets:
    blocks_needed.add(b['block'])

# Batch fetch timestamps
blocks_list = sorted(blocks_needed)
for i, blk in enumerate(blocks_list):
    try:
        header = w3.eth.get_block(blk)
        block_timestamps[blk] = header['timestamp']
    except:
        pass
    if i % 500 == 0:
        print(f"  timestamp progress: {i}/{len(blocks_list)}")
    time.sleep(0.02)

# Add timestamp to bets
for b in bets:
    ts = block_timestamps.get(b['block'], 0)
    b['timestamp'] = datetime.fromtimestamp(ts) if ts else None

# Determine win/loss per epoch
# Group bets by epoch
epoch_bets = defaultdict(list)
for b in bets:
    epoch_bets[b['epoch']].append(b)

# For each epoch, check if wallet claimed (won)
for epoch, ebets in epoch_bets.items():
    won = epoch in claimed_epochs
    for b in ebets:
        b['won'] = won
        b['claim_amount'] = claim_amounts.get(epoch, 0)

# Stats
total_bets = len(bets)
total_wins = sum(1 for b in bets if b['won'])
total_losses = total_bets - total_wins
total_amount_bet = sum(b['amount'] for b in bets)
total_claimed = sum(b['claim_amount'] for b in bets)
net_pnl = total_claimed - total_amount_bet
win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0

bull_bets = [b for b in bets if b['direction'] == 'BULL']
bear_bets = [b for b in bets if b['direction'] == 'BEAR']

# Time range
timestamps = [b['timestamp'] for b in bets if b['timestamp']]
time_start = min(timestamps) if timestamps else None
time_end = max(timestamps) if timestamps else None

# Unique epochs
unique_epochs = len(epoch_bets)

# Bet amount distribution
amounts = [b['amount'] for b in bets]
avg_bet = sum(amounts) / len(amounts) if amounts else 0
min_bet = min(amounts) if amounts else 0
max_bet = max(amounts) if amounts else 0

# Monthly breakdown
monthly = defaultdict(lambda: {'bets': 0, 'wins': 0, 'amount': 0.0, 'claimed': 0.0})
for b in bets:
    if b['timestamp']:
        key = b['timestamp'].strftime('%Y-%m')
        monthly[key]['bets'] += 1
        if b['won']:
            monthly[key]['wins'] += 1
        monthly[key]['amount'] += b['amount']
        monthly[key]['claimed'] += b['claim_amount']

# Hourly distribution
hourly = defaultdict(lambda: {'bets': 0, 'wins': 0})
for b in bets:
    if b['timestamp']:
        h = b['timestamp'].hour
        hourly[h]['bets'] += 1
        if b['won']:
            hourly[h]['wins'] += 1

# Save raw data
output = {
    'wallet': WALLET,
    'time_range': f"{time_start} ~ {time_end}" if time_start else "N/A",
    'total_bets': total_bets,
    'total_wins': total_wins,
    'total_losses': total_losses,
    'win_rate': round(win_rate, 2),
    'total_amount_bet': round(total_amount_bet, 4),
    'total_claimed': round(total_claimed, 4),
    'net_pnl': round(net_pnl, 4),
    'bull_bets': len(bull_bets),
    'bear_bets': len(bear_bets),
    'unique_epochs': unique_epochs,
    'avg_bet': round(avg_bet, 6),
    'min_bet': round(min_bet, 6),
    'max_bet': round(max_bet, 6),
    'monthly': {k: v for k, v in sorted(monthly.items())},
    'hourly': {str(k): v for k, v in sorted(hourly.items())},
}

print(f"\n{'='*50}")
print(f"Wallet: {WALLET}")
print(f"Period: {output['time_range']}")
print(f"Total bets: {total_bets}")
print(f"Wins: {total_wins} / Losses: {total_losses} (WR: {win_rate:.1f}%)")
print(f"Total bet: {total_amount_bet:.4f} BNB")
print(f"Total claimed: {total_claimed:.4f} BNB")
print(f"Net P&L: {net_pnl:+.4f} BNB")
print(f"BULL bets: {len(bull_bets)} | BEAR bets: {len(bear_bets)}")
print(f"Unique epochs: {unique_epochs}")
print(f"Avg bet: {avg_bet:.6f} BNB (min: {min_bet:.6f}, max: {max_bet:.6f})")

with open('/home/cowbike/prediction-signals/wallet_analysis.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, default=str)

print("\nData saved to wallet_analysis.json")
