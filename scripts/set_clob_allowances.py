#!/usr/bin/env python3
"""
Set CLOB Allowances for Polymarket Trading.

This script sets the required approvals on Polygon for trading:
1. USDC approval for the exchange contracts (for BUY orders)
2. CTF (Conditional Token) approval for the exchange contracts (for SELL orders)

Run this once per wallet before trading.

Usage:
    python scripts/set_clob_allowances.py

Requires:
    - web3 package: pip install web3
    - polymarket_api_creds.json with private_key
    - POL in wallet for gas fees
"""

import json
import os
import sys

try:
    from web3 import Web3
    from web3.constants import MAX_INT
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    print("ERROR: web3 package not installed. Run: pip install web3")
    sys.exit(1)


# Contract addresses on Polygon
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e on Polygon
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"   # Conditional Token Framework

# Exchange addresses that need approval
EXCHANGE_TARGETS = [
    ("CTF Exchange", "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"),
    ("Neg Risk CTF Exchange", "0xC5d563A36AE78145C45a50134d48A1215220f80a"),
    ("Neg Risk Adapter", "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"),
]

# ABIs
ERC20_APPROVE_ABI = json.loads('''
[{
    "constant": false,
    "inputs": [
        {"name": "_spender", "type": "address"},
        {"name": "_value", "type": "uint256"}
    ],
    "name": "approve",
    "outputs": [{"name": "", "type": "bool"}],
    "payable": false,
    "stateMutability": "nonpayable",
    "type": "function"
}]
''')

ERC1155_SET_APPROVAL_ABI = json.loads('''
[{
    "inputs": [
        {"internalType": "address", "name": "operator", "type": "address"},
        {"internalType": "bool", "name": "approved", "type": "bool"}
    ],
    "name": "setApprovalForAll",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
}]
''')


def load_credentials():
    """Load credentials from polymarket_api_creds.json."""
    creds_path = os.path.join(os.path.dirname(__file__), "..", "polymarket_api_creds.json")

    if not os.path.exists(creds_path):
        print(f"ERROR: Credentials file not found: {creds_path}")
        sys.exit(1)

    with open(creds_path) as f:
        creds = json.load(f)

    private_key = creds.get("private_key")
    if not private_key:
        print("ERROR: private_key not found in credentials file")
        sys.exit(1)

    return private_key


def main():
    print("=" * 60)
    print("Polymarket CLOB Allowance Setup")
    print("=" * 60)
    print()

    # Load credentials
    private_key = load_credentials()

    # Connect to Polygon
    rpc_url = os.environ.get("POLYGON_RPC_URL", "https://polygon-rpc.com")
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not web3.is_connected():
        print("ERROR: Failed to connect to Polygon RPC")
        sys.exit(1)

    print(f"Connected to Polygon (chain_id: {web3.eth.chain_id})")

    # Derive address from private key
    account = web3.eth.account.from_key(private_key)
    pub_key = account.address

    print(f"Wallet: {pub_key}")

    # Check POL balance for gas
    pol_balance = web3.eth.get_balance(pub_key)
    pol_balance_formatted = web3.from_wei(pol_balance, 'ether')
    print(f"POL Balance: {pol_balance_formatted:.4f} POL")

    if pol_balance < web3.to_wei(0.01, 'ether'):
        print("WARNING: Low POL balance. You may not have enough for gas fees.")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)

    # Create contracts
    usdc = web3.eth.contract(address=USDC_ADDRESS, abi=ERC20_APPROVE_ABI)
    ctf = web3.eth.contract(address=CTF_ADDRESS, abi=ERC1155_SET_APPROVAL_ABI)

    nonce = web3.eth.get_transaction_count(pub_key)
    chain_id = web3.eth.chain_id

    print()
    print("Setting approvals for exchange contracts...")
    print("-" * 60)

    for name, target in EXCHANGE_TARGETS:
        print(f"\n[{name}] {target}")

        # 1. USDC approval
        print("  - Setting USDC approval...", end=" ")
        try:
            raw_tx = usdc.functions.approve(target, int(MAX_INT, 0)).build_transaction({
                "chainId": chain_id,
                "from": pub_key,
                "nonce": nonce,
                "gasPrice": web3.eth.gas_price,
            })
            signed_tx = web3.eth.account.sign_transaction(raw_tx, private_key=private_key)
            tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, 600)

            if receipt.status == 1:
                print(f"OK (tx: {tx_hash.hex()[:16]}...)")
            else:
                print(f"FAILED (tx: {tx_hash.hex()[:16]}...)")

            nonce += 1
        except Exception as e:
            print(f"ERROR: {e}")

        # 2. CTF approval (for selling positions)
        print("  - Setting CTF approval...", end=" ")
        try:
            raw_tx = ctf.functions.setApprovalForAll(target, True).build_transaction({
                "chainId": chain_id,
                "from": pub_key,
                "nonce": nonce,
                "gasPrice": web3.eth.gas_price,
            })
            signed_tx = web3.eth.account.sign_transaction(raw_tx, private_key=private_key)
            tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, 600)

            if receipt.status == 1:
                print(f"OK (tx: {tx_hash.hex()[:16]}...)")
            else:
                print(f"FAILED (tx: {tx_hash.hex()[:16]}...)")

            nonce += 1
        except Exception as e:
            print(f"ERROR: {e}")

    print()
    print("=" * 60)
    print("Allowance setup complete!")
    print("You should now be able to place BUY and SELL orders.")
    print("=" * 60)


if __name__ == "__main__":
    main()
