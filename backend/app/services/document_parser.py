import html
import re
from datetime import datetime, timezone
from typing import Any

COMMON_LAB_TESTS = (
    "hemoglobin",
    "fasting blood glucose",
    "blood glucose",
    "serum creatinine",
    "creatinine",
    "total cholesterol",
    "cholesterol",
    "platelets",
    "wbc",
    "rbc",
    "urea",
    "uric acid",
    "sgot",
    "sgpt",
    "bilirubin",
    "tsh",
    "hba1c",
)


def classify_document(raw_text: str, filename: str = "") -> str:
    combined = (raw_text + " " + filename).lower()
    lab_keywords = ("test name", "reference range", "diagnostic", "blood count", "biochemistry", "pathology", "lab report")
    prescription_keywords = ("rx", "tab ", "cap ", "syp ", "dr.", "mbbs", "tablets", "capsules", "prescription")

    lab_score = sum(1 for k in lab_keywords if k in combined)
    rx_score = sum(1 for k in prescription_keywords if k in combined)

    if lab_score > rx_score:
        return "lab_report"
    if rx_score > 0:
        return "prescription"
    return "other"


def extract_document_date(raw_text: str) -> datetime | None:
    patterns = [
        r"Date[:\s]+(\d{4}-\d{2}-\d{2})",
        r"Date[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def parse_prescription(raw_text: str) -> dict[str, Any]:
    medications: list[dict[str, Any]] = []
    doctor_header = None

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    # Extract doctor line
    for line in lines[:3]:
        if re.search(r"\b(dr\.|doctor|mbbs|md|clinic|hospital)\b", line, re.IGNORECASE):
            doctor_header = line
            break

    rx_section = False
    med_pattern = re.compile(
        r"^(?:\d+[\.\)]\s*)?(?:(Tab|Cap|Syp|Inj|Oint)\.?\s+)?([A-Za-z0-9\s]+?)(?:\s+(\d+(?:\.\d+)?\s*(?:mg|ml|mcg|g|IU)(?:/\d+(?:\.\d+)?\s*(?:mg|ml|mcg|g|IU))?))?(?:\s*-\s*|\s+(.+))?$",
        re.IGNORECASE,
    )

    for line in lines:
        if re.search(r"\b(?:Rx|Prescription)\b", line, re.IGNORECASE):
            rx_section = True
            continue

        # Instructions are commonly printed on the line after the drug and dose.
        if medications and re.match(r"^(?:take|use|apply|inject)\b", line, re.IGNORECASE):
            previous = medications[-1]
            previous["instructions"] = line
            if previous["frequency"] is None:
                freq_match = re.search(
                    r"\b(OD|BD|TDS|QDS|HS|SOS|once daily|twice daily|thrice daily)\b",
                    line,
                    re.IGNORECASE,
                )
                if freq_match:
                    frequency = freq_match.group(1)
                    previous["frequency"] = (
                        frequency.title() if " " in frequency else frequency.upper()
                    )
            continue

        if rx_section or re.match(r"^(?:\d+[\.\)]\s*)?(?:Tab|Cap|Syp|Inj)\b", line, re.IGNORECASE):
            match = med_pattern.match(line)
            if match:
                form, raw_name, dosage, rest = match.groups()
                if not form and not dosage:
                    continue
                clean_name = (form + " " + raw_name).strip() if form else raw_name.strip()
                if len(clean_name) < 3:
                    continue

                freq = None
                duration = None
                if rest:
                    freq_match = re.search(
                        r"\b(OD|BD|TDS|QDS|HS|SOS|once daily|twice daily|thrice daily)\b",
                        rest,
                        re.IGNORECASE,
                    )
                    if freq_match:
                        frequency = freq_match.group(1)
                        freq = frequency.title() if " " in frequency else frequency.upper()

                    dur_match = re.search(r"x\s*(\d+\s*(?:days|weeks|months|d|w))", rest, re.IGNORECASE)
                    if dur_match:
                        duration = dur_match.group(1)

                medications.append({
                    "name": clean_name,
                    "dosage": dosage.strip() if dosage else None,
                    "frequency": freq,
                    "duration": duration,
                    "instructions": rest.strip() if rest else None,
                })

    return {
        "doctor_header": doctor_header,
        "medications": medications,
    }


def parse_lab_report(raw_text: str) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []

    # 1. HTML table parsing (standard output from Sarvam AI doc-ai-digitise-v1)
    if "<table" in raw_text.lower() and "<tr" in raw_text.lower():
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", raw_text, re.DOTALL | re.IGNORECASE)
        for r in rows:
            if "<td" not in r.lower():
                continue
            cells = [html.unescape(c.strip()) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.DOTALL | re.IGNORECASE)]
            if not cells or len(cells) < 2:
                continue
            test_name = cells[0].strip()
            if test_name.lower() in ("test name", "test", "investigation", "parameter"):
                continue
            val = ""
            unit = None
            ref_range = None
            flag = None
            if len(cells) == 2:
                val = cells[1].strip()
            elif len(cells) == 3:
                val_str = cells[1].strip()
                vm = re.match(r"^([\d\.\s\-<]+)\s*([a-zA-Z/%]+(?:\/[a-zA-Z]+)?)$", val_str)
                if vm:
                    val = vm.group(1).strip()
                    unit = vm.group(2).strip()
                else:
                    val = val_str
                ref_raw = cells[2].strip()
                fm = re.search(r"\(?(normal|high|low|abnormal)\)?\s*$", ref_raw, re.I)
                if fm:
                    flag = fm.group(1).lower()
                    ref_range = ref_raw[:fm.start()].strip()
                else:
                    ref_range = ref_raw
            elif len(cells) >= 4:
                val = cells[1].strip()
                unit = cells[2].strip() or None
                ref_raw = cells[3].strip()
                fm = re.search(r"\(?(normal|high|low|abnormal)\)?\s*$", ref_raw, re.I)
                if fm:
                    flag = fm.group(1).lower()
                    ref_range = ref_raw[:fm.start()].strip()
                else:
                    ref_range = ref_raw
            observations.append({
                "test_name": test_name,
                "value": val,
                "unit": unit,
                "reference_range": ref_range,
                "flag": flag,
            })
        if observations:
            return {"observations": observations}

    # 2. Markdown table parsing
    md_lines = [line_text.strip() for line_text in raw_text.splitlines() if line_text.strip()]
    if any(line_text.startswith("|") and line_text.endswith("|") for line_text in md_lines):
        for line in md_lines:
            if not line.startswith("|") or not line.endswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or all(set(c) <= {"-", ":", " "} for c in cells):
                continue
            test_name = cells[0].strip()
            if test_name.lower() in ("test name", "test", "investigation", "parameter"):
                continue
            val = ""
            unit = None
            ref_range = None
            flag = None
            if len(cells) == 2:
                val = cells[1].strip()
            elif len(cells) == 3:
                val_str = cells[1].strip()
                vm = re.match(r"^([\d\.\s\-<]+)\s*([a-zA-Z/%]+(?:\/[a-zA-Z]+)?)$", val_str)
                if vm:
                    val = vm.group(1).strip()
                    unit = vm.group(2).strip()
                else:
                    val = val_str
                ref_raw = html.unescape(cells[2].strip())
                fm = re.search(r"\(?(normal|high|low|abnormal)\)?\s*$", ref_raw, re.I)
                if fm:
                    flag = fm.group(1).lower()
                    ref_range = ref_raw[:fm.start()].strip()
                else:
                    ref_range = ref_raw
            elif len(cells) >= 4:
                val = cells[1].strip()
                unit = cells[2].strip() or None
                ref_raw = html.unescape(cells[3].strip())
                fm = re.search(r"\(?(normal|high|low|abnormal)\)?\s*$", ref_raw, re.I)
                if fm:
                    flag = fm.group(1).lower()
                    ref_range = ref_raw[:fm.start()].strip()
                else:
                    ref_range = ref_raw
            observations.append({
                "test_name": test_name,
                "value": val,
                "unit": unit,
                "reference_range": ref_range,
                "flag": flag,
            })
        if observations:
            return {"observations": observations}

    # 3. Plaintext whitespace-separated pattern
    row_pattern = re.compile(
        r"^([A-Za-z\s]+?)\s{2,}(\d+(?:\.\d+)?)\s+([a-zA-Z/%]+(?:\/[a-zA-Z]+)?)\s+([\d\.\s\-<]+)\s*(?:\(?([A-Za-z]+)\)?)?$"
    )

    for line in md_lines:
        match = row_pattern.match(line)
        if match:
            test_name, val, unit, ref_range, flag = match.groups()
            observations.append({
                "test_name": test_name.strip(),
                "value": val.strip(),
                "unit": unit.strip(),
                "reference_range": ref_range.strip(),
                "flag": flag.strip().lower() if flag else None,
            })

    return {
        "observations": observations,
    }


def parse_document(raw_text: str, filename: str = "") -> tuple[str, datetime | None, dict[str, Any]]:
    doc_type = classify_document(raw_text, filename)
    doc_date = extract_document_date(raw_text)

    if doc_type == "prescription":
        structured = parse_prescription(raw_text)
    elif doc_type == "lab_report":
        structured = parse_lab_report(raw_text)
    else:
        structured = {"raw_excerpt": raw_text[:500]}

    structured["document_type"] = doc_type
    if doc_date:
        structured["document_date"] = doc_date.isoformat()

    return doc_type, doc_date, structured
