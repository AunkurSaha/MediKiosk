import re

from app.core.errors import WorkflowError

# Standard Indian mobile number regex: 10 digits starting with 6, 7, 8, or 9
INDIAN_MOBILE_REGEX = re.compile(r"^[6-9]\d{9}$")


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize input phone number to canonical E.164 format (+91XXXXXXXXXX).

    Accepts:
      - 10 digits: 9876543210
      - Leading 0: 09876543210
      - Country code: 919876543210, +919876543210
      - Spaced / hyphens / parens: +91 98765-43210, (0)9876543210

    Rejects non-Indian or improperly formatted numbers.
    """
    if not raw_phone or not isinstance(raw_phone, str):
        raise WorkflowError("INVALID_PHONE", "Mobile phone number is required.", 400)

    # Strip whitespace, hyphens, brackets, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw_phone.strip())

    # Handle leading '+'
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    # Handle country prefix 91 or trunk 0
    if cleaned.startswith("91") and len(cleaned) == 12:
        digits = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        digits = cleaned[1:]
    elif len(cleaned) == 10:
        digits = cleaned
    else:
        raise WorkflowError(
            "INVALID_PHONE",
            "Please provide a valid 10-digit Indian mobile phone number.",
            400,
        )

    if not INDIAN_MOBILE_REGEX.match(digits):
        raise WorkflowError(
            "INVALID_PHONE",
            "Indian mobile numbers must be 10 digits starting with 6, 7, 8, or 9.",
            400,
        )

    return f"+91{digits}"


def mask_phone_number(canonical_phone: str) -> str:
    """Mask phone number for safe logging and display, e.g., +91******3210."""
    if not canonical_phone:
        return ""
    if canonical_phone.startswith("+91") and len(canonical_phone) == 13:
        return f"+91******{canonical_phone[-4:]}"
    if len(canonical_phone) >= 7:
        return f"{canonical_phone[:3]}****{canonical_phone[-4:]}"
    return "****"
