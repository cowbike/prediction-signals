#!/usr/bin/env python3
"""Find profitable wallets by analyzing recent rounds."""
import json, time, sys
from web3 import Web3
from collections import defaultdict

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
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

def main():
    w3 = connect()
    if not w3:
        print("Failed to connect to BSC")
        return
    
    # 合约ABI（简化版）
    abi = [
        {
            "constant": True,
            "inputs": [],
            "name": "currentEpoch",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "epoch", "type": "uint256"}],
            "name": "rounds",
            "outputs": [
                {"name": "epoch", "type": "uint256"},
                {"name": "startTimestamp", "type": "uint256"},
                {"name": "lockTimestamp", "type": "uint256"},
                {"name": "closeTimestamp", "type": "uint256"},
                {"name": "lockPrice", "type": "int256"},
                {"name": "closePrice", "type": "int256"},
                {"name": "lockOracleId", "type": "uint256"},
                {"name": "closeOracleId", "type": "uint256"},
                {"name": "totalAmount", "type": "uint256"},
                {"name": "bullAmount", "type": "uint256"},
                {"name": "bearAmount", "type": "uint256"},
                {"name": "rewardBaseCalAmount", "type": "uint256"},
                {"name": "rewardAmount", "type": "uint256"},
                {"name": "oracleCalled", "type": "bool"}
            ],
            "type": "function"
        }
    ]
    
    contract = w3.eth.contract(address=CONTRACT, abi=abi)
    
    # 获取当前轮次
    try:
        current_epoch = contract.functions.currentEpoch().call()
        print(f"Current epoch: {current_epoch}")
    except Exception as e:
        print(f"Error getting current epoch: {e}")
        return
    
    # 分析最近20轮
    wallet_claims = defaultdict(int)
    wallet_bets = defaultdict(int)
    
    print(f"Analyzing last 20 rounds (epochs {current_epoch-20} to {current_epoch-1})")
    
    for epoch in range(current_epoch-20, current_epoch):
        try:
            round_data = contract.functions.rounds(epoch).call()
            total_amount = round_data[8]
            bull_amount = round_data[9]
            bear_amount = round_data[10]
            
            print(f"Epoch {epoch}: total={total_amount/1e18:.4f} BNB, bull={bull_amount/1e18:.4f} BNB, bear={bear_amount/1e18:.4f} BNB")
            
            # 这里我们无法直接获取每个钱包的下注情况
            # 需要查询事件日志
            
        except Exception as e:
            print(f"Error getting round {epoch}: {e}")
            continue
    
    print("\nNote: To analyze individual wallets, we need to query bet and claim events.")
    print("This requires BSCScan API or direct event log queries.")
    print("Due to RPC rate limits, we need a different approach.")
    
    # 建议使用BSCScan API
    print("\n建议：")
    print("1. 使用BSCScan API查询betBull/betBear和Claim事件")
    print("2. 分析每个钱包的净盈亏")
    print("3. 找到盈利大户的完整地址")
    
    # 保存当前轮次信息
    with open('recent_rounds.json', 'w') as f:
        json.dump({
            'current_epoch': current_epoch,
            'analyzed_epochs': list(range(current_epoch-20, current_epoch))
        }, f, indent=2)

if __name__ == "__main__":
    main()