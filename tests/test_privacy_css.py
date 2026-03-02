import unittest

class TestPrivacyCss(unittest.TestCase):
    """Ensure privacy-related CSS selectors are present in styles.css."""

    def setUp(self):
        with open('app/static/css/styles.css', 'r') as f:
            self.css = f.read()

    def test_blur_selectors_exist(self):
        # selectors for table first-column blur
        expected = [
            'body.privacy-mode table#stocksTable td:first-child',
            'body.privacy-mode table#etfTable td:first-child',
            'body.privacy-mode table#mfTable td:first-child',
            'body.privacy-mode table#physicalGoldTable td:first-child',
            'body.privacy-mode table[aria-label="SIPs table"] td:first-child',
            'body.privacy-mode .breakdown-segment',
            'body.privacy-mode #etf-section tbody tr td:nth-child(10)',
            'body.privacy-mode .breakdown-segment .breakdown-pl span',
        ]
        for sel in expected:
            self.assertIn(sel, self.css, f"CSS should contain privacy blur selector '{sel}'")

    def test_blur_filter_property(self):
        # ensure filter: blur is mentioned at least once in appropriate context
        self.assertIn('filter: blur', self.css)

    def test_js_applies_privacy_class(self):
        # verify visibility-manager.js uses body.classList to toggle privacy-mode
        with open('app/static/js/visibility-manager.js', 'r') as f:
            js = f.read()
        self.assertIn("body.classList.add('privacy-mode')", js)
        self.assertIn("body.classList.remove('privacy-mode')", js)
