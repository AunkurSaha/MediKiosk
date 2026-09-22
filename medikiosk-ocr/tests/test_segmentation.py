import cv2
import numpy as np

from app.segmentation import segment_lines


def test_segments_lines_in_reading_order():
    image = np.full((140, 500), 255, dtype=np.uint8)
    cv2.putText(image, "FIRST LINE", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
    cv2.putText(image, "SECOND LINE", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    regions = segment_lines(encoded.tobytes())
    assert len(regions) == 2
    assert regions[0][0][1] < regions[1][0][1]


def test_invalid_image_reports_segmentation_failure():
    try:
        segment_lines(b"not an image")
    except ValueError as error:
        assert str(error) == "OCR_SEGMENTATION_FAILED"
    else:
        raise AssertionError("Expected invalid image to fail")
