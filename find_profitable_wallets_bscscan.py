#!/usr/bin/env python3
"""Find profitable wallets using BSCScan API."""
import json, time, sys, urllib.request
from collections import defaultdict

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
API_KEY = "YourBSCScanAPIKey"  # 需要用户提供的API Key

def fetch_claim_events(start_block, end_block):
    """Fetch claim events from BSCScan API."""
    url = (f"https://api.bscscan.com/api?module=logs&action=getLogs"
           f"&address={CONTRACT}"
           f"&fromBlock={start_block}&toBlock={end_block}"
           f"&topic0=0x34fcbac0073d7c3d388e51312faf357774904998eeb8fca628b9e6f65ee1cbf7"
           f"&page=1&offset=1000&apikey={API_KEY}")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if data['status'] == '1' and isinstance(data['result'], list):
            return data['result']
        else:
            print(f"API error: {data.get('message', 'Unknown error')}")
            return []
    except Exception as e:
        print(f"Request failed: {e}")
        return []

def main():
    # 获取当前区块号
    try:
        req = urllib.request.Request(
            "https://api.bscscan.com/api?module=proxy&action=eth_blockNumber&apikey=" + API_KEY,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if 'result' in data:
            current_block = int(data['result'], 16)
            print(f"Current block: {current_block}")
        else:
            print("Failed to get current block")
            return
    except Exception as e:
        print(f"Error getting block: {e}")
        return
    
    # 分析最近10000个区块（约6小时）
    start_block = current_block - 10000
    end_block = current_block
    
    print(f"Analyzing blocks {start_block} to {end_block}")
    
    # 获取Claim事件
    claims = fetch_claim_events(start_block, end_block)
    print(f"Found {len(claims)} claim events")
    
    # 分析每个钱包的claim金额
    wallet_claims = defaultdict(int)
    wallet_epochs = defaultdict(list)
    
    for claim in claims:
        try:
            # 解析事件数据
            sender = '0x' + claim['topics'][1][-40:]
            epoch = int(claim['topics'][2], 16)
            amount = int(claim['data'], 16)
            
            wallet_claims[sender] += amount
            wallet_epochs[sender].append(epoch)
        except Exception as e:
            print(f"Error parsing claim: {e}")
            continue
    
    # 按claim金额排序
    sorted_wallets = sorted(wallet_claims.items(), key=lambda x: x[1], reverse=True)
    
    print("\nTop 10 profitable wallets (by claim amount):")
    for i, (wallet, claims) in enumerate(sorted_wallets[:10]):
        epochs = wallet_epochs[wallet]
        print(f"{i+1}. {wallet}: claims={claims/1e18:.4f} BNB, bets={len(epochs)}")
    
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