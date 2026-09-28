"""COM port scanner that detects EVC devices on available ports."""

import logging
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from evc_gui.services.serial_service import SerialService

log = logging.getLogger(__name__)

@dataclass(frozen=True)
class DetectedDevice:
    """Represents a detected EVC device on a specific port."""
    port: str
    baudrate: int
    product: str
    serial_number: str
    firmware: str

class PortScanner:
    """Scans available COM ports to detect EVC devices."""
    
    # Baud rates to try (ordered by priority - fast rates first, then slower)
    BAUD_CANDIDATES = (57600, 230400, 115200, 38400, 19200, 9600)
    SCAN_TIMEOUT = 0.5
    MAX_WORKERS = 8
    
    def __init__(self):
        self.serial = SerialService()
    
    def scan_ports(self) -> list[DetectedDevice]:
        """
        Scan all available ports and return list of detected devices.
        Uses parallel scanning across ports, but sequential baud rate attempts per port
        to avoid race conditions.
        """
        ports = self.serial.ports()
        if not ports:
            log.info("No COM ports available")
            return []
        
        detected_devices = []
        log.info("Scanning %d port(s) for EVC devices", len(ports))
        
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # Submit one task per port (not per baud rate)
            # This prevents race conditions on the same port
            futures = {}
            for port in ports:
                future = executor.submit(self._probe_port_all_bauds, port)
                futures[future] = port
            
            # Collect results as they complete
            for future in as_completed(futures):
                port = futures[future]
                try:
                    device = future.result()
                    if device:
                        detected_devices.append(device)
                        log.info("Detected device on %s@%d: %s (SN:%s)",
                                 device.port, device.baudrate, device.product, device.serial_number)
                except Exception as exc:
                    log.debug("Error scanning %s: %s", port, exc)
        
        # Sort by port name for consistent display
        detected_devices.sort(key=lambda d: (d.port, d.baudrate))
        log.info("Scan complete: found %d device(s)", len(detected_devices))
        return detected_devices
    
    def _probe_port_all_bauds(self, port: str) -> Optional[DetectedDevice]:
        """
        Try to detect a device on a given port by trying all baud rates sequentially.
        Returns the detected device, or None if not found.
        """
        for baudrate in self.BAUD_CANDIDATES:
            device = self._probe_port(port, baudrate)
            if device:
                return device
        return None
    
    def _probe_port(self, port: str, baudrate: int) -> Optional[DetectedDevice]:
        """
        Probe a single port at a specific baud rate.
        Returns DetectedDevice if successful, None otherwise.
        Includes retry logic for handling port contention.
        """
        service = SerialService()  # Use local instance for thread safety
        
        # Try to connect with retry logic for handling port contention
        max_retries = 2
        for attempt in range(max_retries):
            result = service.connect(port, baudrate, timeout=self.SCAN_TIMEOUT)
            if result.ok:
                break
            # If failed, wait briefly before retrying to avoid port contention
            if attempt < max_retries - 1:
                time.sleep(0.05)
        
        if not result.ok:
            return None
        
        try:
            # Query version info
            ver_result = service.send_command("ver", timeout=self.SCAN_TIMEOUT)
            if not ver_result.ok:
                return None
            
            # Validate response format
            if not self._is_valid_ver_response(ver_result.response):
                return None
            
            # Extract product type
            product = self._extract_product_type(ver_result.response)
            firmware = self._extract_firmware(ver_result.response)
            
            if not product:
                return None
            
            # Query serial number
            sn_result = service.send_command("sn", timeout=self.SCAN_TIMEOUT)
            if not sn_result.ok:
                return None
            
            serial_number = self._extract_unit_serial(sn_result.response)
            if not serial_number:
                return None
            
            # Resolve product name (for Chronos variants)
            resolved_product = self._resolve_product_name(product, serial_number)
            
            return DetectedDevice(
                port=port,
                baudrate=baudrate,
                product=resolved_product,
                serial_number=serial_number,
                firmware=firmware
            )
        finally:
            service.disconnect()
    
    @staticmethod
    def _is_valid_ver_response(response: str) -> bool:
        """Validate that the response looks like a ver command response."""
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        if not lines:
            return False
        if any("�" in line for line in lines):
            return False
        # Look for 'ver' command echo or version info
        has_ver_echo = any(line.lower() == "ver" for line in lines)
        has_version_info = any(
            "evc" in line.lower() and "version" in line.lower()
            for line in lines
        )
        return has_ver_echo or has_version_info or any("EVC" in line for line in lines)
    
    @staticmethod
    def _extract_product_type(response: str) -> str:
        """Extract product type from ver response (e.g., 'Tykon', 'Quantum', etc)."""
        import re
        for line in response.splitlines():
            match = re.search(r"^EVC\s+([A-Za-z0-9_-]+)\b", line.strip())
            if match:
                return match.group(1)
        return ""
    
    @staticmethod
    def _extract_unit_serial(response: str) -> str:
        """Extract unit serial number from sn response."""
        import re
        for line in response.splitlines():
            match = re.search(r"Unit\s+S/N:\s*(\S+)", line.strip())
            if match:
                return match.group(1)
        return ""
    
    @staticmethod
    def _extract_firmware(response: str) -> str:
        """Extract firmware version from ver response."""
        import re
        for line in response.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "version" in stripped.lower() or "fw" in stripped.lower():
                return stripped
        return ""
    
    @staticmethod
    def _resolve_product_name(product: str, serial_number: str) -> str:
        """Resolve Chronos variants based on serial number."""
        if product.strip().lower() != "chronos":
            return product
        
        prefix = PortScanner._serial_prefix(serial_number)
        if prefix is None:
            return "Chronos"
        if 191 <= prefix <= 195:
            return "Chronos 1"
        if prefix >= 196:
            return "Chronos 2.0"
        return "Chronos"
    
    @staticmethod
    def _serial_prefix(serial_number: str) -> Optional[int]:
        """Extract numeric prefix from serial number."""
        serial_digits = "".join(ch for ch in serial_number if ch.isdigit())
        if len(serial_digits) < 3:
            return None
        try:
            return int(serial_digits[:3])
        except ValueError:
            return None
