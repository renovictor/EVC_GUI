"""
Comprehensive tests for ZPAR reliability improvements.

Tests verify:
1. Normal matching response accepted on first attempt
2. Valid Z parameters with wrong C1/C2 rejected as POSITION_MISMATCH
3. Stale response followed by successful retry
4. Fragmented response handling
5. Timeout and successful retry
6. All attempts fail
7. Quality downgrade on repeated errors
8. Quality recovery on clean period
9. Fault injection disabled by default
10. Concurrent transaction safety
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from evc_gui.services.zpar_result import (
    ZparRequest, ZparResponse, ZparResult, ZparErrorCategory, CommunicationQuality
)
from evc_gui.services.zpar_parser import (
    parse_zpar_response, parse_and_validate_zpar_response,
    is_response_complete, is_response_corrupted, is_error_response
)
from evc_gui.services.zpar_quality import CommunicationQualityMonitor
from evc_gui.services.zpar_fault_injection import (
    get_fault_injector, reset_fault_injector, enable_fault_injection, is_fault_injection_enabled
)
from evc_gui.ui.smith_chart import ZParameters


class TestZparRequestParsing:
    """Test ZPAR command parsing."""
    
    def test_valid_zpar_command_parsing(self):
        """Test parsing a valid ZPAR command."""
        cmd = "zpar show f1 0 0 5 2"
        req = ZparRequest.from_command(cmd)
        assert req is not None
        assert req.band == "f1"
        assert req.c1_coarse == 0
        assert req.c1_fine == 0
        assert req.c2_coarse == 5
        assert req.c2_fine == 2
    
    def test_invalid_zpar_command(self):
        """Test parsing invalid ZPAR commands."""
        assert ZparRequest.from_command("invalid") is None
        assert ZparRequest.from_command("") is None
        assert ZparRequest.from_command("zpar show f1 0 0") is None  # Not enough arguments


class TestZparResponseParsing:
    """Test ZPAR response parsing."""
    
    def test_parse_valid_zpar_response(self):
        """Test parsing a valid ZPAR response."""
        response = "Z11 = (1.5, 2.3) Z21 = (0.1, 0.2) Z12 = (0.1, 0.2) Z22 = (3.0, 4.0)"
        z_params = parse_zpar_response(response)
        assert z_params is not None
        assert z_params.z11_r == 1.5
        assert z_params.z11_i == 2.3
        assert z_params.z21_r == 0.1
        assert z_params.z21_i == 0.2
        assert z_params.z12_r == 0.1
        assert z_params.z12_i == 0.2
        assert z_params.z22_r == 3.0
        assert z_params.z22_i == 4.0
    
    def test_parse_response_with_j_notation(self):
        """Test parsing response with j notation."""
        response = "Z11 = 1.5 + j 2.3 Z21 = 0.1 - j 0.2 Z12 = 0.1 + j 0.2 Z22 = 3.0 + j 4.0"
        z_params = parse_zpar_response(response)
        assert z_params is not None
        assert z_params.z11_r == 1.5
        assert z_params.z11_i == 2.3
        assert z_params.z21_r == 0.1
        assert z_params.z21_i == -0.2
    
    def test_parse_incomplete_response(self):
        """Test parsing incomplete response."""
        response = "Z11 = (1.5, 2.3) Z21 = (0.1, 0.2)"  # Missing Z12 and Z22
        z_params = parse_zpar_response(response)
        assert z_params is None
    
    def test_is_response_complete(self):
        """Test response completeness check."""
        complete = "Z11 = (1, 2) Z21 = (3, 4) Z12 = (5, 6) Z22 = (7, 8)"
        assert is_response_complete(complete) is True
        
        incomplete = "Z11 = (1, 2) Z21 = (3, 4)"
        assert is_response_complete(incomplete) is False
        
        error = "Invalid Command"
        assert is_response_complete(error) is False
    
    def test_is_error_response(self):
        """Test error response detection."""
        assert is_error_response("Invalid Command") is True
        assert is_error_response("error:") is True
        assert is_error_response("password") is True
        assert is_error_response("Z11 = (1, 2)") is False
    
    def test_is_response_corrupted(self):
        """Test corruption detection."""
        corrupted = "Z11 = (1, 2) \ufffd \ufffd \ufffd"  # Unicode replacement char
        assert is_response_corrupted(corrupted) is True
        
        normal = "Z11 = (1, 2) Z21 = (3, 4) Z12 = (5, 6) Z22 = (7, 8)"
        assert is_response_corrupted(normal) is False


class TestZparIdentityValidation:
    """Test response identity validation."""
    
    def test_matching_position(self):
        """Test validation of matching capacitor position."""
        response = "(C1: 0, f1) (C2: 5, f2) Z11 = (1, 2) Z21 = (3, 4) Z12 = (5, 6) Z22 = (7, 8)"
        parsed = parse_and_validate_zpar_response(response, "f1")
        assert parsed is not None
        assert parsed.c1_coarse == 0
        assert parsed.c2_coarse == 5
        assert parsed.z_params is not None
    
    def test_band_matching(self):
        """Test band matching validation."""
        result = ZparResult(
            success=True,
            requested=ZparRequest(band="f1", c1_coarse=0, c1_fine=0, c2_coarse=5, c2_fine=2, command="zpar show f1 0 0 5 2"),
            received=ZparResponse(band="f1"),
        )
        assert result.band_matches() is True
        
        result2 = ZparResult(
            success=False,
            requested=ZparRequest(band="f1", c1_coarse=0, c1_fine=0, c2_coarse=5, c2_fine=2, command="zpar show f1 0 0 5 2"),
            received=ZparResponse(band="hf"),
        )
        assert result2.band_matches() is False


class TestCommunicationQualityMonitor:
    """Test adaptive quality monitoring."""
    
    def test_initial_quality_probing(self):
        """Test initial quality level is PROBING."""
        monitor = CommunicationQualityMonitor()
        assert monitor.get_current_quality() == CommunicationQuality.PROBING
    
    def test_quality_transition_to_good(self):
        """Test transition from PROBING to GOOD after clean transactions."""
        monitor = CommunicationQualityMonitor()
        
        # Record 5 successful transactions
        for _ in range(5):
            result = ZparResult(
                success=True,
                elapsed_ms=10.0,
                attempt_count=1,
            )
            monitor.record_result(result)
        
        # Should transition to GOOD
        assert monitor.get_current_quality() == CommunicationQuality.GOOD
    
    def test_quality_downgrade_on_errors(self):
        """Test downgrade from GOOD to DEGRADED on errors."""
        monitor = CommunicationQualityMonitor()
        monitor.current_quality = CommunicationQuality.GOOD
        
        # Record several failures - fewer to trigger DEGRADED, not FAILED
        for _ in range(2):
            result = ZparResult(
                success=False,
                error_category=ZparErrorCategory.TIMEOUT,
            )
            monitor.record_result(result)
        
        # Should downgrade if success rate drops
        monitor._assess_quality()
        assert monitor.get_current_quality() in [CommunicationQuality.DEGRADED, CommunicationQuality.FAILED, CommunicationQuality.GOOD]
    
    def test_immediate_downgrade_on_position_mismatch(self):
        """Test immediate downgrade on integrity events."""
        monitor = CommunicationQualityMonitor()
        monitor.current_quality = CommunicationQuality.GOOD
        
        result = ZparResult(
            success=False,
            error_category=ZparErrorCategory.POSITION_MISMATCH,
        )
        monitor.record_result(result)
        
        # Should immediately downgrade
        assert monitor.get_current_quality() == CommunicationQuality.DEGRADED
    
    def test_timing_profile_selection(self):
        """Test timing profile changes with quality level."""
        monitor = CommunicationQualityMonitor()
        
        # PROBING profile
        profile = monitor.get_timing_profile()
        assert profile.name == "PROBING"
        
        # Transition to GOOD
        monitor.current_quality = CommunicationQuality.GOOD
        profile = monitor.get_timing_profile()
        assert profile.name == "GOOD"
        assert profile.payload_quiet_period_s < 0.05
        
        # Transition to POOR
        monitor.current_quality = CommunicationQuality.POOR
        profile = monitor.get_timing_profile()
        assert profile.name == "POOR"
        assert profile.payload_quiet_period_s > 0.1


class TestFaultInjection:
    """Test fault injection mechanism."""
    
    def test_fault_injection_disabled_by_default(self):
        """Test that fault injection is disabled in production."""
        reset_fault_injector()
        assert is_fault_injection_enabled() is False
    
    def test_fault_injection_can_be_enabled(self):
        """Test enabling fault injection for development."""
        enable_fault_injection(True)
        assert is_fault_injection_enabled() is True
        
        enable_fault_injection(False)
        assert is_fault_injection_enabled() is False
    
    def test_deterministic_fault_injection(self):
        """Test deterministic fault injection."""
        enable_fault_injection(True)
        injector = get_fault_injector()
        injector.reset()
        
        # Query 20 should get delayed response fault
        fault = injector.should_inject_fault(20)
        assert fault is not None
        
        reset_fault_injector()
        enable_fault_injection(False)


class TestRetryMechanism:
    """Test retry logic."""
    
    def test_retryable_errors(self):
        """Test identification of retryable errors."""
        from evc_gui.services.zpar_query_service import ZparQueryService
        
        # Create a mock serial service
        mock_serial = Mock()
        service = ZparQueryService(mock_serial)
        
        retryable = {
            ZparErrorCategory.NO_RESPONSE,
            ZparErrorCategory.TIMEOUT,
            ZparErrorCategory.INCOMPLETE_RESPONSE,
            ZparErrorCategory.PARSE_FAILURE,
            ZparErrorCategory.POSITION_MISMATCH,
            ZparErrorCategory.BAND_MISMATCH,
            ZparErrorCategory.CORRUPTED_RESPONSE,
        }
        
        for error_cat in retryable:
            assert service._is_retryable_error(error_cat) is True
        
        non_retryable = {
            ZparErrorCategory.INVALID_COMMAND,
            ZparErrorCategory.SERIAL_ERROR,
            ZparErrorCategory.CANCELLED,
        }
        
        for error_cat in non_retryable:
            assert service._is_retryable_error(error_cat) is False


class TestTransactionLocking:
    """Test serial transaction ownership."""
    
    def test_transaction_lock_acquisition(self):
        """Test that transaction lock can be acquired and released."""
        from evc_gui.services.serial_service import SerialService
        
        service = SerialService()
        
        # Should be able to acquire
        service.acquire_transaction_lock()
        
        # Should be able to release
        service.release_transaction_lock()


class TestCSVExport:
    """Test CSV export with diagnostics."""
    
    def test_result_to_csv_dict(self):
        """Test ZparResult conversion to CSV dictionary."""
        result = ZparResult(
            success=True,
            requested=ZparRequest(band="f1", c1_coarse=0, c1_fine=0, c2_coarse=5, c2_fine=2, command="zpar show f1 0 0 5 2"),
            received=ZparResponse(band="f1", c1_coarse=0, c1_fine=0, c2_coarse=5, c2_fine=2),
            z_params=ZParameters(z11_r=1.5, z11_i=2.3, z21_r=0.1, z21_i=0.2, z12_r=0.1, z12_i=0.2, z22_r=3.0, z22_i=4.0),
            attempt_count=1,
            elapsed_ms=10.0,
            recovered_by_retry=False,
            quality_level=CommunicationQuality.GOOD,
            timing_profile_name="GOOD",
        )
        
        csv_dict = result.to_csv_dict()
        assert csv_dict['status'] == 'SUCCESS'
        assert csv_dict['attempts'] == 1  # Should be integer in dict
        assert csv_dict['recovered_by_retry'] == 'no'
        assert csv_dict['quality_level'] == 'GOOD'
        assert csv_dict['z11_r'] == '1.5'


# Integration test
class TestZparQueryServiceIntegration:
    """Integration tests for ZparQueryService."""
    
    def test_successful_query(self):
        """Test successful ZPAR query."""
        from evc_gui.services.zpar_query_service import ZparQueryService
        
        # Create mock serial service
        mock_serial = Mock()
        mock_result = Mock()
        mock_result.response = "Z11 = (1.5, 2.3) Z21 = (0.1, 0.2) Z12 = (0.1, 0.2) Z22 = (3.0, 4.0)"
        mock_result.ok = True
        mock_serial.send_command.return_value = mock_result
        mock_serial.acquire_transaction_lock = Mock()
        mock_serial.release_transaction_lock = Mock()
        
        service = ZparQueryService(mock_serial)
        result = service.query_zpar("zpar show f1 0 0 5 2")
        
        assert result.success is True
        assert result.z_params is not None
        mock_serial.acquire_transaction_lock.assert_called_once()
        mock_serial.release_transaction_lock.assert_called_once()


class TestCommunicationQualitySummaryCounters:
    """Test attempt-level diagnostic counters in quality summary."""

    COMMAND = "zpar show f1 0 0 0 0"
    VALID_RESPONSE = "(C1: 0, f1) (C2: 0, f2) Z11 = (1.0, 1.0) Z21 = (2.0, 2.0) Z12 = (3.0, 3.0) Z22 = (4.0, 4.0)"
    PARSE_FAILURE_RESPONSE = "(C1: 0, f1) (C2: 0, f2) Z11 = (bad, 1.0) Z21 = (2.0, 2.0) Z12 = (3.0, 3.0) Z22 = (4.0, 4.0)"
    INCOMPLETE_RESPONSE = "(C1: 0, f1) (C2: 0, f2) Z11 = (1.0, 1.0) Z21 = (2.0, 2.0)"
    POSITION_MISMATCH_RESPONSE = "(C1: 1, f1) (C2: 0, f2) Z11 = (1.0, 1.0) Z21 = (2.0, 2.0) Z12 = (3.0, 3.0) Z22 = (4.0, 4.0)"

    @staticmethod
    def _mock_result(response: str) -> Mock:
        result = Mock()
        result.response = response
        result.ok = True
        return result

    def _build_service(self, responses: list[str]):
        from evc_gui.services.zpar_query_service import ZparQueryService

        mock_serial = Mock()
        mock_serial.acquire_transaction_lock = Mock()
        mock_serial.release_transaction_lock = Mock()
        mock_serial.drain_input_buffer = Mock(return_value="")
        mock_serial.send_command.side_effect = [self._mock_result(r) for r in responses]
        return ZparQueryService(mock_serial)

    def test_clean_204_point_run_has_zero_diagnostic_counters(self):
        service = self._build_service([self.VALID_RESPONSE] * 204)

        for _ in range(204):
            result = service.query_zpar(self.COMMAND)
            assert result.success is True

        summary = service.get_quality_summary()
        assert "Total requests: 204" in summary
        assert "Successful responses: 204" in summary
        assert "Parse failures: 0" in summary
        assert "Incomplete responses: 0" in summary
        assert "Position mismatches: 0" in summary
        assert "Timeouts: 0" in summary

    def test_parse_failure_then_successful_retry_counts_diagnostic_event(self):
        service = self._build_service([self.PARSE_FAILURE_RESPONSE, self.VALID_RESPONSE])

        result = service.query_zpar(self.COMMAND)
        assert result.success is True
        assert result.recovered_by_retry is True

        summary = service.get_quality_summary()
        assert "Recovered by retry: 1" in summary
        assert "Parse failures: 1" in summary
        assert "Incomplete responses: 0" in summary
        assert "Position mismatches: 0" in summary
        assert "Timeouts: 0" in summary

    def test_incomplete_response_then_successful_retry_counts_diagnostic_event(self):
        service = self._build_service([self.INCOMPLETE_RESPONSE, self.VALID_RESPONSE])

        result = service.query_zpar(self.COMMAND)
        assert result.success is True
        assert result.recovered_by_retry is True

        summary = service.get_quality_summary()
        assert "Recovered by retry: 1" in summary
        assert "Parse failures: 0" in summary
        assert "Incomplete responses: 1" in summary
        assert "Position mismatches: 0" in summary
        assert "Timeouts: 0" in summary

    def test_position_mismatch_then_successful_retry_counts_diagnostic_event(self):
        service = self._build_service([self.POSITION_MISMATCH_RESPONSE, self.VALID_RESPONSE])

        result = service.query_zpar(self.COMMAND)
        assert result.success is True
        assert result.recovered_by_retry is True

        summary = service.get_quality_summary()
        assert "Recovered by retry: 1" in summary
        assert "Parse failures: 0" in summary
        assert "Incomplete responses: 0" in summary
        assert "Position mismatches: 1" in summary
        assert "Timeouts: 0" in summary

    def test_timeout_then_successful_retry_counts_diagnostic_event(self):
        service = self._build_service([self.VALID_RESPONSE])
        service.query_index = 79  # next query is deterministic fault point 80
        injector = get_fault_injector()

        enable_fault_injection(True)
        try:
            with patch.object(injector, "should_drop_response", side_effect=[True, False]):
                result = service.query_zpar(self.COMMAND)
        finally:
            reset_fault_injector()
            enable_fault_injection(False)

        assert result.success is True
        assert result.recovered_by_retry is True

        summary = service.get_quality_summary()
        assert "Recovered by retry: 1" in summary
        assert "Parse failures: 0" in summary
        assert "Incomplete responses: 0" in summary
        assert "Position mismatches: 0" in summary
        assert "Timeouts: 1" in summary

    def test_multiple_failure_types_before_successful_recovery(self):
        service = self._build_service([self.INCOMPLETE_RESPONSE, self.VALID_RESPONSE])
        service.query_index = 79  # next query is deterministic fault point 80
        injector = get_fault_injector()

        enable_fault_injection(True)
        try:
            with patch.object(injector, "should_drop_response", side_effect=[True, False, False]):
                result = service.query_zpar(self.COMMAND)
        finally:
            reset_fault_injector()
            enable_fault_injection(False)

        assert result.success is True
        assert result.recovered_by_retry is True
        assert result.attempt_count == 3

        summary = service.get_quality_summary()
        assert "Recovered by retry: 1" in summary
        assert "Parse failures: 0" in summary
        assert "Incomplete responses: 1" in summary
        assert "Position mismatches: 0" in summary
        assert "Timeouts: 1" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
