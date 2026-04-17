#!/usr/bin/env python3
"""Fetch whale bets by querying blocks one by one."""
import json, time
from web3 import Web3

WALLET = "0xd8b53f94144b5bad90b156ecca28422c26c08e6c"
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
                return w3
        except:
            continue
    return None

def get_bets_in_block(w3, block_number, wallet_topic, bet_bull_topic, bet_bear_topic):
    """Get bets from a specific block."""
    bets = []
    
    try:
        # 查询betBull事件
        logs = w3.eth.get_logs({
            'address': CONTRACT,
            'fromBlock': block_number,
            'toBlock': block_number,
            'topics': [bet_bull_topic, wallet_topic]
        })
        
        for log in logs:
            epoch = int(log['topics'][2].hex(), 16)
            amount = int(log['data'].hex(), 16) / 1e18
            bets.append({
                'epoch': epoch,
                'direction': 'BULL',
                'amount': amount,
                'block': block_number,
                'tx_hash': log['transactionHash'].hex()
            })
        
        # 查询betBear事件
        logs = w3.eth.get_logs({
            'address': CONTRACT,
            'fromBlock': block_number,
            'toBlock': block_number,
            'topics': [bet_bear_topic, wallet_topic]
        })
        
        for log in logs:
            epoch = int(log['topics'][2].hex(), 16)
            amount = int(log['data'].hex(), 16) / 1e18
            bets.append({
                'epoch': epoch,
                'direction': 'BEAR',
                'amount': amount,
                'block': block_number,
                'tx_hash': log['transactionHash'].hex()
            })
        
        return bets
    except Exception as e:
        return None  # 表示查询失败

def main():
    print("=" * 60)
    print("🐋 逐个区块查询赚钱大户下注记录")
    print("=" * 60)
    print(f"钱包地址: {WALLET}")
    
    # 连接BSC
    w3 = connect()
    if not w3:
        print("❌ 无法连接BSC")
        return
    
    print("✅ 已连接BSC")
    
    # 获取当前区块
    current_block = w3.eth.block_number
    print(f"当前区块: {current_block}")
    
    # 准备topic
    bet_bull_topic = Web3.keccak(text="betBull(uint256,address,uint256)").hex()
    bet_bear_topic = Web3.keccak(text="betBear(uint256,address,uint256)").hex()
    wallet_topic = '0x' + WALLET[2:].lower().zfill(64)
    
    # 逐个区块查询
    print("\n📊 开始查询最近的区块...")
    
    all_bets = []
    failed_count = 0
    max_failures = 20  # 最多连续失败20次
    
    # 从当前区块开始，往前查询
    block = current_block
    rpc_index = 0
    
    while len(all_bets) < 5000 and failed_count < max_failures:
        # 切换RPC节点
        if failed_count > 0 and failed_count % 5 == 0:
            rpc_index = (rpc_index + 1) % len(RPCS)
            try:
                w3 = Web3(Web3.HTTPProvider(RPCS[rpc_index], request_kwargs={'timeout': 30}))
                if w3.is_connected():
                    print(f"切换到RPC: {RPCS[rpc_index]}")
                else:
                    failed_count += 1
                    continue
            except:
                failed_count += 1
                continue
        
        # 查询当前区块
        bets = get_bets_in_block(w3, block, wallet_topic, bet_bull_topic, bet_bear_topic)
        
        if bets is None:
            # 查询失败
            failed_count += 1
            time.sleep(1)
            block -= 1
            continue
        
        # 查询成功，重置失败计数
        failed_count = 0
        
        if bets:
            all_bets.extend(bets)
            print(f"区块 {block}: 找到 {len(bets)} 笔下注，总计 {len(all_bets)} 笔")
        
        # 继续查询前一个区块
        block -= 1
        
        # 每查询100个区块打印一次进度
        if (current_block - block) % 100 == 0:
            print(f"已查询 {current_block - block} 个区块，找到 {len(all_bets)} 笔下注")
        
        # 短暂延迟，避免请求过快
        time.sleep(0.1)
    
    print(f"\n✅ 查询完成，找到 {len(all_bets)} 笔下注记录")
    
    if not all_bets:
        print("❌ 未找到下注记录")
        return
    
    # 按epoch排序
    all_bets.sort(key=lambda x: x['epoch'])
    
    # 去重（可能有重复的交易）
    seen_tx = set()
    unique_bets = []
    for bet in all_bets:
        if bet['tx_hash'] not in seen_tx:
            seen_tx.add(bet['tx_hash'])
            unique_bets.append(bet)
    
    print(f"去重后: {len(unique_bets)} 笔下注")
    
    # 统计信息
    total_amount = sum(b['amount'] for b in unique_bets)
    bull_bets = len([b for b in unique_bets if b['direction'] == 'BULL'])
    bear_bets = len([b for b in unique_bets if b['direction'] == 'BEAR'])
    
    print(f"\n📈 统计信息：")
    print(f"  总下注次数: {len(unique_bets)}")
    print(f"  总下注金额: {total_amount:.4f} BNB")
    print(f"  BULL方向: {bull_bets} 次 ({bull_bets/len(unique_bets)*100:.1f}%)")
    print(f"  BEAR方向: {bear_bets} 次 ({bear_bets/len(unique_bets)*100:.1f}%)")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_real_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': WALLET,
            'total_bets': len(unique_bets),
            'stats': {
                'total_amount': total_amount,
                'bull_bets': bull_bets,
                'bear_bets': bear_bets,
                'bull_pct': bull_bets/len(unique_bets)*100 if unique_bets else 0,
                'bear_pct': bear_bets/len(unique_bets)*100 if unique_bets else 0
            },
            'bets': unique_bets
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近20笔下注
    print(f"\n📊 最近20笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'区块'}")
    print("-" * 50)
    
    for bet in unique_bets[-20:]:
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.6f} {bet['block']}")
    
    print("\n" + "=" * 60)
    print("💡 下一步：获取每轮结果，计算输赢")
    print("=" * 60)

if __name__ == "__main__":
    main()