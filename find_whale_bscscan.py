#!/usr/bin/env python3
"""Use BSCScan API to find whale address and fetch bets."""
import json, time, urllib.request, urllib.parse

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
TARGET_PREFIX = "0xc2fa81e"

def fetch_bscscan_logs(topic0, from_block, to_block):
    """Fetch logs from BSCScan API."""
    url = (f"https://api.bscscan.com/api?module=logs&action=getLogs"
           f"&address={CONTRACT}"
           f"&fromBlock={from_block}&toBlock={to_block}"
           f"&topic0={topic0}"
           f"&page=1&offset=1000")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if data['status'] == '1' and isinstance(data['result'], list):
            return data['result']
        else:
            print(f"API响应: {data.get('message', 'Unknown')}")
            return []
    except Exception as e:
        print(f"请求失败: {e}")
        return []

def main():
    print("=" * 60)
    print("🔍 使用BSCScan API查找赚钱大户地址")
    print("=" * 60)
    
    # betBull事件签名
    bet_bull_topic = "0x5c7b7b683048b1b10e166dd0d3c3e4a8b64fe5c31c6f34e7f7c6e79e30a6a7ae"
    bet_bear_topic = "0x5c7b7b683048b1b10e166dd0d3c3e4a8b64fe5c31c6f34e7f7c6e79e30a6a7af"
    
    # 查询最近的区块
    # 先获取当前区块号
    try:
        url = "https://api.bscscan.com/api?module=proxy&action=eth_blockNumber"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if 'result' in data:
            current_block = int(data['result'], 16)
            print(f"当前区块: {current_block}")
        else:
            print("无法获取当前区块")
            return
    except Exception as e:
        print(f"获取区块号失败: {e}")
        return
    
    # 查询最近10000个区块
    start_block = current_block - 10000
    end_block = current_block
    
    print(f"查询区块 {start_block} 到 {end_block}...")
    
    # 查询betBull事件
    print("查询betBull事件...")
    bull_logs = fetch_bscscan_logs(bet_bull_topic, start_block, end_block)
    print(f"找到 {len(bull_logs)} 个betBull事件")
    
    # 查询betBear事件
    print("查询betBear事件...")
    bear_logs = fetch_bscscan_logs(bet_bear_topic, start_block, end_block)
    print(f"找到 {len(bear_logs)} 个betBear事件")
    
    # 查找匹配的地址
    found_addresses = set()
    
    for log in bull_logs + bear_logs:
        try:
            # 从topics中提取sender地址
            if 'topics' in log and len(log['topics']) > 1:
                sender = '0x' + log['topics'][1][-40:]
                if sender.lower().startswith(TARGET_PREFIX.lower()):
                    found_addresses.add(sender)
                    print(f"✅ 找到匹配地址: {sender}")
        except Exception as e:
            print(f"解析日志失败: {e}")
    
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

if __name__ == "__main__":
    main()