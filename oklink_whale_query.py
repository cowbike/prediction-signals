#!/usr/bin/env python3
"""Fetch whale bets using OKLink API."""
import json, time, urllib.request

WALLET_ADDRESS = "0xd8b53f94144b5bad90b156ecca28422c26c08e6c"
CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"

def fetch_oklink_transactions(address, page=1, limit=100):
    """Fetch transactions from OKLink API."""
    url = f"https://www.oklink.com/api/v5/explorer/address/transaction-list?chainShortName=bsc&address={address}&page={page}&limit={limit}"
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if data.get('code') == '0':
            return data.get('data', [])
        else:
            print(f"OKLink API错误: {data.get('msg', 'Unknown')}")
            return []
    except Exception as e:
        print(f"请求失败: {e}")
        return []

def fetch_oklink_internal_transactions(address, page=1, limit=100):
    """Fetch internal transactions from OKLink API."""
    url = f"https://www.oklink.com/api/v5/explorer/address/internal-transaction-list?chainShortName=bsc&address={address}&page={page}&limit={limit}"
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        
        if data.get('code') == '0':
            return data.get('data', [])
        else:
            print(f"OKLink API错误: {data.get('msg', 'Unknown')}")
            return []
    except Exception as e:
        print(f"请求失败: {e}")
        return []

def analyze_transactions(transactions):
    """Analyze transactions to find betBull/betBear events."""
    print(f"分析 {len(transactions)} 笔交易...")
    
    bets = []
    
    for tx in transactions:
        try:
            # 检查是否是合约交互
            if tx.get('to') != CONTRACT:
                continue
            
            # 检查方法调用
            method = tx.get('methodId', '')
            input_data = tx.get('input', '')
            
            # betBull方法签名: 0xe8e39d94
            # betBear方法签名: 0x6d6c9860
            if method == '0xe8e39d94' or input_data.startswith('0xe8e39d94'):
                direction = 'BULL'
            elif method == '0x6d6c9860' or input_data.startswith('0x6d6c9860'):
                direction = 'BEAR'
            else:
                continue
            
            # 提取epoch（从input数据中）
            if len(input_data) >= 74:
                epoch_hex = input_data[10:74]  # 去除方法签名(8字符)后取64字符
                epoch = int(epoch_hex, 16)
            else:
                epoch = 0
            
            # 提取金额
            value = int(tx.get('value', '0'), 16) if tx.get('value', '0').startswith('0x') else int(tx.get('value', '0'))
            amount = value / 1e18
            
            bets.append({
                'epoch': epoch,
                'direction': direction,
                'amount': amount,
                'tx_hash': tx.get('txHash', ''),
                'timestamp': tx.get('transactionTime', ''),
                'block': tx.get('height', 0)
            })
            
        except Exception as e:
            print(f"解析交易失败: {e}")
            continue
    
    return bets

def get_round_result_from_oklink(epoch):
    """Get round result from OKLink or other source."""
    # 这里我们可以尝试从其他API获取round结果
    # 或者从我们已有的数据中查找
    return None

def main():
    print("=" * 60)
    print("🐋 使用OKLink查询赚钱大户下注记录")
    print("=" * 60)
    print(f"钱包地址: {WALLET_ADDRESS}")
    
    # 获取交易记录
    print("\n📊 获取交易记录...")
    
    all_transactions = []
    page = 1
    max_pages = 50  # 最多查询50页
    
    while page <= max_pages:
        print(f"  获取第 {page} 页...")
        
        transactions = fetch_oklink_transactions(WALLET_ADDRESS, page, 100)
        if not transactions:
            print(f"  第 {page} 页无数据，停止查询")
            break
        
        all_transactions.extend(transactions)
        print(f"  已获取 {len(all_transactions)} 笔交易")
        
        # 如果获取的交易数量少于限制，说明没有更多数据
        if len(transactions) < 100:
            break
        
        page += 1
        time.sleep(1)  # 避免请求过快
    
    print(f"\n✅ 总共获取 {len(all_transactions)} 笔交易")
    
    # 分析交易，找出下注记录
    print("\n🎯 分析下注记录...")
    bets = analyze_transactions(all_transactions)
    
    print(f"✅ 找到 {len(bets)} 笔下注记录")
    
    if not bets:
        print("❌ 未找到下注记录")
        print("可能原因：")
        print("1. 该地址没有在PancakeSwap Prediction上下注")
        print("2. OKLink API返回的数据不包含完整的input数据")
        print("3. 需要使用其他方法查询")
        return
    
    # 按epoch排序
    bets.sort(key=lambda x: x['epoch'])
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_oklink_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': WALLET_ADDRESS,
            'total_bets': len(bets),
            'bets': bets
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示统计信息
    total_amount = sum(b['amount'] for b in bets)
    bull_bets = len([b for b in bets if b['direction'] == 'BULL'])
    bear_bets = len([b for b in bets if b['direction'] == 'BEAR'])
    
    print(f"\n📈 统计信息：")
    print(f"  总下注次数: {len(bets)}")
    print(f"  总下注金额: {total_amount:.4f} BNB")
    print(f"  BULL方向: {bull_bets} 次")
    print(f"  BEAR方向: {bear_bets} 次")
    
    # 显示最近10笔下注
    print(f"\n📊 最近10笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'时间'}")
    print("-" * 50)
    
    for bet in bets[-10:]:
        timestamp = bet.get('timestamp', '')
        if timestamp:
            # 转换时间戳
            try:
                ts = int(timestamp) / 1000
                time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))
            except:
                time_str = timestamp
        else:
            time_str = "未知"
        
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.4f} {time_str}")
    
    print("\n" + "=" * 60)
    print("💡 下一步：")
    print("1. 获取每轮的结果数据")
    print("2. 计算每笔下注的输赢")
    print("3. 分析赚钱大户的策略")
    print("=" * 60)

if __name__ == "__main__":
    main()