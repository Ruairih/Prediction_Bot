"""
Universe Fetcher - Fetches all markets from Polymarket API.

Populates Tier 1 (market_universe table) with metadata and price snapshots.

Rate limit aware:
- Polymarket API: ~100 requests/minute
- Fetches 100 markets per request
- 10,000 markets = 100 requests = ~1 minute
- Runs every 5 minutes with backoff
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from polymarket_bot.storage.models import MarketUniverse, OutcomeToken, PriceSnapshot

logger = logging.getLogger(__name__)

# Polymarket API endpoints
POLYMARKET_API_BASE = "https://clob.polymarket.com"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"


class UniverseFetcher:
    """
    Fetches all markets from Polymarket and updates market_universe.

    Uses the Gamma API for market metadata and CLOB API for prices.
    """

    def __init__(
        self,
        universe_repo,
        page_size: int = 100,
        max_pages: int = 200,
        rate_limit_delay: float = 0.6,  # ~100 req/min
    ):
        self.universe_repo = universe_repo
        self.page_size = page_size
        self.max_pages = max_pages
        self.rate_limit_delay = rate_limit_delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_all_markets(self) -> list[MarketUniverse]:
        """
        Fetch all markets from Polymarket.

        Returns list of MarketUniverse objects.
        """
        session = await self._get_session()
        all_markets = []
        offset = 0

        for page in range(self.max_pages):
            try:
                # Fetch page of markets from Gamma API
                url = f"{GAMMA_API_BASE}/markets"
                params = {
                    "limit": self.page_size,
                    "offset": offset,
                    "closed": "false",  # Exclude resolved markets initially
                }

                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"API returned {resp.status} for page {page}")
                        break

                    data = await resp.json()

                if not data:
                    logger.info(f"No more markets at offset {offset}")
                    break

                # Parse markets
                for item in data:
                    market = self._parse_market(item)
                    if market:
                        all_markets.append(market)

                logger.debug(f"Fetched page {page + 1}, got {len(data)} markets")
                offset += self.page_size

                # Rate limiting
                await asyncio.sleep(self.rate_limit_delay)

            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching page {page}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        logger.info(f"Fetched {len(all_markets)} markets total")
        return all_markets

    def _parse_market(self, data: dict) -> Optional[MarketUniverse]:
        """Parse API response into MarketUniverse model."""
        try:
            condition_id = data.get("conditionId") or data.get("condition_id")
            if not condition_id:
                return None

            # Parse outcomes/tokens
            outcomes = []
            tokens = data.get("tokens", []) or data.get("clobTokenIds", [])

            if isinstance(tokens, list):
                for i, token in enumerate(tokens):
                    if isinstance(token, dict):
                        outcomes.append(OutcomeToken(
                            token_id=token.get("token_id", ""),
                            outcome=token.get("outcome", f"Outcome {i}"),
                            outcome_index=i,
                        ))
                    elif isinstance(token, str):
                        # Just token IDs
                        outcome_name = "Yes" if i == 0 else "No" if i == 1 else f"Outcome {i}"
                        outcomes.append(OutcomeToken(
                            token_id=token,
                            outcome=outcome_name,
                            outcome_index=i,
                        ))

            # Parse end date
            end_date = None
            end_str = data.get("endDate") or data.get("end_date_iso")
            if end_str:
                try:
                    end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Parse created date
            created_at = None
            created_str = data.get("createdAt") or data.get("created_at")
            if created_str:
                try:
                    created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Parse prices (primary outcome = YES = index 0)
            price = None
            outcomePrices = data.get("outcomePrices", [])
            if outcomePrices and len(outcomePrices) > 0:
                try:
                    price = float(outcomePrices[0])
                except (ValueError, TypeError):
                    pass

            # Get spread from best bid/ask
            best_bid = None
            best_ask = None
            spread = None

            if "bestBid" in data:
                try:
                    best_bid = float(data["bestBid"])
                except (ValueError, TypeError):
                    pass
            if "bestAsk" in data:
                try:
                    best_ask = float(data["bestAsk"])
                except (ValueError, TypeError):
                    pass
            if best_bid is not None and best_ask is not None:
                spread = best_ask - best_bid

            # Parse volume
            volume_24h = 0.0
            volume_total = 0.0
            liquidity = 0.0

            if "volume" in data:
                try:
                    volume_total = float(data["volume"])
                except (ValueError, TypeError):
                    pass
            if "volume24hr" in data:
                try:
                    volume_24h = float(data["volume24hr"])
                except (ValueError, TypeError):
                    pass
            if "liquidity" in data:
                try:
                    liquidity = float(data["liquidity"])
                except (ValueError, TypeError):
                    pass

            return MarketUniverse(
                condition_id=condition_id,
                market_id=data.get("id") or data.get("marketSlug"),
                question=data.get("question", "Unknown"),
                description=data.get("description"),
                category=data.get("category") or data.get("groupItemTitle"),
                end_date=end_date,
                created_at=created_at,
                outcomes=outcomes,
                outcome_count=len(outcomes) if outcomes else 2,
                price=price,
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
                volume_24h=volume_24h,
                volume_total=volume_total,
                liquidity=liquidity,
                is_resolved=data.get("closed", False) or data.get("resolved", False),
            )

        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None

    async def update_universe(self) -> int:
        """
        Fetch all markets and update the universe table.

        Returns count of markets updated.
        """
        markets = await self.fetch_all_markets()
        if not markets:
            logger.warning("No markets fetched")
            return 0

        # Save to database
        count = await self.universe_repo.upsert_batch(markets)
        logger.info(f"Updated {count} markets in universe")

        # Save price snapshots for change calculation
        now = datetime.utcnow()
        for m in markets:
            if m.price is not None:
                snapshot = PriceSnapshot(
                    condition_id=m.condition_id,
                    snapshot_at=now,
                    price=m.price,
                    volume_24h=m.volume_24h,
                )
                await self.universe_repo.save_price_snapshot(snapshot)

        # Sync resolutions from existing polymarket_resolutions table
        await self._sync_resolutions()

        return count

    async def _sync_resolutions(self) -> int:
        """
        Sync resolution data from polymarket_resolutions to market_universe.

        This ensures we have resolution outcomes for P&L calculation.
        """
        try:
            result = await self.universe_repo.db.execute("""
                UPDATE market_universe u
                SET
                    is_resolved = TRUE,
                    resolution_outcome = r.winning_outcome,
                    winning_outcome_index = r.winning_outcome_index,
                    resolved_at = r.resolved_at::timestamp
                FROM polymarket_resolutions r
                WHERE u.condition_id = r.condition_id
                  AND (u.is_resolved = FALSE OR u.resolution_outcome IS NULL)
            """)
            # Parse "UPDATE N"
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info(f"Synced {count} resolutions to market_universe")
            return count
        except Exception as e:
            logger.error(f"Error syncing resolutions: {e}")
            return 0

    async def fetch_resolved_markets(self) -> list[MarketUniverse]:
        """Fetch recently resolved markets to update resolution status."""
        session = await self._get_session()
        resolved = []

        try:
            url = f"{GAMMA_API_BASE}/markets"
            params = {
                "limit": 100,
                "closed": "true",
            }

            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        market = self._parse_market(item)
                        if market:
                            market.is_resolved = True
                            resolved.append(market)

        except Exception as e:
            logger.error(f"Error fetching resolved markets: {e}")

        return resolved


class UniverseUpdater:
    """
    Background task that periodically updates the market universe.

    Coordinates:
    - Universe fetching (every 5 min)
    - Score computation (every 15 min)
    - Tier promotion cycles (every 15 min)
    - Price change calculation (every 5 min)
    """

    def __init__(
        self,
        fetcher: UniverseFetcher,
        tier_manager,
        universe_repo,
        fetch_interval: int = 300,  # 5 minutes
        tier_interval: int = 900,  # 15 minutes
    ):
        self.fetcher = fetcher
        self.tier_manager = tier_manager
        self.universe_repo = universe_repo
        self.fetch_interval = fetch_interval
        self.tier_interval = tier_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background update loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Universe updater started")

    async def stop(self):
        """Stop the background update loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.fetcher.close()
        logger.info("Universe updater stopped")

    async def _run_loop(self):
        """Main update loop."""
        last_fetch = 0
        last_tier_cycle = 0

        while self._running:
            try:
                now = asyncio.get_event_loop().time()

                # Fetch universe every fetch_interval
                if now - last_fetch >= self.fetch_interval:
                    logger.info("Fetching market universe...")
                    count = await self.fetcher.update_universe()
                    logger.info(f"Universe updated: {count} markets")
                    last_fetch = now

                    # Compute price changes
                    await self._update_price_changes()

                # Run tier cycle every tier_interval
                if now - last_tier_cycle >= self.tier_interval:
                    logger.info("Running tier promotion cycle...")

                    # Update scores first
                    markets = await self.universe_repo.get_top_by_score(5000)
                    await self.tier_manager.update_scores_for_markets(markets)

                    # Run promotion/demotion
                    stats = await self.tier_manager.run_promotion_cycle()
                    logger.info(f"Tier cycle stats: {stats}")
                    last_tier_cycle = now

                # Sleep briefly
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in universe update loop: {e}")
                await asyncio.sleep(60)

    async def _update_price_changes(self):
        """Update price change fields for all markets."""
        try:
            # Get all non-resolved markets
            from polymarket_bot.storage.repositories.universe_repo import MarketQuery

            markets = await self.universe_repo.query(
                MarketQuery(include_resolved=False, limit=10000)
            )

            condition_ids = [m.condition_id for m in markets]
            changes = await self.universe_repo.compute_price_changes(condition_ids)

            # Update markets with changes
            for condition_id, (change_1h, change_24h) in changes.items():
                await self.universe_repo.db.execute(
                    """
                    UPDATE market_universe
                    SET price_change_1h = $2, price_change_24h = $3
                    WHERE condition_id = $1
                    """,
                    condition_id,
                    change_1h,
                    change_24h,
                )

            logger.debug(f"Updated price changes for {len(changes)} markets")

        except Exception as e:
            logger.error(f"Error updating price changes: {e}")
