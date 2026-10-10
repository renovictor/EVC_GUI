"""
Adaptive communication quality monitoring for ZPAR transactions.

Tracks communication metrics and automatically adjusts timing profiles
based on observed link quality without user intervention.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from enum import Enum
from datetime import datetime
from evc_gui.services.zpar_result import CommunicationQuality, ZparErrorCategory

log = logging.getLogger(__name__)


@dataclass
class TimingProfile:
    """Configuration for ZPAR communication timing."""
    name: str
    payload_quiet_period_s: float  # Time to wait for payload to stabilize
    command_guard_delay_s: float  # Delay before sending next command
    overall_timeout_s: float  # Maximum time to wait for response


# Predefined timing profiles for different link qualities
TIMING_PROFILES = {
    CommunicationQuality.PROBING: TimingProfile(
        name="PROBING",
        payload_quiet_period_s=0.05,
        command_guard_delay_s=0.01,
        overall_timeout_s=1.0,
    ),
    CommunicationQuality.GOOD: TimingProfile(
        name="GOOD",
        payload_quiet_period_s=0.04,
        command_guard_delay_s=0.0,
        overall_timeout_s=0.5,
    ),
    CommunicationQuality.DEGRADED: TimingProfile(
        name="DEGRADED",
        payload_quiet_period_s=0.08,
        command_guard_delay_s=0.02,
        overall_timeout_s=1.0,
    ),
    CommunicationQuality.POOR: TimingProfile(
        name="POOR",
        payload_quiet_period_s=0.15,
        command_guard_delay_s=0.05,
        overall_timeout_s=1.5,
    ),
    CommunicationQuality.FAILED: TimingProfile(
        name="FAILED",
        payload_quiet_period_s=0.20,
        command_guard_delay_s=0.10,
        overall_timeout_s=2.0,
    ),
}


@dataclass
class QualityMetrics:
    """Accumulated metrics for quality calculation."""
    total_requests: int = 0
    successful_requests: int = 0
    first_attempt_successes: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    incomplete_response_count: int = 0
    parse_failure_count: int = 0
    position_mismatch_count: int = 0
    band_mismatch_count: int = 0
    unrecoverable_failures: int = 0
    
    # Response times in milliseconds
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def add_success(self, elapsed_ms: float, recovered_by_retry: bool = False):
        """Record a successful response."""
        self.total_requests += 1
        self.successful_requests += 1
        if not recovered_by_retry:
            self.first_attempt_successes += 1
        else:
            self.retry_count += 1
        self.response_times.append(elapsed_ms)
    
    def add_retry(self):
        """Record a retry attempt."""
        self.retry_count += 1
    
    def add_error(self, error_category: ZparErrorCategory):
        """Record an error by category."""
        self.total_requests += 1
        
        if error_category == ZparErrorCategory.TIMEOUT:
            self.timeout_count += 1
        elif error_category == ZparErrorCategory.INCOMPLETE_RESPONSE:
            self.incomplete_response_count += 1
        elif error_category == ZparErrorCategory.PARSE_FAILURE:
            self.parse_failure_count += 1
        elif error_category == ZparErrorCategory.POSITION_MISMATCH:
            self.position_mismatch_count += 1
        elif error_category == ZparErrorCategory.BAND_MISMATCH:
            self.band_mismatch_count += 1
        else:
            self.unrecoverable_failures += 1
    
    def success_rate(self) -> float:
        """Return percentage of successful requests (0-100)."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0
    
    def first_attempt_rate(self) -> float:
        """Return percentage of first-attempt successes (0-100)."""
        if self.successful_requests == 0:
            return 100.0
        return (self.first_attempt_successes / self.successful_requests) * 100.0
    
    def median_response_time_ms(self) -> Optional[float]:
        """Return median response time in ms."""
        if not self.response_times:
            return None
        sorted_times = sorted(self.response_times)
        mid = len(sorted_times) // 2
        if len(sorted_times) % 2 == 1:
            return float(sorted_times[mid])
        return float((sorted_times[mid - 1] + sorted_times[mid]) / 2)
    
    def p95_response_time_ms(self) -> Optional[float]:
        """Return approximate 95th percentile response time in ms."""
        if len(self.response_times) < 2:
            return None if not self.response_times else float(self.response_times[0])
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return float(sorted_times[min(idx, len(sorted_times) - 1)])


class CommunicationQualityMonitor:
    """
    Monitors ZPAR transaction quality and adaptively adjusts timing profiles.
    
    Uses a rolling window of transactions to classify link quality
    and transition between timing profiles automatically.
    """
    
    def __init__(self):
        self.current_quality = CommunicationQuality.PROBING
        self.previous_quality = CommunicationQuality.PROBING
        self.forced_quality: Optional[CommunicationQuality] = None
        self.metrics = QualityMetrics()
        
        # Tracking for quality transitions
        self.quality_changes: list[tuple[datetime, CommunicationQuality, str]] = []
        self.last_quality_change_time = time.monotonic()
        self.clean_streak_start = time.monotonic()
        
        # Hysteresis: minimum requests/time before downgrade vs upgrade
        self.DOWNGRADE_THRESHOLD_REQUESTS = 5
        self.DOWNGRADE_THRESHOLD_QUALITY_LOSS = 15.0  # percentage points
        self.UPGRADE_THRESHOLD_REQUESTS = 20
        self.UPGRADE_THRESHOLD_TIME_S = 10.0
        
        # Immediate downgrade triggers (single event)
        self.IMMEDIATE_DOWNGRADE_EVENTS = [
            ZparErrorCategory.POSITION_MISMATCH,
            ZparErrorCategory.BAND_MISMATCH,
            ZparErrorCategory.CORRUPTED_RESPONSE,
        ]
    
    def record_result(self, result):
        """Record a ZPAR transaction result and update quality."""
        from evc_gui.services.zpar_result import ZparResult
        
        if not isinstance(result, ZparResult):
            return
        
        if result.success:
            self.metrics.add_success(result.elapsed_ms, result.recovered_by_retry)
        else:
            self.metrics.add_error(result.error_category)

        if self.forced_quality is not None:
            return
        
        # Check for immediate downgrade triggers
        if result.error_category in self.IMMEDIATE_DOWNGRADE_EVENTS:
            self._maybe_downgrade_quality("integrity_event")
        else:
            # Normal quality assessment
            self._assess_quality()
    
    def get_timing_profile(self) -> TimingProfile:
        """Get current timing profile for ZPAR transactions."""
        active_quality = self.forced_quality or self.current_quality
        return TIMING_PROFILES[active_quality]
    
    def get_current_quality(self) -> CommunicationQuality:
        """Get current quality level."""
        return self.forced_quality or self.current_quality

    def set_forced_quality(self, quality: Optional[CommunicationQuality]):
        """Force a specific timing quality profile, or clear override with None."""
        self.forced_quality = quality

    def get_forced_quality(self) -> Optional[CommunicationQuality]:
        """Get forced quality override if set."""
        return self.forced_quality
    
    def reset(self):
        """Reset metrics and quality state (e.g., at start of new session)."""
        self.metrics = QualityMetrics()
        self.current_quality = CommunicationQuality.PROBING
        self.previous_quality = CommunicationQuality.PROBING
        self.clean_streak_start = time.monotonic()
    
    def _assess_quality(self):
        """Assess current quality based on metrics and adjust if needed."""
        current_time = time.monotonic()
        time_since_change = current_time - self.last_quality_change_time
        recent_requests = min(20, self.metrics.total_requests)
        
        success_rate = self.metrics.success_rate()
        first_attempt_rate = self.metrics.first_attempt_rate()
        
        # Determine target quality based on metrics
        target_quality = self.current_quality
        
        if self.current_quality == CommunicationQuality.PROBING:
            if recent_requests >= 5 and success_rate >= 95.0:
                target_quality = CommunicationQuality.GOOD
        elif self.current_quality == CommunicationQuality.GOOD:
            if success_rate < 80.0 or first_attempt_rate < 80.0:
                target_quality = CommunicationQuality.DEGRADED
        elif self.current_quality == CommunicationQuality.DEGRADED:
            if success_rate < 60.0:
                target_quality = CommunicationQuality.POOR
            elif success_rate >= 95.0 and time_since_change >= self.UPGRADE_THRESHOLD_TIME_S:
                target_quality = CommunicationQuality.GOOD
        elif self.current_quality == CommunicationQuality.POOR:
            if success_rate < 40.0:
                target_quality = CommunicationQuality.FAILED
            elif success_rate >= 90.0 and time_since_change >= self.UPGRADE_THRESHOLD_TIME_S * 1.5:
                target_quality = CommunicationQuality.DEGRADED
        
        if target_quality != self.current_quality:
            self._transition_quality(target_quality, "metrics_based")
    
    def _maybe_downgrade_quality(self, reason: str = ""):
        """Potentially downgrade quality based on serious issues."""
        if self.current_quality == CommunicationQuality.PROBING:
            self._transition_quality(CommunicationQuality.DEGRADED, reason)
        elif self.current_quality == CommunicationQuality.GOOD:
            self._transition_quality(CommunicationQuality.DEGRADED, reason)
        elif self.current_quality == CommunicationQuality.DEGRADED:
            self._transition_quality(CommunicationQuality.POOR, reason)
        elif self.current_quality == CommunicationQuality.POOR:
            self._transition_quality(CommunicationQuality.FAILED, reason)
    
    def _transition_quality(self, new_quality: CommunicationQuality, reason: str = ""):
        """Record a quality transition."""
        if new_quality == self.current_quality:
            return
        
        self.previous_quality = self.current_quality
        self.current_quality = new_quality
        self.last_quality_change_time = time.monotonic()
        self.clean_streak_start = time.monotonic()
        
        timestamp = datetime.now()
        self.quality_changes.append((timestamp, new_quality, reason))
        
        log.info(
            "ZPAR quality transition: %s -> %s reason=%s requests=%d success_rate=%.1f%% "
            "first_attempt=%.1f%% retries=%d timeouts=%d position_mismatches=%d",
            self.previous_quality.value,
            new_quality.value,
            reason,
            self.metrics.total_requests,
            self.metrics.success_rate(),
            self.metrics.first_attempt_rate(),
            self.metrics.retry_count,
            self.metrics.timeout_count,
            self.metrics.position_mismatch_count,
        )
    
    def get_summary(self) -> str:
        """Get a text summary of quality metrics."""
        mode_text = "AUTO" if self.forced_quality is None else f"FORCED ({self.forced_quality.value})"
        lines = [
            f"Timing profile mode: {mode_text}",
            f"Operating environment quality: {self.current_quality.value}",
            f"Active timing profile: {self.get_current_quality().value}",
            f"Total requests: {self.metrics.total_requests}",
            f"Successful responses: {self.metrics.successful_requests}",
            f"First-attempt successes: {self.metrics.first_attempt_successes}",
            f"Recovered by retry: {self.metrics.retry_count}",
            f"Success rate: {self.metrics.success_rate():.1f}%",
            f"First-attempt rate: {self.metrics.first_attempt_rate():.1f}%",
        ]
        
        if self.metrics.timeout_count > 0:
            lines.append(f"Timeouts: {self.metrics.timeout_count}")
        if self.metrics.incomplete_response_count > 0:
            lines.append(f"Incomplete responses: {self.metrics.incomplete_response_count}")
        if self.metrics.parse_failure_count > 0:
            lines.append(f"Parse failures: {self.metrics.parse_failure_count}")
        if self.metrics.position_mismatch_count > 0:
            lines.append(f"Position mismatches: {self.metrics.position_mismatch_count}")
        if self.metrics.band_mismatch_count > 0:
            lines.append(f"Band mismatches: {self.metrics.band_mismatch_count}")
        if self.metrics.unrecoverable_failures > 0:
            lines.append(f"Unrecoverable failures: {self.metrics.unrecoverable_failures}")
        
        if self.metrics.response_times:
            lines.append(f"Min response time: {min(self.metrics.response_times):.2f}ms")
            lines.append(f"Max response time: {max(self.metrics.response_times):.2f}ms")
            avg = sum(self.metrics.response_times) / len(self.metrics.response_times)
            lines.append(f"Avg response time: {avg:.2f}ms")
            median = self.metrics.median_response_time_ms()
            if median is not None:
                lines.append(f"Median response time: {median:.2f}ms")
            p95 = self.metrics.p95_response_time_ms()
            if p95 is not None:
                lines.append(f"P95 response time: {p95:.2f}ms")
        
        return "\n".join(lines)
