#!/usr/bin/env python3
"""Find profitable wallets in PancakeSwap Prediction by analyzing claim events."""
import json, time, sys
from web3 import Web3
from collections import defaultdict

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
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

def main():
    w3 = connect()
    if not w3:
        print("Failed to connect to BSC")
        return
    
    # 获取最近1000个区块的Claim事件
    cur = w3.eth.block_number
    start = cur - 1000  # 大约1小时
    
    print(f"Searching blocks {start} to {cur}")
    
    # Claim事件签名
    CLAIM_TOPIC = Web3.keccak(text="Claim(address,uint256,uint256)").hex()
    
    try:
        logs = w3.eth.get_logs({
            'address': CONTRACT,
            'fromBlock': start,
            'toBlock': cur,
            'topics': [CLAIM_TOPIC]
        })
        
        print(f"Found {len(logs)} claim events")
        
        # 分析每个钱包的claim金额
        wallet_claims = defaultdict(int)
        wallet_bets = defaultdict(int)
        
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
        
        # 按claim金额排序
        sorted_wallets = sorted(wallet_claims.items(), key=lambda x: x[1], reverse=True)
        
        print("\nTop 10 profitable wallets:")
        for i, (wallet, claims) in enumerate(sorted_wallets[:10]):
            bets = wallet_bets[wallet]
            avg_claim = claims / bets if bets > 0 else 0
            print(f"{i+1}. {wallet}: claims={claims/1e18:.4f} BNB, bets={bets}, avg={avg_claim/1e18:.4f} BNB")
        
        # 保存到文件
        with open('profitable_wallets.json', 'w') as f:
            json.dump(sorted_wallets[:20], f, indent=2)
        
        print(f"\nSaved top 20 wallets to profitable_wallets.json")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()