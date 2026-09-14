from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np
from pikmin.vision import load_templates, match_image, _load_templates, check_image_has_target


def paste(image, template, x, y):
    h, w = template.shape[:2]
    ih, iw = image.shape[:2]
    left, top, right, bottom = max(0, x), max(0, y), min(iw, x+w), min(ih, y+h)
    crop = template[top-y:bottom-y, left-x:right-x]
    mask = crop[:, :, 3] > 1
    roi = image[top:bottom, left:right]
    roi[mask] = crop[:, :, :3][mask]


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        rng = np.random.default_rng(19)
        color = rng.integers(40, 230, (48, 48, 3), dtype=np.uint8)
        self.template = np.dstack([color, np.full((48, 48), 255, np.uint8)])
        cv2.imencode('.png', self.template)[1].tofile(self.folder/'target.png')
        self.templates = load_templates(self.folder, scale=.5)

    def test_full_and_four_edges_and_corner(self):
        for x, y in [(60, 70), (-8, 70), (220, 70), (60, -8), (60, 220), (-5, -5)]:
            with self.subTest(x=x, y=y):
                image = np.full((256, 256, 3), 15, np.uint8)
                paste(image, self.template, x, y)
                result = match_image(image, self.templates, .02)
                self.assertIsNotNone(result)
                self.assertEqual((result.x, result.y), (x, y))
                self.assertGreaterEqual(result.visible, .65)
                self.assertLess(result.score, .001)

    def test_too_little_visible_rejected(self):
        image = np.full((256, 256, 3), 15, np.uint8)
        paste(image, self.template, -36, 70)
        self.assertIsNone(match_image(image, self.templates, .02))

    def test_empty_background_rejected(self):
        self.assertIsNone(match_image(np.full((256, 256, 3), 15, np.uint8), self.templates, .02))

    def test_template_cache_is_reused_and_invalidated(self):
        self.assertIs(self.templates, load_templates(self.folder, scale=.5))
        cv2.imencode('.png', self.template[:40])[1].tofile(self.folder/'target.png')
        self.assertIsNot(self.templates, load_templates(self.folder, scale=.5))

    def test_transparent_border_is_cropped(self):
        bordered = cv2.copyMakeBorder(self.template, 12, 12, 12, 12, cv2.BORDER_CONSTANT)
        cv2.imencode('.png', bordered)[1].tofile(self.folder/'border.png')
        templates = load_templates(self.folder)
        self.assertTrue(all(t.mask.shape == (48, 48) for t in templates))

    def test_unicode_path_and_old_api(self):
        image = np.full((256, 256, 3), 15, np.uint8)
        paste(image, self.template, 60, 70)
        path = self.folder/'截圖.png'
        cv2.imencode('.png', image)[1].tofile(path)
        self.assertEqual(check_image_has_target(path, self.folder, .02), (True, 'target.png'))


if __name__ == '__main__':
    unittest.main()
