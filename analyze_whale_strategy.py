#!/usr/bin/env python3
"""Analyze whale betting strategy against 5000 rounds data."""
import json
import random

# 读取5000期数据
with open('/home/cowbike/prediction-signals/rounds_5000.json', 'r') as f:
    rounds = json.load(f)

print("=" * 70)
print("🐋 赚钱大户下注策略深度分析")
print("=" * 70)
print(f"数据范围: Epoch {rounds[0]['epoch']} - {rounds[-1]['epoch']} (共{len(rounds)}轮)")

# 从OKLink获取的统计数据
print(f"\n📊 钱包实际下注统计 (来自OKLink):")
print(f"  betBull: 47,254 笔")
print(f"  betBear: 47,020 笔")
print(f"  总下注: 94,274 笔")
print(f"  方向比例: 50.1% BULL / 49.9% BEAR")

# 模拟不同的下注策略
print(f"\n{'='*70}")
print("📈 策略模拟分析")
print("=" * 70)

# 策略1: 纯随机下注 (50/50)
print("\n【策略1】纯随机下注 (50% BULL / 50% BEAR)")
print("-" * 50)

random.seed(42)  # 固定随机种子以便复现
total_bet = 0
wins = 0
losses = 0
profit = 0
bet_amount = 0.03  # 假设平均下注0.03 BNB

for round_data in rounds:
    # 随机选择方向
    bet_direction = random.choice(['BULL', 'BEAR'])
    result = round_data['result']
    
    total_bet += bet_amount
    
    if result == 'DRAW':
        # 平局退回
        pass
    elif bet_direction == result:
        # 赢了
        wins += 1
        # 计算收益 (假设赔率 based on pool ratio)
        if bet_direction == 'BULL':
            odds = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
        else:
            odds = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
        profit += bet_amount * odds * 0.98  # 假设平台抽成2%
    else:
        # 输了
        losses += 1
        profit -= bet_amount

win_rate = wins / len(rounds) * 100
roi = profit / total_bet * 100

print(f"  总下注: {len(rounds)} 轮")
print(f"  赢: {wins} 轮")
print(f"  输: {losses} 轮")
print(f"  胜率: {win_rate:.1f}%")
print(f"  总投入: {total_bet:.2f} BNB")
print(f"  总盈亏: {profit:.4f} BNB")
print(f"  ROI: {roi:.1f}%")

# 策略2: 反向下注 (跟大众反着来)
print("\n【策略2】反向下注 (大众下BULL我下BEAR，反之亦然)")
print("-" * 50)

total_bet = 0
wins = 0
losses = 0
profit = 0

for round_data in rounds:
    # 如果BULL池子大，说明大众看好BULL，我就下BEAR
    if round_data['bull_bnb'] > round_data['bear_bnb']:
        bet_direction = 'BEAR'
    else:
        bet_direction = 'BULL'
    
    result = round_data['result']
    total_bet += bet_amount
    
    if result == 'DRAW':
        pass
    elif bet_direction == result:
        wins += 1
        if bet_direction == 'BULL':
            odds = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
        else:
            odds = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
        profit += bet_amount * odds * 0.98
    else:
        losses += 1
        profit -= bet_amount

win_rate = wins / len(rounds) * 100
roi = profit / total_bet * 100

print(f"  总下注: {len(rounds)} 轮")
print(f"  赢: {wins} 轮")
print(f"  输: {losses} 轮")
print(f"  胜率: {win_rate:.1f}%")
print(f"  总投入: {total_bet:.2f} BNB")
print(f"  总盈亏: {profit:.4f} BNB")
print(f"  ROI: {roi:.1f}%")

# 策略3: 顺势而为 (跟着大众下)
print("\n【策略3】顺势而为 (大众下BULL我下BULL，反之亦然)")
print("-" * 50)

total_bet = 0
wins = 0
losses = 0
profit = 0

for round_data in rounds:
    # 如果BULL池子大，说明大众看好BULL，我也下BULL
    if round_data['bull_bnb'] > round_data['bear_bnb']:
        bet_direction = 'BULL'
    else:
        bet_direction = 'BEAR'
    
    result = round_data['result']
    total_bet += bet_amount
    
    if result == 'DRAW':
        pass
    elif bet_direction == result:
        wins += 1
        if bet_direction == 'BULL':
            odds = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
        else:
            odds = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
        profit += bet_amount * odds * 0.98
    else:
        losses += 1
        profit -= bet_amount

win_rate = wins / len(rounds) * 100
roi = profit / total_bet * 100

print(f"  总下注: {len(rounds)} 轮")
print(f"  赢: {wins} 轮")
print(f"  输: {losses} 轮")
print(f"  胜率: {win_rate:.1f}%")
print(f"  总投入: {total_bet:.2f} BNB")
print(f"  总盈亏: {profit:.4f} BNB")
print(f"  ROI: {roi:.1f}%")

# 策略4: 只在极端偏差时下注
print("\n【策略4】只在极端偏差时下注 (赔率>1.5x)")
print("-" * 50)

total_bet = 0
wins = 0
losses = 0
skips = 0
profit = 0

for round_data in rounds:
    bull_ratio = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
    bear_ratio = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
    
    # 只在极端偏差时下注
    if bull_ratio > 1.5:
        bet_direction = 'BEAR'  # 反向下注
    elif bear_ratio > 1.5:
        bet_direction = 'BULL'  # 反向下注
    else:
        skips += 1
        continue
    
    result = round_data['result']
    total_bet += bet_amount
    
    if result == 'DRAW':
        pass
    elif bet_direction == result:
        wins += 1
        if bet_direction == 'BULL':
            odds = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
        else:
            odds = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
        profit += bet_amount * odds * 0.98
    else:
        losses += 1
        profit -= bet_amount

total_rounds = wins + losses
win_rate = wins / total_rounds * 100 if total_rounds > 0 else 0
roi = profit / total_bet * 100 if total_bet > 0 else 0

print(f"  下注轮数: {total_rounds} 轮 (跳过 {skips} 轮)")
print(f"  赢: {wins} 轮")
print(f"  输: {losses} 轮")
print(f"  胜率: {win_rate:.1f}%")
print(f"  总投入: {total_bet:.2f} BNB")
print(f"  总盈亏: {profit:.4f} BNB")
print(f"  ROI: {roi:.1f}%")

# 策略5: 动态下注金额 (根据赔率调整)
print("\n【策略5】动态下注金额 (根据赔率调整下注大小)")
print("-" * 50)

total_bet = 0
wins = 0
losses = 0
profit = 0

for round_data in rounds:
    bull_ratio = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
    bear_ratio = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
    
    # 根据赔率调整下注金额
    if bull_ratio > 1.5:
        bet_direction = 'BEAR'
        # 赔率越高，下注越大
        dynamic_bet = min(0.1, 0.02 * bull_ratio)
    elif bear_ratio > 1.5:
        bet_direction = 'BULL'
        dynamic_bet = min(0.1, 0.02 * bear_ratio)
    else:
        # 正常情况，小额下注
        bet_direction = random.choice(['BULL', 'BEAR'])
        dynamic_bet = 0.01
    
    result = round_data['result']
    total_bet += dynamic_bet
    
    if result == 'DRAW':
        pass
    elif bet_direction == result:
        wins += 1
        if bet_direction == 'BULL':
            odds = round_data['bear_bnb'] / round_data['bull_bnb'] if round_data['bull_bnb'] > 0 else 1
        else:
            odds = round_data['bull_bnb'] / round_data['bear_bnb'] if round_data['bear_bnb'] > 0 else 1
        profit += dynamic_bet * odds * 0.98
    else:
        losses += 1
        profit -= dynamic_bet

win_rate = wins / len(rounds) * 100
roi = profit / total_bet * 100 if total_bet > 0 else 0

print(f"  总下注: {len(rounds)} 轮")
print(f"  赢: {wins} 轮")
print(f"  输: {losses} 轮")
print(f"  胜率: {win_rate:.1f}%")
print(f"  总投入: {total_bet:.2f} BNB")
print(f"  总盈亏: {profit:.4f} BNB")
print(f"  ROI: {roi:.1f}%")

print(f"\n{'='*70}")
print("💡 核心洞察")
print("=" * 70)
print("""
1. 赚钱大户的下注模式：
   - 94,274笔下注，几乎每轮都下
   - BULL和BEAR各占50%，方向均衡
   - 每笔下注金额较小(0.02-0.06 BNB)

2. 可能的盈利策略：
   - 不是简单的反向下注（反向下注ROI为负）
   - 可能结合了赔率分析和时机选择
   - 动态调整下注金额和方向

3. 关键成功因素：
   - 高频下注：94,274笔需要极大的执行力
   - 严格资金管理：每笔下注控制在0.02-0.06 BNB
   - 长期坚持：从2022年9月持续至今

4. 风险提示：
   - 单纯随机下注是亏损的
   - 需要算法支持才能盈利
   - 需要大量资金支撑高频下注
""")

# 保存分析结果
output = {
    'wallet': '0xd8b53F94144B5bAD90b156eCCA28422c26c08e6C',
    'total_bets': 94274,
    'bull_bets': 47254,
    'bear_bets': 47020,
    'analysis_date': '2026-04-15',
    'rounds_analyzed': len(rounds),
    'epoch_range': f"{rounds[0]['epoch']} - {rounds[-1]['epoch']}"
}

with open('/home/cowbike/prediction-signals/whale_analysis_summary.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"\n💾 分析结果已保存到 whale_analysis_summary.json")