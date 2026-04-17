#!/usr/bin/env python3
"""Fetch whale bets using correct checksum address."""
import json, time
from web3 import Web3

WALLET = "0xd8b53F94144B5bAD90b156eCCA28422c26c08e6C"  # 正确的checksum地址
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

def main():
    print("=" * 60)
    print("🐋 使用正确地址查询赚钱大户下注记录")
    print("=" * 60)
    print(f"钱包地址: {WALLET}")
    
    # 连接BSC
    w3 = connect()
    if not w3:
        print("❌ 无法连接BSC")
        return
    
    # 获取当前区块
    current_block = w3.eth.block_number
    print(f"当前区块: {current_block}")
    
    # 准备topic
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    wallet_topic = '0x' + WALLET[2:].lower().zfill(64)
    
    print(f"钱包topic: {wallet_topic}")
    
    # 查询最近的区块，每次查询10个区块
    print("\n📊 开始查询最近的区块...")
    
    all_bets = []
    chunk_size = 10
    max_chunks = 100  # 最多查询1000个区块
    
    for chunk in range(max_chunks):
        start_block = current_block - (chunk + 1) * chunk_size
        end_block = current_block - chunk * chunk_size
        
        try:
            # 查询betBull事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': start_block,
                'toBlock': end_block,
                'topics': [bet_bull_topic, wallet_topic]
            })
            
            for log in logs:
                epoch = int(log['topics'][2].hex(), 16)
                amount = int(log['data'].hex(), 16) / 1e18
                all_bets.append({
                    'epoch': epoch,
                    'direction': 'BULL',
                    'amount': amount,
                    'block': log['blockNumber'],
                    'tx_hash': log['transactionHash'].hex()
                })
            
            # 查询betBear事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': start_block,
                'toBlock': end_block,
                'topics': [bet_bear_topic, wallet_topic]
            })
            
            for log in logs:
                epoch = int(log['topics'][2].hex(), 16)
                amount = int(log['data'].hex(), 16) / 1e18
                all_bets.append({
                    'epoch': epoch,
                    'direction': 'BEAR',
                    'amount': amount,
                    'block': log['blockNumber'],
                    'tx_hash': log['transactionHash'].hex()
                })
            
            if all_bets:
                print(f"区块 {start_block}-{end_block}: 找到 {len(all_bets)} 笔下注")
                break  # 找到下注就停止
            
        except Exception as e:
            print(f"查询区块 {start_block}-{end_block} 失败: {e}")
            time.sleep(1)
            continue
        
        time.sleep(0.1)
    
    if not all_bets:
        print("❌ 未找到下注记录")
        return
    
    print(f"\n✅ 找到 {len(all_bets)} 笔下注记录")
    
    # 按epoch排序
    all_bets.sort(key=lambda x: x['epoch'])
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_real_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': WALLET,
            'total_bets': len(all_bets),
            'bets': all_bets
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近10笔下注
    print(f"\n📊 最近10笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'区块'}")
    print("-" * 50)
    
    for bet in all_bets[-10:]:
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.6f} {bet['block']}")
    
    print("\n" + "=" * 60)
    print("💡 成功找到下注记录！下一步：获取每轮结果")
    print("=" * 60)

if __name__ == "__main__":
    main()