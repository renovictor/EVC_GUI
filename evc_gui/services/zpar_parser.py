"""
ZPAR response parsing and identity validation.

Validates that responses belong to the requested command by parsing
capacitor position metadata from EVC ZPAR responses.
"""

from __future__ import annotations
import re
import logging
import math
from typing import Optional
from evc_gui.ui.smith_chart import ZParameters
from evc_gui.services.zpar_result import ZparResponse

log = logging.getLogger(__name__)

# Regular expression to parse number formats: integers, decimals, scientific notation
NUMBER_PATTERN = r"([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)"


def parse_zpar_response(response: str) -> Optional[ZParameters]:
    """
    Parse ZPAR response to extract Z-parameters only (compatibility layer).
    Does not validate identity or capacitor position.
    
    Response format:
    (C1: x, f1) (C2: x, f2)   Z11 = (r, i)  Z21 = (r, i)  Z12 = (r, i)  Z22 = (r, i)
    """
    text = response.replace("\r", "\n")
    
    def parse_pair(label: str) -> tuple[float, float] | None:
        # Try tuple format first: Z11 = (1.5, 2.3) or Z11: (1.5, 2.3)
        tuple_match = re.search(
            rf"{label}\s*[:=]\s*\(\s*{NUMBER_PATTERN}\s*,\s*{NUMBER_PATTERN}\s*\)",
            text,
            re.IGNORECASE,
        )
        if tuple_match:
            return float(tuple_match.group(1)), float(tuple_match.group(2))
        
        # Try j-notation: Z11 = 1.5 + j 2.3 or Z11 = 1.5 - j 2.3
        j_match = re.search(
            rf"{label}\s*[:=]\s*{NUMBER_PATTERN}\s*([+-])\s*j\s*{NUMBER_PATTERN}",
            text,
            re.IGNORECASE,
        )
        if j_match:
            real = float(j_match.group(1))
            imag = float(j_match.group(3))
            if j_match.group(2) == "-":
                imag = -imag
            return real, imag
        
        return None
    
    try:
        z11 = parse_pair("Z11")
        z21 = parse_pair("Z21")
        z12 = parse_pair("Z12")
        z22 = parse_pair("Z22")
        
        if all([z11, z21, z12, z22]):
            # Validate that all values are finite
            all_values = [z11[0], z11[1], z21[0], z21[1], z12[0], z12[1], z22[0], z22[1]]
            if all(math.isfinite(v) for v in all_values):
                return ZParameters(
                    z11_r=z11[0],
                    z11_i=z11[1],
                    z21_r=z21[0],
                    z21_i=z21[1],
                    z12_r=z12[0],
                    z12_i=z12[1],
                    z22_r=z22[0],
                    z22_i=z22[1],
                )
    except (ValueError, AttributeError, TypeError):
        pass
    
    return None


def parse_and_validate_zpar_response(response: str, requested_band: str) -> Optional[ZparResponse]:
    """
    Parse ZPAR response and extract identity metadata.
    
    Attempts to extract:
    - Band information (if provided by firmware)
    - C1 and C2 capacitor positions
    - Z-parameters
    
    Returns ZparResponse with all available fields, or None if response is unusable.
    """
    if not response or not response.strip():
        return None
    
    text = response.replace("\r", "\n")
    
    # Parse Z-parameters
    z_params = parse_zpar_response(text)
    if not z_params:
        return None
    
    # Try to extract capacitor position metadata
    # Look for patterns like "(C1: 0, f1)" or "C1 coarse=0 fine=0"
    c1_coarse = None
    c1_fine = None
    c2_coarse = None
    c2_fine = None
    band = None
    
    # Try pattern: (C1: 0, f1) (C2: 5, f2)
    cap_pattern = r"\(C1:\s*(\d+)\s*,\s*f1\)\s*\(C2:\s*(\d+)\s*,\s*f2\)"
    cap_match = re.search(cap_pattern, text, re.IGNORECASE)
    if cap_match:
        c1_coarse = int(cap_match.group(1))
        c2_coarse = int(cap_match.group(2))
        c1_fine = 0  # f1 typically means fine=0 in shorthand
        c2_fine = 0  # f2 typically means fine=0 in shorthand
    
    # Try pattern: C1 coarse=0 fine=0 C2 coarse=5 fine=2
    detailed_pattern = r"C1\s+coarse=(\d+)\s+fine=(\d+)\s+C2\s+coarse=(\d+)\s+fine=(\d+)"
    detailed_match = re.search(detailed_pattern, text, re.IGNORECASE)
    if detailed_match:
        c1_coarse = int(detailed_match.group(1))
        c1_fine = int(detailed_match.group(2))
        c2_coarse = int(detailed_match.group(3))
        c2_fine = int(detailed_match.group(4))
    
    # Try to extract band information if provided
    band_pattern = r"band\s*[:=]\s*(f1|hf|lf)"
    band_match = re.search(band_pattern, text, re.IGNORECASE)
    if band_match:
        band = band_match.group(1).lower()
    
    return ZparResponse(
        band=band,
        c1_coarse=c1_coarse,
        c1_fine=c1_fine,
        c2_coarse=c2_coarse,
        c2_fine=c2_fine,
        z_params=z_params,
        raw_response=text,
    )


def is_response_complete(response: str) -> bool:
    """
    Check if response appears to be complete (contains all expected Z-parameters).
    """
    if not response:
        return False
    
    text = response.replace("\r", "\n").lower()
    
    # Check for error responses
    if any(phrase in text for phrase in ["invalid command", "error", "password"]):
        return False
    
    # Check for required Z-parameters
    required = ["z11", "z21", "z12", "z22"]
    return all(param in text for param in required)


def is_response_corrupted(response: str) -> bool:
    """
    Check if response contains corruption indicators.
    """
    if not response:
        return False
    
    text = response
    
    # Check for unusual replacement characters that indicate corruption
    if "\ufffd" in text:  # Unicode replacement character
        return True
    
    # Check for excessively malformed lines
    lines = text.split("\n")
    malformed_lines = sum(1 for line in lines if not any(c.isalnum() for c in line) and len(line) > 50)
    if malformed_lines > len(lines) // 2:
        return True
    
    return False


def is_error_response(response: str) -> bool:
    """
    Check if response is an error or invalid command response.
    """
    if not response:
        return False
    
    text = response.lower()
    
    error_indicators = [
        "invalid command",
        "error:",
        "error ",
        "bad command",
        "unknown command",
        "password",
    ]
    
    return any(indicator in text for indicator in error_indicators)
