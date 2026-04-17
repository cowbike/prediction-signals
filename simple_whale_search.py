#!/usr/bin/env python3
"""Simple script to find whale address with minimal queries."""
import json, time
from web3 import Web3

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"

def main():
    print("=" * 60)
    print("🔍 简单查询：查找赚钱大户地址")
    print("=" * 60)
    
    # 连接BSC
    try:
        w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/", request_kwargs={'timeout': 30}))
        if not w3.is_connected():
            print("❌ 无法连接BSC")
            return
        print("✅ 已连接BSC")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    # 获取当前区块
    current_block = w3.eth.block_number
    print(f"当前区块: {current_block}")
    
    # 查询最近的100个区块
    start_block = current_block - 100
    end_block = current_block
    
    print(f"查询区块 {start_block} 到 {end_block}...")
    
    # betBull事件签名
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    
    try:
        # 查询betBull事件
        logs = w3.eth.get_logs({
            'address': CONTRACT,
            'fromBlock': start_block,
            'toBlock': end_block,
            'topics': [bet_bull_topic]
        })
        
        print(f"找到 {len(logs)} 个betBull事件")
        
        # 查找匹配的地址
        found_addresses = set()
        for log in logs:
            sender = '0x' + log['topics'][1].hex()[-40:]
            if sender.lower().startswith('0xc2fa81e'):
                found_addresses.add(sender)
                print(f"✅ 找到匹配地址: {sender}")
        
        if found_addresses:
            print(f"\n🎉 找到的地址: {list(found_addresses)}")
            
            # 保存地址
            with open('/home/cowbike/prediction-signals/whale_address.json', 'w') as f:
                json.dump({
                    'found_addresses': list(found_addresses),
                    'timestamp': time.time()
                }, f, indent=2)
            
            print("地址已保存到 whale_address.json")
        else:
            print("\n❌ 未找到匹配地址")
            print("尝试查询更多区块...")
            
            # 尝试查询更多区块
            for i in range(10):
                start = current_block - (i+2) * 100
                end = current_block - (i+1) * 100
                
                try:
                    logs = w3.eth.get_logs({
                        'address': CONTRACT,
                        'fromBlock': start,
                        'toBlock': end,
                        'topics': [bet_bull_topic]
                    })
                    
                    for log in logs:
                        sender = '0x' + log['topics'][1].hex()[-40:]
                        if sender.lower().startswith('0xc2fa81e'):
                            found_addresses.add(sender)
                            print(f"✅ 找到匹配地址: {sender}")
                    
                    if found_addresses:
                        break
                        
                except Exception as e:
                    print(f"查询区块 {start}-{end} 失败: {e}")
                    time.sleep(1)
                    continue
                
                time.sleep(0.1)
            
            if found_addresses:
                print(f"\n🎉 找到的地址: {list(found_addresses)}")
                
                # 保存地址
                with open('/home/cowbike/prediction-signals/whale_address.json', 'w') as f:
                    json.dump({
                        'found_addresses': list(found_addresses),
                        'timestamp': time.time()
                    }, f, indent=2)
                
                print("地址已保存到 whale_address.json")
            else:
                print("\n❌ 未找到匹配地址")
                print("可能原因：")
                print("1. 该地址最近没有下注活动")
                print("2. 需要查询更早的区块")
                print("3. 地址前缀不正确")
    
    except Exception as e:
        print(f"查询失败: {e}")

if __name__ == "__main__":
    main()