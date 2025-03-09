import logging
import os
import requests
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv, set_key
from web3 import Web3
from web3.middleware import geth_poa_middleware
from src.constants.abi import ERC20_ABI
from src.connections.base_connection import BaseConnection, Action, ActionParameter
from src.constants.networks import SONIC_NETWORKS

logger = logging.getLogger("connections.sonic_connection")


class SonicConnectionError(Exception):
    """Base exception for Sonic connection errors"""
    pass


class SonicConnection(BaseConnection):

    def __init__(self, config: Dict[str, Any]):
        logger.info("Initializing Sonic connection...")
        self._web3 = None

        # Get network configuration
        network = config.get("network", "mainnet")
        if network not in SONIC_NETWORKS:
            raise ValueError(f"Invalid network '{network}'. Must be one of: {', '.join(SONIC_NETWORKS.keys())}")

        network_config = SONIC_NETWORKS[network]
        self.explorer = network_config["scanner_url"]
        self.rpc_url = network_config["rpc_url"]

        super().__init__(config)
        self._initialize_web3()
        self.ERC20_ABI = ERC20_ABI
        self.NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        self.aggregator_api = "https://aggregator-api.kyberswap.com/sonic/api/v1"
        self.dex_api = "https://api.dexscreener.com/latest/dex/search?q="
        self.security_api = "https://api.auditone.io/securityStats"


    def _get_explorer_link(self, tx_hash: str) -> str:
        """Generate block explorer link for transaction"""
        return f"{self.explorer}/tx/{tx_hash}"

    def _initialize_web3(self):
        """Initialize Web3 connection"""
        if not self._web3:
            self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)
            if not self._web3.is_connected():
                raise SonicConnectionError("Failed to connect to Sonic network")

            try:
                chain_id = self._web3.eth.chain_id
                logger.info(f"Connected to network with chain ID: {chain_id}")
            except Exception as e:
                logger.warning(f"Could not get chain ID: {e}")

    @property
    def is_llm_provider(self) -> bool:
        return False

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Sonic configuration from JSON"""
        required = ["network"]
        missing = [field for field in required if field not in config]
        if missing:
            raise ValueError(f"Missing config fields: {', '.join(missing)}")

        if config["network"] not in SONIC_NETWORKS:
            raise ValueError(
                f"Invalid network '{config['network']}'. Must be one of: {', '.join(SONIC_NETWORKS.keys())}")

        return config

    def get_token_by_ticker(self, ticker: str) -> Optional[str]:
        """Get token address by ticker symbol"""
        try:
            if ticker.lower() in ["s", "S"]:
                return "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

            response = requests.get(
                f"https://api.dexscreener.com/latest/dex/search?q={ticker}"
            )
            response.raise_for_status()

            data = response.json()
            if not data.get('pairs'):
                return None

            sonic_pairs = [
                pair for pair in data["pairs"] if pair.get("chainId") == "sonic"
            ]
            sonic_pairs.sort(key=lambda x: x.get("fdv", 0), reverse=True)

            sonic_pairs = [
                pair
                for pair in sonic_pairs
                if pair.get("baseToken", {}).get("symbol", "").lower() == ticker.lower()
            ]

            if sonic_pairs:
                return sonic_pairs[0].get("baseToken", {}).get("address")
            return None

        except Exception as error:
            logger.error(f"Error fetching token address: {str(error)}")
            return None

    def register_actions(self) -> None:
        self.actions = {
            "get-token-by-ticker": Action(
                name="get-token-by-ticker",
                parameters=[
                    ActionParameter("ticker", True, str, "Token ticker symbol to look up")
                ],
                description="Get token address by ticker symbol"
            ),
            "get-balance": Action(
                name="get-balance",
                parameters=[
                    ActionParameter("address", False, str, "Address to check balance for"),
                    ActionParameter("token_address", False, str, "Optional token address")
                ],
                description="Get $S or token balance"
            ),
            "transfer": Action(
                name="transfer",
                parameters=[
                    ActionParameter("to_address", True, str, "Recipient address"),
                    ActionParameter("amount", True, float, "Amount to transfer"),
                    ActionParameter("token_address", False, str, "Optional token address")
                ],
                description="Send $S or tokens"
            ),
            "swap": Action(
                name="swap",
                parameters=[
                    ActionParameter("token_in", True, str, "Input token address"),
                    ActionParameter("token_out", True, str, "Output token address"),
                    ActionParameter("amount", True, float, "Amount to swap"),
                    ActionParameter("slippage", False, float, "Max slippage percentage")
                ],
                description="Swap tokens"
            ),
            "get-token-stats": Action(
                name="get-token-stats",
                parameters=[
                    ActionParameter("token_symbol", True, str, "Token ticker symbol to look up")
                ],
                description="Get token address by ticker symbol"
            ),
            "get-security-stats": Action(
                name="get-security-stats",
                parameters=[
                    ActionParameter("project_name", True, str, "Protocol name")
                ],
                description="Get security stats by protocol name")
        }

    def configure(self) -> bool:
        logger.info("\n🔷 SONIC CHAIN SETUP")
        if self.is_configured():
            logger.info("Sonic connection is already configured")
            response = input("Do you want to reconfigure? (y/n): ")
            if response.lower() != 'y':
                return True

        try:
            if not os.path.exists('.env'):
                with open('.env', 'w') as f:
                    f.write('')

            private_key = input("\nEnter your wallet private key: ")
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            set_key('.env', 'SONIC_PRIVATE_KEY', private_key)

            if not self._web3.is_connected():
                raise SonicConnectionError("Failed to connect to Sonic network")

            account = self._web3.eth.account.from_key(private_key)
            logger.info(f"\n✅ Successfully connected with address: {account.address}")
            return True

        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False

    def is_configured(self, verbose: bool = False) -> bool:
        try:
            load_dotenv()
            if not os.getenv('SONIC_PRIVATE_KEY'):
                if verbose:
                    logger.error("Missing SONIC_PRIVATE_KEY in .env")
                return False

            if not self._web3.is_connected():
                if verbose:
                    logger.error("Not connected to Sonic network")
                return False
            return True

        except Exception as e:
            if verbose:
                logger.error(f"Configuration check failed: {e}")
            return False

    def get_balance(self, address: Optional[str] = None, token_address: Optional[str] = None) -> float:
        """Get balance for an address or the configured wallet"""
        try:
            if not address:
                private_key = os.getenv('SONIC_PRIVATE_KEY')
                if not private_key:
                    raise SonicConnectionError("No wallet configured")
                account = self._web3.eth.account.from_key(private_key)
                address = account.address

            if token_address:
                contract = self._web3.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=self.ERC20_ABI
                )
                balance = contract.functions.balanceOf(address).call()
                decimals = contract.functions.decimals().call()
                return balance / (10 ** decimals)
            else:
                balance = self._web3.eth.get_balance(address)
                return self._web3.from_wei(balance, 'ether')

        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            raise

    def transfer(self, to_address: str, amount: float, token_address: Optional[str] = None) -> str:
        """Transfer $S or tokens to an address"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)
            chain_id = self._web3.eth.chain_id

            if token_address:
                contract = self._web3.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=self.ERC20_ABI
                )
                decimals = contract.functions.decimals().call()
                amount_raw = int(amount * (10 ** decimals))

                tx = contract.functions.transfer(
                    Web3.to_checksum_address(to_address),
                    amount_raw
                ).build_transaction({
                    'from': account.address,
                    'nonce': self._web3.eth.get_transaction_count(account.address),
                    'gasPrice': self._web3.eth.gas_price,
                    'chainId': chain_id
                })
            else:
                tx = {
                    'nonce': self._web3.eth.get_transaction_count(account.address),
                    'to': Web3.to_checksum_address(to_address),
                    'value': self._web3.to_wei(amount, 'ether'),
                    'gas': 21000,
                    'gasPrice': self._web3.eth.gas_price,
                    'chainId': chain_id
                }

            signed = account.sign_transaction(tx)
            tx_hash = self._web3.eth.send_raw_transaction(signed.rawTransaction)

            # Log and return explorer link immediately
            tx_link = self._get_explorer_link(tx_hash.hex())
            return f"⛓️ Transfer transaction sent: {tx_link}"

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            raise

    def _get_swap_route(self, token_in: str, token_out: str, amount_in: float) -> Dict:
        """Get the best swap route from Kyberswap API"""
        try:
            # Handle native token address

            # Convert amount to raw value
            if token_in.lower() == self.NATIVE_TOKEN.lower():
                amount_raw = self._web3.to_wei(amount_in, 'ether')
            else:
                token_contract = self._web3.eth.contract(
                    address=Web3.to_checksum_address(token_in),
                    abi=self.ERC20_ABI
                )
                decimals = token_contract.functions.decimals().call()
                amount_raw = int(amount_in * (10 ** decimals))

            # Set up API request
            url = f"{self.aggregator_api}/routes"
            headers = {"x-client-id": "ZerePyBot"}
            params = {
                "tokenIn": token_in,
                "tokenOut": token_out,
                "amountIn": str(amount_raw),
                "gasInclude": "true"
            }

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            if data.get("code") != 0:
                raise SonicConnectionError(f"API error: {data.get('message')}")

            return data["data"]

        except Exception as e:
            logger.error(f"Failed to get swap route: {e}")
            raise

    def _get_encoded_swap_data(self, route_summary: Dict, slippage: float = 0.5) -> str:
        """Get encoded swap data from Kyberswap API"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)

            url = f"{self.aggregator_api}/route/build"
            headers = {"x-client-id": "zerepy"}

            payload = {
                "routeSummary": route_summary,
                "sender": account.address,
                "recipient": account.address,
                "slippageTolerance": int(slippage * 100),  # Convert to bps
                "deadline": int(time.time() + 1200),  # 20 minutes
                "source": "ZerePyBot"
            }

            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()
            if data.get("code") != 0:
                raise SonicConnectionError(f"API error: {data.get('message')}")

            return data["data"]["data"]

        except Exception as e:
            logger.error(f"Failed to encode swap data: {e}")
            raise

    def _handle_token_approval(self, token_address: str, spender_address: str, amount: int) -> None:
        """Handle token approval for spender"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)

            token_contract = self._web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )

            # Check current allowance
            current_allowance = token_contract.functions.allowance(
                account.address,
                spender_address
            ).call()

            if current_allowance < amount:
                approve_tx = token_contract.functions.approve(
                    spender_address,
                    amount
                ).build_transaction({
                    'from': account.address,
                    'nonce': self._web3.eth.get_transaction_count(account.address),
                    'gasPrice': self._web3.eth.gas_price,
                    'chainId': self._web3.eth.chain_id
                })

                signed_approve = account.sign_transaction(approve_tx)
                tx_hash = self._web3.eth.send_raw_transaction(signed_approve.rawTransaction)
                logger.info(f"Approval transaction sent: {self._get_explorer_link(tx_hash.hex())}")

                # Wait for approval to be mined
                self._web3.eth.wait_for_transaction_receipt(tx_hash)

        except Exception as e:
            logger.error(f"Approval failed: {e}")
            raise

    def swap(self, private_key:str, token_in: str, token_out: str, amount: float, slippage: float = 0.5) -> str:
        """Execute a token swap using the KyberSwap router"""
        try:
            #private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)

            # Check token balance before proceeding
            current_balance = self.get_balance(
                address=account.address,
                token_address=None if token_in.lower() == self.NATIVE_TOKEN.lower() else token_in
            )

            if current_balance < amount:
                raise ValueError(f"Insufficient balance. Required: {amount}, Available: {current_balance}")

            # Get optimal swap route
            route_data = self._get_swap_route(token_in, token_out, amount)

            # Get encoded swap data
            encoded_data = self._get_encoded_swap_data(route_data["routeSummary"], slippage)

            # Get router address from route data
            router_address = route_data["routerAddress"]

            # Handle token approval if not using native token
            if token_in.lower() != self.NATIVE_TOKEN.lower():
                if token_in.lower() == "0x039e2fb66102314ce7b64ce5ce3e5183bc94ad38".lower():  # $S token
                    amount_raw = self._web3.to_wei(amount, 'ether')
                else:
                    token_contract = self._web3.eth.contract(
                        address=Web3.to_checksum_address(token_in),
                        abi=self.ERC20_ABI
                    )
                    decimals = token_contract.functions.decimals().call()
                    amount_raw = int(amount * (10 ** decimals))
                self._handle_token_approval(token_in, router_address, amount_raw)

            # Prepare transaction
            tx = {
                'from': account.address,
                'to': Web3.to_checksum_address(router_address),
                'data': encoded_data,
                'nonce': self._web3.eth.get_transaction_count(account.address),
                'gasPrice': self._web3.eth.gas_price,
                'chainId': self._web3.eth.chain_id,
                'value': self._web3.to_wei(amount, 'ether') if token_in.lower() == self.NATIVE_TOKEN.lower() else 0
            }

            # Estimate gas
            try:
                tx['gas'] = self._web3.eth.estimate_gas(tx)
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}, using default gas limit")
                tx['gas'] = 500000  # Default gas limit

            # Sign and send transaction
            signed_tx = account.sign_transaction(tx)
            tx_hash = self._web3.eth.send_raw_transaction(signed_tx.rawTransaction)

            # Log and return explorer link immediately
            tx_link = self._get_explorer_link(tx_hash.hex())
            return f"🔄 Swap transaction sent: {tx_link}"

        except Exception as e:
            logger.error(f"Swap failed: {e}")
            raise

    def get_token_stats(self, token_symbol: str) -> Dict[str, Any]:
        """
        Fetches consolidated stats for a given token symbol on Sonic.

        Parameters:
        - token_symbol (str): The symbol of the token (e.g., "Anon")

        Returns:
        - Total Liquidity (USD)
        - Total Market Cap (one common value)
        - Total Volume (24h)
        - Total Buys (24h)
        - Total Sells (24h)
        - Total Trading Pairs
        - Average Price in USD (priceUsd)
        """
        try:
            response = requests.get(f"{self.dex_api}{token_symbol}")
            response.raise_for_status()
            data = response.json().get("pairs", [])

            if not data:
                return {"status": "error", "message": f"No trading pairs found for {token_symbol}"}

            # Aggregated stats
            total_liquidity_usd = 0
            total_volume_24h = 0
            total_buys = 0
            total_sells = 0
            total_pairs = 0
            total_market_cap = 0  # Single value, set once
            weighted_price_sum = 0
            total_liquidity_weight = 0  # Used for weighted average price

            for pair in data:
                try:
                    base_token = pair.get("baseToken", {}).get("symbol", "").lower()
                    if base_token != token_symbol.lower():
                        continue  # Skip non-matching tokens

                    liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0))
                    volume_24h = float(pair.get("volume", {}).get("h24", 0))
                    buys_24h = pair.get("txns", {}).get("h24", {}).get("buys", 0)
                    sells_24h = pair.get("txns", {}).get("h24", {}).get("sells", 0)
                    market_cap = float(pair.get("marketCap", 0))
                    price_usd = float(pair.get("priceUsd", 0))  # Fetch price per pair

                    total_liquidity_usd += liquidity_usd
                    total_volume_24h += volume_24h
                    total_buys += buys_24h
                    total_sells += sells_24h
                    total_pairs += 1

                    # Set market cap only once (assuming it's consistent across pairs)
                    if total_market_cap == 0:
                        total_market_cap = market_cap

                    # Compute weighted average price in USD
                    if price_usd > 0 and liquidity_usd > 0:
                        weighted_price_sum += price_usd * liquidity_usd
                        total_liquidity_weight += liquidity_usd

                except Exception as e:
                    logger.warning(f"Skipping malformed pair data: {e}")

            if total_pairs == 0:
                return {"status": "error", "message": f"No active pairs found for {token_symbol}"}

            # Calculate the weighted average price
            average_price_usd = round(weighted_price_sum / total_liquidity_weight,
                                      4) if total_liquidity_weight > 0 else 0

            return {
                "status":"success",
                "token": token_symbol.upper(),
                "totalPairs": total_pairs,
                "totalLiquidityUsd": round(total_liquidity_usd, 2),
                "totalMarketCap": round(total_market_cap, 2),
                "totalVolume24h": round(total_volume_24h, 2),
                "totalBuys": total_buys,
                "totalSells": total_sells,
                "priceUsd": average_price_usd  # Weighted average price
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching token stats: {e}")
            return {"status": "error", "message": str(e)}

    def get_security_stats(self, project_name: str) -> Dict[str, Any]:
        """
        Fetches security stats for a given project from AuditOne API.

        Parameters:
        - project_name (str): The name of the project (e.g., "Solv Protocol")

        Returns:
        - Security Stats (Audit Reports, Score, Incidents, etc.)
        """
        try:
            payload = {"project_name": project_name}
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            response = requests.post(self.security_api, json=payload, headers=headers)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching security stats for {project_name}: {e}")
            return {"status": "error", "message": f"Failed to fetch security stats for {project_name}"}

    def perform_action(self, action_name: str, kwargs) -> Any:
        """Execute a Sonic action with validation"""
        if action_name not in self.actions:
            raise KeyError(f"Unknown action: {action_name}")

        load_dotenv()

        if not self.is_configured(verbose=True):
            raise SonicConnectionError("Sonic is not properly configured")

        action = self.actions[action_name]
        errors = action.validate_params(kwargs)
        if errors:
            raise ValueError(f"Invalid parameters: {', '.join(errors)}")

        method_name = action_name.replace('-', '_')
        method = getattr(self, method_name)
        return method(**kwargs)