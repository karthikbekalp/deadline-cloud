# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Update checker module for Deadline Cloud integrations.

This module provides functionality to check if a newer version of a Deadline Cloud
integration is available by comparing the installed version against a remote manifest.
"""

from __future__ import annotations

__all__ = [
    "MANIFEST_URL",
    "UpdateCheckStatus",
    "UpdateCheckResult",
    "check_for_updates",
    "get_current_platform",
]

import json
import logging
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from packaging.version import Version, InvalidVersion

logger = logging.getLogger(__name__)

MANIFEST_URL = "https://downloads.deadlinecloud.amazonaws.com/submitters/manifest.json"
MANIFEST_TIMEOUT_SECONDS = 5
MANIFEST_BASE_URL = "https://downloads.deadlinecloud.amazonaws.com/submitters"


class UpdateCheckStatus(Enum):
    """Status of the update check operation."""

    SUCCESS = "success"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    PARSE_ERROR = "parse_error"
    INVALID_VERSION = "invalid_version"
    INTEGRATION_NOT_FOUND = "integration_not_found"


@dataclass
class UpdateCheckResult:
    """Result of an update check operation.

    Attributes:
        status: The status of the update check operation.
        update_available: Whether an update is available. Always False on error.
        current_version: The currently installed version (from input).
        latest_version: The latest version from the manifest (if available).
        download_url: URL to download the latest submitter (if available).
        error_message: Human-readable error description (if an error occurred).
    """

    status: UpdateCheckStatus
    update_available: bool = False
    current_version: Optional[str] = None
    latest_version: Optional[str] = None
    download_url: Optional[str] = None
    error_message: Optional[str] = None


def get_current_platform() -> str:
    """
    Detect the current operating system.

    Returns:
        "linux", "macos", or "windows" based on the current platform.
    """
    platform = sys.platform
    if platform.startswith("linux"):
        return "linux"
    elif platform == "darwin":
        return "macos"
    elif platform == "win32" or platform == "cygwin":
        return "windows"
    else:
        # Default to linux for unknown platforms
        return "linux"


def check_for_updates(
    integration_name: str,
    current_version: str,
) -> UpdateCheckResult:
    """
    Check if a newer version of a Deadline Cloud integration is available.

    Fetches the remote manifest and compares the installed version against
    the latest version listed for the current platform.

    If the ``settings.submitter_update_notification`` config value is
    ``"false"``, the check is skipped and a result with
    ``update_available=False`` is returned immediately.

    Args:
        integration_name: Package name of the integration as it appears in the
            manifest (e.g., "deadline-cloud-for-cinema-4d").
        current_version: The currently installed version string (e.g., "0.9.2").

    Returns:
        An UpdateCheckResult describing whether an update is available.
    """
    # Allow customers to suppress the update notification via config
    try:
        from ..config import config_file

        notification_enabled = config_file.str2bool(
            config_file.get_setting("settings.submitter_update_notification")
        )
        if not notification_enabled:
            logger.info("Update notification suppressed by settings.submitter_update_notification")
            return UpdateCheckResult(
                status=UpdateCheckStatus.SUCCESS,
                update_available=False,
                current_version=current_version,
            )
    except Exception:
        # If we can't read the config, proceed with the check
        pass

    platform = get_current_platform()

    # Fetch the manifest
    try:
        req = urllib.request.Request(MANIFEST_URL)
        with urllib.request.urlopen(req, timeout=MANIFEST_TIMEOUT_SECONDS) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return UpdateCheckResult(
            status=UpdateCheckStatus.NETWORK_ERROR,
            current_version=current_version,
            error_message=f"Network error: {e}",
        )
    except TimeoutError:
        return UpdateCheckResult(
            status=UpdateCheckStatus.TIMEOUT_ERROR,
            current_version=current_version,
            error_message="Request timed out",
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return UpdateCheckResult(
            status=UpdateCheckStatus.PARSE_ERROR,
            current_version=current_version,
            error_message=f"Failed to parse manifest: {e}",
        )

    # Navigate: DeadlineCloudSubmitter.versions.latest.{platform}
    try:
        platform_data = manifest["DeadlineCloudSubmitter"]["versions"]["latest"][platform]
    except (KeyError, TypeError):
        return UpdateCheckResult(
            status=UpdateCheckStatus.PARSE_ERROR,
            current_version=current_version,
            error_message=f"Platform '{platform}' not found in manifest",
        )

    # Look up the integration version
    component_versions = platform_data.get("componentVersions", {})
    latest_version_str = component_versions.get(integration_name)
    if latest_version_str is None:
        return UpdateCheckResult(
            status=UpdateCheckStatus.INTEGRATION_NOT_FOUND,
            current_version=current_version,
            error_message=f"Integration '{integration_name}' not found in manifest",
        )

    # Compare versions — let InvalidVersion propagate for current_version
    # since that's a caller bug, but handle it gracefully for the manifest version.
    current_ver = Version(current_version)
    try:
        latest_ver = Version(latest_version_str)
    except InvalidVersion as e:
        return UpdateCheckResult(
            status=UpdateCheckStatus.INVALID_VERSION,
            current_version=current_version,
            latest_version=latest_version_str,
            error_message=f"Invalid version: {e}",
        )

    # Build the download URL from the installer path in the manifest
    installer_path = platform_data.get("installer")
    download_url = f"{MANIFEST_BASE_URL}{installer_path}" if installer_path else None

    return UpdateCheckResult(
        status=UpdateCheckStatus.SUCCESS,
        update_available=latest_ver > current_ver,
        current_version=current_version,
        latest_version=latest_version_str,
        download_url=download_url,
    )
