"""
PRAMAAN v1  --  Assurance Report Formatting & Sanitization.

Provides escaping, path censorship, palette definitions, and deterministic
disposition derivation for PDF assurance reports.
"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils
from typing import Any

from reportlab.lib import colors


# ---------------------------------------------------------------------------
# Color Palette (Slate / Modern Technical Theme)
# ---------------------------------------------------------------------------

COLOR_PRIMARY = colors.HexColor("#0f172a")       # Slate 900
COLOR_SECONDARY = colors.HexColor("#1e293b")     # Slate 800
COLOR_TEXT_MAIN = colors.HexColor("#334155")     # Slate 700
COLOR_TEXT_MUTED = colors.HexColor("#64748b")    # Slate 500
COLOR_BG_LIGHT = colors.HexColor("#f8fafc")      # Slate 50
COLOR_BG_ALT = colors.HexColor("#f1f5f9")        # Slate 100
COLOR_BORDER = colors.HexColor("#cbd5e1")        # Slate 300
COLOR_BORDER_LIGHT = colors.HexColor("#e2e8f0")  # Slate 200

# Semantic status colors
COLOR_PASS = colors.HexColor("#059669")          # Emerald 600
COLOR_WARN = colors.HexColor("#d97706")          # Amber 600
COLOR_DANGER = colors.HexColor("#e11d48")        # Rose 600
COLOR_CRITICAL = colors.HexColor("#9f1239")      # Rose 800
COLOR_INFO = colors.HexColor("#2563eb")          # Blue 600
COLOR_NEUTRAL = colors.HexColor("#64748b")       # Slate 500


def get_risk_color(risk: str) -> colors.HexColor:
    """Return badge color for risk level."""
    r = (risk or "").upper()
    if r in ("NONE", "CLEAN"):
        return COLOR_PASS
    if r == "LOW":
        return COLOR_INFO
    if r == "MEDIUM":
        return COLOR_WARN
    if r in ("HIGH", "CRITICAL"):
        return COLOR_DANGER
    return COLOR_NEUTRAL


def get_severity_color(sev: str) -> colors.HexColor:
    """Return badge color for severity."""
    s = (sev or "").upper()
    if s == "INFO":
        return COLOR_INFO
    if s == "LOW":
        return COLOR_PASS
    if s == "MEDIUM":
        return COLOR_WARN
    if s == "HIGH":
        return COLOR_DANGER
    if s == "CRITICAL":
        return COLOR_CRITICAL
    return COLOR_NEUTRAL


def get_status_color(status: str) -> colors.HexColor:
    """Return badge color for detector execution status."""
    st = (status or "").upper()
    if st in ("SUCCESS", "COMPLETE", "VERIFIED"):
        return COLOR_PASS
    if st in ("PARTIAL", "INVESTIGATE"):
        return COLOR_WARN
    if st in ("FAILED", "REJECT"):
        return COLOR_DANGER
    return COLOR_NEUTRAL


# ---------------------------------------------------------------------------
# Sanitization & Security Escaping
# ---------------------------------------------------------------------------

_PATH_PATTERN_WINDOWS = re.compile(r"[a-zA-Z]:\\[^\s\<\>\"\'\:]+", re.IGNORECASE)
_PATH_PATTERN_UNIX = re.compile(r"/(?:home|tmp|var|usr|Users)/[^\s\<\>\"\'\:]+", re.IGNORECASE)


def censor_paths(text: str) -> str:
    """
    Remove absolute local filesystem paths from text to avoid path leakage.
    Replaces absolute paths with their filename or generic indicator.
    """
    if not text:
        return ""

    def _replace_win(match: re.Match) -> str:
        p = match.group(0)
        return p.split("\\")[-1] or "local_file"

    def _replace_unix(match: re.Match) -> str:
        p = match.group(0)
        return p.split("/")[-1] or "local_file"

    t = _PATH_PATTERN_WINDOWS.sub(_replace_win, text)
    t = _PATH_PATTERN_UNIX.sub(_replace_unix, t)
    return t


def safe_escape(value: Any) -> str:
    """
    Safely stringify, censor paths, and escape text for ReportLab Paragraphs.
    Prevents XML/HTML injection and handles None gracefully.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        import json
        text = json.dumps(value)
    else:
        text = str(value)

    censored = censor_paths(text)
    return saxutils.escape(censored)


# ---------------------------------------------------------------------------
# Recommendation Derivation
# ---------------------------------------------------------------------------

def generate_recommendation(
    overall_risk: str,
    overall_confidence: str,
    coverage_fraction: float,
    findings_count: int,
    audit_valid: bool | None,
) -> tuple[str, str]:
    """
    Derive deterministic, non-authoritative recommended disposition.

    Returns:
      (disposition_title, rationale_statement)
    """
    r = (overall_risk or "NONE").upper()
    conf = (overall_confidence or "HIGH").upper()

    if audit_valid is False:
        return (
            "REJECT / AUDIT CHAIN COMPROMISED",
            "Tamper-evident audit chain verification failed. The cryptographic integrity "
            "and sequence continuity of this assessment record cannot be verified.",
        )

    if r in ("HIGH", "CRITICAL"):
        return (
            "QUARANTINE / REJECT ARTIFACT",
            "High-severity integrity violations or cryptographic hash mismatches were detected. "
            "The artifact or inference stream must be quarantined and investigated before use.",
        )

    if r == "MEDIUM":
        return (
            "INVESTIGATE / ANALYST REVIEW REQUIRED",
            "Anomalies, sequence inconsistencies, or elevated statistical variations were observed. "
            "Detailed analyst inspection of reported evidence is required before operational clearance.",
        )

    if r == "LOW":
        return (
            "ACCEPT WITH MONITORING",
            "Minor baseline variances recorded without critical integrity compromises. "
            "Artifact may be accepted subject to standard runtime anomaly monitoring.",
        )

    # Risk is NONE
    if coverage_fraction < 0.6 or conf in ("LOW", "MODERATE"):
        return (
            "PROVISIONAL ACCEPTANCE / INCOMPLETE COVERAGE",
            f"No integrity anomalies were detected on evaluated pathways. However, evaluated coverage "
            f"is {round(coverage_fraction * 100, 1)}% ({conf} confidence). "
            "Supplemental testing on unexercised capabilities is recommended.",
        )

    return (
        "ACCEPT / NO INTEGRITY ANOMALY DETECTED",
        "All applicable cryptographic bindings, statistical baselines, and provenance checks passed "
        "with high confidence. No integrity defects or unauthorized alterations were observed.",
    )
