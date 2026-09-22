"""Conservative line segmentation for prescription photographs."""

from __future__ import annotations

import cv2
import numpy as np


def segment_lines(content: bytes) -> list[tuple[list[int], np.ndarray]]:
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("OCR_SEGMENTATION_FAILED")
    binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kernel_width = max(12, image.shape[1] // 30)
    connected = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 3)),
    )
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width >= 10 and height >= 5:
            padding = 4
            left, top = max(0, x - padding), max(0, y - padding)
            right = min(image.shape[1], x + width + padding)
            bottom = min(image.shape[0], y + height + padding)
            boxes.append(([left, top, right - left, bottom - top], image[top:bottom, left:right]))
    boxes.sort(key=lambda item: (item[0][1], item[0][0]))
    return boxes
