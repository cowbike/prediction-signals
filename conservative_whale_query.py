#!/usr/bin/env python3
"""Fetch whale bets with conservative RPC usage."""
import json, time
from web3 import Web3

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

def find_whale_address(w3):
    """Find whale address with conservative queries."""
    print("🔍 查找赚钱大户地址（保守查询策略）...")
    
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    
    current_block = w3.eth.block_number
    print(f"当前区块: {current_block}")
    
    # 使用非常小的查询范围：每次50个区块
    chunk_size = 50
    max_chunks = 100  # 最多查询5000个区块
    
    found_addresses = set()
    
    for i in range(max_chunks):
        start_block = current_block - (i + 1) * chunk_size
        end_block = current_block - i * chunk_size
        
        try:
            # 查询betBull事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': start_block,
                'toBlock': end_block,
                'topics': [bet_bull_topic]
            })
            
            for log in logs:
                sender = '0x' + log['topics'][1].hex()[-40:]
                if sender.lower().startswith('0xc2fa81e'):
                    found_addresses.add(sender)
                    print(f"✅ 找到地址: {sender}")
            
            # 查询betBear事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': start_block,
                'toBlock': end_block,
                'topics': [bet_bear_topic]
            })
            
            for log in logs:
                sender = '0x' + log['topics'][1].hex()[-40:]
                if sender.lower().startswith('0xc2fa81e'):
                    found_addresses.add(sender)
                    print(f"✅ 找到地址: {sender}")
            
            if found_addresses:
                print(f"🎉 找到地址: {list(found_addresses)}")
                return list(found_addresses)[0]
            
            # 每查询5次打印进度
            if (i + 1) % 5 == 0:
                print(f"  已查询 {(i+1)*chunk_size} 个区块...")
            
        except Exception as e:
            print(f"查询区块 {start_block}-{end_block} 失败: {e}")
            time.sleep(2)  # 失败后等待更长时间
            continue
        
        time.sleep(0.2)  # 每次查询后等待200ms
    
    print("❌ 未找到匹配地址")
    return None

def get_whale_bets(w3, wallet_address, num_rounds=5000):
    """Get betting history for a specific wallet."""
    print(f"📊 查询钱包 {wallet_address} 的下注记录...")
    
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    
    # 准备钱包地址的topic
    wallet_topic = '0x' + wallet_address[2:].lower().zfill(64)
    
    current_block = w3.eth.block_number
    
    # 查询最近的区块，但使用保守策略
    chunk_size = 50
    max_chunks = 200  # 最多查询10000个区块
    
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
            time.sleep(2)
            continue
        
        time.sleep(0.1)  # 每次查询后等待100ms
    
    # 按epoch排序
    bets.sort(key=lambda x: x['epoch'])
    
    return bets[:num_rounds]

def get_round_result(w3, epoch):
    """Get round result for a specific epoch."""
    selector = "0x8c65c81f"
    epoch_hex = hex(epoch)[2:].zfill(64)
    
    for attempt in range(3):
        try:
            result = w3.eth.call({'to': CONTRACT, 'data': selector + epoch_hex})
            result_bytes = bytes(result)
            
            # 解析round数据
            lock_price = int.from_bytes(result_bytes[128:160], 'big', signed=True)
            close_price = int.from_bytes(result_bytes[160:192], 'big', signed=True)
            
            if close_price > lock_price:
                return 'BULL'
            elif close_price < lock_price:
                return 'BEAR'
            else:
                return 'DRAW'
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                return None

def main():
    print("=" * 60)
    print("🐋 保守策略查询赚钱大户数据")
    print("=" * 60)
    
    # 连接BSC
    w3 = connect()
    if not w3:
        print("❌ 无法连接BSC")
        return
    
    # 查找地址
    wallet_address = find_whale_address(w3)
    
    if not wallet_address:
        print("\n❌ 无法找到钱包地址")
        print("尝试使用已知的盈利大户地址格式...")
        # 从之前的分析中，我们知道盈利大户的地址是0xc2fa81e...
        # 但我们需要完整地址。让我尝试一个可能的地址
        wallet_address = "0xc2fa81e"  # 这不是完整地址
        print(f"使用地址前缀: {wallet_address}")
        print("注意：这不是完整地址，无法查询")
        return
    
    # 查询下注记录
    print(f"\n📊 查询钱包 {wallet_address} 的下注记录（最多5000笔）...")
    bets = get_whale_bets(w3, wallet_address, 5000)
    
    if not bets:
        print("❌ 未找到下注记录")
        return
    
    print(f"✅ 找到 {len(bets)} 笔下注记录")
    
    # 获取每轮结果（只查询最近的100笔，避免太多请求）
    print("\n🎯 获取最近100笔下注的结果...")
    results = {}
    for i, bet in enumerate(bets[-100:]):
        if i % 10 == 0:
            print(f"  处理 {i+1}/100...")
        
        epoch = bet['epoch']
        if epoch not in results:
            result = get_round_result(w3, epoch)
            results[epoch] = result
            time.sleep(0.2)  # 避免限制
    
    # 分析最近的100笔下注
    print("\n📈 分析最近100笔下注...")
    
    recent_bets = bets[-100:]
    total_bets = len(recent_bets)
    total_amount = sum(b['amount'] for b in recent_bets)
    wins = 0
    losses = 0
    draws = 0
    
    for bet in recent_bets:
        epoch = bet['epoch']
        direction = bet['direction']
        result = results.get(epoch)
        
        if result == direction:
            wins += 1
        elif result == 'DRAW':
            draws += 1
        else:
            losses += 1
    
    win_rate = wins / total_bets * 100 if total_bets > 0 else 0
    
    print(f"\n📈 最近100笔下注统计：")
    print(f"  总下注次数: {total_bets}")
    print(f"  总下注金额: {total_amount:.4f} BNB")
    print(f"  赢: {wins}")
    print(f"  输: {losses}")
    print(f"  平: {draws}")
    print(f"  胜率: {win_rate:.1f}%")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_recent_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': wallet_address,
            'total_bets': len(bets),
            'recent_100': {
                'total_bets': total_bets,
                'total_amount': total_amount,
                'wins': wins,
                'losses': losses,
                'draws': draws,
                'win_rate': win_rate
            },
            'bets': recent_bets,
            'results': results
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近10笔下注
    print(f"\n📊 最近10笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'结果':<6}")
    print("-" * 40)
    
    for bet in recent_bets[-10:]:
        result = results.get(bet['epoch'], '未知')
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.4f} {result or '未知':<6}")
    
    print("\n" + "=" * 60)
    print("💡 结论：")
    if win_rate > 50:
        print(f"✅ 钱包 {wallet_address} 胜率超过50%！")
        print(f"   胜率: {win_rate:.1f}%")
    else:
        print(f"❌ 钱包 {wallet_address} 胜率低于50%")
        print(f"   胜率: {win_rate:.1f}%")
    print("=" * 60)

if __name__ == "__main__":
    main()