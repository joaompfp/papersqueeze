# Paperless-ngx Setup Guide

Configuration steps for Paperless-ngx to work with PaperSqueeze.

**Note**: Steps marked with 🤖 can be automated via API during first run. Steps marked with 👤 require manual WebUI configuration.

---

## 1. Custom Fields 🤖

Create these custom fields in **Settings → Custom Fields**.

### Financial Fields

| Name | Data Type | Notes |
|------|-----------|-------|
| `amt_primary` | Monetary | Primary amount (required) |
| `gen_total_net` | Monetary | Net amount before VAT |
| `gen_total_vat` | Monetary | VAT amount |

### Identifier Fields

| Name | Data Type | Notes |
|------|-----------|-------|
| `gen_number` | Text | Document reference number |
| `gen_supplier_nif` | Text | Supplier tax ID (NIF) |
| `gen_contract_ref` | Text | Contract reference |

### Payment Fields

| Name | Data Type | Notes |
|------|-----------|-------|
| `pay_mb_entity` | Text | Multibanco entity |
| `pay_mb_ref` | Text | Multibanco reference |
| `pay_ref` | Text | Combined payment reference |
| `pay_due_date` | Date | Payment due date |

### Date & Period Fields

| Name | Data Type | Notes |
|------|-----------|-------|
| `gen_issue_date` | Date | Document issue date |
| `gen_period` | Text | Billing/tax period |

### Other Fields

| Name | Data Type | Notes |
|------|-----------|-------|
| `gen_consumption` | Text | Energy/water consumption |
| `gen_ref_extra` | Text | Extra reference (kVA, CPE, plate) |
| `gen_description` | Text | General description |

---

## 2. Document Types 🤖

Create in **Settings → Document Types**.

| Name | Notes |
|------|-------|
| `Fatura` | Invoices |
| `Recibo` | Receipts |
| `Declaração Fiscal` | Tax declarations |
| `Guia de Pagamento` | Payment guides |
| `Recibo de Vencimentos` | Payroll receipts |

---

## 3. Tags 🤖

Create in **Settings → Tags**.

### Workflow Tags

| Name | Color | Notes |
|------|-------|-------|
| `ai-processed` | Green | Successfully processed by AI |
| `ai-review-needed` | Yellow | Needs manual review |
| `ai-approved` | Blue | Manually approved after review |
| `ai-rejected` | Red | Rejected/incorrect extraction |

### Category Tags

| Name | Color | Notes |
|------|-------|-------|
| `utilities` | - | Utility bills |
| `car` | - | Vehicle-related |
| `tax` | - | Tax documents |
| `income` | - | Income documents |
| `accounting` | - | Accounting documents |

---

## 4. Correspondents 👤

Create correspondents as you encounter new suppliers. Common examples:

| Name | Notes |
|------|-------|
| `IBERDROLA` | Electricity |
| `EDP` | Electricity/Gas |
| `EPAL` | Water |
| `Autoridade Tributária` | Tax authority |
| `ANSR` | Traffic fines |

**Tip**: PaperSqueeze uses `correspondent_id` as primary template selector.

---

## 5. Post-Consume Hook 👤

Configure Paperless to call PaperSqueeze after document ingestion.

### Option A: Environment Variable

In your `docker-compose.yml`:

```yaml
environment:
  PAPERLESS_POST_CONSUME_SCRIPT: /usr/src/paperless/scripts/post_consume.sh
```

### Option B: paperless.conf

```
PAPERLESS_POST_CONSUME_SCRIPT=/usr/src/paperless/scripts/post_consume.sh
```

The `post_consume.sh` script receives `DOCUMENT_ID` as environment variable.

---

## 6. API Token 👤

Generate an API token for PaperSqueeze:

1. Go to **Settings → Users & Groups**
2. Click your user
3. Generate/copy **Auth Token**
4. Add to `config.yaml` or set `PAPERLESS_API_TOKEN` environment variable

---

## Verification Checklist

After setup, verify:

- [ ] All custom fields created (13 fields)
- [ ] Document types created (5 types)
- [ ] Tags created (9 tags)
- [ ] At least one correspondent exists
- [ ] Post-consume hook configured
- [ ] API token generated and configured
- [ ] Test document processes without errors

---

## Automation Note

On first run, PaperSqueeze can automatically create missing:
- Custom fields
- Document types
- Tags

Run `python -m papersqueeze --setup` to auto-create via API.

Correspondents must be created manually as they depend on your specific suppliers.
