"""
File validation service for uploaded imports.

NOTE/TODO: Future enhancements planned:
- Integrate ClamAV or similar virus scanning via clamd socket
- Validate file headers against declared source_type (e.g., nmap XML
  should start with <?xml or <!-- Nmap)
- Enforce organization-specific file type policies

Currently this module logs validation warnings but does NOT reject files.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum file size: 50 MB (network scan outputs can be large for full /16 scans)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# Allowed file extensions for import uploads
ALLOWED_EXTENSIONS = frozenset({
    ".xml", ".txt", ".log", ".csv", ".json", ".cap", ".pcap", ".pcapng",
})

# Magic byte signatures for common file types
MAGIC_BYTES = {
    b"<?xml": "xml",
    b"\xd4\xc3\xb2\xa1": "pcap",        # pcap little-endian
    b"\xa1\xb2\xc3\xd4": "pcap",        # pcap big-endian
    b"\x0a\x0d\x0d\x0a": "pcapng",      # pcapng
}


class FileValidationResult:
    """Result of file validation checks."""

    def __init__(self):
        self.warnings: list[str] = []
        self.errors: list[str] = []

    @property
    def passed(self) -> bool:
        """True if no blocking errors (warnings are acceptable)."""
        return len(self.errors) == 0


def check_file_size(content_length: int) -> Optional[str]:
    """Check if file size is within allowed limits.

    Returns warning message if oversized, None if OK.
    """
    if content_length > MAX_FILE_SIZE_BYTES:
        return (
            f"File size ({content_length / 1024 / 1024:.1f} MB) exceeds "
            f"limit ({MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB)"
        )
    return None


def check_file_extension(filename: Optional[str]) -> Optional[str]:
    """Check if file extension is in the allowlist.

    Returns warning message if not allowed, None if OK.
    """
    if not filename:
        return "No filename provided -- cannot check extension"
    ext = Path(filename).suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        return f"File extension '{ext}' is not in the allowlist: {sorted(ALLOWED_EXTENSIONS)}"
    return None


def check_magic_bytes(content: bytes) -> Optional[str]:
    """Check file header (magic bytes) against known signatures.

    Returns warning message if unrecognized, None if OK.
    TODO: Cross-reference detected type against declared source_type.
    """
    if len(content) < 5:
        return "File is too small to check magic bytes"

    header = content[:16]
    for magic, file_type in MAGIC_BYTES.items():
        if header.startswith(magic):
            logger.debug(f"Magic bytes match: {file_type}")
            return None

    # Plain text files (netstat, arp, traceroute, ping) won't have magic bytes.
    # This is expected and not a warning for text-based scan outputs.
    try:
        header.decode("utf-8")
        return None  # Valid UTF-8 text, no warning needed
    except UnicodeDecodeError:
        return "File header does not match any known signature and is not valid UTF-8"


def validate_upload(
    filename: Optional[str],
    content: bytes,
) -> FileValidationResult:
    """
    Run all validation checks on an uploaded file.

    Currently logs warnings but does NOT block uploads.
    This function is designed to be the integration point for
    future virus scanning and strict validation.

    TODO: Add virus scanning (ClamAV integration)
    TODO: Add strict mode that rejects files with errors
    """
    result = FileValidationResult()

    # Size check
    size_warning = check_file_size(len(content))
    if size_warning:
        result.warnings.append(size_warning)
        logger.warning(f"File validation: {size_warning}")

    # Extension check
    ext_warning = check_file_extension(filename)
    if ext_warning:
        result.warnings.append(ext_warning)
        logger.warning(f"File validation: {ext_warning}")

    # Magic bytes check
    magic_warning = check_magic_bytes(content)
    if magic_warning:
        result.warnings.append(magic_warning)
        logger.warning(f"File validation: {magic_warning}")

    if result.passed and not result.warnings:
        logger.debug(f"File validation passed: {filename}")

    return result
