"""
Comprehensive ZPAR query service with validation, retry, and recovery.

This service handles all ZPAR transactions with:
- Request/response identity validation
- Automatic retry with clean recovery
- Adaptive communication quality
- Structured result tracking
- Optional development fault injection
"""

from __future__ import annotations
import logging
import time
from typing import Optional

from evc_gui.services.serial_service import SerialService
from evc_gui.services.zpar_result import (
    ZparRequest, ZparResponse, ZparResult, ZparErrorCategory, CommunicationQuality
)
from evc_gui.services.zpar_parser import (
    parse_zpar_response, parse_and_validate_zpar_response,
    is_response_complete, is_response_corrupted, is_error_response
)
from evc_gui.services.zpar_quality import CommunicationQualityMonitor
from evc_gui.services.zpar_fault_injection import (
    get_fault_injector, FaultType, is_fault_injection_enabled
)

log = logging.getLogger(__name__)

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_S = 0.05
RETRY_ESCALATION_FACTOR = 2.0  # exponential backoff


class ZparQueryService:
    """
    Complete ZPAR query service with validation, retry, and recovery.
    
    Provides a single entry point for all ZPAR transactions with
    automatic failure recovery and communication quality monitoring.
    """
    
    def __init__(self, serial_service: SerialService):
        self.serial = serial_service
        self.quality_monitor = CommunicationQualityMonitor()
        self.query_index = 0  # For fault injection
        self.last_valid_response: Optional[str] = None  # For stale injection
    
    def query_zpar(self, cmd: str) -> ZparResult:
        """
        Execute a ZPAR query with full validation, retry, and recovery.
        
        Returns: ZparResult with complete diagnostics
        """
        self.query_index += 1
        request = ZparRequest.from_command(cmd)
        
        if not request:
            result = ZparResult(
                success=False,
                error_category=ZparErrorCategory.INVALID_COMMAND,
                error_message=f"Invalid ZPAR command format: {cmd}",
                quality_level=self.quality_monitor.get_current_quality(),
                timing_profile_name=self.quality_monitor.get_timing_profile().name,
            )
            return result
        
        # Acquire transaction lock for exclusive serial access
        self.serial.acquire_transaction_lock()
        try:
            return self._execute_transaction_with_retry(request)
        finally:
            self.serial.release_transaction_lock()
    
    def _execute_transaction_with_retry(self, request: ZparRequest) -> ZparResult:
        """Execute transaction with retry logic and clean recovery."""
        timing_profile = self.quality_monitor.get_timing_profile()
        start_time = time.monotonic()
        
        for attempt_num in range(1, MAX_RETRY_ATTEMPTS + 1):
            # Check for fault injection
            fault_config = get_fault_injector().should_inject_fault(self.query_index)
            
            # Handle stale response injection
            if fault_config and fault_config.fault_type == FaultType.STALE_RESPONSE:
                if self.last_valid_response:
                    log.info("[FAULT INJECTION] Returning stale response for query %d", self.query_index)
                    return ZparResult(
                        success=False,
                        requested=request,
                        error_category=ZparErrorCategory.POSITION_MISMATCH,
                        error_message="[INJECTED] Stale response",
                        attempt_count=attempt_num,
                        elapsed_ms=(time.monotonic() - start_time) * 1000,
                        quality_level=self.quality_monitor.get_current_quality(),
                        timing_profile_name=timing_profile.name,
                    )
            
            # Clean the input buffer before send
            if attempt_num > 1:
                drained = self.serial.drain_input_buffer(
                    timeout_s=0.05,
                    quiet_period_s=timing_profile.payload_quiet_period_s
                )
                if drained:
                    log.debug("Drained %d bytes before retry attempt %d", len(drained), attempt_num)
            
            # Apply guard delay if configured
            if timing_profile.command_guard_delay_s > 0:
                time.sleep(timing_profile.command_guard_delay_s)
            
            # Apply delayed response fault if configured
            if fault_config and fault_config.fault_type == FaultType.DELAYED_RESPONSE:
                get_fault_injector().apply_delayed_response(fault_config)
            
            # Check if response should be dropped
            if fault_config and get_fault_injector().should_drop_response(fault_config):
                log.info("[FAULT INJECTION] Dropping response (simulating timeout)")
                result = ZparResult(
                    success=False,
                    requested=request,
                    error_category=ZparErrorCategory.TIMEOUT,
                    error_message="[INJECTED] Dropped response",
                    attempt_count=attempt_num,
                    elapsed_ms=(time.monotonic() - start_time) * 1000,
                    quality_level=self.quality_monitor.get_current_quality(),
                    timing_profile_name=timing_profile.name,
                )
                if attempt_num < MAX_RETRY_ATTEMPTS:
                    self._apply_retry_backoff(attempt_num)
                continue
            
            # Execute the actual ZPAR command
            cmd_result = self.serial.send_command(
                request.command,
                timeout=timing_profile.overall_timeout_s,
                read_timeout=timing_profile.payload_quiet_period_s / 2,
                payload_quiet_period_s=timing_profile.payload_quiet_period_s,
            )
            
            elapsed_ms = (time.monotonic() - start_time) * 1000
            
            # Parse and validate response
            result = self._parse_and_validate(request, cmd_result.response, elapsed_ms, attempt_num)
            
            if result.success:
                self.last_valid_response = cmd_result.response
                get_fault_injector().record_valid_response(cmd_result.response)
                self.quality_monitor.record_result(result)
                return result
            
            # Check if error is retryable
            if not self._is_retryable_error(result.error_category):
                self.quality_monitor.record_result(result)
                return result
            
            # Not the last attempt, apply backoff and retry
            if attempt_num < MAX_RETRY_ATTEMPTS:
                self._apply_retry_backoff(attempt_num)
        
        # All retries exhausted
        final_result = ZparResult(
            success=False,
            requested=request,
            error_category=ZparErrorCategory.UNKNOWN,
            error_message=f"Failed after {MAX_RETRY_ATTEMPTS} attempts",
            attempt_count=MAX_RETRY_ATTEMPTS,
            elapsed_ms=(time.monotonic() - start_time) * 1000,
            quality_level=self.quality_monitor.get_current_quality(),
            timing_profile_name=timing_profile.name,
        )
        self.quality_monitor.record_result(final_result)
        return final_result
    
    def _parse_and_validate(self, request: ZparRequest, response: str, elapsed_ms: float, attempt: int) -> ZparResult:
        """Parse and validate response identity."""
        timing_profile = self.quality_monitor.get_timing_profile()
        base_result = {
            'requested': request,
            'attempt_count': attempt,
            'elapsed_ms': elapsed_ms,
            'quality_level': self.quality_monitor.get_current_quality(),
            'timing_profile_name': timing_profile.name,
        }
        
        # Check for various response issues
        if not response or not response.strip():
            return ZparResult(
                success=False,
                error_category=ZparErrorCategory.NO_RESPONSE,
                error_message="No response received",
                **base_result
            )
        
        if is_error_response(response):
            return ZparResult(
                success=False,
                error_category=ZparErrorCategory.INVALID_COMMAND,
                error_message="Device returned error response",
                raw_response=response[:255],
                **base_result
            )
        
        if is_response_corrupted(response):
            return ZparResult(
                success=False,
                error_category=ZparErrorCategory.CORRUPTED_RESPONSE,
                error_message="Response appears corrupted",
                raw_response=response[:255],
                **base_result
            )
        
        if not is_response_complete(response):
            return ZparResult(
                success=False,
                error_category=ZparErrorCategory.INCOMPLETE_RESPONSE,
                error_message="Response missing Z-parameters",
                raw_response=response[:255],
                **base_result
            )
        
        # Parse and validate identity
        parsed = parse_and_validate_zpar_response(response, request.band)
        
        if not parsed or not parsed.z_params:
            return ZparResult(
                success=False,
                error_category=ZparErrorCategory.PARSE_FAILURE,
                error_message="Failed to parse Z-parameters from response",
                raw_response=response[:255],
                **base_result
            )
        
        # Validate capacitor position match if metadata available
        if parsed.c1_coarse is not None and parsed.c1_fine is not None:
            if (parsed.c1_coarse != request.c1_coarse or parsed.c1_fine != request.c1_fine or
                parsed.c2_coarse != request.c2_coarse or parsed.c2_fine != request.c2_fine):
                return ZparResult(
                    success=False,
                    received=parsed,
                    error_category=ZparErrorCategory.POSITION_MISMATCH,
                    error_message=f"Capacitor position mismatch: requested C1=({request.c1_coarse},{request.c1_fine}) "
                                   f"C2=({request.c2_coarse},{request.c2_fine}) but got "
                                   f"C1=({parsed.c1_coarse},{parsed.c1_fine}) C2=({parsed.c2_coarse},{parsed.c2_fine})",
                    **base_result
                )
        
        # Validate band match if metadata available
        if parsed.band and parsed.band.lower() != request.band.lower():
            return ZparResult(
                success=False,
                received=parsed,
                error_category=ZparErrorCategory.BAND_MISMATCH,
                error_message=f"Band mismatch: requested {request.band} but got {parsed.band}",
                **base_result
            )
        
        # Success!
        return ZparResult(
            success=True,
            requested=request,
            received=parsed,
            z_params=parsed.z_params,
            attempt_count=attempt,
            elapsed_ms=elapsed_ms,
            recovered_by_retry=(attempt > 1),
            quality_level=self.quality_monitor.get_current_quality(),
            timing_profile_name=timing_profile.name,
            raw_response=response[:500],
        )
    
    def _is_retryable_error(self, error_category: ZparErrorCategory) -> bool:
        """Check if error should trigger a retry."""
        retryable = {
            ZparErrorCategory.NO_RESPONSE,
            ZparErrorCategory.TIMEOUT,
            ZparErrorCategory.INCOMPLETE_RESPONSE,
            ZparErrorCategory.PARSE_FAILURE,
            ZparErrorCategory.POSITION_MISMATCH,
            ZparErrorCategory.BAND_MISMATCH,
            ZparErrorCategory.CORRUPTED_RESPONSE,
        }
        return error_category in retryable
    
    def _apply_retry_backoff(self, attempt_num: int):
        """Apply exponential backoff before retry."""
        delay_s = RETRY_BASE_DELAY_S * (RETRY_ESCALATION_FACTOR ** (attempt_num - 1))
        delay_s = min(delay_s, 0.20)  # Cap at 200ms
        log.debug("Retry backoff: sleeping %.3fs before attempt %d", delay_s, attempt_num + 1)
        time.sleep(delay_s)
    
    def reset_session(self):
        """Reset for new contour download session."""
        self.query_index = 0
        self.last_valid_response = None
        self.quality_monitor.reset()
    
    def get_quality_level(self) -> CommunicationQuality:
        """Get current communication quality level."""
        return self.quality_monitor.get_current_quality()
    
    def get_quality_summary(self) -> str:
        """Get text summary of communication quality."""
        return self.quality_monitor.get_summary()

    def set_forced_timing_profile(self, profile_name: str | None):
        """Force a timing profile by name, or clear with None/AUTO."""
        if not profile_name:
            self.quality_monitor.set_forced_quality(None)
            return
        normalized = profile_name.strip().upper()
        if normalized == "AUTO":
            self.quality_monitor.set_forced_quality(None)
            return
        try:
            quality = CommunicationQuality[normalized]
        except KeyError:
            raise ValueError(f"Unsupported timing profile: {profile_name}") from None
        self.quality_monitor.set_forced_quality(quality)

    def get_forced_timing_profile_name(self) -> str:
        """Get current forced timing profile name, or AUTO when not forced."""
        forced = self.quality_monitor.get_forced_quality()
        return forced.value if forced else "AUTO"
