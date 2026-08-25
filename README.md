# WhatsApp Business AI Agent

Automated WhatsApp business agent featuring n8n workflow integration, Razorpay payments, and AI-driven conversational knowledge retrieval (RAG).

## Overview

A production-ready WhatsApp chatbot powered by RAG for customer support and lead automation. Built with FastAPI, SQLite, and ChromaDB, the system handles end-to-end user interactions via the Meta Cloud API. It features dynamic document ingestion for the knowledge base, conversational memory, workflow automation via n8n, and integrated payment processing via Razorpay.

## Tech Stack

Python · FastAPI · WhatsApp API · n8n · Razorpay · ChromaDB · SQLite

## Key Features

- **WhatsApp Meta Integration:** Full API support including webhook verification, message handling, and read receipts.
- **RAG Pipeline:** Accurate answers grounded entirely in uploaded company documents (PDF, DOCX, TXT), powered by ChromaDB.
- **Workflow Automation:** Complex business logic orchestration using n8n for lead qualification and outcome tracking.
- **Payment Processing:** Integrated with Razorpay to seamlessly handle customer transactions directly via chat.
- **Conversation Memory:** Context-aware session management with automated timeout and user profile capture.

## Getting Started

```bash
# Setup virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the API
python run.py
```
