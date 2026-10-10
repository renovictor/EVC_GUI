"""
Development-only deterministic fault injection for ZPAR transactions.

This module provides controlled fault injection for testing ZPAR robustness
without affecting production behavior. Disabled by default.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# Global flag: Set to False in production, True for testing
ZPAR_FAULT_INJECTION_ENABLED = False


class FaultType(Enum):
    """Types of faults that can be injected."""
    DELAYED_RESPONSE = "delayed_response"
    FRAGMENTED_RESPONSE = "fragmented_response"
    STALE_RESPONSE = "stale_response"
    DROPPED_RESPONSE = "dropped_response"


@dataclass
class FaultInjectionConfig:
    """Configuration for a specific fault injection."""
    fault_type: FaultType
    delay_ms: int = 0
    fragment_gap_ms: int = 0


# Deterministic fault mapping: query_index -> fault configuration
# query_index is the cumulative count of ZPAR queries within a contour download
FAULT_INJECTION_MAP: dict[int, FaultInjectionConfig] = {
    # Example: query 20 gets delayed by 100ms
    20: FaultInjectionConfig(FaultType.DELAYED_RESPONSE, delay_ms=100),
    # Example: query 40 gets fragmented with 80ms gap
    40: FaultInjectionConfig(FaultType.FRAGMENTED_RESPONSE, fragment_gap_ms=80),
    # Example: query 60 gets stale response (previous valid response)
    60: FaultInjectionConfig(FaultType.STALE_RESPONSE),
    # Example: query 80 gets dropped/timeout
    80: FaultInjectionConfig(FaultType.DROPPED_RESPONSE),
}


class ZparFaultInjector:
    """
    Manages deterministic fault injection for ZPAR transactions.
    
    This class is completely isolated and only active when
    ZPAR_FAULT_INJECTION_ENABLED is True.
    """
    
    def __init__(self):
        self.query_count = 0
        self.last_valid_response: Optional[str] = None
        self.fault_history: list[tuple[int, FaultType, str]] = []
    
    def should_inject_fault(self, query_index: int) -> Optional[FaultInjectionConfig]:
        """Check if a fault should be injected for this query."""
        if not ZPAR_FAULT_INJECTION_ENABLED:
            return None
        
        config = FAULT_INJECTION_MAP.get(query_index)
        if config:
            log.info("[FAULT INJECTION] query=%d type=%s", query_index, config.fault_type.value)
            self.fault_history.append((query_index, config.fault_type, "injected"))
        
        return config
    
    def record_valid_response(self, response: str):
        """Record a valid response for potential stale injection."""
        if ZPAR_FAULT_INJECTION_ENABLED:
            self.last_valid_response = response
    
    def get_stale_response(self) -> Optional[str]:
        """Get the previously recorded response for stale injection."""
        if ZPAR_FAULT_INJECTION_ENABLED and self.last_valid_response:
            log.info("[FAULT INJECTION] returning stale response from previous transaction")
            return self.last_valid_response
        return None
    
    def apply_delayed_response(self, config: FaultInjectionConfig):
        """Apply response delay."""
        if config.delay_ms > 0:
            delay_s = config.delay_ms / 1000.0
            log.info("[FAULT INJECTION] applying %dms delay", config.delay_ms)
            time.sleep(delay_s)
    
    def should_drop_response(self, config: FaultInjectionConfig) -> bool:
        """Check if response should be dropped."""
        if config.fault_type == FaultType.DROPPED_RESPONSE:
            log.info("[FAULT INJECTION] dropping response (simulating timeout)")
            return True
        return False
    
    def should_fragment_response(self, config: FaultInjectionConfig) -> bool:
        """Check if response should be fragmented."""
        return config.fault_type == FaultType.FRAGMENTED_RESPONSE
    
    def should_return_stale(self, config: FaultInjectionConfig) -> bool:
        """Check if stale response should be returned."""
        return config.fault_type == FaultType.STALE_RESPONSE
    
    def reset(self):
        """Reset state for new session."""
        self.query_count = 0
        self.last_valid_response = None
        self.fault_history.clear()
    
    def get_report(self) -> str:
        """Get report of all injected faults."""
        if not self.fault_history:
            return "No faults injected"
        
        lines = [f"Fault injection report ({len(self.fault_history)} faults):"]
        for query_idx, fault_type, status in self.fault_history:
            lines.append(f"  query={query_idx} type={fault_type.value} {status}")
        return "\n".join(lines)


# Global instance
_global_injector: Optional[ZparFaultInjector] = None


def get_fault_injector() -> ZparFaultInjector:
    """Get the global fault injector instance."""
    global _global_injector
    if _global_injector is None:
        _global_injector = ZparFaultInjector()
    return _global_injector


def reset_fault_injector():
    """Reset the global fault injector."""
    global _global_injector
    if _global_injector:
        _global_injector.reset()


def enable_fault_injection(enabled: bool = True):
    """Enable or disable fault injection (development only)."""
    global ZPAR_FAULT_INJECTION_ENABLED
    ZPAR_FAULT_INJECTION_ENABLED = enabled
    log.info("ZPAR fault injection: %s", "ENABLED" if enabled else "DISABLED")


def is_fault_injection_enabled() -> bool:
    """Check if fault injection is currently enabled."""
    return ZPAR_FAULT_INJECTION_ENABLED
