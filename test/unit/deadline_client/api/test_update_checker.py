# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Tests for the deadline.client.api._update_checker module.
"""

import json
from unittest.mock import patch, MagicMock
import socket
import urllib.error

import pytest

from deadline.client.api._update_checker import (
    UpdateCheckStatus,
    check_for_updates,
    get_current_platform,
    DOWNLOAD_BASE_URL,
)
from packaging.version import InvalidVersion


SAMPLE_MANIFEST = {
    "DeadlineCloudSubmitter": {
        "versions": {
            "latest": {
                "linux": {
                    "componentVersions": {
                        "deadline-cloud": "0.54.2",
                        "deadline-cloud-for-blender": "0.6.1",
                        "deadline-cloud-for-cinema-4d": "0.10.0",
                        "deadline-cloud-for-maya": "0.15.13",
                        "deadline-cloud-for-nuke": "0.18.16",
                    },
                    "installer": "/latest/linux/DeadlineCloudSubmitter-linux-x64-installer.run",
                    "sha256": "/latest/linux/DeadlineCloudSubmitter-linux-x64-installer.run.sha256",
                },
                "macos": {
                    "componentVersions": {
                        "deadline-cloud": "0.54.2",
                        "deadline-cloud-for-cinema-4d": "0.10.0",
                        "deadline-cloud-for-maya": "0.15.13",
                        "deadline-cloud-for-nuke": "0.18.16",
                    },
                    "installer": "/latest/macos/DeadlineCloudSubmitter-osx-installer.app.zip",
                    "sha256": "/latest/macos/DeadlineCloudSubmitter-osx-installer.app.zip.sha256",
                },
                "windows": {
                    "componentVersions": {
                        "deadline-cloud": "0.54.2",
                        "deadline-cloud-for-cinema-4d": "0.10.0",
                        "deadline-cloud-for-maya": "0.15.13",
                        "deadline-cloud-for-nuke": "0.18.16",
                    },
                    "installer": "/latest/windows/DeadlineCloudSubmitter-windows-x64-installer.exe",
                    "sha256": "/latest/windows/DeadlineCloudSubmitter-windows-x64-installer.exe.sha256",
                },
            }
        }
    }
}


class TestGetCurrentPlatform:
    """Tests for get_current_platform()."""

    @pytest.mark.parametrize(
        "sys_platform, expected",
        [
            ("linux", "linux"),
            ("linux2", "linux"),
            ("darwin", "macos"),
            ("win32", "windows"),
            ("cygwin", "windows"),
            ("freebsd", "linux"),  # unknown defaults to linux
        ],
    )
    def test_platform_detection(self, sys_platform, expected):
        with patch("deadline.client.api._update_checker.sys") as mock_sys:
            mock_sys.platform = sys_platform
            assert get_current_platform() == expected


def _mock_urlopen(manifest_data):
    """Helper to create a mock urlopen context manager returning manifest JSON."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(manifest_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


PLATFORM_INSTALLER_URLS = {
    "linux": f"{DOWNLOAD_BASE_URL}/latest/linux/DeadlineCloudSubmitter-linux-x64-installer.run",
    "macos": f"{DOWNLOAD_BASE_URL}/latest/macos/DeadlineCloudSubmitter-osx-installer.app.zip",
    "windows": f"{DOWNLOAD_BASE_URL}/latest/windows/DeadlineCloudSubmitter-windows-x64-installer.exe",
}


class TestCheckForUpdates:
    """Tests for check_for_updates()."""

    @pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_update_available(self, mock_urlopen_fn, platform):
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        with patch(
            "deadline.client.api._update_checker.get_current_platform", return_value=platform
        ):
            result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.SUCCESS
        assert result.update_available is True
        assert result.current_version == "0.9.1"
        assert result.latest_version == "0.10.0"
        assert result.download_url == PLATFORM_INSTALLER_URLS[platform]

    @pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_no_update_available(self, mock_urlopen_fn, platform):
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        with patch(
            "deadline.client.api._update_checker.get_current_platform", return_value=platform
        ):
            result = check_for_updates("deadline-cloud-for-cinema-4d", "0.10.0")

        assert result.status == UpdateCheckStatus.SUCCESS
        assert result.update_available is False
        assert result.latest_version == "0.10.0"

    @pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_current_version_newer_than_manifest(self, mock_urlopen_fn, platform):
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        with patch(
            "deadline.client.api._update_checker.get_current_platform", return_value=platform
        ):
            result = check_for_updates("deadline-cloud-for-cinema-4d", "1.0.0")

        assert result.status == UpdateCheckStatus.SUCCESS
        assert result.update_available is False

    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen_fn):
        mock_urlopen_fn.side_effect = urllib.error.URLError("Connection refused")

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.NETWORK_ERROR
        assert result.update_available is False
        assert result.error_message is not None
        assert "Network error" in result.error_message

    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen_fn):
        mock_urlopen_fn.side_effect = TimeoutError()

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.TIMEOUT_ERROR
        assert result.update_available is False

    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_socket_timeout_error(self, mock_urlopen_fn):
        mock_urlopen_fn.side_effect = socket.timeout("timed out")

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.TIMEOUT_ERROR
        assert result.update_available is False

    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_parse_error(self, mock_urlopen_fn):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen_fn.return_value = mock_resp

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.PARSE_ERROR
        assert result.update_available is False

    @pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_integration_not_found(self, mock_urlopen_fn, platform):
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        with patch(
            "deadline.client.api._update_checker.get_current_platform", return_value=platform
        ):
            result = check_for_updates("deadline-cloud-for-houdini", "1.0.0")

        assert result.status == UpdateCheckStatus.INTEGRATION_NOT_FOUND
        assert result.update_available is False
        assert result.error_message is not None
        assert "not found" in result.error_message

    @patch("deadline.client.api._update_checker.get_current_platform", return_value="unknown_os")
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_platform_not_in_manifest(self, mock_urlopen_fn, mock_platform):
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.PARSE_ERROR
        assert result.error_message is not None
        assert "not found in manifest" in result.error_message

    @patch("deadline.client.api._update_checker.get_current_platform", return_value="macos")
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_invalid_version_in_manifest(self, mock_urlopen_fn, mock_platform):
        bad_manifest = {
            "DeadlineCloudSubmitter": {
                "versions": {
                    "latest": {
                        "macos": {
                            "componentVersions": {
                                "deadline-cloud-for-cinema-4d": "not.a.version!",
                            },
                        }
                    }
                }
            }
        }
        mock_urlopen_fn.return_value = _mock_urlopen(bad_manifest)

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.INVALID_VERSION
        assert result.update_available is False

    @patch("deadline.client.api._update_checker.get_current_platform", return_value="macos")
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_missing_installer_key_returns_no_download_url(self, mock_urlopen_fn, mock_platform):
        manifest_without_installer = {
            "DeadlineCloudSubmitter": {
                "versions": {
                    "latest": {
                        "macos": {
                            "componentVersions": {
                                "deadline-cloud-for-cinema-4d": "0.10.0",
                            },
                        }
                    }
                }
            }
        }
        mock_urlopen_fn.return_value = _mock_urlopen(manifest_without_installer)

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.SUCCESS
        assert result.update_available is False
        assert result.download_url is None

    @pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_invalid_current_version_raises(self, mock_urlopen_fn, platform):
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        with patch(
            "deadline.client.api._update_checker.get_current_platform", return_value=platform
        ):
            with pytest.raises(InvalidVersion):
                check_for_updates("deadline-cloud-for-cinema-4d", "bad-version")


class TestConfigOptOut:
    """Tests for the settings.submitter_update_notification opt-out."""

    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_notification_suppressed(self, mock_urlopen_fn, fresh_deadline_config):
        """When submitter_update_notification is false, check is skipped."""
        from deadline.client.config.config_file import set_setting

        set_setting("settings.submitter_update_notification", "false")

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.SUCCESS
        assert result.update_available is False
        # Should not have fetched the manifest at all
        mock_urlopen_fn.assert_not_called()

    @patch("deadline.client.api._update_checker.get_current_platform", return_value="macos")
    @patch("deadline.client.api._update_checker.urllib.request.urlopen")
    def test_notification_enabled_by_default(
        self, mock_urlopen_fn, mock_platform, fresh_deadline_config
    ):
        """When submitter_update_notification is default (true), check proceeds."""
        mock_urlopen_fn.return_value = _mock_urlopen(SAMPLE_MANIFEST)

        result = check_for_updates("deadline-cloud-for-cinema-4d", "0.9.1")

        assert result.status == UpdateCheckStatus.SUCCESS
        assert result.update_available is True
        mock_urlopen_fn.assert_called_once()
