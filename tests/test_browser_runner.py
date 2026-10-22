"""Browser launcher must not assume local /usr/bin/chromium exists in CI."""
import os
from unittest import TestCase
from unittest.mock import Mock, patch

from browser_runner import launch_chromium


class BrowserLauncherTests(TestCase):
    def test_missing_explicit_executable_is_error_not_fallback(self):
        with patch.dict(os.environ, {'DAYFLARE_CHROMIUM_BIN': '/this/dayflare-browser-is-missing'}):
            with self.assertRaises(FileNotFoundError):
                launch_chromium(Mock())

    def test_hosted_ci_can_use_playwright_managed_chromium(self):
        browser = Mock()
        with patch.dict(os.environ, {}, clear=True), patch('browser_runner.Path.is_file', return_value=False):
            launch_chromium(browser)
        browser.chromium.launch.assert_called_once_with(headless=True, args=['--no-sandbox'])

    def test_existing_system_browser_is_used_locally(self):
        browser = Mock()
        with patch.dict(os.environ, {}, clear=True), patch('browser_runner.Path.is_file', return_value=True):
            launch_chromium(browser)
        browser.chromium.launch.assert_called_once_with(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])


if __name__=='__main__':
    import unittest
    unittest.main()
