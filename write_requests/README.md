# Audited write queue

A configured private deployment may place one JSON request at a time under:

```text
write_requests/pending/
```

The write workflow moves the request into a completed or failed receipt after
processing.

This reusable upstream intentionally contains no real pending requests,
receipts, item keys, annotation keys, or library versions.

Synthetic request shape:

```json
{
  "schema_version": 1,
  "request_id": "example-add-tags",
  "operation": "add_tags",
  "target": {
    "item_key": "ITEM0001"
  },
  "expected": {
    "item_version": 1
  },
  "payload": {
    "tags": ["example"]
  },
  "human_confirmation": {
    "explicit": true,
    "summary": "Synthetic example only"
  }
}
```
