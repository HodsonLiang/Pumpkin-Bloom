"""Synthetic timing comparison, not a substitute for real screenshot validation."""
import time
from pathlib import Path
import cv2
import numpy as np
from pikmin.vision import load_templates, match_image, read_image
from tests.test_vision import paste


def main():
    folder = Path(__file__).resolve().parent.parent/'mushroom_pics'
    raw = [(p.name, read_image(p, cv2.IMREAD_UNCHANGED)) for p in sorted(folder.glob('*.png'))]
    templates = load_templates(folder)
    background = np.random.default_rng(2026).integers(0, 256, (2340, 1080, 3), dtype=np.uint8)
    target = raw[-1][1]
    cases = {'no_hit': background, 'full_target': background.copy(), 'left_clipped': background.copy()}
    paste(cases['full_target'], target, 500, 1100)
    paste(cases['left_clipped'], target, -75, 1100)
    def old(image):
        for name, template in raw:
            mask = (template[:, :, 3] > 1).astype(np.uint8)
            scores = cv2.matchTemplate(image, template[:, :, :3], cv2.TM_SQDIFF_NORMED, mask=mask)
            if cv2.minMaxLoc(scores)[0] <= .058:
                return name
        return None
    for name, image in cases.items():
        before_times, timings = [], []
        for _ in range(3):
            t = time.perf_counter()
            before = old(image)
            before_times.append(time.perf_counter()-t)
            t = time.perf_counter()
            after = match_image(image, templates)
            timings.append(time.perf_counter()-t)
        elapsed_old = np.median(before_times)
        print(f'{name}: old median={elapsed_old:.3f}s/{before}, new median={np.median(timings):.3f}s/{after}, speedup={elapsed_old/np.median(timings):.1f}x', flush=True)


if __name__ == '__main__':
    main()
