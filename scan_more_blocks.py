#!/usr/bin/env python3
"""Fetch whale bets by scanning more blocks."""
import json, time
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

WALLET = "0xd8b53F94144B5bAD90b156eCCA28422c26c08e6C"
CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"

def main():
    print("=" * 60)
    print("🐋 扫描更多区块查找赚钱大户下注记录")
    print("=" * 60)
    
    # 连接
    w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/", request_kwargs={'timeout': 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"连接状态: {w3.is_connected()}")
    
    # 获取当前区块
    current_block = w3.eth.block_number
    print(f"当前区块: {current_block}")
    
    # 扫描最近的500个区块（每5分钟一个区块，500个区块约42小时）
    print("\n📊 扫描最近的500个区块...")
    
    found_bets = []
    blocks_to_scan = 500
    
    for i in range(blocks_to_scan):
        block_num = current_block - i
        
        # 每扫描100个区块打印进度
        if i % 100 == 0:
            print(f"已扫描 {i} 个区块，找到 {len(found_bets)} 笔下注")
        
        try:
            # 获取区块信息
            block = w3.eth.get_block(block_num, full_transactions=True)
            
            # 遍历交易
            for tx in block['transactions']:
                # 检查是否是发往Prediction合约的交易
                if tx.get('to') and tx['to'].lower() == CONTRACT.lower():
                    # 检查是否是来自目标钱包的交易
                    if tx.get('from') and tx['from'].lower() == WALLET.lower():
                        input_data = tx.get('input', '0x')
                        
                        if input_data.startswith('0xe8e39d94'):
                            direction = 'BULL'
                        elif input_data.startswith('0x6d6c9860'):
                            direction = 'BEAR'
                        else:
                            continue
                        
                        # 提取epoch
                        if len(input_data) >= 74:
                            epoch_hex = input_data[10:74]
                            epoch = int(epoch_hex, 16)
                        else:
                            epoch = 0
                        
                        # 提取金额
                        value = tx.get('value', 0)
                        amount = value / 1e18
                        
                        found_bets.append({
                            'epoch': epoch,
                            'direction': direction,
                            'amount': amount,
                            'block': block_num,
                            'tx_hash': tx['hash'].hex()
                        })
                        
                        print(f"  🎯 找到下注! 区块 {block_num}, Epoch {epoch}: {direction} {amount:.6f} BNB")
            
            # 短暂延迟，避免请求过快
            if i % 10 == 0:
                time.sleep(0.1)
            
        except Exception as e:
            # 静默处理错误，继续扫描
            continue
    
    print(f"\n✅ 扫描完成，找到 {len(found_bets)} 笔下注记录")
    
    if not found_bets:
        print("❌ 未找到下注记录")
        print("可能需要扫描更多区块（500个区块约42小时）")
        return
    
    # 按区块号排序（从新到旧）
    found_bets.sort(key=lambda x: x['block'], reverse=True)
    
    # 统计信息
    total_amount = sum(b['amount'] for b in found_bets)
    bull_bets = len([b for b in found_bets if b['direction'] == 'BULL'])
    bear_bets = len([b for b in found_bets if b['direction'] == 'BEAR'])
    
    print(f"\n📈 统计信息：")
    print(f"  总下注次数: {len(found_bets)}")
    print(f"  总下注金额: {total_amount:.4f} BNB")
    print(f"  BULL方向: {bull_bets} 次 ({bull_bets/len(found_bets)*100:.1f}%)")
    print(f"  BEAR方向: {bear_bets} 次 ({bear_bets/len(found_bets)*100:.1f}%)")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_real_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': WALLET,
            'total_bets': len(found_bets),
            'blocks_scanned': blocks_to_scan,
            'stats': {
                'total_amount': total_amount,
                'bull_bets': bull_bets,
                'bear_bets': bear_bets,
                'bull_pct': bull_bets/len(found_bets)*100 if found_bets else 0,
                'bear_pct': bear_bets/len(found_bets)*100 if found_bets else 0
            },
            'bets': found_bets
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近20笔下注
    print(f"\n📊 最近20笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'区块'}")
    print("-" * 50)
    
    for bet in found_bets[:20]:
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.6f} {bet['block']}")
    
    print("\n" + "=" * 60)
    print("💡 下一步：获取每轮结果，计算输赢")
    print("=" * 60)

if __name__ == "__main__":
    main()