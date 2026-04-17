#!/usr/bin/env python3
"""Fetch real betting history for profitable wallet 0xc2fa81e..."""
import json, time, sys, os
from web3 import Web3
from datetime import datetime

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
    "https://bsc-dataseed4.binance.org/",
]

# 先尝试找到完整地址
TARGET_PREFIX = "0xc2fa81e"

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

def find_wallet_address(w3):
    """Find the full address starting with 0xc2fa81e."""
    print(f"🔍 搜索以 {TARGET_PREFIX} 开头的钱包地址...")
    
    # 方法1：查询最近的betBull/betBear事件，找匹配的地址
    # betBull事件签名
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    
    # 查询最近的区块
    current_block = w3.eth.block_number
    start_block = current_block - 10000  # 最近10000个区块
    
    print(f"查询区块 {start_block} 到 {current_block}...")
    
    # 由于RPC限制，我们使用更小的范围
    chunk_size = 500
    found_addresses = set()
    
    for chunk_start in range(start_block, current_block, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, current_block)
        
        try:
            # 查询betBull事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': chunk_start,
                'toBlock': chunk_end,
                'topics': [bet_bull_topic]
            })
            
            for log in logs:
                # 提取sender地址（topics[1]）
                sender = '0x' + log['topics'][1].hex()[-40:]
                if sender.lower().startswith(TARGET_PREFIX.lower()):
                    found_addresses.add(sender)
                    print(f"✅ 找到匹配地址: {sender}")
            
            # 查询betBear事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': chunk_start,
                'toBlock': chunk_end,
                'topics': [bet_bear_topic]
            })
            
            for log in logs:
                sender = '0x' + log['topics'][1].hex()[-40:]
                if sender.lower().startswith(TARGET_PREFIX.lower()):
                    found_addresses.add(sender)
                    print(f"✅ 找到匹配地址: {sender}")
            
            if found_addresses:
                break
                
        except Exception as e:
            print(f"查询区块 {chunk_start}-{chunk_end} 失败: {e}")
            time.sleep(1)
            continue
        
        time.sleep(0.1)  # 避免限制
    
    if found_addresses:
        return list(found_addresses)[0]
    else:
        print("❌ 未找到匹配地址")
        return None

def get_wallet_bets(w3, wallet_address, start_epoch, end_epoch):
    """Get betting history for a specific wallet."""
    print(f"📊 查询钱包 {wallet_address} 的下注记录...")
    
    # betBull事件签名
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    
    # 查询最近的区块
    current_block = w3.eth.block_number
    start_block = current_block - 50000  # 查询最近50000个区块
    
    # 准备钱包地址的topic
    wallet_topic = '0x' + wallet_address[2:].lower().zfill(64)
    
    bets = []
    
    # 由于RPC限制，我们使用更小的范围
    chunk_size = 200
    processed_blocks = 0
    
    for chunk_start in range(start_block, current_block, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, current_block)
        
        try:
            # 查询betBull事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': chunk_start,
                'toBlock': chunk_end,
                'topics': [bet_bull_topic, wallet_topic]
            })
            
            for log in logs:
                # 解析事件数据
                epoch = int(log['topics'][2].hex(), 16)
                amount = int(log['data'].hex(), 16)
                
                bets.append({
                    'epoch': epoch,
                    'direction': 'BULL',
                    'amount': amount / 1e18,
                    'block': log['blockNumber'],
                    'tx_hash': log['transactionHash'].hex()
                })
            
            # 查询betBear事件
            logs = w3.eth.get_logs({
                'address': CONTRACT,
                'fromBlock': chunk_start,
                'toBlock': chunk_end,
                'topics': [bet_bear_topic, wallet_topic]
            })
            
            for log in logs:
                epoch = int(log['topics'][2].hex(), 16)
                amount = int(log['data'].hex(), 16)
                
                bets.append({
                    'epoch': epoch,
                    'direction': 'BEAR',
                    'amount': amount / 1e18,
                    'block': log['blockNumber'],
                    'tx_hash': log['transactionHash'].hex()
                })
            
            processed_blocks += chunk_size
            if processed_blocks % 1000 == 0:
                print(f"  已处理 {processed_blocks} 个区块，找到 {len(bets)} 笔下注")
            
        except Exception as e:
            print(f"查询区块 {chunk_start}-{chunk_end} 失败: {e}")
            time.sleep(2)
            continue
        
        time.sleep(0.05)  # 避免限制
    
    # 按epoch排序
    bets.sort(key=lambda x: x['epoch'])
    
    return bets

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
    print("🐋 查询赚钱大户0xc2fa81e的真实下注记录")
    print("=" * 60)
    
    # 连接BSC
    w3 = connect()
    if not w3:
        print("❌ 无法连接BSC")
        return
    
    # 查找完整地址
    wallet_address = find_wallet_address(w3)
    if not wallet_address:
        print("❌ 无法找到钱包地址，尝试使用已知地址...")
        # 从记忆或文件中查找已知地址
        wallet_address = "0xc2fa81e"  # 暂时使用前缀
        print(f"使用地址前缀: {wallet_address}")
    
    # 获取当前epoch
    current_epoch = int(w3.eth.call({
        'to': CONTRACT,
        'data': "0x76671808"
    }).hex(), 16)
    
    print(f"📊 当前epoch: {current_epoch}")
    
    # 查询下注记录
    print("\n📈 查询下注记录（最近50000个区块）...")
    bets = get_wallet_bets(w3, wallet_address, current_epoch-5000, current_epoch)
    
    print(f"\n✅ 找到 {len(bets)} 笔下注记录")
    
    if not bets:
        print("❌ 未找到下注记录")
        return
    
    # 获取每轮结果
    print("\n🎯 获取每轮结果...")
    results = {}
    for i, bet in enumerate(bets):
        if i % 10 == 0:
            print(f"  处理 {i+1}/{len(bets)}...")
        
        epoch = bet['epoch']
        if epoch not in results:
            result = get_round_result(w3, epoch)
            results[epoch] = result
            time.sleep(0.1)  # 避免限制
    
    # 分析下注记录
    print("\n📊 分析下注记录...")
    
    total_bets = len(bets)
    total_amount = sum(b['amount'] for b in bets)
    wins = 0
    losses = 0
    draws = 0
    profit = 0
    
    bet_details = []
    
    for bet in bets:
        epoch = bet['epoch']
        direction = bet['direction']
        amount = bet['amount']
        result = results.get(epoch)
        
        if result == direction:
            outcome = 'WIN'
            wins += 1
            # 计算收益（简化：假设赔率为2x）
            profit += amount * 1.9  # 假设平台抽成5%
        elif result == 'DRAW':
            outcome = 'DRAW'
            draws += 1
            profit += amount  # 平局退回
        else:
            outcome = 'LOSE'
            losses += 1
            profit -= amount
        
        bet_details.append({
            'epoch': epoch,
            'direction': direction,
            'amount': amount,
            'result': result,
            'outcome': outcome,
            'profit': profit
        })
    
    # 计算统计信息
    win_rate = wins / total_bets * 100 if total_bets > 0 else 0
    roi = profit / total_amount * 100 if total_amount > 0 else 0
    
    print(f"\n📈 统计结果：")
    print(f"  总下注次数: {total_bets}")
    print(f"  总下注金额: {total_amount:.4f} BNB")
    print(f"  赢: {wins}")
    print(f"  输: {losses}")
    print(f"  平: {draws}")
    print(f"  胜率: {win_rate:.1f}%")
    print(f"  总盈亏: {profit:.4f} BNB")
    print(f"  ROI: {roi:.1f}%")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_real_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': wallet_address,
            'total_bets': total_bets,
            'total_amount': total_amount,
            'wins': wins,
            'losses': losses,
            'draws': draws,
            'win_rate': win_rate,
            'profit': profit,
            'roi': roi,
            'bets': bet_details
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近10笔下注
    print(f"\n📊 最近10笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'结果':<6} {'盈亏(BNB)':<12}")
    print("-" * 60)
    
    for bet in bet_details[-10:]:
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.4f} {bet['result'] or '未知':<6} {bet['profit']:<12.4f}")
    
    print("\n" + "=" * 60)
    print("💡 结论：")
    if roi > 0:
        print(f"✅ 钱包 {wallet_address} 盈利！")
        print(f"   ROI: {roi:.1f}%")
    else:
        print(f"❌ 钱包 {wallet_address} 亏损！")
        print(f"   ROI: {roi:.1f}%")
    print("=" * 60)

if __name__ == "__main__":
    main()