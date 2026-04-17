#!/usr/bin/env python3
"""Use The Graph to query PancakeSwap Prediction data."""
import json, time, urllib.request

# PancakeSwap Prediction V2 子图
SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/pancakeswap/prediction-v2"

def query_subgraph(query, variables=None):
    """Query The Graph subgraph."""
    data = {
        "query": query,
        "variables": variables or {}
    }
    
    try:
        req = urllib.request.Request(
            SUBGRAPH_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        
        if 'errors' in result:
            print(f"GraphQL错误: {result['errors']}")
            return None
        
        return result.get('data')
    except Exception as e:
        print(f"查询失败: {e}")
        return None

def find_whale_address():
    """Find whale address starting with 0xc2fa81e."""
    print("🔍 使用The Graph查找赚钱大户地址...")
    
    # 查询最近的betBull/betBear事件
    query = """
    query GetRecentBets($first: Int!, $skip: Int!) {
      bets(first: $first, skip: $skip, orderBy: createdAt, orderDirection: desc) {
        id
        sender
        amount
        position
        round {
          id
          epoch
        }
        createdAt
      }
    }
    """
    
    # 查询最近的1000笔下注
    variables = {
        "first": 1000,
        "skip": 0
    }
    
    data = query_subgraph(query, variables)
    if not data:
        print("❌ 查询失败")
        return None
    
    bets = data.get('bets', [])
    print(f"找到 {len(bets)} 笔下注")
    
    # 查找匹配的地址
    target_prefix = "0xc2fa81e"
    found_addresses = set()
    
    for bet in bets:
        sender = bet.get('sender', '')
        if sender.lower().startswith(target_prefix.lower()):
            found_addresses.add(sender)
            print(f"✅ 找到匹配地址: {sender}")
    
    if found_addresses:
        return list(found_addresses)[0]
    else:
        print("❌ 未找到匹配地址")
        return None

def get_whale_bets(wallet_address, limit=5000):
    """Get betting history for a specific wallet."""
    print(f"📊 查询钱包 {wallet_address} 的下注记录...")
    
    all_bets = []
    skip = 0
    batch_size = 1000
    
    while len(all_bets) < limit:
        query = """
        query GetWalletBets($sender: String!, $first: Int!, $skip: Int!) {
          bets(where: { sender: $sender }, first: $first, skip: $skip, orderBy: createdAt, orderDirection: desc) {
            id
            sender
            amount
            position
            round {
              id
              epoch
              position
              failed
            }
            createdAt
          }
        }
        """
        
        variables = {
            "sender": wallet_address.lower(),
            "first": batch_size,
            "skip": skip
        }
        
        data = query_subgraph(query, variables)
        if not data:
            break
        
        bets = data.get('bets', [])
        if not bets:
            break
        
        all_bets.extend(bets)
        skip += batch_size
        
        print(f"  已获取 {len(all_bets)} 笔下注...")
        
        if len(bets) < batch_size:
            break
        
        time.sleep(0.5)  # 避免限制
    
    return all_bets[:limit]

def analyze_bets(bets):
    """Analyze betting history."""
    print(f"\n📈 分析 {len(bets)} 笔下注...")
    
    total_bets = len(bets)
    total_amount = 0
    wins = 0
    losses = 0
    draws = 0
    
    bet_details = []
    
    for bet in bets:
        try:
            amount = float(bet.get('amount', 0)) / 1e18  # 转换为BNB
            position = bet.get('position', '')  # BULL或BEAR
            round_data = bet.get('round', {})
            epoch = round_data.get('epoch', 0)
            round_position = round_data.get('position', '')  # 实际结果
            failed = round_data.get('failed', False)
            
            total_amount += amount
            
            # 判断输赢
            if failed:
                outcome = 'DRAW'
                draws += 1
            elif position == round_position:
                outcome = 'WIN'
                wins += 1
            else:
                outcome = 'LOSE'
                losses += 1
            
            bet_details.append({
                'epoch': int(epoch),
                'direction': position,
                'amount': amount,
                'result': round_position,
                'outcome': outcome,
                'timestamp': bet.get('createdAt', 0)
            })
            
        except Exception as e:
            print(f"解析下注失败: {e}")
            continue
    
    # 计算统计信息
    win_rate = wins / total_bets * 100 if total_bets > 0 else 0
    
    # 计算盈亏（简化计算）
    profit = 0
    for bet in bet_details:
        if bet['outcome'] == 'WIN':
            # 假设赔率为1.98x（平台抽成1%）
            profit += bet['amount'] * 0.98
        elif bet['outcome'] == 'LOSE':
            profit -= bet['amount']
        # DRAW不盈不亏
    
    roi = profit / total_amount * 100 if total_amount > 0 else 0
    
    return {
        'total_bets': total_bets,
        'total_amount': total_amount,
        'wins': wins,
        'losses': losses,
        'draws': draws,
        'win_rate': win_rate,
        'profit': profit,
        'roi': roi,
        'bet_details': bet_details
    }

def main():
    print("=" * 60)
    print("🐋 使用The Graph查询赚钱大户数据")
    print("=" * 60)
    
    # 查找地址
    wallet_address = find_whale_address()
    
    if not wallet_address:
        print("\n尝试使用已知地址...")
        # 从之前的分析中，我们知道盈利大户的地址
        # 但需要完整地址。让我尝试一个可能的地址格式
        wallet_address = "0xc2fa81e"  # 这不是完整地址
        print(f"使用地址前缀: {wallet_address}")
        print("注意：需要完整42字符地址才能查询")
        return
    
    # 查询下注记录
    print(f"\n📊 查询钱包 {wallet_address} 的下注记录（最多5000笔）...")
    bets = get_whale_bets(wallet_address, 5000)
    
    if not bets:
        print("❌ 未找到下注记录")
        return
    
    # 分析下注
    analysis = analyze_bets(bets)
    
    print(f"\n📈 统计结果：")
    print(f"  总下注次数: {analysis['total_bets']}")
    print(f"  总下注金额: {analysis['total_amount']:.4f} BNB")
    print(f"  赢: {analysis['wins']}")
    print(f"  输: {analysis['losses']}")
    print(f"  平: {analysis['draws']}")
    print(f"  胜率: {analysis['win_rate']:.1f}%")
    print(f"  总盈亏: {analysis['profit']:.4f} BNB")
    print(f"  ROI: {analysis['roi']:.1f}%")
    
    # 保存数据
    output_file = '/home/cowbike/prediction-signals/whale_real_bets.json'
    with open(output_file, 'w') as f:
        json.dump({
            'wallet_address': wallet_address,
            'analysis': {
                'total_bets': analysis['total_bets'],
                'total_amount': analysis['total_amount'],
                'wins': analysis['wins'],
                'losses': analysis['losses'],
                'draws': analysis['draws'],
                'win_rate': analysis['win_rate'],
                'profit': analysis['profit'],
                'roi': analysis['roi']
            },
            'bet_details': analysis['bet_details']
        }, f, indent=2)
    
    print(f"\n💾 数据已保存到: {output_file}")
    
    # 显示最近10笔下注
    print(f"\n📊 最近10笔下注：")
    print(f"{'Epoch':<10} {'方向':<6} {'金额(BNB)':<12} {'结果':<6} {'盈亏'}")
    print("-" * 60)
    
    for bet in analysis['bet_details'][:10]:
        outcome_str = "✅" if bet['outcome'] == 'WIN' else "❌" if bet['outcome'] == 'LOSE' else "➖"
        print(f"{bet['epoch']:<10} {bet['direction']:<6} {bet['amount']:<12.4f} {bet['result'] or '未知':<6} {outcome_str}")
    
    print("\n" + "=" * 60)
    print("💡 结论：")
    if analysis['roi'] > 0:
        print(f"✅ 钱包 {wallet_address} 盈利！")
        print(f"   ROI: {analysis['roi']:.1f}%")
    else:
        print(f"❌ 钱包 {wallet_address} 亏损！")
        print(f"   ROI: {analysis['roi']:.1f}%")
    print("=" * 60)

if __name__ == "__main__":
    main()