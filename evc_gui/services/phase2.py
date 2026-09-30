from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import csv
import logging
import math
import queue
import re
import threading
from collections import deque

from PySide6.QtCore import QObject, QThread, Signal

from evc_gui.services.serial_service import SerialService

log = logging.getLogger(__name__)

PDAT1_RAW_HEADERS = ["Fx", "Pfwd", "Pref", "LoadR", "Load X", "Inp R", "Inp X", "C1 %", "C2 %"]
PSUM1_LEFT_RAW_HEADERS = [
    "V_Tune",
    "V_NG",
    "I_Tune",
    "P_Tune",
    "Rs",
    "Xs",
    "Rl",
    "Xl",
    "C1c",
    "C1f",
    "C2c",
    "C2f",
    "C1%",
    "C2%",
    "Vpp_Tune",
    "Vpp_NG",
    "Vcap",
    "VBias",
    "IBias",
    "Iout",
    "PhOut",
    "Pout",
    "Eff%",
]
PSUM1_RIGHT_RAW_HEADERS = ["HVDC", "DcBias", "DcBias_RNG", "Amb.Temp", "PA.Temp"]
LOG_ROTATION_INTERVAL = timedelta(hours=3)


@dataclass(frozen=True)
class EvcSample:
    timestamp: datetime
    pfwd: float
    pref: float
    c1: float
    c2: float
    vpp: float
    dc_bias: float
    pout: float
    iout: float
    rs: float | None = None
    xs: float | None = None
    lf_rs: float | None = None
    lf_xs: float | None = None
    lf_pfwd: float | None = None
    lf_pref: float | None = None
    lf_c1: float | None = None
    lf_c2: float | None = None
    lf_vpp: float | None = None
    lf_dc_bias: float | None = None
    lf_pout: float | None = None
    lf_iout: float | None = None


def _to_float(text: str) -> float:
    return float(text.replace("%", ""))


def parse_pdat1_line(line: str) -> dict[str, float]:
    if "HF:" in line and "LF:" in line:
        hf_tokens, lf_tokens = _split_quantum_hf_lf_tokens(line)
        if len(hf_tokens) < 8 or len(lf_tokens) < 8:
            raise ValueError(f"Invalid Quantum pdat1 payload: {line}")
        return {
            "pfwd": _to_float(hf_tokens[0]),
            "pref": _to_float(hf_tokens[1]),
            "load_r": _to_float(hf_tokens[4]),
            "load_x": _to_float(hf_tokens[5]),
            "c1": _to_float(hf_tokens[6]),
            "c2": _to_float(hf_tokens[7]),
            "lf_pfwd": _to_float(lf_tokens[0]),
            "lf_pref": _to_float(lf_tokens[1]),
            "lf_c1": _to_float(lf_tokens[6]),
            "lf_c2": _to_float(lf_tokens[7]),
            "lf_load_r": _to_float(lf_tokens[4]),
            "lf_load_x": _to_float(lf_tokens[5]),
        }
    payload = line.split(":", 1)[1] if ":" in line else line
    values = re.findall(r"[-+]?\d+(?:\.\d+)?", payload)
    if len(values) < 8:
        raise ValueError(f"Invalid pdat1 payload: {line}")
    return {
        "pfwd": _to_float(values[0]),
        "pref": _to_float(values[1]),
        "load_r": _to_float(values[4]),
        "load_x": _to_float(values[5]),
        "c1": _to_float(values[6]),
        "c2": _to_float(values[7]),
    }


def parse_psum1_line(line: str) -> dict[str, float]:
    if "HF:" in line and "LF:" in line and "|" in line:
        hf_tokens, lf_tokens = _split_quantum_hf_lf_tokens(line)
        right_tokens = line.split("|", 1)[1].split()
        if len(hf_tokens) < 23 or len(lf_tokens) < 23 or len(right_tokens) < 2:
            raise ValueError(f"Incomplete Quantum psum1 payload: {line}")
        return {
            "rs": _to_float(hf_tokens[4]),
            "xs": _to_float(hf_tokens[5]),
            "vpp": _to_float(hf_tokens[14]),
            "iout": _to_float(hf_tokens[19]),
            "pout": _to_float(hf_tokens[21]),
            "dc_bias": _to_float(right_tokens[1]),
            "lf_rs": _to_float(lf_tokens[4]),
            "lf_xs": _to_float(lf_tokens[5]),
            "lf_vpp": _to_float(lf_tokens[14]),
            "lf_iout": _to_float(lf_tokens[19]),
            "lf_pout": _to_float(lf_tokens[21]),
            "lf_dc_bias": _to_float(right_tokens[1]),
        }
    if "|" in line:
        left, right = line.split("|", 1)
        left_tokens = left.split()
        right_tokens = right.split()
        if len(left_tokens) < 23 or len(right_tokens) < 2:
            raise ValueError(f"Incomplete psum1 payload: {line}")
        return {
            "rs": _to_float(left_tokens[4]),
            "xs": _to_float(left_tokens[5]),
            "vpp": _to_float(left_tokens[14]),
            "iout": _to_float(left_tokens[19]),
            "pout": _to_float(left_tokens[21]),
            "dc_bias": _to_float(right_tokens[1]),
        }

    # Chronos format (no "|"): V I P Rs Xs Rl Xl C1c C1f C2c C2f C1% C2% Vpp Vcap DcBias Iout PhOut HVDC Temp Pout Eff%
    tokens = line.split()
    if len(tokens) < 21:
        raise ValueError(f"Incomplete psum1 payload: {line}")
    return {
        "rs": _to_float(tokens[3]),
        "xs": _to_float(tokens[4]),
        "vpp": _to_float(tokens[13]),
        "dc_bias": _to_float(tokens[15]),
        "iout": _to_float(tokens[16]),
        "pout": _to_float(tokens[20]),
    }


def _map_raw_tokens(headers: list[str], tokens: list[str]) -> dict[str, str]:
    return {header: tokens[index] if index < len(tokens) else "" for index, header in enumerate(headers)}


def parse_pdat1_raw_columns(line: str) -> dict[str, str]:
    if "HF:" in line and "LF:" in line:
        hf_tokens, _ = _split_quantum_hf_lf_tokens(line)
        if len(hf_tokens) < 8:
            log.warning("Incomplete Quantum pdat1 raw payload: %s", line)
        return {"Fx": "HF"} | _map_raw_tokens(PDAT1_RAW_HEADERS[1:], hf_tokens)
    fx = ""
    payload = line
    if ":" in line:
        left, payload = line.split(":", 1)
        fx_tokens = left.split()
        if fx_tokens:
            fx = fx_tokens[-1]
    elif re.match(r"^\s*F\d+\b", line):
        parts = line.split(maxsplit=1)
        if parts:
            fx = parts[0]
            payload = parts[1] if len(parts) > 1 else ""
    values = re.findall(r"[-+]?\d+(?:\.\d+)?", payload)
    if len(values) < 8:
        log.warning("Incomplete pdat1 raw payload: %s", line)
    return {"Fx": fx} | _map_raw_tokens(PDAT1_RAW_HEADERS[1:], values)


def parse_psum1_raw_columns(line: str) -> dict[str, str]:
    if "HF:" in line and "LF:" in line and "|" in line:
        hf_tokens, _ = _split_quantum_hf_lf_tokens(line)
        right_tokens = line.split("|", 1)[1].split()
        if len(hf_tokens) < len(PSUM1_LEFT_RAW_HEADERS) or len(right_tokens) < len(PSUM1_RIGHT_RAW_HEADERS[:2]):
            log.warning("Incomplete Quantum psum1 raw payload: %s", line)
        return _map_raw_tokens(PSUM1_LEFT_RAW_HEADERS, hf_tokens) | _map_raw_tokens(PSUM1_RIGHT_RAW_HEADERS, right_tokens)
    if "|" in line:
        left, right = line.split("|", 1)
        left_tokens = left.split()
        right_tokens = right.split()
        if len(left_tokens) < len(PSUM1_LEFT_RAW_HEADERS) or len(right_tokens) < len(PSUM1_RIGHT_RAW_HEADERS):
            log.warning("Incomplete psum1 raw payload: %s", line)
        return _map_raw_tokens(PSUM1_LEFT_RAW_HEADERS, left_tokens) | _map_raw_tokens(PSUM1_RIGHT_RAW_HEADERS, right_tokens)

    # Chronos format (no "|"): keep shared fields in left columns and map HVDC/DcBias/Temp into right columns.
    tokens = line.split()
    row = {header: "" for header in (*PSUM1_LEFT_RAW_HEADERS, *PSUM1_RIGHT_RAW_HEADERS)}
    if len(tokens) < 21:
        log.warning("Incomplete psum1 raw payload: %s", line)
    row["V_Tune"] = tokens[0] if len(tokens) > 0 else ""
    row["V_NG"] = tokens[1] if len(tokens) > 1 else ""
    row["I_Tune"] = tokens[2] if len(tokens) > 2 else ""
    row["Rs"] = tokens[3] if len(tokens) > 3 else ""
    row["Xs"] = tokens[4] if len(tokens) > 4 else ""
    row["Rl"] = tokens[5] if len(tokens) > 5 else ""
    row["Xl"] = tokens[6] if len(tokens) > 6 else ""
    row["C1c"] = tokens[7] if len(tokens) > 7 else ""
    row["C1f"] = tokens[8] if len(tokens) > 8 else ""
    row["C2c"] = tokens[9] if len(tokens) > 9 else ""
    row["C2f"] = tokens[10] if len(tokens) > 10 else ""
    row["C1%"] = tokens[11] if len(tokens) > 11 else ""
    row["C2%"] = tokens[12] if len(tokens) > 12 else ""
    row["Vpp_Tune"] = tokens[13] if len(tokens) > 13 else ""
    row["Vcap"] = tokens[14] if len(tokens) > 14 else ""
    row["DcBias"] = tokens[15] if len(tokens) > 15 else ""
    row["Iout"] = tokens[16] if len(tokens) > 16 else ""
    row["PhOut"] = tokens[17] if len(tokens) > 17 else ""
    row["HVDC"] = tokens[18] if len(tokens) > 18 else ""
    row["Amb.Temp"] = tokens[19] if len(tokens) > 19 else ""
    row["Pout"] = tokens[20] if len(tokens) > 20 else ""
    row["Eff%"] = tokens[21] if len(tokens) > 21 else ""
    return row


def _split_quantum_hf_lf_tokens(line: str) -> tuple[list[str], list[str]]:
    left = line.split("|", 1)[0]
    if "HF:" not in left or "LF:" not in left:
        return [], []
    hf_part = left.split("HF:", 1)[1].split("LF:", 1)[0].strip()
    lf_part = left.split("LF:", 1)[1].strip()
    return hf_part.split(), lf_part.split()


class SerialWorker(QThread):
    sample_ready = Signal(object, str, str)
    worker_error = Signal(str)

    def __init__(
        self,
        serial: SerialService,
        poll_interval_ms: int = 120,
        command_timeout: float = 0.8,
        demo_mode: bool = False,
    ):
        super().__init__()
        self._serial = serial
        self._poll_interval_ms = max(20, poll_interval_ms)
        self._command_timeout = command_timeout
        self._demo_mode = demo_mode
        self._running = threading.Event()
        self._demo_tick = 0

    def start_polling(self):
        self._running.set()
        self.start()

    def stop_polling(self):
        self._running.clear()
        self.wait(3000)

    def run(self):
        while self._running.is_set():
            if self._demo_mode:
                sample, pdat_line, psum_line = self._build_demo_sample()
                self.sample_ready.emit(sample, pdat_line, psum_line)
                self.msleep(self._poll_interval_ms)
                continue
            if not self._serial.connected:
                self.worker_error.emit("Serial disconnected during RUN state")
                return
            pdat = self._serial.send_command("pdat1", timeout=self._command_timeout)
            if not pdat.ok:
                self.worker_error.emit(pdat.message)
                self.msleep(self._poll_interval_ms)
                continue
            psum = self._serial.send_command("psum1", timeout=self._command_timeout)
            if not psum.ok:
                self.worker_error.emit(psum.message)
                self.msleep(self._poll_interval_ms)
                continue
            pdat_line = _extract_payload_line(pdat.response)
            psum_line = _extract_payload_line(psum.response)
            try:
                pdat_values = parse_pdat1_line(pdat_line)
                psum_values = parse_psum1_line(psum_line)
                sample = EvcSample(
                    timestamp=datetime.now(),
                    pfwd=pdat_values["pfwd"],
                    pref=pdat_values["pref"],
                    c1=pdat_values["c1"],
                    c2=pdat_values["c2"],
                    vpp=psum_values["vpp"],
                    dc_bias=psum_values["dc_bias"],
                    pout=psum_values["pout"],
                    iout=psum_values["iout"],
                    rs=pdat_values["load_r"],
                    xs=pdat_values["load_x"],
                    lf_rs=psum_values.get("lf_rs", pdat_values.get("lf_load_r")),
                    lf_xs=psum_values.get("lf_xs", pdat_values.get("lf_load_x")),
                    lf_pfwd=pdat_values.get("lf_pfwd"),
                    lf_pref=pdat_values.get("lf_pref"),
                    lf_c1=pdat_values.get("lf_c1"),
                    lf_c2=pdat_values.get("lf_c2"),
                    lf_vpp=psum_values.get("lf_vpp"),
                    lf_dc_bias=psum_values.get("lf_dc_bias"),
                    lf_pout=psum_values.get("lf_pout"),
                    lf_iout=psum_values.get("lf_iout"),
                )
            except Exception as exc:
                self.worker_error.emit(f"Phase 2 parse error: {exc}")
                self.msleep(self._poll_interval_ms)
                continue
            self.sample_ready.emit(sample, pdat_line, psum_line)
            self.msleep(self._poll_interval_ms)

    def _build_demo_sample(self) -> tuple[EvcSample, str, str]:
        elapsed_s = (self._demo_tick * self._poll_interval_ms) / 1000.0
        self._demo_tick += 1

        # Continuous waveforms keep demo logs non-zero and visibly dynamic from run start.
        pfwd = 420.0 + 260.0 * math.sin(elapsed_s * 0.9) + 90.0 * math.sin(elapsed_s * 0.21)
        pfwd = max(20.0, pfwd)
        pref = max(1.0, (pfwd * 0.07) + 9.0 * math.sin(elapsed_s * 1.4))
        c1 = max(0.0, min(100.0, 48.0 + 30.0 * math.sin(elapsed_s * 0.35)))
        c2 = max(0.0, min(100.0, 52.0 + 34.0 * math.cos(elapsed_s * 0.27)))
        vpp = max(80.0, 520.0 + 140.0 * math.sin(elapsed_s * 0.5))
        dc_bias = -58.0 + 18.0 * math.sin(elapsed_s * 0.31)
        pout = max(0.0, pfwd - pref)
        iout = (pout / vpp) if vpp > 0 else 0.0
        rs = 0.6 + 0.18 * math.sin(elapsed_s * 0.42)
        xs = 45.0 + 12.0 * math.cos(elapsed_s * 0.37)
        sample = EvcSample(
            timestamp=datetime.now(),
            pfwd=pfwd,
            pref=pref,
            c1=c1,
            c2=c2,
            vpp=vpp,
            dc_bias=dc_bias,
            pout=pout,
            iout=iout,
            rs=rs,
            xs=xs,
        )
        pdat_line = f"F1 : {pfwd:6.1f} {pref:5.1f} 0.10 -14.44 {rs:4.2f} {xs:5.2f} {c1:5.1f} {c2:5.1f}"
        psum_line = (
            f"0.00 0.00 0.00 89.38 {rs:4.2f} {xs:5.2f} 0.10 -14.44 6 63 6 63 "
            f"{c1:4.1f}% {c2:4.1f}% {vpp:6.3f} 0.000 0.00 -4.90 0.00 {iout:5.2f} 0.00 {pout:6.2f} 0.0% | "
            f"1200.00 {dc_bias:7.2f} HI -50.00 -50.00"
        )
        return sample, pdat_line, psum_line


def _extract_payload_line(response: str) -> str:
    candidates: list[str] = []
    for line in response.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(">") and " " not in stripped:
            continue
        if ">" in stripped:
            _, tail = stripped.rsplit(">", 1)
            stripped = tail.strip()
            if not stripped:
                continue
        lowered = stripped.lower()
        if lowered in {"pdat1", "psum1"}:
            continue
        candidates.append(stripped)
    if candidates:
        return candidates[-1]
    return ""


class CsvWriter:
    _STOP = object()

    def __init__(self, tmp_path: Path, final_path: Path, headers: list[str]):
        self._tmp_path = tmp_path
        self._final_path = final_path
        self._headers = headers
        self._queue: queue.Queue[object] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._started = False

    def start(self):
        if self._started:
            return
        self._tmp_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread.start()
        self._started = True

    def enqueue(self, row: dict[str, object]):
        if self._started:
            self._queue.put(row)

    def close(self):
        if not self._started:
            return
        self._queue.put(self._STOP)
        self._thread.join(timeout=2)
        self._tmp_path.replace(self._final_path)
        self._started = False

    def _loop(self):
        file_exists = self._tmp_path.exists()
        with self._tmp_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._headers)
            if not file_exists:
                writer.writeheader()
                f.flush()
            while True:
                item = self._queue.get()
                if item is self._STOP:
                    f.flush()
                    return
                writer.writerow(item)
                f.flush()


class DataController(QObject):
    sample_added = Signal(object)

    def __init__(
        self,
        logs_dir: Path,
        product: str,
        serial_number: str,
        firmware: str,
        max_samples: int = 7200,
    ):
        super().__init__()
        self._samples: deque[EvcSample] = deque(maxlen=max_samples)
        self._logs_dir = logs_dir
        self._safe_serial = re.sub(r"[^0-9A-Za-z_-]", "", serial_number) or "unknown"
        self._raw_writer: CsvWriter | None = None
        self._active_log_started_at: datetime | None = None
        self._meta = {
            "firmware": firmware or "",
        }
        self._open_writers(datetime.now())

    def _open_writers(self, started_at: datetime):
        date_code = started_at.strftime("%Y%m%d")
        time_code = started_at.strftime("%H%M")
        base_name = f"{self._safe_serial}Tykon_GUI_{date_code}_{time_code}"
        raw_base = f"{base_name}_raw.csv"
        self._raw_writer = CsvWriter(
            tmp_path=self._logs_dir / f"{raw_base}.tmp",
            final_path=self._logs_dir / raw_base,
            headers=[
                "timestamp",
                "firmware",
                *PDAT1_RAW_HEADERS,
                *PSUM1_LEFT_RAW_HEADERS,
                *PSUM1_RIGHT_RAW_HEADERS,
            ],
        )
        self._raw_writer.start()
        self._active_log_started_at = started_at

    def _rotate_writers_if_needed(self, current_time: datetime):
        if self._active_log_started_at is None:
            self._open_writers(current_time)
            return
        if current_time - self._active_log_started_at < LOG_ROTATION_INTERVAL:
            return
        if self._raw_writer is not None:
            self._raw_writer.close()
        self._open_writers(current_time)

    def append_sample(self, sample: EvcSample, raw_pdat1: str, raw_psum1: str):
        self._samples.append(sample)
        self._rotate_writers_if_needed(sample.timestamp)
        stamp = sample.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        raw_row = {
            "timestamp": stamp,
            "firmware": self._meta["firmware"],
        }
        raw_row.update(parse_pdat1_raw_columns(raw_pdat1))
        raw_row.update(parse_psum1_raw_columns(raw_psum1))
        if self._raw_writer is not None:
            self._raw_writer.enqueue(raw_row)
        self.sample_added.emit(sample)

    def window(self, seconds: int) -> list[EvcSample]:
        if not self._samples:
            return []
        end = self._samples[-1].timestamp
        start = end - timedelta(seconds=max(1, seconds))
        return [s for s in self._samples if s.timestamp >= start]

    def latest(self) -> EvcSample | None:
        return self._samples[-1] if self._samples else None

    def close(self):
        if self._raw_writer is not None:
            self._raw_writer.close()
