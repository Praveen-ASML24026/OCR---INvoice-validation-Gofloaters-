import numpy as np
import pytest

from invoice_parser.confidence import (
    calculate_confidence_scores,
    score_date,
    score_gstin,
    score_invoice_number,
    score_taxable_amount,
)
from invoice_parser.preprocessor import (
    deskew_image,
    enhance_contrast_clahe,
    estimate_skew_angle,
    preprocess_image,
    reduce_noise,
)


def test_confidence_scoring_complete():
    doc = {
        "invoice": {"number": "INV-2026/099", "date": "2026-04-12", "due_date": "2026-05-12"},
        "operator": {"gstin": "33AAYCS6808H1ZT", "state": "Tamil Nadu"},
        "gofloaters": {"gstin": "29AAYCS6808H1ZI", "state": "Karnataka"},
        "tax": {"taxable_amount": 5000.0, "cgst": 450.0, "sgst": 450.0, "total": 5900.0},
        "extraction_sources": {"invoice.number": "labeled_kv"},
    }

    scores = calculate_confidence_scores(doc)
    assert scores["invoice_number"] >= 0.90
    assert scores["taxable_amount"] == 1.0  # Mathematical invariant holds exactly
    assert scores["gstin"] >= 0.95
    assert scores["dates"] >= 0.95
    assert scores["overall"] >= 0.95
    assert scores["details"]["tax_invariant_verified"] is True


def test_confidence_scoring_mismatch_penalty():
    doc = {
        "invoice": {"number": "123", "date": "invalid-date"},
        "operator": {"gstin": "INVALID_GSTIN"},
        "gofloaters": {},
        "tax": {"taxable_amount": 1000.0, "cgst": 100.0, "total": 2000.0},  # Math invariant broken
    }

    scores = calculate_confidence_scores(doc)
    assert scores["taxable_amount"] < 1.0
    assert scores["gstin"] < 0.70
    assert scores["details"]["tax_invariant_verified"] is False


def test_image_preprocessing_pipeline():
    # Create synthetic test image (white canvas with dark rectangle)
    img = np.ones((200, 300, 3), dtype=np.uint8) * 255
    img[50:150, 50:250] = 50

    # 1. CLAHE Contrast enhancement
    clahe_img = enhance_contrast_clahe(img)
    assert clahe_img.shape == img.shape

    # 2. Noise reduction
    denoised = reduce_noise(img)
    assert denoised.shape == img.shape

    # 3. Deskew
    deskewed, angle = deskew_image(img)
    assert deskewed.shape == img.shape
    assert isinstance(angle, float)

    # 4. End-to-end preprocessing function
    processed = preprocess_image(img, auto_deskew=True, apply_clahe=True, denoise=True)
    assert processed.shape == img.shape
    assert processed.dtype == np.uint8
