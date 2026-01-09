# PaperSqueeze Custom Fields

Canonical field naming for Paperless-ngx integration.

## Financial

| Key | Paperless Field | Type | Description |
|-----|-----------------|------|-------------|
| total_gross | `amt_primary` | monetary | Primary amount (universal) |
| total_net | `gen_total_net` | monetary | Net amount before VAT |
| total_vat | `gen_total_vat` | monetary | VAT amount |

## Identifiers

| Key | Paperless Field | Type | Description |
|-----|-----------------|------|-------------|
| invoice_number | `gen_number` | string | Document reference number |
| nif | `gen_supplier_nif` | string | Supplier tax ID (9 digits) |
| contract_ref | `gen_contract_ref` | string | Contract or reference number |

## Payment

| Key | Paperless Field | Type | Description |
|-----|-----------------|------|-------------|
| mb_entity | `pay_mb_entity` | string | MB entity code |
| mb_ref | `pay_mb_ref` | string | MB reference |

## Dates

| Key | Paperless Field | Type | Description |
|-----|-----------------|------|-------------|
| issue_date | `gen_issue_date` | date | Document issue date |
| due_date | `pay_due_date` | date | Payment due date |
| period | `gen_period` | string | Billing/tax period |

## Metrics

| Key | Paperless Field | Type | Description |
|-----|-----------------|------|-------------|
| consumption | `gen_consumption` | string | Energy/water consumption |
| ref_extra | `gen_ref_extra` | string | Extra reference (kVA, CPE, plate) |

## Description

| Key | Paperless Field | Type | Description |
|-----|-----------------|------|-------------|
| short_desc | `gen_description` | string | General description |

---

## Naming Conventions

- `gen_*` - Generic fields used across document types
- `pay_*` - Payment-related fields
- `amt_*` - Monetary amounts
