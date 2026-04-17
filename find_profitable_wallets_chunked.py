#!/usr/bin/env python3
"""Find profitable wallets with retry and smaller chunks."""
import json, time, sys
from web3 import Web3
from collections import defaultdict

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
    "https://bsc-dataseed4.binance.org/",
]

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

def get_logs_with_retry(w3, start_block, end_block, max_retries=3):
    """Get logs with retry and exponential backoff."""
    CLAIM_TOPIC = Web3.keccak(text="Claim(address,uint256,uint256)").hex()
    
    for attempt in range(max_retries):
        try:
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': start_block,
                'toBlock': end_block,
                'topics': [CLAIM_TOPIC]
            })
            return logs
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Attempt {attempt+1} failed, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                print(f"All attempts failed: {e}")
                return []

def main():
    w3 = connect()
    if not w3:
        print("Failed to connect to BSC")
        return
    
    # 获取当前区块号
    try:
        current_block = w3.eth.block_number
        print(f"Current block: {current_block}")
    except Exception as e:
        print(f"Error getting block: {e}")
        return
    
    # 分析最近10000个区块，但分成10个小块
    total_blocks = 10000
    chunk_size = 1000
    start_block = current_block - total_blocks
    
    wallet_claims = defaultdict(int)
    wallet_bets = defaultdict(int)
    
    print(f"Analyzing blocks {start_block} to {current_block} in chunks of {chunk_size}")
    
    for chunk_start in range(start_block, current_block, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, current_block)
        
        print(f"Processing blocks {chunk_start} to {chunk_end}...")
        
        logs = get_logs_with_retry(w3, chunk_start, chunk_end)
        
        for log in logs:
            try:
                # 解析事件数据
                sender = '0x' + log['topics'][1].hex()[-40:]
                epoch = int(log['topics'][2].hex(), 16)
                amount = int(log['data'].hex(), 16)
                
                wallet_claims[sender] += amount
                wallet_bets[sender] += 1
            except Exception as e:
                print(f"Error parsing log: {e}")
                continue
        
        # 短暂延迟以避免限制
        time.sleep(0.5)
    
    # 按claim金额排序
    sorted_wallets = sorted(wallet_claims.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\nAnalyzed {sum(wallet_bets.values())} claim events from {len(wallet_claims)} wallets")
    
    print("\nTop 10 profitable wallets:")
    for i, (wallet, claims) in enumerate(sorted_wallets[:10]):
        bets = wallet_bets[wallet]
        avg_claim = claims / bets if bets > 0 else 0
        print(f"{i+1}. {wallet}: claims={claims/1e18:.4f} BNB, bets={bets}, avg={avg_claim/1e18:.4f} BNB")
    
    # 保存到文件
    with open('profitable_wallets.json', 'w') as f:
        json.dump(sorted_wallets[:20], f, indent=2)
    
    print(f"\nSaved top 20 wallets to profitable_wallets.json")
    
    # 检查是否有0xc2fa81e
    for wallet, _ in sorted_wallets[:50]:
        if wallet.lower().startswith('0xc2fa81e'):
            print(f"\nFound target wallet: {wallet}")
            break

if __name__ == "__main__":
    main()