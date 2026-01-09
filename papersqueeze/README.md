# PaperSqueeze

AI-powered document metadata enhancer for paperless-ngx.

```
+----------------------+     +----------------+     +------------------+
|      DOCUMENT        | --> |       AI       | --> |   PAPERLESS-NGX  |
|  +----------------+  |     |  +-----------+ |     |  +------------+  |
|  |  ###  OCR  ### |  |     |  | Classify  | |     |  | Title      |  |
|  |  -----------   |  |     |  | Extract   | |     |  | Tags       |  |
|  |  -----------   |  |     |  | Normalize | |     |  | Fields     |  |
|  +----------------+  |     |  +-----------+ |     |  +------------+  |
+----------------------+     +----------------+     +------------------+
```

**Version:** 0.1.0 (Proof of Concept)

## Philosophy

> **"Paperless-ngx is the source of truth. PaperSqueeze only fills gaps and suggests improvements."**

PaperSqueeze is an **assistant** to paperless-ngx's built-in AI classifiers, not a replacement. It:

- **Fills empty fields** when confident
- **Suggests changes** to existing values (queued for human review)
- **Never overwrites** existing metadata without review
- Uses a **confidence-based** approach to decide what to apply automatically

## Features

- **Smart merge strategy** - Respects existing paperless-ngx metadata
- **Two-model AI approach** - Fast classification (Haiku) + accurate extraction (Sonnet)
- **Review queue** - Changes to existing values go through human review
- **Confidence scoring** - Only applies changes when confident
- **Portuguese market focus** - Optimized for PT documents (utilities, tax, fines)
- **Ledger-style titles** - Clean, aligned document titles
- **Dry-run mode** - Test safely without applying changes

## Installation

## Relationship with paperless-ngx-postprocessor (IMPORTANT)

PaperSqueeze is designed to run after the document has been post-processed by the separate
`paperless-ngx-postprocessor` project in many deployments. In our typical setup the
`paperless-ngx-postprocessor` code sits next to `papersqueeze` in the same `scripts/`
mount on the host machine (for convenience), but it is a different project and should
not be edited as part of `papersqueeze`.

- Responsibility: Level-1 postprocessing (title/asn/date normalization and rule-based
  metadata fixes) is handled by the postprocessor. PaperSqueeze runs on the *outputs*
  of that step and performs AI-based extraction, merging and review.
- Files location: you may see a sibling folder named `paperless-ngx-postprocessor/`
  next to this repo when running inside a Paperless-ngx `scripts/` mount.
- Do NOT modify those files here: treat `paperless-ngx-postprocessor/` as an external
  project. Keep changes in `papersqueeze` only.

If you want to avoid accidental commits of the other project's files when developing
inside the shared `scripts/` folder, add the `paperless-ngx-postprocessor/` path to
your outer `.gitignore` (example below). This repository also ignores that folder by
default (see `.gitignore`).

Example ignore entry for the shared `scripts/` repo hosting both projects:

    paperless-ngx-postprocessor/


PaperSqueeze runs inside your paperless-ngx Docker container as a post-consume script.

### Prerequisites

Your paperless-ngx scripts folder should be mounted as a volume. Check your `docker-compose.yml`:

```yaml
volumes:
  - ./scripts:/usr/src/paperless/scripts
```

### 1. Clone into your scripts folder

```bash
# On your host machine, cd to your paperless scripts folder
cd /path/to/your/paperless/scripts

# Clone the repo
git clone https://github.com/YOUR_USERNAME/papersqueeze.git

# Or if scripts folder IS your mount point:
git clone https://github.com/YOUR_USERNAME/papersqueeze.git .
```

### 2. Install the only required dependency

```bash
# anthropic SDK is the ONLY new dependency
# (pydantic, pyyaml, httpx are already in paperless-ngx)
docker exec -it paperless-ngx pip install anthropic
```

**That's it!** One `pip install` command. The anthropic SDK pulls in httpx automatically.

### 3. Configure

Edit `/usr/src/paperless/scripts/config.yaml`:

```yaml
paperless:
  url: "http://localhost:8000/api"
  token: "${PAPERLESS_API_TOKEN}"  # Set this environment variable

anthropic:
  api_key: "${ANTHROPIC_API_KEY}"  # Set this environment variable

# Map your custom field names
fields:
  financial:
    total_gross: "Total Gross"  # Must match exactly
  # ...
```

### 4. Create required tags in paperless-ngx

Go to paperless-ngx Admin and create these tags:
- `ai-review-needed`
- `ai-approved`
- `ai-rejected`
- `ai-processed`

### 5. Set up post-consume hook

In your paperless-ngx `docker-compose.yml`, add environment variables:

```yaml
environment:
  PAPERLESS_POST_CONSUME_SCRIPT: /usr/src/paperless/scripts/post_consume.sh
  PAPERLESS_API_TOKEN: your-api-token
  ANTHROPIC_API_KEY: your-anthropic-key
```

Create `/usr/src/paperless/scripts/post_consume.sh`:

```bash
#!/bin/bash
cd /usr/src/paperless/scripts
python -m papersqueeze process "$DOCUMENT_ID"
```

## Usage

### Process a single document

```bash
# Inside the container
python -m papersqueeze process 123

# Dry run (see what would happen)
python -m papersqueeze process 123 --dry-run
```

### Process multiple documents

```bash
# By tag
python -m papersqueeze batch --tag "utilities"

# By correspondent
python -m papersqueeze batch --correspondent "IBERDROLA"

# Dry run
python -m papersqueeze batch --tag "inbox" --dry-run
```

### Review workflow

```bash
# List documents pending review
python -m papersqueeze review list

# Approve changes for a document
python -m papersqueeze review approve 123

# Reject changes
python -m papersqueeze review reject 123 --reason "Incorrect extraction"
```

### Check configuration

```bash
python -m papersqueeze info
```

## How It Works

### Processing Pipeline

```
Document arrives in paperless-ngx
        |
        v
[Post-consume hook triggers PaperSqueeze]
        |
        v
[Classify document type] (Haiku - fast/cheap)
   - utilities_energy
   - utilities_water
   - tax_at_guides
   - law_enforcement_fines
   - fallback_general
        |
        v
[Extract metadata] (Sonnet - accurate)
   - issue_date, total_gross, invoice_number, etc.
   - Each field has a confidence score
        |
        v
[Normalize data]
   - Dates -> YYYY-MM-DD
   - Amounts -> 1234.56 (no currency symbols)
   - Clean up regional formatting
        |
        v
[Smart merge with existing metadata]
   - Empty field + confident AI -> AUTO-APPLY
   - Empty field + low confidence -> NEEDS REVIEW
   - Existing value + AI agrees -> KEEP EXISTING
   - Existing value + AI disagrees (high conf) -> NEEDS REVIEW
   - Existing value + AI disagrees (low conf) -> KEEP EXISTING
        |
        v
[Apply or queue for review]
   - Auto-apply: Update document, tag "ai-processed"
   - Review: Tag "ai-review-needed", store proposed changes
```

### Confidence Thresholds

| Threshold | Default | Purpose |
|-----------|---------|---------|
| `confidence_threshold` | 0.7 | Minimum to auto-fill empty fields |
| `review_threshold` | 0.9 | Minimum to suggest overwriting existing |

### Title Formatting

PaperSqueeze generates Ledger-style titles:

```
2025-01-15 | Contr. 6.9 kVA | 150 kWh | 45.67 EUR
2025-01-10 | CPE 12345 | 8 m³ | 23.45 EUR
2025-01-05 | AT (Tax) | DMR 2025/01 | 150.00 EUR
```

## Configuration

### config.yaml

```yaml
# Paperless-ngx connection
paperless:
  url: "${PAPERLESS_URL:http://localhost:8000/api}"
  token: "${PAPERLESS_API_TOKEN}"

# Anthropic Claude
anthropic:
  api_key: "${ANTHROPIC_API_KEY}"
  gatekeeper_model: "claude-haiku-4-5-20250514"
  specialist_model: "claude-sonnet-4-20250514"

# Processing behavior
processing:
  confidence_threshold: 0.7
  review_threshold: 0.9
  dry_run: false

# Custom field mapping (by NAME, not ID)
fields:
  financial:
    total_gross: "Total Gross"
  identifiers:
    invoice_number: "Invoice Number"
  dates:
    issue_date: "Issue Date"
```

### templates.yaml

Define document types and extraction rules:

```yaml
templates:
  - id: "utilities_energy"
    description: "Electricity invoices"
    document_type: "Invoice"
    extraction:
      rules: "Extract consumption in kWh..."
      fields:
        - name: consumption_kwh
          type: number
          required: false
    field_mapping:
      consumption_kwh: "Consumption"
    title_format: "{issue_date} | {consumption_kwh} kWh | {total_gross} EUR"
```

## Development

### Setup

```bash
# Clone the repo
git clone https://github.com/your-repo/papersqueeze.git
cd papersqueeze

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

### Run tests

```bash
pytest
pytest --cov=papersqueeze  # with coverage
```

### Code quality

```bash
ruff check src/
mypy src/
```

## Project Structure

```
papersqueeze/
├── pyproject.toml
├── config/
│   ├── config.example.yaml
│   └── templates.example.yaml
├── src/papersqueeze/
│   ├── __init__.py
│   ├── cli.py              # Click CLI
│   ├── exceptions.py       # Custom exceptions
│   ├── api/
│   │   ├── paperless.py    # Paperless-ngx client
│   │   └── claude.py       # Anthropic SDK client
│   ├── config/
│   │   ├── schema.py       # Pydantic models
│   │   └── loader.py       # YAML + env loader
│   ├── models/
│   │   ├── document.py     # Document models
│   │   └── extraction.py   # AI extraction models
│   ├── processors/         # Document type handlers
│   ├── services/
│   │   ├── processor.py    # Main orchestrator
│   │   ├── merge.py        # Smart merge logic
│   │   ├── confidence.py   # Confidence scoring
│   │   └── review.py       # Review queue
│   └── utils/
│       ├── normalization.py
│       └── formatting.py
└── tests/
```

## Migration from v2.x

If you were using the previous version:

1. **Create new config files** from the examples
2. **Map your custom fields** by NAME (not numeric ID)
3. **Create the new review tags** in paperless-ngx
4. **Existing documents** keep their metadata - no re-processing needed
5. Use `--dry-run` to test before applying changes

## License

GNU AGPL v3 - See [LICENSE](LICENSE)

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Support

- Issues: [GitHub Issues](https://github.com/your-repo/papersqueeze/issues)
- Documentation: This README + inline code comments
