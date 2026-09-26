import logging
from dataclasses import dataclass
import serial
from serial.tools import list_ports

log = logging.getLogger(__name__)

@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    message: str

class SerialService:
    def __init__(self):
        self._serial = None

    @staticmethod
    def ports() -> list[str]:
        return [p.device for p in list_ports.comports()]

    @property
    def connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def connect(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> ConnectionResult:
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

    def disconnect(self):
        if self._serial:
            try:
                if self._serial.is_open:
                    self._serial.close()
                    log.info("Serial disconnected")
            finally:
                self._serial = None
