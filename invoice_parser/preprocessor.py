"""
Image and Document Preprocessing Module for Invoice OCR
Provides auto-deskewing, CLAHE contrast enhancement, and noise reduction
using OpenCV and PIL to optimize OCR accuracy on degraded or scanned invoices.
"""
import logging
import math
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("invoice_parser.preprocessor")


def estimate_skew_angle(gray_img: np.ndarray) -> float:
    """
    Estimates the skew angle (in degrees) of a text document image.
    Uses Hough Line Transform on edge-detected text lines.
    Returns angle in degrees (-45.0 to 45.0).
    """
    h, w = gray_img.shape[:2]
    # Invert binary threshold so text is white on black
    blur = cv2.GaussianBlur(gray_img, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
    )

    # Detect line segments using Probabilistic Hough Transform
    lines = cv2.HoughLinesP(
        thresh,
        rho=1,
        theta=np.pi / 180,
        threshold=100,
        minLineLength=w // 8,
        maxLineGap=20,
    )

    angles: List[float] = []
    if lines is not None:
        for line in lines:
            coords = line.flatten()
            if len(coords) < 4:
                continue
            x1, y1, x2, y2 = coords[:4]
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0:
                continue
            angle = math.degrees(math.atan2(dy, dx))
            # Focus on nearly horizontal text baselines (-45° to +45°)
            if -45.0 < angle < 45.0:
                angles.append(angle)

    if angles:
        # Return median angle for outlier robustness
        return float(np.median(angles))

    # Fallback to minAreaRect on text points if Hough lines didn't yield enough samples
    try:
        pts = cv2.findNonZero(thresh)
        if pts is not None and len(pts) > 50:
            rect = cv2.minAreaRect(pts)
            angle = rect[-1]
            if angle < -45:
                angle += 90
            elif angle > 45:
                angle -= 90
            if -45.0 < angle < 45.0:
                return float(angle)
    except Exception:
        pass

    return 0.0


def deskew_image(img: np.ndarray, max_skew_limit: float = 45.0) -> Tuple[np.ndarray, float]:
    """
    Detects skew angle and rotates the image to level text baselines.
    Returns (deskewed_image, angle_rotated).
    """
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    angle = estimate_skew_angle(gray)

    # Skip rotation if skew is negligible (< 0.4 degree) or excessive (> max_skew_limit)
    if abs(angle) < 0.4 or abs(angle) > max_skew_limit:
        return img, 0.0

    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    # Rotate counter-clockwise by skew angle
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255) if len(img.shape) == 3 else 255,
    )
    return rotated, angle


def enhance_contrast_clahe(img: np.ndarray, clip_limit: float = 2.0, tile_size: int = 8) -> np.ndarray:
    """
    Applies CLAHE (Contrast Limited Adaptive Histogram Equalization)
    to enhance faint text without blowing out white document backgrounds.
    """
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))

    if len(img.shape) == 3:
        # Convert BGR to LAB color space and equalize the Luminance channel
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_clahe = clahe.apply(l)
        enhanced_lab = cv2.merge((l_clahe, a, b))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    else:
        return clahe.apply(img)


def reduce_noise(img: np.ndarray) -> np.ndarray:
    """
    Applies edge-preserving bilateral filtering to reduce paper grain
    and scanner sensor noise while keeping text character boundaries crisp.
    """
    return cv2.bilateralFilter(img, d=5, sigmaColor=50, sigmaSpace=50)


def preprocess_image(
    image_input: Union[str, Path, np.ndarray, Image.Image],
    auto_deskew: bool = True,
    apply_clahe: bool = True,
    denoise: bool = True,
) -> np.ndarray:
    """
    Full preprocessing pipeline for an invoice image:
    1. Deskew
    2. Denoise
    3. CLAHE Contrast Enhancement
    Returns preprocessed BGR numpy array.
    """
    # Load into OpenCV BGR format
    if isinstance(image_input, (str, Path)):
        img = cv2.imread(str(image_input))
        if img is None:
            # Fallback loading via PIL if OpenCV failed on exotic image format
            pil_img = Image.open(str(image_input)).convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    elif isinstance(image_input, Image.Image):
        rgb_img = image_input.convert("RGB")
        img = cv2.cvtColor(np.array(rgb_img), cv2.COLOR_RGB2BGR)
    elif isinstance(image_input, np.ndarray):
        img = image_input.copy()
    else:
        raise TypeError(f"Unsupported image input type: {type(image_input)}")

    if auto_deskew:
        img, _angle = deskew_image(img)

    if denoise:
        img = reduce_noise(img)

    if apply_clahe:
        img = enhance_contrast_clahe(img)

    return img


def preprocess_image_file_to_temp(file_path: Union[str, Path]) -> Path:
    """
    Preprocesses an image file and saves the result to a temporary PNG file.
    Returns the Path to the temporary preprocessed file.
    """
    path = Path(file_path)
    processed_bgr = preprocess_image(path)
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close()

    cv2.imwrite(str(temp_path), processed_bgr)
    return temp_path


def preprocess_scanned_pdf(pdf_path: Union[str, Path]) -> Path:
    """
    Preprocesses each page of a scanned PDF (using pypdfium2 and OpenCV)
    and saves the cleaned, deskewed, contrast-enhanced pages back into a temporary PDF.
    Returns the Path to the cleaned PDF for RapidOCR/Docling processing.
    """
    import pypdfium2 as pdfium

    pdf_path = Path(pdf_path)
    doc = pdfium.PdfDocument(pdf_path)
    processed_pil_pages: List[Image.Image] = []

    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            # Render page at 200 DPI for high-fidelity OCR reading
            bitmap = page.render(scale=2.0)
            pil_page = bitmap.to_pil()
            page.close()

            # Preprocess image
            processed_bgr = preprocess_image(pil_page)
            # Convert back to PIL Image (RGB)
            rgb = cv2.cvtColor(processed_bgr, cv2.COLOR_BGR2RGB)
            processed_pil_pages.append(Image.fromarray(rgb))
    finally:
        doc.close()

    if not processed_pil_pages:
        return pdf_path

    # Save all preprocessed pages into a single PDF
    temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temp_pdf_path = Path(temp_pdf.name)
    temp_pdf.close()

    first_page = processed_pil_pages[0]
    rest_pages = processed_pil_pages[1:] if len(processed_pil_pages) > 1 else []
    first_page.save(str(temp_pdf_path), save_all=True, append_images=rest_pages, resolution=200.0)

    logger.info(f"Preprocessed scanned PDF saved to {temp_pdf_path} ({len(processed_pil_pages)} pages)")
    return temp_pdf_path
