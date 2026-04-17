#!/usr/bin/env python3
"""Batch fetch 5000 rounds data with resume support."""
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

OUTPUT_FILE = '/home/cowbike/prediction-signals/rounds_5000.json'
PROGRESS_FILE = '/home/cowbike/prediction-signals/fetch_progress.json'

def connect():
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 30}))
            if w3.is_connected():
                return w3
        except:
            continue
    return None

def get_current_epoch(w3):
    """Get current epoch from contract."""
    selector = "0x76671808"
    try:
        result = w3.eth.call({'to': CONTRACT, 'data': selector})
        return int.from_bytes(result, 'big')
    except Exception as e:
        print(f"Error getting epoch: {e}")
        return None

def get_round_data(w3, epoch):
    """Get round data for a specific epoch."""
    selector = "0x8c65c81f"
    epoch_hex = hex(epoch)[2:].zfill(64)
    
    for attempt in range(3):
        try:
            result = w3.eth.call({'to': CONTRACT, 'data': selector + epoch_hex})
            result_bytes = bytes(result)
            
            # Parse round data
            lock_price = int.from_bytes(result_bytes[128:160], 'big', signed=True)
            close_price = int.from_bytes(result_bytes[160:192], 'big', signed=True)
            total_amount = int.from_bytes(result_bytes[256:288], 'big')
            bull_amount = int.from_bytes(result_bytes[288:320], 'big')
            bear_amount = int.from_bytes(result_bytes[320:352], 'big')
            
            if close_price > lock_price:
                result_dir = "BULL"
            elif close_price < lock_price:
                result_dir = "BEAR"
            else:
                result_dir = "DRAW"
            
            # 计算赔率偏差
            if bull_amount > 0 and bear_amount > 0:
                bull_ratio = bull_amount / bear_amount
                bear_ratio = bear_amount / bull_amount
            else:
                bull_ratio = 0
                bear_ratio = 0
            
            return {
                'epoch': epoch,
                'lock_price': lock_price / 1e8,
                'close_price': close_price / 1e8,
                'result': result_dir,
                'total_bnb': total_amount / 1e18,
                'bull_bnb': bull_amount / 1e18,
                'bear_bnb': bear_amount / 1e18,
                'bull_ratio': bull_ratio,
                'bear_ratio': bear_ratio,
                'extreme_bull': bull_ratio > 1.5,
                'extreme_bear': bear_ratio > 1.5
            }
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                return None

def load_progress():
    """Load progress from file."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'start_epoch': None, 'fetched_epochs': [], 'last_epoch': None}

def save_progress(progress):
    """Save progress to file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def main():
    print("=" * 60)
    print("🚀 批量爬取5000期PancakeSwap Prediction数据")
    print("=" * 60)
    
    # 连接BSC
    w3 = connect()
    if not w3:
        print("❌ 无法连接BSC")
        return
    
    # 获取当前epoch
    current_epoch = get_current_epoch(w3)
    if not current_epoch:
        print("❌ 无法获取当前epoch")
        return
    
    print(f"📊 当前epoch: {current_epoch}")
    
    # 加载进度
    progress = load_progress()
    
    # 确定起始epoch
    if progress['start_epoch'] is None:
        start_epoch = current_epoch - 5000
        progress['start_epoch'] = start_epoch
        progress['fetched_epochs'] = []
        print(f"🎯 目标: 爬取 {start_epoch} 到 {current_epoch-1} (共5000期)")
    else:
        start_epoch = progress['start_epoch']
        print(f"🔄 继续上次进度: 从 {start_epoch} 开始")
        print(f"   已完成: {len(progress['fetched_epochs'])} 期")
    
    # 加载已有数据
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            all_data = json.load(f)
    else:
        all_data = []
    
    # 创建已爬取epoch的集合，用于快速查找
    fetched_set = set(progress['fetched_epochs'])
    
    # 开始爬取
    print(f"\n📈 开始爬取数据...")
    batch_size = 50  # 每批处理50个
    errors = 0
    
    for epoch in range(start_epoch, current_epoch):
        # 跳过已爬取的
        if epoch in fetched_set:
            continue
        
        # 获取数据
        data = get_round_data(w3, epoch)
        
        if data:
            all_data.append(data)
            progress['fetched_epochs'].append(epoch)
            progress['last_epoch'] = epoch
            
            # 每100期保存一次
            if len(all_data) % 100 == 0:
                # 保存数据
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(all_data, f, indent=2)
                save_progress(progress)
                
                # 计算统计信息
                print(f"  ✅ 已完成 {len(all_data)} 期 (epoch: {epoch})")
                
                # 计算反向下注胜率
                extreme_bull = [r for r in all_data if r['extreme_bull']]
                extreme_bear = [r for r in all_data if r['extreme_bear']]
                
                if extreme_bull:
                    wins = len([r for r in extreme_bull if r['result'] == 'BEAR'])
                    win_rate = wins / len(extreme_bull) * 100
                    print(f"     BULL极端偏差 → 反向下BEAR胜率: {win_rate:.1f}% ({wins}/{len(extreme_bull)})")
                
                if extreme_bear:
                    wins = len([r for r in extreme_bear if r['result'] == 'BULL'])
                    win_rate = wins / len(extreme_bear) * 100
                    print(f"     BEAR极端偏差 → 反向下BULL胜率: {win_rate:.1f}% ({wins}/{len(extreme_bear)})")
        else:
            errors += 1
            if errors > 10:
                print(f"  ⚠️ 连续错误过多，暂停5秒...")
                time.sleep(5)
                errors = 0
        
        # 控制请求速率
        time.sleep(0.05)
        
        # 检查是否完成
        if len(all_data) >= 5000:
            print(f"\n🎉 已完成5000期数据爬取！")
            break
    
    # 最终保存
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)
    save_progress(progress)
    
    print(f"\n📊 最终统计:")
    print(f"  总计爬取: {len(all_data)} 期")
    print(f"  时间范围: epoch {start_epoch} 到 {progress.get('last_epoch', current_epoch-1)}")
    
    # 计算最终统计
    extreme_bull = [r for r in all_data if r['extreme_bull']]
    extreme_bear = [r for r in all_data if r['extreme_bear']]
    
    print(f"\n📈 反向下注策略分析:")
    print(f"  BULL极端偏差 (>1.5x): {len(extreme_bull)} 轮")
    if extreme_bull:
        wins = len([r for r in extreme_bull if r['result'] == 'BEAR'])
        print(f"    → 反向下BEAR胜率: {wins/len(extreme_bull)*100:.1f}% ({wins}/{len(extreme_bull)})")
    
    print(f"  BEAR极端偏差 (>1.5x): {len(extreme_bear)} 轮")
    if extreme_bear:
        wins = len([r for r in extreme_bear if r['result'] == 'BULL'])
        print(f"    → 反向下BULL胜率: {wins/len(extreme_bear)*100:.1f}% ({wins}/{len(extreme_bear)})")
    
    # 计算整体胜率
    total_wins = len([r for r in all_data if (r['extreme_bull'] and r['result'] == 'BEAR') or (r['extreme_bear'] and r['result'] == 'BULL')])
    total_extreme = len(extreme_bull) + len(extreme_bear)
    
    if total_extreme > 0:
        overall_win_rate = total_wins / total_extreme * 100
        print(f"\n🏆 反向下注整体胜率: {overall_win_rate:.1f}% ({total_wins}/{total_extreme})")
    
    print(f"\n💾 数据已保存到: {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()