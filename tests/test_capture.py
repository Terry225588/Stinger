import numpy as np

from screenmatch.capture import image_signature, normalize_region


def test_signature_ignores_tiny_noise_and_sees_a_real_change():
    base = np.zeros((90, 120, 4), dtype=np.uint8)
    base[:] = (240, 240, 240, 255)
    flicker = base.copy()
    flicker[0, 0, 0] = 242
    changed = base.copy()
    changed[:, :] = (10, 10, 10, 255)
    assert image_signature(base) == image_signature(flicker)
    assert image_signature(base) != image_signature(changed)


def test_region_must_be_large_enough():
    assert normalize_region({"top": 1, "left": 2, "width": 30, "height": 40}) == {
        "top": 1,
        "left": 2,
        "width": 30,
        "height": 40,
    }
    try:
        normalize_region({"top": 0, "left": 0, "width": 8, "height": 40})
    except ValueError as exc:
        assert "太小" in str(exc)
    else:
        raise AssertionError("小区域应该被拒绝")
