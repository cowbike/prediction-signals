#!/usr/bin/env python3
"""Fetch real betting history for wallet 0xd8b53f94144b5bad90b156ecca28422c26c08e6c"""
import json, time, urllib.request

WALLET = "0xd8b53f94144b5bad90b156ecca28422c26c08e6c"
CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"

# betBull: 0xe8e39d94
# betBear: 0x6d6c9860

def fetch_bscscan_txs(address, startblock=0, endblock=99999999):
    """Fetch transactions from BSCScan API (no key needed for basic queries)."""
    url = (f"https://api.bscscan.com/api?module=account&action=txlist"
           f"&address={address}&startblock={startblock}&endblock={endblock}"
           f"&page=1&offset=10000&sort=desc")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if data['status'] == '1':
            return data['result']
        else:
            print(f"API响应: {data.get('message', 'Unknown')}")
            return []
    except Exception as e:
        print(f"请求失败: {e}")
        return []

def analyze_transactions(transactions):
    """Analyze transactions to find betBull/betBear events."""
    bets = []
    
    for tx in transactions:
        try:
            # 检查是否是发往Prediction合约的交易
            if tx.get('to', '').lower() != CONTRACT.lower():
                continue
            
            # 获取input数据
            input_data = tx.get('input', '')
            if len(input_data) < 10:
                continue
            
            # 检查方法签名
            method_sig = input_data[:10]
            
            if method_sig == '0xe8e39d94':
                direction = 'BULL'
            elif method_sig == '0x6d6c9860':
                direction = 'BEAR'
            else:
                continue
            
            # 提取epoch（从input数据中）
            if len(input_data) >= 74:
                epoch_hex = input_data[10:74]
                epoch = int(epoch_hex, 16)
            else:
                epoch = 0
            
            # 提取金额
            value = int(tx.get('value', '0'))
            amount = value / 1e18
            
            # 获取区块号和时间戳
            block = int(tx.get('blockNumber', 0))
            timestamp = int(tx.get('timeStamp', 0))
            
            bets.append({
                'epoch': epoch,
                'direction': direction,
                'amount': amount,
                'tx_hash': tx.get('hash', ''),
                'block': block,
                'timestamp': timestamp,
                'isError': tx.get('isError', '0')
            })
            
        except Exception as e:
            continue
    
    return bets

def main():
    print("=" * 60)
    print("🐋 使用BSCScan API查询赚钱大户下注记录")
    print("=" * 60)
    print(f"钱包地址: {WALLET}")
    
    # 获取交易记录
    print("\n📊 获取交易记录...")
    transactions = fetch_bscscan_txs(WALLET)
    
    if not transactions:
        print("❌ 未获取到交易记录")
        return
    
    print(f"✅ 获取到 {len(transactions)} 笔交易")
    
    # 分析交易，找出下注记录
    print("\n🎯 分析下注记录...")
    bets = analyze_transactions(transactions)
    
    print(f"✅ 找到 {len(bets)} 笔下注记录")
    
    if not bets:
        print("❌ 未找到下注记录")
        return
    
    # 过滤出成功的下注
    successful_bets = [b for b in bets if b['isError'] == '0']
    print(f"   其中成功: {len(successful_bets)} 笔")
    
    # 按时间排序（从新到旧）
    successful_bets.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # 取最近5000笔
    recent_bets = successful_bets[:5000]
    print(f"   取最近 {len(recent_bets)} 笔进行分析")
    
    # 统计信息
    total_amount = sum(b['amount'] for b in recent_bets)
    bull_bets = len([b for b in recent_bets if b['direction'] == 'BULL'])
    bear_bets = len([b for b in recent_bets if b['direction'] == 'BEAR'])
    
    print(f"\n📈 最近{len(recent_bets)}笔下注统计：")
    print(f"  总下注金额: {total_amount:.4f} BNB")
    print(f"  BULL方向: {bull_bets} 次 ({bull_bets/len(recent_bets)*100:.1f}%)")
    print(f"  BEAR方向: {bear_bets} 次 ({bear_bets/len(recent_bets)*100:.1f}%)")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_real_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': WALLET,
            'total_bets': len(successful_bets),
            'recent_5000': len(recent_bets),
            'stats': {
                'total_amount': total_amount,
                'bull_bets': bull_bets,
                'bear_bets': bear_bets,
                'bull_pct': bull_bets/len(recent_bets)*100 if recent_bets else 0,
                'bear_pct': bear_bets/len(recent_bets)*100 if recent_bets else 0
            },
            'bets': recent_bets
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近20笔下注
    print(f"\n📊 最近20笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'状态'}")
    print("-" * 50)
    
    for bet in recent_bets[:20]:
        status = "✅" if bet['isError'] == '0' else "❌"
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.6f} {status}")
    
    print("\n" + "=" * 60)
    print("💡 下一步：需要获取每轮的结果来计算输赢")
    print("=" * 60)

if __name__ == "__main__":
    main()