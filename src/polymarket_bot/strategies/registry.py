"""
Strategy registry for dynamic strategy management.

Allows registering strategies by name and looking them up at runtime.
This enables configuration-driven strategy selection.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Type

from .protocol import Strategy


class StrategyNotFoundError(Exception):
    """Raised when a requested strategy is not found in the registry."""

    pass


class DuplicateStrategyError(Exception):
    """Raised when attempting to register a strategy with a name that already exists."""

    pass


class StrategyRegistry:
    """
    Registry for strategy lookup and management.

    Strategies can be registered either as instances or classes.
    The registry prevents duplicate names to avoid confusion.

    Usage:
        registry = StrategyRegistry()

        # Register a strategy
        registry.register(MyStrategy())

        # Or register by class
        registry.register_class(MyStrategy)

        # Look up by name
        strategy = registry.get("my_strategy")

        # List all available
        names = registry.list_all()
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._strategies: Dict[str, Strategy] = {}
        self._classes: Dict[str, Type[Strategy]] = {}

    def register(self, strategy: Strategy) -> None:
        """
        Register a strategy instance.

        Args:
            strategy: Strategy instance to register

        Raises:
            DuplicateStrategyError: If a strategy with this name already exists
        """
        name = strategy.name
        if name in self._strategies:
            raise DuplicateStrategyError(
                f"Strategy '{name}' is already registered. "
                f"Use a different name or unregister first."
            )
        self._strategies[name] = strategy

    def register_class(self, strategy_class: Type[Strategy]) -> None:
        """
        Register a strategy class (for lazy instantiation).

        Args:
            strategy_class: Strategy class to register

        Raises:
            DuplicateStrategyError: If a strategy with this name already exists
        """
        # Instantiate to get the name
        instance = strategy_class()
        name = instance.name

        if name in self._strategies or name in self._classes:
            raise DuplicateStrategyError(
                f"Strategy '{name}' is already registered. "
                f"Use a different name or unregister first."
            )
        self._classes[name] = strategy_class
        self._strategies[name] = instance

    def get(self, name: str) -> Strategy:
        """
        Get a strategy by name.

        Args:
            name: Strategy name to look up

        Returns:
            The registered strategy instance

        Raises:
            StrategyNotFoundError: If no strategy with this name exists
        """
        if name not in self._strategies:
            available = ", ".join(self.list_all()) or "(none)"
            raise StrategyNotFoundError(
                f"Strategy '{name}' not found. Available: {available}"
            )
        return self._strategies[name]

    def get_optional(self, name: str) -> Optional[Strategy]:
        """
        Get a strategy by name, returning None if not found.

        Args:
            name: Strategy name to look up

        Returns:
            The strategy instance or None
        """
        return self._strategies.get(name)

    def unregister(self, name: str) -> bool:
        """
        Remove a strategy from the registry.

        Args:
            name: Strategy name to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._strategies:
            del self._strategies[name]
            if name in self._classes:
                del self._classes[name]
            return True
        return False

    def list_all(self) -> List[str]:
        """
        List all registered strategy names.

        Returns:
            Sorted list of strategy names
        """
        return sorted(self._strategies.keys())

    def __len__(self) -> int:
        """Return number of registered strategies."""
        return len(self._strategies)

    def __contains__(self, name: str) -> bool:
        """Check if a strategy is registered."""
        return name in self._strategies


# Global default registry
_default_registry: Optional[StrategyRegistry] = None


def get_default_registry() -> StrategyRegistry:
    """Get the default global strategy registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = StrategyRegistry()
    return _default_registry


def register_strategy(strategy: Strategy) -> None:
    """Register a strategy in the default registry."""
    get_default_registry().register(strategy)


def get_strategy(name: str) -> Strategy:
    """Get a strategy from the default registry."""
    return get_default_registry().get(name)
