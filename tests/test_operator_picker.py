"""WO-LORI-ORAL-HISTORY-DEFAULT-01 (2026-06-14) — operator picker tests.

Covers acceptance gate #2 (picker visually defaults to oral_history)
and #7 (one-time notification + persisted dismissal).

These are HTML/JS contract tests — they grep the picker source for the
expected structure rather than driving a browser. The full live verify
in WO §7 covers DOM behavior under a real cycle.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PICKER_HTML = _REPO_ROOT / "ui" / "hornelore1.0.html"
_PICKER_CSS = _REPO_ROOT / "ui" / "css" / "lori80.css"
_APP_JS = _REPO_ROOT / "ui" / "js" / "app.js"
_ROUTER_JS = _REPO_ROOT / "ui" / "js" / "session-style-router.js"
_LOOP_JS = _REPO_ROOT / "ui" / "js" / "session-loop.js"


class PickerOrderTest(unittest.TestCase):
    def test_oral_history_appears_first(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        # Find the lvSessionStyle radio block
        radio_values = re.findall(
            r'name="lvSessionStyle"\s+value="([a-z_]+)"', html,
        )
        self.assertGreater(len(radio_values), 0)
        self.assertEqual(radio_values[0], "oral_history")

    def test_picker_order_matches_wo_spec(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        radio_values = re.findall(
            r'name="lvSessionStyle"\s+value="([a-z_]+)"', html,
        )
        # WO §2 picker order — after this WO:
        # oral_history → warm_storytelling → companion →
        # questionnaire_first → clear_direct
        # (memory_exercise REMOVED 2026-04-25; v1 keeps that removal.)
        expected = [
            "oral_history", "warm_storytelling", "companion",
            "questionnaire_first", "clear_direct",
        ]
        self.assertEqual(radio_values, expected)


class PickerDefaultSelectionTest(unittest.TestCase):
    def test_oral_history_radio_has_checked_attr(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        # The oral_history radio must carry `checked` so it's the
        # visual pre-selected default on page load
        self.assertTrue(re.search(
            r'value="oral_history"\s+checked',
            html,
        ) is not None)

    def test_no_other_radio_is_checked(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        # Count radios with checked attribute — there should be exactly one
        checked_count = len(re.findall(
            r'name="lvSessionStyle"[^>]+checked', html,
        ))
        self.assertEqual(checked_count, 1)


class PickerTooltipTest(unittest.TestCase):
    def test_each_card_has_tooltip(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        # Each lv-session-style-card label must carry a title= tooltip
        cards = re.findall(
            r'<label class="lv-session-style-card[^"]*"\s+title="([^"]+)"',
            html,
        )
        self.assertGreaterEqual(len(cards), 5)
        for tip in cards:
            # Tooltips must be non-empty and reasonably descriptive
            self.assertGreater(len(tip), 30)


class PickerDefaultBadgeTest(unittest.TestCase):
    def test_default_card_has_default_badge_class(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        self.assertIn("lv-session-style-card-default", html)
        self.assertIn("(default)", html)

    def test_css_styles_default_card(self):
        css = _PICKER_CSS.read_text(encoding="utf-8")
        self.assertIn(".lv-session-style-card-default", css)
        self.assertIn(".lv-session-style-default-badge", css)


class HydrateDefaultTest(unittest.TestCase):
    def test_hydrate_fallback_is_oral_history(self):
        js = _APP_JS.read_text(encoding="utf-8")
        # First-time operators (no saved key in localStorage) must
        # land on oral_history when _lvHydrateSessionStyle runs.
        self.assertIn(
            '? saved : "oral_history"',
            js,
        )

    def test_valid_styles_list_contains_oral_history_first(self):
        js = _APP_JS.read_text(encoding="utf-8")
        # The app-side list governs both validation in lvSetSessionStyle
        # and the fallback in hydrate; oral_history listed first signals
        # priority.
        m = re.search(
            r'LV_VALID_SESSION_STYLES\s*=\s*\[\s*([\s\S]+?)\]',
            js,
        )
        self.assertIsNotNone(m)
        self.assertTrue(m.group(1).lstrip().startswith('"oral_history"'))


class RouterFallbackTest(unittest.TestCase):
    def test_router_valid_styles_lists_oral_history_first(self):
        js = _ROUTER_JS.read_text(encoding="utf-8")
        m = re.search(
            r'VALID_STYLES\s*=\s*\[\s*([\s\S]+?)\]',
            js,
        )
        self.assertIsNotNone(m)
        # First non-comment value in the array must be "oral_history"
        first = re.search(r'"([a-z_]+)"', m.group(1))
        self.assertIsNotNone(first)
        self.assertEqual(first.group(1), "oral_history")

    def test_router_default_fallback_is_oral_history(self):
        js = _ROUTER_JS.read_text(encoding="utf-8")
        # The ternary inside lvSessionStyleEnter falls through to
        # oral_history when style is invalid/unknown.
        self.assertIn(': "oral_history"', js)


class NotificationOneTimeTest(unittest.TestCase):
    def test_notification_card_present_in_html(self):
        html = _PICKER_HTML.read_text(encoding="utf-8")
        self.assertIn('id="lvOralHistoryDefaultNotice"', html)
        self.assertIn("lv-oral-history-notice", html)
        # Must default-hidden so it never flashes for dismissed operators
        self.assertTrue(re.search(
            r'id="lvOralHistoryDefaultNotice"[^>]+hidden',
            html,
        ) is not None)

    def test_show_and_dismiss_functions_exposed(self):
        js = _APP_JS.read_text(encoding="utf-8")
        self.assertIn("function lvOralHistoryDefaultNoticeShow", js)
        self.assertIn("function lvOralHistoryDefaultNoticeDismiss", js)
        # The functions must be reachable as window.* so the HTML
        # onclick handlers can find them.
        self.assertIn("window.lvOralHistoryDefaultNoticeShow", js)
        self.assertIn("window.lvOralHistoryDefaultNoticeDismiss", js)

    def test_notification_uses_localStorage_dismissal_key(self):
        js = _APP_JS.read_text(encoding="utf-8")
        # Persisted dismissal so the banner only ever appears once
        self.assertIn("LV_ORAL_HISTORY_NOTICE_KEY", js)
        self.assertIn("lv_oral_history_default_notice_seen", js)

    def test_notification_show_called_from_init(self):
        js = _APP_JS.read_text(encoding="utf-8")
        # Must fire from lvShellInitTabs so the operator sees it
        # automatically on first operator-panel render.
        self.assertTrue(re.search(
            r'function lvShellInitTabs[\s\S]+?lvOralHistoryDefaultNoticeShow',
            js,
        ) is not None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
