#!/usr/bin/env python3
"""Use a known whale address to fetch betting history."""
import json, time
from web3 import Web3

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"

# 从之前的深度分析中，我们知道盈利大户的地址是0xc2fa81e...
# 但我们需要完整地址。让我尝试一个可能的地址格式
# 实际上，我需要找到完整地址。让我尝试使用一个已知的盈利大户地址

# 从记忆中，我知道盈利大户赚了218 BNB，使用反众下注策略
# 让我尝试使用一个可能的地址格式
WALLET_ADDRESS = "0xc2fa81e000000000000000000000000000000000"  # 假设的完整地址

def connect():
    try:
        w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/", request_kwargs={'timeout': 30}))
        if w3.is_connected():
            print("✅ 已连接BSC")
            return w3
        else:
            print("❌ 无法连接BSC")
            return None
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return None

def get_whale_bets(w3, wallet_address, num_rounds=5000):
    """Get betting history for a specific wallet."""
    print(f"📊 查询钱包 {wallet_address} 的下注记录...")
    
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    
    # 准备钱包地址的topic
    wallet_topic = '0x' + wallet_address[2:].lower().zfill(64)
    
    current_block = w3.eth.block_number
    
    # 使用非常小的查询范围
    chunk_size = 10  # 每次只查询10个区块
    max_chunks = 100  # 最多查询1000个区块
    
    bets = []
    
    for i in range(max_chunks):
        start_block = current_block - (i + 1) * chunk_size
        end_block = current_block - i * chunk_size
        
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
                amount = int(log['data'].hex(), 16)
                
                bets.append({
                    'epoch': epoch,
                    'direction': 'BULL',
                    'amount': amount / 1e18,
                    'block': log['blockNumber']
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
                amount = int(log['data'].hex(), 16)
                
                bets.append({
                    'epoch': epoch,
                    'direction': 'BEAR',
                    'amount': amount / 1e18,
                    'block': log['blockNumber']
                })
            
            # 每查询10次打印进度
            if (i + 1) % 10 == 0:
                print(f"  已查询 {(i+1)*chunk_size} 个区块，找到 {len(bets)} 笔下注")
            
            # 如果找到足够的下注，就停止
            if len(bets) >= num_rounds:
                print(f"🎉 已找到 {len(bets)} 笔下注，满足要求")
                break
            
        except Exception as e:
            print(f"查询区块 {start_block}-{end_block} 失败: {e}")
            time.sleep(2)  # 失败后等待更长时间
            continue
        
        time.sleep(0.5)  # 每次查询后等待500ms
    
    # 按epoch排序
    bets.sort(key=lambda x: x['epoch'])
    
    return bets[:num_rounds]

def main():
    print("=" * 60)
    print("🐋 使用假设地址查询下注记录")
    print("=" * 60)
    
    # 连接BSC
    w3 = connect()
    if not w3:
        return
    
    # 使用假设的地址
    print(f"使用地址: {WALLET_ADDRESS}")
    print("注意：这是假设的地址，可能不正确")
    
    # 查询下注记录
    print(f"\n📊 查询下注记录（最多5000笔）...")
    bets = get_whale_bets(w3, WALLET_ADDRESS, 5000)
    
    if not bets:
        print("❌ 未找到下注记录")
        print("可能原因：")
        print("1. 地址不正确")
        print("2. 该地址没有下注活动")
        print("3. 需要查询更早的区块")
        return
    
    print(f"✅ 找到 {len(bets)} 笔下注记录")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_assumed_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': WALLET_ADDRESS,
            'total_bets': len(bets),
            'bets': bets
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近10笔下注
    print(f"\n📊 最近10笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'区块'}")
    print("-" * 40)
    
    for bet in bets[-10:]:
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.4f} {bet['block']}")
    
    print("\n" + "=" * 60)
    print("💡 结论：")
    print(f"查询到 {len(bets)} 笔下注记录")
    print("但这只是假设的地址，需要找到真正的地址才能进行准确分析")
    print("=" * 60)

if __name__ == "__main__":
    main()