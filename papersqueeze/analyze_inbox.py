#!/usr/bin/env python3
"""Analyze recent inbox documents to understand extraction needs."""

import json
import urllib.request
import os
import re

token = os.environ.get("PAPERLESS_API_TOKEN")
headers = {"Authorization": f"Token {token}", "Host": "localhost"}

def get_doc(doc_id):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/documents/{doc_id}/",
        headers=headers
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def extract_values(content):
    """Try to extract common values from OCR content."""
    results = {}

    # Invoice number patterns
    inv_patterns = [
        r'Fatura\s+(?:n[.º°]?\s*)?([A-Z0-9./]+[-/][A-Z0-9./]+)',
        r'Factura\s+n[.º°]?\s*([A-Z0-9./\s]+)',
        r'FT\s+([A-Z0-9./]+)',
    ]
    for pat in inv_patterns:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            results['invoice_number'] = m.group(1).strip()
            break

    # Total amount patterns
    total_patterns = [
        r'Total[:\s]+(?:\(?\s*EUR\s*\)?)?\s*([0-9.,]+)',
        r'Total\s+\(\s*EUR\s*\)\s*([0-9.,]+)',
        r'Total\s+Documento[:\s]+([0-9.,]+)',
    ]
    for pat in total_patterns:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            results['total'] = m.group(1).strip()
            break

    # NIF patterns
    nif_patterns = [
        r'(?:N\.?I\.?[FP]\.?|Contribuinte)[:\s]*(\d{9})',
        r'NIF[:\s]*(\d{9})',
    ]
    for pat in nif_patterns:
        matches = re.findall(pat, content, re.IGNORECASE)
        if matches:
            results['nif_found'] = matches[:2]  # First 2 NIFs
            break

    # Date patterns
    date_patterns = [
        r'Data[:\s]+(\d{4}[-/]\d{2}[-/]\d{2})',
        r'(\d{4}[-/]\d{2}[-/]\d{2})',
    ]
    for pat in date_patterns:
        m = re.search(pat, content)
        if m:
            results['date'] = m.group(1)
            break

    return results

# Get recent documents
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/documents/?page_size=15&ordering=-added",
    headers=headers
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

print(f"Analyzing {len(data['results'])} recent documents...\n")

for doc in data['results'][:15]:
    doc_id = doc['id']
    full_doc = get_doc(doc_id)
    content = full_doc.get('content', '')

    print("=" * 70)
    print(f"ID {doc_id}: {doc['title'][:55]}")
    print(f"  File: {doc.get('original_file_name', '')[:55]}")
    print(f"  Custom fields filled: {len([cf for cf in doc.get('custom_fields', []) if cf.get('value')])}")

    # Extract values
    extracted = extract_values(content)
    if extracted:
        print(f"  EXTRACTED:")
        for k, v in extracted.items():
            print(f"    {k}: {v}")
    else:
        print(f"  EXTRACTED: (nothing matched)")

    # Show first few lines of content
    lines = [l.strip() for l in content.split('\n') if l.strip()][:5]
    print(f"  Content preview: {' | '.join(lines)[:100]}...")
    print()
