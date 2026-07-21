# n8n Integration Guide

This document outlines how to integrate the Bheem AI Lead Qualification platform with **n8n** using the new Event-Driven Architecture.

## Architecture Overview
The FastAPI application serves as the core intelligence engine. It performs AI extraction, RAG querying, and natural language generation. 

It delegates all automation and orchestration to **n8n** by:
1. **Emitting Domain Events**: The system publishes versioned events (like `LeadUpdated`) to an internal Event Bus, which asynchronously POSTs them to an n8n webhook.
2. **Exposing Stable Automation APIs**: n8n can query state or issue commands back to the system using the `/api/v1` REST endpoints.

## 1. Subscribing to Events
To receive events from the platform, configure your n8n webhook URL in `config/company.yaml`:
```yaml
integrations:
  n8n:
    webhook_url: "http://n8n:5678/webhook/bheem-events"
```

### Event Payload Schema
Every event sent to the webhook follows the standard `DomainEvent` envelope:
```json
{
  "event_id": "c138b321-...",
  "event_type": "LeadUpdated",
  "event_version": "1.0",
  "occurred_at": "2026-07-20T10:15:30Z",
  "tenant": "default",
  "payload": {
    "phone_number": "1234567890",
    "name": "John Doe",
    "profile": { ... }
  }
}
```

### Available Events
- **`LeadUpdated` (v1.0)**: Emitted whenever the background extraction updates a field in a lead's profile.
- **`LeadQualified` (v1.0)**: Emitted when the AI determines that the lead profile is fully complete. Use this event in n8n to sync the lead to Salesforce, HubSpot, or a Google Sheet.
- **`KnowledgeRepositoryUpdated` (v1.0)**: Emitted when a knowledge base ingestion or index rebuild completes.

## 2. Issuing Commands (REST API)
n8n can interact with the intelligence layer using the following production-ready endpoints (Base URL: `http://fastapi-host/api/v1`):

### Queries
- `GET /health` - Basic health check.
- `GET /leads` - Returns a list of all known users/leads.
- `GET /leads/{phone_number}/profile` - Returns the structured `LeadField` profile and `is_complete` status.
- `GET /knowledge/status` - Returns RAG index metadata.

### Commands (Asynchronous)
These endpoints trigger background jobs and return immediately.
- `POST /knowledge/ingest?source_type=website&url=https://example.com` - Triggers a crawl and markdown extraction. Emits `KnowledgeRepositoryUpdated` upon completion.
- `POST /knowledge/rebuild` - Rebuilds the FAISS/Chroma index from the local markdown files. Emits `KnowledgeRepositoryUpdated` upon completion.

## 3. Example n8n Workflows

### 3.1 Lead Qualification CRM Sync
1. **Trigger**: Webhook node listening on `/webhook/bheem-events`.
2. **Switch Node**: Check if `{{ $json.body.event_type }}` is equal to `LeadQualified`.
3. **Action Node**: Transform `{{ $json.body.payload.profile }}` into CRM fields.
4. **HubSpot Node**: Create/Update Contact.

### 3.2 Scheduled Knowledge Base Refresh
1. **Trigger**: Cron node (e.g., Every Monday at 2 AM).
2. **HTTP Request Node**: `POST http://fastapi/api/v1/knowledge/ingest?source_type=website&url=https://client.com`.
3. **Wait Node**: Wait for Webhook event `KnowledgeRepositoryUpdated` (Action: rebuild).
4. **Email Node**: Send "Knowledge Base Successfully Refreshed" to the site administrator.
