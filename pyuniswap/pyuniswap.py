import requests
from web3 import Web3
import os
import json
import time
from functools import wraps
from web3.types import (
    TxParams,
    Wei,
    Address,
    ChecksumAddress,
    ENS,
    Nonce,
    HexBytes,
)

class Token:
    ETH_ADDRESS = Web3.toChecksumAddress('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')
    MAX_AMOUNT = int('0x' + 'f' * 64, 16)

    def __init__(self, address='0xe9e7cea3dedca5984780bafc599bd69add087d56', provider=None):
        self.address = Web3.toChecksumAddress(address)
        self.provider = os.environ['PROVIDER'] if not provider else provider

        adapter = requests.adapters.HTTPAdapter(pool_connections=1000, pool_maxsize=1000)
        session = requests.Session()
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        self.web3 = Web3(Web3.HTTPProvider(self.provider, session=session))
        self.web3 = Web3(Web3.HTTPProvider(self.provider))
        self.wallet_address = None
        self.router = self.web3.eth.contract(
                address=Web3.toChecksumAddress('0x10ed43c718714eb63d5aa57b78b54704e256024e'),
            abi=json.load(open("pyuniswap/abi_files/" + "router.abi")))
        self.erc20_abi = json.load(
            open("pyuniswap/abi_files/" + "erc20.abi"))
        self.gas_limit = 1200000
        self.gas_price = 5000000000


    def set_gaslimit(self, gas_price, gas_limit):
        self.gas_limit = gas_limit
        self.gas_price = gas_price

    def connect_wallet(self, wallet_address='', private_key=''):
        self.wallet_address = Web3.toChecksumAddress(wallet_address)
        self.private_key = private_key
        
    def is_connected(self):
        return False if not self.wallet_address else True

    def require_connected(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.is_connected():
                raise RuntimeError('Please connect the wallet first!')
            return func(self, *args, **kwargs)

        return wrapper

    def create_transaction_params(self, value=0):
        return {
            "from": self.wallet_address,
            "value": value,
            'gasPrice': self.gas_price,
            "gas": self.gas_limit,
            "nonce": self.web3.eth.getTransactionCount(self.wallet_address)
        }

    def send_transaction(self, func, params):
        tx = func.buildTransaction(params)
        signed_tx = self.web3.eth.account.sign_transaction(tx, private_key=self.private_key)
        tx_hash = self.web3.eth.sendRawTransaction(signed_tx.rawTransaction)
        tx = tx_hash.hex()
        self.web3.eth.waitForTransactionReceipt(tx)
        return tx_hash

    @require_connected
    def is_approved(self, token_address=None, amount=MAX_AMOUNT):
        token_address = Web3.toChecksumAddress(token_address) if token_address else self.address
        erc20_contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
        approved_amount = erc20_contract.functions.allowance(self.wallet_address, self.router.address).call()
        return approved_amount >= amount

    @require_connected
    def approve(self, token_address, amount=MAX_AMOUNT, gas_price=None, timeout=900):
        if not gas_price:
            gas_price = self.web3.eth.gasPrice
        token_address = Web3.toChecksumAddress(token_address)
        erc20_contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
        func = erc20_contract.functions.approve(self.router.address, amount)
        params = self.create_transaction_params()
        tx = self.send_transaction(func, params)
        self.web3.eth.waitForTransactionReceipt(tx, timeout=timeout)

    def price(self, amount=int(1e18), address=''):
        address = Web3.toChecksumAddress(address)
        return self.router.functions.getAmountsOut(amount, [address, Web3.toChecksumAddress('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')]).call()[-1]

    def received_amount_by_swap(self, input_token_amount=int(1e18), input_token_address=ETH_ADDRESS):
        input_token_address = Web3.toChecksumAddress(input_token_address)
        return self.router.functions.getAmountsOut(input_token_amount, [input_token_address, self.address]).call()[-1]

    def balance(self, address=None):
        address = Web3.toChecksumAddress(address)
        erc20_contract = self.web3.eth.contract(address=address, abi=self.erc20_abi)
        return erc20_contract.functions.balanceOf(self.wallet_address).call()

    def buy_pp(self, token_address='', amount=0, slippage=0, timeout=900):

        self.address = Web3.toChecksumAddress(token_address)

        received_amount = self.received_amount_by_swap(amount)
        min_out = int(received_amount * (1 - slippage))
        func = self.router.functions.swapExactETHForTokens(min_out, [Web3.toChecksumAddress('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'), self.address],
                                                            self.wallet_address, int(time.time() + timeout))
        params = self.create_transaction_params(value=amount)
        return self.send_transaction(func, params)

    def sell(self, token_address, amount, timeout=900):
        self.address = Web3.toChecksumAddress(token_address)
        min_out = 0
        if not self.is_approved(self.address, amount):
            self.approve(self.address, gas_price=self.gas_price, timeout=timeout)
        func = self.router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(amount, min_out, [self.address, Web3.toChecksumAddress('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')],
                                                               self.wallet_address, int(time.time() + timeout))
        params = self.create_transaction_params()
        return self.send_transaction(func, params)