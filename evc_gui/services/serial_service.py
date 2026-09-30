import logging
import threading
from dataclasses import dataclass
from typing import Callable
import time
import serial
from serial.tools import list_ports

log = logging.getLogger(__name__)

@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    message: str

@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str
    response: str

class SerialService:
    def __init__(self):
        self._serial = None

    @staticmethod
    def ports() -> list[str]:
        """Get list of available COM ports, excluding Intel AMT and other non-device ports."""
        return [
            p.device for p in list_ports.comports()
            if p.device and not SerialService._should_skip_port(p)
        ]
    
    @staticmethod
    def _should_skip_port(port_info) -> bool:
        """Check if a port should be skipped during scanning."""
        description = port_info.description.lower() if port_info.description else ""
        # Skip Intel Management and other non-device ports
        skip_patterns = ["intel", "amt", "management technology"]
        return any(pattern in description for pattern in skip_patterns)

    @property
    def connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def connect(self, port: str, baudrate: int = 57600, timeout: float = 1.0) -> ConnectionResult:
        self.disconnect()
        try:
            self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout, write_timeout=timeout)
            log.info("Serial connected: port=%s baud=%s", port, baudrate)
            return ConnectionResult(True, f"Connected to {port} at {baudrate} baud")
        except Exception as exc:
            log.exception("Serial connection failed")
            self._serial = None
            return ConnectionResult(False, f"Connection failed: {exc}")

    def probe(self, command: bytes = b"\r\n") -> ConnectionResult:
        if not self.connected:
            return ConnectionResult(False, "Serial port is not connected")
        try:
            self._serial.reset_input_buffer()
            self._serial.write(command)
            self._serial.flush()
            reply = self._serial.readline().decode(errors="replace").strip()
            msg = f"Reply: {reply}" if reply else "Port opened and probe sent; no reply received"
            log.info(msg)
            return ConnectionResult(True, msg)
        except Exception as exc:
            log.exception("Serial probe failed")
            return ConnectionResult(False, f"Probe failed: {exc}")

    def send_command(
        self,
        command: str,
        timeout: float = 1.0,
        cancel_event: threading.Event | None = None,
        end_markers: tuple[str, ...] = (),
        line_callback: Callable[[str], None] | None = None,
        read_timeout: float | None = None,
        payload_quiet_period_s: float | None = None,
        line_ending: str = "\r\n",
    ) -> CommandResult:
        if not self.connected:
            return CommandResult(False, "Serial port is not connected", "")
        command = command.strip()
        if not command:
            return CommandResult(False, "Command is empty", "")
        old_timeout = self._serial.timeout
        deadline = time.monotonic() + timeout
        lines: list[str] = []
        seen_payload = False
        last_payload_at: float | None = None
        try:
            self._serial.reset_input_buffer()
            self._serial.write(f"{command}{line_ending}".encode("ascii", errors="ignore"))
            self._serial.flush()
            if read_timeout is None:
                self._serial.timeout = min(0.1, max(0.01, timeout / 2))
            else:
                self._serial.timeout = max(0.005, min(float(read_timeout), timeout))
            while time.monotonic() < deadline:
                if cancel_event is not None and cancel_event.is_set():
                    return CommandResult(False, f"Command '{command}' cancelled", "\n".join(lines))
                raw = self._serial.readline()
                if not raw:
                    if (
                        seen_payload
                        and payload_quiet_period_s is not None
                        and last_payload_at is not None
                        and (time.monotonic() - last_payload_at) >= payload_quiet_period_s
                    ):
                        break
                    continue
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                prompt_only = line.endswith(">") and " " not in line
                # Ignore leading prompt-only lines; wait until command output starts.
                if prompt_only and not seen_payload:
                    continue
                lines.append(line)
                if line_callback is not None:
                    line_callback(line)
                if end_markers and any(marker.lower() in line.lower() for marker in end_markers):
                    response = "\n".join(lines)
                    msg = f"Command '{command}' response received (end marker)"
                    log.info(msg)
                    return CommandResult(True, msg, response)
                if prompt_only:
                    break
                if line.lower() != command.lower():
                    seen_payload = True
                    last_payload_at = time.monotonic()
            response = "\n".join(lines)
            if not lines:
                return CommandResult(False, f"No response for '{command}'", "")
            msg = f"Command '{command}' response received"
            log.info(msg)
            return CommandResult(True, msg, response)
        except Exception as exc:
            log.exception("Serial command failed: %s", command)
            return CommandResult(False, f"Command '{command}' failed: {exc}", "")
        finally:
            self._serial.timeout = old_timeout

    def disconnect(self):
        if self._serial:
            try:
                if self._serial.is_open:
                    self._serial.close()
                    log.info("Serial disconnected")
            finally:
                self._serial = None
