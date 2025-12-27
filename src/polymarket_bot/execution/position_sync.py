"""
Position Sync Service - Syncs positions from Polymarket to local database.

Handles importing existing Polymarket positions that were created outside
the bot (manual trades, other tools, etc.) so the bot can manage them.

Key Design Decisions (per Codex review):
1. Uses `hold_start_at` for exit logic, not `entry_timestamp`
2. Imported positions default to Option A (hold_start_at = now, 7-day hold starts fresh)
3. Updates both database AND in-memory PositionTracker cache
4. Idempotent - safe to run multiple times
5. Logs all sync activity for audit trail

Hold Policies:
- "new": Set hold_start_at to now (7-day hold starts fresh) - DEFAULT
- "mature": Set hold_start_at to N days ago (exit logic applies immediately)
- "actual": Fetch trade history and use actual first BUY timestamp
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx

if TYPE_CHECKING:
    from polymarket_bot.storage import Database
    from .position_tracker import PositionTracker

logger = logging.getLogger(__name__)

# Polymarket data API
POLYMARKET_DATA_API = "https://data-api.polymarket.com"


@dataclass
class RemotePosition:
    """Position data from Polymarket API."""
    token_id: str  # 'asset' field from API
    condition_id: str
    size: Decimal
    avg_price: Decimal
    current_price: Decimal
    outcome: str
    outcome_index: int
    title: str
    end_date: Optional[str] = None
    unrealized_pnl: Optional[Decimal] = None


@dataclass
class SyncResult:
    """Result of a position sync operation."""
    run_id: str
    positions_found: int
    positions_imported: int
    positions_updated: int
    positions_closed: int
    errors: List[str]
    started_at: datetime
    completed_at: datetime

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class PositionSyncService:
    """
    Syncs positions from Polymarket to local database.

    Usage:
        sync_service = PositionSyncService(db, position_tracker)

        # Dry run first
        result = await sync_service.sync_positions(
            wallet_address="0x...",
            dry_run=True
        )
        print(f"Would import {result.positions_imported} positions")

        # Actual sync
        result = await sync_service.sync_positions(
            wallet_address="0x...",
            dry_run=False,
            hold_policy="new"  # Start 7-day hold from now
        )
    """

    def __init__(
        self,
        db: "Database",
        position_tracker: Optional["PositionTracker"] = None,
    ) -> None:
        self._db = db
        self._position_tracker = position_tracker

    async def fetch_remote_positions(
        self, wallet_address: str
    ) -> tuple[List[RemotePosition], bool]:
        """
        Fetch positions from Polymarket data API.

        Args:
            wallet_address: Wallet address to query

        Returns:
            Tuple of (positions, partial_response)
        """
        url = f"{POLYMARKET_DATA_API}/positions?user={wallet_address}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        positions: List[RemotePosition] = []
        invalid_entries = 0
        partial_response = False

        # Check for pagination indicators (Codex review: guard against truncated results)
        # If the API returns a paginated response, we should not close positions
        # that appear missing (they might be on the next page)
        if isinstance(data, dict):
            # Paginated response format: {"positions": [...], "next_cursor": "...", "has_more": true}
            if "next_cursor" in data or "has_more" in data or "cursor" in data:
                logger.warning(
                    "API response contains pagination indicators. "
                    "Results may be truncated. Treating as partial."
                )
                partial_response = True
            # Extract positions list from dict if present
            if "positions" in data:
                data = data["positions"]
            elif "data" in data:
                data = data["data"]
            else:
                logger.warning(f"Unexpected paginated response structure: {list(data.keys())}")
                return positions, True

        # Validate response is a list (Codex review: guard against unexpected payloads)
        if not isinstance(data, list):
            logger.warning(f"Unexpected API response type: {type(data)}")
            return positions, True

        for p in data:
            if not isinstance(p, dict):
                invalid_entries += 1
                continue

            # Safely extract size with null handling (Codex review)
            size_raw = p.get("size")
            token_id = p.get("asset", "")
            condition_id = p.get("conditionId", "")
            if size_raw is None or not token_id or not condition_id:
                invalid_entries += 1
                continue
            try:
                size = Decimal(str(size_raw))
            except Exception:
                invalid_entries += 1
                continue

            if size <= 0:
                continue  # Skip zero-size positions

            # Safely extract other fields with null coercion (Codex review)
            def safe_decimal(val, default=0):
                if val is None:
                    return Decimal(str(default))
                try:
                    return Decimal(str(val))
                except Exception:
                    return Decimal(str(default))

            positions.append(RemotePosition(
                token_id=token_id,
                condition_id=condition_id,
                size=size,
                avg_price=safe_decimal(p.get("avgPrice"), 0),
                current_price=safe_decimal(p.get("curPrice"), 0),
                outcome=p.get("outcome", ""),
                outcome_index=p.get("outcomeIndex", 0),
                title=p.get("title", ""),
                end_date=p.get("endDate"),
                unrealized_pnl=safe_decimal(p.get("cashPnl"), 0),
            ))

        if invalid_entries > 0:
            logger.warning(
                f"Skipped {invalid_entries} invalid position entries from API; "
                f"treating response as partial."
            )
            partial_response = True

        return positions, partial_response

    async def fetch_trade_timestamps(
        self, wallet_address: str
    ) -> Dict[str, datetime]:
        """
        Fetch user's trade history to get actual purchase timestamps.

        The positions API doesn't include when positions were opened,
        but the trades API has timestamps for each trade.

        Args:
            wallet_address: Wallet address to query

        Returns:
            Dict of token_id -> earliest BUY timestamp for that token
        """
        url = f"{POLYMARKET_DATA_API}/trades?user={wallet_address}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch trade history: {e}")
            return {}

        if not isinstance(data, list):
            logger.warning(f"Unexpected trades API response type: {type(data)}")
            return {}

        # Build mapping: token_id -> earliest BUY timestamp
        token_first_buy: Dict[str, datetime] = {}

        for trade in data:
            if not isinstance(trade, dict):
                continue

            # Only care about BUY trades (opening positions)
            side = trade.get("side", "").upper()
            if side != "BUY":
                continue

            token_id = trade.get("asset", "")
            timestamp_raw = trade.get("timestamp")

            if not token_id or timestamp_raw is None:
                continue

            try:
                # API returns Unix timestamp (int64)
                if isinstance(timestamp_raw, (int, float)):
                    trade_time = datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)
                elif isinstance(timestamp_raw, str):
                    # Handle ISO format if ever returned
                    trade_time = datetime.fromisoformat(
                        timestamp_raw.replace("Z", "+00:00")
                    )
                else:
                    continue

                # Keep the earliest BUY for each token
                if token_id not in token_first_buy:
                    token_first_buy[token_id] = trade_time
                elif trade_time < token_first_buy[token_id]:
                    token_first_buy[token_id] = trade_time

            except Exception as e:
                logger.debug(f"Failed to parse trade timestamp: {e}")
                continue

        logger.info(f"Found trade timestamps for {len(token_first_buy)} tokens")
        return token_first_buy

    async def get_local_positions(
        self,
        import_sources: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all open positions from local database.

        Args:
            import_sources: Optional list of import_source values to include.
                If None, include all open positions.

        Returns:
            Dict of token_id -> position data
        """
        query = """
            SELECT token_id, condition_id, size, entry_price, entry_cost,
                   status, import_source, hold_start_at, entry_timestamp
            FROM positions
            WHERE status = 'open'
        """
        params: List[Any] = []
        if import_sources is not None:
            query += " AND import_source = ANY($1)"
            params.append(import_sources)

        rows = await self._db.fetch(query, *params)

        return {
            row["token_id"]: dict(row)
            for row in rows
        }

    async def sync_positions(
        self,
        wallet_address: str,
        dry_run: bool = True,
        hold_policy: str = "new",
        mature_days: int = 8,
    ) -> SyncResult:
        """
        Sync remote positions to local database.

        Args:
            wallet_address: Polymarket wallet address
            dry_run: If True, only report what would change
            hold_policy: How to set hold_start_at for imports:
                - "new": Set to now (7-day hold starts fresh) - DEFAULT
                - "mature": Set to N days ago (exit logic applies immediately)
                - "actual": Use actual trade timestamps from trade history
            mature_days: Days to backdate if hold_policy="mature"

        Returns:
            SyncResult with counts and any errors
        """
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(timezone.utc)
        errors: List[str] = []

        logger.info(f"[{run_id}] Starting position sync for {wallet_address}")
        logger.info(f"[{run_id}] Mode: {'DRY RUN' if dry_run else 'LIVE'}, Policy: {hold_policy}")

        # Fetch trade timestamps if using "actual" policy
        trade_timestamps: Dict[str, datetime] = {}
        if hold_policy == "actual":
            trade_timestamps = await self.fetch_trade_timestamps(wallet_address)
            logger.info(f"[{run_id}] Fetched {len(trade_timestamps)} trade timestamps")

        # Fetch remote and local positions
        try:
            remote_positions, partial_response = await self.fetch_remote_positions(
                wallet_address
            )
        except Exception as e:
            errors.append(f"Failed to fetch remote positions: {e}")
            return SyncResult(
                run_id=run_id,
                positions_found=0,
                positions_imported=0,
                positions_updated=0,
                positions_closed=0,
                errors=errors,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        # Reconcile all open positions regardless of import_source.
        local_positions = await self.get_local_positions(import_sources=None)

        logger.info(f"[{run_id}] Found {len(remote_positions)} remote, {len(local_positions)} local")
        if partial_response:
            logger.warning(
                f"[{run_id}] Remote positions response was partial or invalid. "
                f"Close detection will be skipped for safety."
            )

        imported = 0
        updated = 0
        closed = 0

        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Process remote positions
        remote_token_ids = set()
        for remote in remote_positions:
            remote_token_ids.add(remote.token_id)
            local = local_positions.get(remote.token_id)

            if local is None:
                # Calculate hold_start and age_source based on policy
                # age_source determines if exit logic trusts the timestamp:
                # - "actual": Timestamp from trade history, trusted
                # - "unknown": Timestamp set to NOW, NOT trusted (eligible for exit)
                if hold_policy == "actual":
                    actual_timestamp = trade_timestamps.get(remote.token_id)
                    if actual_timestamp:
                        hold_start = actual_timestamp
                        age_source = "actual"  # Trusted timestamp
                        hold_age_days = (now - hold_start).days
                        logger.info(
                            f"[{run_id}] IMPORT: {remote.title[:50]}... "
                            f"({remote.size} {remote.outcome} @ ${remote.avg_price:.4f}) "
                            f"[ACTUAL: {hold_age_days}d old, age_source=actual]"
                        )
                    else:
                        # Fallback to "new" if no trade history found
                        hold_start = now
                        age_source = "unknown"  # NOT trusted - eligible for exit
                        logger.warning(
                            f"[{run_id}] IMPORT: {remote.title[:50]}... "
                            f"({remote.size} {remote.outcome} @ ${remote.avg_price:.4f}) "
                            f"[NO TRADE HISTORY - age_source=unknown, ELIGIBLE FOR EXIT]"
                        )
                elif hold_policy == "mature":
                    hold_start = now - timedelta(days=mature_days)
                    age_source = "unknown"  # Backdated but not verified
                    logger.info(
                        f"[{run_id}] IMPORT: {remote.title[:50]}... "
                        f"({remote.size} {remote.outcome} @ ${remote.avg_price:.4f}) "
                        f"[MATURE: {mature_days}d backdated, age_source=unknown]"
                    )
                else:  # "new" policy (default)
                    hold_start = now
                    age_source = "unknown"  # NOT trusted - eligible for exit
                    logger.info(
                        f"[{run_id}] IMPORT: {remote.title[:50]}... "
                        f"({remote.size} {remote.outcome} @ ${remote.avg_price:.4f}) "
                        f"[NEW: age_source=unknown, ELIGIBLE FOR EXIT]"
                    )

                hold_start_str = hold_start.strftime("%Y-%m-%dT%H:%M:%SZ")

                if not dry_run:
                    try:
                        await self._import_position(remote, hold_start_str, now_str, age_source)
                        imported += 1
                    except Exception as e:
                        errors.append(f"Failed to import {remote.token_id}: {e}")
                else:
                    imported += 1

            else:
                # Position exists - check for size changes
                local_size = Decimal(str(local["size"]))
                if abs(remote.size - local_size) > Decimal("0.001"):
                    logger.info(
                        f"[{run_id}] UPDATE: {remote.title[:50]}... "
                        f"Size: {local_size} -> {remote.size}"
                    )

                    if not dry_run:
                        try:
                            await self._update_position_size(
                                remote.token_id, remote.size, remote.avg_price, now_str
                            )
                            updated += 1
                        except Exception as e:
                            errors.append(f"Failed to update {remote.token_id}: {e}")
                    else:
                        updated += 1

        # Check for positions that exist locally but not remotely (closed externally)
        # Codex review: Guard against mass-closing on empty API results
        if partial_response:
            logger.warning(
                f"[{run_id}] Skipping close detection due to partial API response."
            )
        elif len(remote_positions) == 0 and len(local_positions) > 0:
            logger.warning(
                f"[{run_id}] API returned 0 positions but {len(local_positions)} exist locally. "
                f"Skipping close detection to prevent accidental data loss. "
                f"If positions were truly closed, re-run sync after verifying API."
            )
        else:
            for token_id, local in local_positions.items():
                if token_id not in remote_token_ids:
                    # Position closed on Polymarket but still open locally
                    logger.info(
                        f"[{run_id}] CLOSE: {token_id} (not found on Polymarket)"
                    )

                    if not dry_run:
                        try:
                            await self._close_position_externally(token_id, now_str)
                            closed += 1
                        except Exception as e:
                            errors.append(f"Failed to close {token_id}: {e}")
                    else:
                        closed += 1

        completed_at = datetime.now(timezone.utc)

        # Log sync result
        if not dry_run:
            await self._log_sync(
                run_id=run_id,
                sync_type="manual",
                wallet_address=wallet_address,
                positions_found=len(remote_positions),
                positions_imported=imported,
                positions_updated=updated,
                positions_closed=closed,
                errors=errors,
                started_at=started_at,
                completed_at=completed_at,
            )

            # Refresh PositionTracker cache
            if self._position_tracker:
                await self._position_tracker.load_positions()
                logger.info(f"[{run_id}] Refreshed PositionTracker cache")

        result = SyncResult(
            run_id=run_id,
            positions_found=len(remote_positions),
            positions_imported=imported,
            positions_updated=updated,
            positions_closed=closed,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
        )

        logger.info(
            f"[{run_id}] Sync complete: "
            f"imported={imported}, updated={updated}, closed={closed}, errors={len(errors)}"
        )

        return result

    async def _import_position(
        self,
        remote: RemotePosition,
        hold_start_str: str,
        now_str: str,
        age_source: str = "unknown",
    ) -> None:
        """Import a new position from Polymarket.

        Args:
            remote: Position data from Polymarket API
            hold_start_str: Hold start timestamp (for exit logic)
            now_str: Current timestamp
            age_source: Reliability of timestamp for exit logic:
                - "actual": From trade history, trusted
                - "unknown": Set to NOW, NOT trusted (eligible for exit)
        """
        entry_cost = float(remote.size * remote.avg_price)

        query = """
            INSERT INTO positions (
                token_id, condition_id, outcome, outcome_index, side,
                size, entry_price, entry_cost, current_price, current_value,
                unrealized_pnl, status, description,
                entry_timestamp, created_at, updated_at,
                imported_at, import_source, hold_start_at, age_source
            ) VALUES (
                $1, $2, $3, $4, 'BUY',
                $5, $6, $7, $8, $9,
                $10, 'open', $11,
                $12, $13, $14,
                $15, 'polymarket_sync', $16, $17
            )
        """

        await self._db.execute(
            query,
            remote.token_id,
            remote.condition_id,
            remote.outcome,
            remote.outcome_index,
            float(remote.size),
            float(remote.avg_price),
            entry_cost,
            float(remote.current_price),
            float(remote.size * remote.current_price),
            float(remote.unrealized_pnl or 0),
            remote.title[:255] if remote.title else None,
            now_str,  # entry_timestamp = now for imports
            now_str,  # created_at
            now_str,  # updated_at
            now_str,  # imported_at
            hold_start_str,  # hold_start_at (based on policy)
            age_source,  # Timestamp reliability for exit logic
        )

    async def _update_position_size(
        self,
        token_id: str,
        new_size: Decimal,
        avg_price: Decimal,
        now_str: str,
    ) -> None:
        """Update position size (external adjustment)."""
        query = """
            UPDATE positions
            SET size = $2,
                entry_cost = $3,
                cost_basis_unknown = TRUE,
                updated_at = $4
            WHERE token_id = $1 AND status = 'open'
        """
        await self._db.execute(
            query,
            token_id,
            float(new_size),
            float(new_size * avg_price),
            now_str,
        )

    async def _close_position_externally(
        self, token_id: str, now_str: str
    ) -> None:
        """Mark position as closed externally."""
        query = """
            UPDATE positions
            SET status = 'closed',
                exit_timestamp = $2,
                resolution = 'external_close',
                exit_pending = FALSE,
                exit_order_id = NULL,
                exit_status = NULL,
                updated_at = $2
            WHERE token_id = $1 AND status = 'open'
        """
        await self._db.execute(query, token_id, now_str)

    async def correct_hold_timestamps(
        self,
        wallet_address: str,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Correct hold_start_at for existing positions using actual trade timestamps.

        This fixes positions that were imported with hold_policy="new" but should
        have their actual purchase dates for proper exit logic.

        Args:
            wallet_address: Wallet to fetch trade history for
            dry_run: If True, only report what would change

        Returns:
            Dict with correction results
        """
        run_id = str(uuid.uuid4())[:8]
        logger.info(f"[{run_id}] Correcting hold timestamps for existing positions")

        # Fetch trade timestamps
        trade_timestamps = await self.fetch_trade_timestamps(wallet_address)
        if not trade_timestamps:
            logger.warning(f"[{run_id}] No trade history found")
            return {"corrected": 0, "errors": ["No trade history found"]}

        # Get local positions
        local_positions = await self.get_local_positions()

        corrected = 0
        errors: List[str] = []
        now = datetime.now(timezone.utc)

        for token_id, local in local_positions.items():
            actual_timestamp = trade_timestamps.get(token_id)
            if not actual_timestamp:
                continue

            # Check if hold_start_at is significantly different from actual
            current_hold_start = local.get("hold_start_at")
            if current_hold_start:
                if isinstance(current_hold_start, str):
                    current_hold_start = datetime.fromisoformat(
                        current_hold_start.replace("Z", "+00:00")
                    )
                elif not current_hold_start.tzinfo:
                    current_hold_start = current_hold_start.replace(tzinfo=timezone.utc)

                # Skip if timestamps are close (within 1 hour)
                diff = abs((current_hold_start - actual_timestamp).total_seconds())
                if diff < 3600:
                    continue

                current_age = (now - current_hold_start).days
                actual_age = (now - actual_timestamp).days

                logger.info(
                    f"[{run_id}] CORRECT: {token_id[:20]}... "
                    f"hold_start: {current_age}d -> {actual_age}d old"
                )

                if not dry_run:
                    try:
                        await self._update_hold_start(token_id, actual_timestamp)
                        corrected += 1
                    except Exception as e:
                        errors.append(f"Failed to correct {token_id}: {e}")
                else:
                    corrected += 1

        logger.info(
            f"[{run_id}] Correction complete: {corrected} positions "
            f"{'would be' if dry_run else ''} updated"
        )

        return {
            "corrected": corrected,
            "errors": errors,
            "dry_run": dry_run,
        }

    async def _update_hold_start(
        self, token_id: str, hold_start: datetime
    ) -> None:
        """Update hold_start_at for an existing position.

        FIX: Also sets age_source='actual' to indicate the timestamp
        came from actual trade history, not a guess.
        """
        hold_start_str = hold_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = """
            UPDATE positions
            SET hold_start_at = $2,
                age_source = 'actual',
                updated_at = $3
            WHERE token_id = $1 AND status = 'open'
        """
        await self._db.execute(query, token_id, hold_start_str, now_str)

    async def _log_sync(
        self,
        run_id: str,
        sync_type: str,
        wallet_address: str,
        positions_found: int,
        positions_imported: int,
        positions_updated: int,
        positions_closed: int,
        errors: List[str],
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        """Log sync operation for audit trail."""
        query = """
            INSERT INTO positions_sync_log (
                run_id, sync_type, wallet_address,
                positions_found, positions_imported, positions_updated, positions_closed,
                errors, started_at, completed_at, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """
        await self._db.execute(
            query,
            run_id,
            sync_type,
            wallet_address,
            positions_found,
            positions_imported,
            positions_updated,
            positions_closed,
            "; ".join(errors) if errors else None,
            started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def quick_sync_sizes(
        self,
        wallet_address: str,
    ) -> Dict[str, Any]:
        """
        Quick sync of position sizes from Polymarket API.

        G12 FIX: Syncs position sizes before exit attempts to prevent
        "not enough balance / allowance" errors when positions were
        partially sold externally.

        This is faster than full sync - only updates sizes, doesn't
        import new positions or close missing ones.

        Args:
            wallet_address: Wallet address to query

        Returns:
            Dict with sync results
        """
        logger.debug("Quick sync: fetching current position sizes...")

        try:
            remote_positions, partial = await self.fetch_remote_positions(wallet_address)

            if partial:
                logger.warning("Quick sync: partial API response, skipping")
                return {"updated": 0, "error": "partial_response"}

            # Build lookup of remote sizes
            remote_sizes: Dict[str, tuple[Decimal, Decimal]] = {}
            for rp in remote_positions:
                remote_sizes[rp.token_id] = (rp.size, rp.avg_price)

            # Get local open positions
            local_positions = await self.get_local_positions()

            updated = 0
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            closed = 0
            for token_id, local in local_positions.items():
                if token_id not in remote_sizes:
                    # Position completely gone from Polymarket - mark as closed
                    logger.info(
                        f"Quick sync: {token_id[:20]}... not found on Polymarket, marking closed"
                    )
                    await self._close_position_externally(token_id, now_str)

                    # Update in-memory tracker if available
                    if self._position_tracker:
                        pos = self._position_tracker.get_position_by_token(token_id)
                        if pos:
                            pos.status = "closed"
                            # Remove from token mapping
                            if token_id in self._position_tracker._token_positions:
                                del self._position_tracker._token_positions[token_id]

                    closed += 1
                    continue

                remote_size, remote_avg_price = remote_sizes[token_id]
                local_size = Decimal(str(local["size"]))

                # Check if size changed significantly
                if abs(remote_size - local_size) > Decimal("0.001"):
                    logger.info(
                        f"Quick sync: {token_id[:20]}... size {local_size} -> {remote_size}"
                    )

                    await self._update_position_size(
                        token_id, remote_size, remote_avg_price, now_str
                    )

                    # Update in-memory tracker if available
                    if self._position_tracker:
                        pos = self._position_tracker.get_position_by_token(token_id)
                        if pos:
                            pos.size = remote_size
                            pos.entry_cost = remote_size * remote_avg_price

                    updated += 1

            if updated > 0 or closed > 0:
                logger.info(f"Quick sync: updated {updated} sizes, closed {closed} missing positions")

            return {"updated": updated, "closed": closed, "checked": len(local_positions)}

        except Exception as e:
            logger.error(f"Quick sync error: {e}")
            return {"updated": 0, "error": str(e)}
