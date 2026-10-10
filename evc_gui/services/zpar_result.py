"""
Structured results for ZPAR transactions.

This module provides result types to replace simple ZParameters | None returns,
enabling detailed diagnostics and error tracking while preserving response validation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import time
from evc_gui.ui.smith_chart import ZParameters


class ZparErrorCategory(Enum):
    """Categorization of ZPAR errors for diagnostics and retry logic."""
    NO_RESPONSE = "no_response"
    TIMEOUT = "timeout"
    INCOMPLETE_RESPONSE = "incomplete_response"
    PARSE_FAILURE = "parse_failure"
    POSITION_MISMATCH = "position_mismatch"
    BAND_MISMATCH = "band_mismatch"
    CORRUPTED_RESPONSE = "corrupted_response"
    INVALID_COMMAND = "invalid_command"
    SERIAL_ERROR = "serial_error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class CommunicationQuality(Enum):
    """Communication quality levels for adaptive timing adjustment."""
    PROBING = "PROBING"
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"
    FAILED = "FAILED"


@dataclass
class ZparRequest:
    """Represents a ZPAR command request with parsed parameters."""
    band: str  # e.g., 'f1', 'hf', 'lf'
    c1_coarse: int
    c1_fine: int
    c2_coarse: int
    c2_fine: int
    command: str

    @staticmethod
    def from_command(cmd: str) -> Optional[ZparRequest]:
        """Parse a zpar show command into structured request.
        
        Expected format: "zpar show <band> <c1_coarse> <c1_fine> <c2_coarse> <c2_fine>"
        """
        parts = cmd.strip().split()
        if len(parts) < 7 or parts[0].lower() != "zpar" or parts[1].lower() != "show":
            return None
        try:
            return ZparRequest(
                band=parts[2].lower(),
                c1_coarse=int(parts[3]),
                c1_fine=int(parts[4]),
                c2_coarse=int(parts[5]),
                c2_fine=int(parts[6]),
                command=cmd,
            )
        except (ValueError, IndexError):
            return None


@dataclass
class ZparResponse:
    """Represents parsed ZPAR response with position metadata."""
    band: Optional[str] = None  # Extracted from response if available
    c1_coarse: Optional[int] = None
    c1_fine: Optional[int] = None
    c2_coarse: Optional[int] = None
    c2_fine: Optional[int] = None
    z_params: Optional[ZParameters] = None
    raw_response: Optional[str] = None


@dataclass
class ZparResult:
    """Complete result of a ZPAR transaction including diagnostics."""
    success: bool
    requested: Optional[ZparRequest] = None
    received: Optional[ZparResponse] = None
    z_params: Optional[ZParameters] = None
    
    # Metadata
    attempt_count: int = 1
    elapsed_ms: float = 0.0
    error_category: ZparErrorCategory = ZparErrorCategory.UNKNOWN
    error_message: str = ""
    
    # Recovery info
    recovered_by_retry: bool = False
    quality_level: CommunicationQuality = CommunicationQuality.PROBING
    timing_profile_name: str = "unknown"
    
    # Tracking for CSV export
    raw_response: str = ""
    parse_details: str = ""

    def to_csv_dict(self) -> dict:
        """Convert result to CSV row dictionary."""
        return {
            'status': 'SUCCESS' if self.success else 'FAILED',
            'attempts': self.attempt_count,
            'elapsed_ms': f"{self.elapsed_ms:.2f}",
            'recovered_by_retry': 'yes' if self.recovered_by_retry else 'no',
            'error_category': self.error_category.value,
            'error_message': self.error_message[:255],  # Truncate for CSV
            'quality_level': self.quality_level.value,
            'timing_profile': self.timing_profile_name,
            'requested_band': self.requested.band if self.requested else '',
            'requested_c1_coarse': self.requested.c1_coarse if self.requested else '',
            'requested_c1_fine': self.requested.c1_fine if self.requested else '',
            'requested_c2_coarse': self.requested.c2_coarse if self.requested else '',
            'requested_c2_fine': self.requested.c2_fine if self.requested else '',
            'response_band': self.received.band if self.received else '',
            'response_c1_coarse': self.received.c1_coarse if self.received else '',
            'response_c1_fine': self.received.c1_fine if self.received else '',
            'response_c2_coarse': self.received.c2_coarse if self.received else '',
            'response_c2_fine': self.received.c2_fine if self.received else '',
            'position_match': 'yes' if self._positions_match() else 'no',
            'z11_r': f"{self.z_params.z11_r:.6g}" if self.z_params else '',
            'z11_i': f"{self.z_params.z11_i:.6g}" if self.z_params else '',
            'z21_r': f"{self.z_params.z21_r:.6g}" if self.z_params else '',
            'z21_i': f"{self.z_params.z21_i:.6g}" if self.z_params else '',
            'z12_r': f"{self.z_params.z12_r:.6g}" if self.z_params else '',
            'z12_i': f"{self.z_params.z12_i:.6g}" if self.z_params else '',
            'z22_r': f"{self.z_params.z22_r:.6g}" if self.z_params else '',
            'z22_i': f"{self.z_params.z22_i:.6g}" if self.z_params else '',
        }

    def _positions_match(self) -> bool:
        """Check if requested and received capacitor positions match."""
        if not self.requested or not self.received:
            return False
        return (
            self.requested.c1_coarse == self.received.c1_coarse and
            self.requested.c1_fine == self.received.c1_fine and
            self.requested.c2_coarse == self.received.c2_coarse and
            self.requested.c2_fine == self.received.c2_fine
        )

    def band_matches(self) -> bool:
        """Check if requested and received bands match (when both known)."""
        if not self.requested or not self.received or not self.received.band:
            return True  # Cannot verify if band info not available
        return self.requested.band.lower() == self.received.band.lower()
