# 🏋️ Bheem — WhatsApp AI Customer Support Chatbot

A production-ready WhatsApp chatbot powered by RAG (Retrieval-Augmented Generation) for Placement & Training Services. Built with **FastAPI**, **SQLite**, **ChromaDB**, and a pluggable LLM provider.

---

## ✨ Features

- **WhatsApp Integration** — Full Meta Cloud API support (webhook verification, message handling, read receipts)
- **RAG Pipeline** — Answers questions using your company documents, never hallucinates
- **Conversation Memory** — Remembers context within a session, auto-expires after configurable timeout
- **User Management** — Identifies users by phone number, captures and remembers names
- **Mock LLM Provider** — Test the entire pipeline locally without any API keys
- **Admin Dashboard** — View users, conversations, and stats via REST endpoints
- **Test Chat Endpoint** — Chat with the bot via HTTP without needing WhatsApp
- **Document Ingestion** — Drop PDFs, DOCX, or TXT files into `knowledge_base/` and ingest
- **Structured Logging** — Console + rotating file logs for every interaction

---

## 📁 Project Structure

```
bheem/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app with lifespan events
│   ├── config.py               # Pydantic settings from .env
│   ├── api/
│   │   ├── routes.py           # Health, admin, test-chat endpoints
│   │   └── webhooks.py         # WhatsApp webhook handlers
│   ├── models/
│   │   ├── database.py         # SQLAlchemy ORM (User, Conversation, Message)
│   │   └── schemas.py          # Pydantic request/response schemas
│   ├── database/
│   │   ├── connection.py       # Async engine & session factory
│   │   └── crud.py             # All database operations
│   ├── services/
│   │   ├── whatsapp.py         # WhatsApp Cloud API client
│   │   ├── ai_service.py       # LLM provider interface (Mock + Antigravity)
│   │   ├── rag.py              # RAG pipeline (ChromaDB + embeddings)
│   │   └── chat.py             # Chat orchestrator
│   └── utils/
│       ├── logger.py           # Structured logging
│       └── document_loader.py  # PDF, DOCX, TXT parser + chunker
├── knowledge_base/             # Drop your company documents here
│   └── sample.txt              # Sample FAQ for testing
├── scripts/
│   └── ingest.py               # CLI to ingest documents
├── tests/
│   ├── test_api.py             # API endpoint tests
│   ├── test_chat.py            # Chat flow tests
│   └── test_rag.py             # RAG pipeline tests
├── data/                       # Created at runtime (DB, ChromaDB, logs)
├── .env.example                # Environment variable template
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── run.py                      # Entry point
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/HarshReddy10/bheem.git
cd bheem

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

For local testing, the defaults work out of the box (`LLM_PROVIDER=mock`).

### 3. Add Company Documents (Optional)

Drop your PDFs, DOCX, or TXT files into the `knowledge_base/` folder. A sample FAQ is included.

### 4. Run the Server

```bash
python run.py
```

The server starts at `http://localhost:8000`. Documents are auto-ingested on first startup.

### 5. Test the Chatbot

Open your browser at **http://localhost:8000/docs** for the interactive Swagger UI.

Or use curl:

```bash
# First message — bot asks for your name
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919876543210", "message": "Hello"}'

# Provide your name
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919876543210", "message": "Harsh"}'

# Ask a question
curl -X POST http://localhost:8000/api/test-chat \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "919876543210", "message": "What training programs do you offer?"}'
```

---

## 🔧 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | Bheem WhatsApp Chatbot | Application display name |
| `APP_ENV` | development | Environment (development/production) |
| `DEBUG` | true | Enable debug mode & hot reload |
| `HOST` | 0.0.0.0 | Server host |
| `PORT` | 8000 | Server port |
| `DATABASE_URL` | sqlite+aiosqlite:///./data/bheem.db | SQLite connection string |
| `LLM_PROVIDER` | mock | LLM provider: `mock` or `antigravity` |
| `ANTIGRAVITY_API_KEY` | — | Antigravity API key |
| `ANTIGRAVITY_API_URL` | — | Antigravity API endpoint |
| `ANTIGRAVITY_MODEL` | antigravity-default | Model name |
| `WHATSAPP_PHONE_NUMBER_ID` | — | Meta WhatsApp Phone Number ID |
| `WHATSAPP_ACCESS_TOKEN` | — | Meta WhatsApp Access Token |
| `WHATSAPP_VERIFY_TOKEN` | bheem_verify_token_2024 | Webhook verification token |
| `WHATSAPP_APP_SECRET` | — | Meta App Secret for signature verification (Mandatory in production; fails closed if unset/default) |
| `KNOWLEDGE_BASE_DIR` | ./knowledge_base | Directory with company documents |
| `RAG_TOP_K` | 5 | Number of chunks to retrieve |
| `RAG_CHUNK_SIZE` | 500 | Characters per chunk |
| `MAX_CONVERSATION_HISTORY` | 20 | Messages to include in LLM context |
| `CONVERSATION_TIMEOUT_HOURS` | 24 | Hours before starting a new conversation |

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Root — status & navigation |
| `GET` | `/api/health` | Health check with RAG status |
| `POST` | `/api/test-chat` | Chat without WhatsApp (for testing) |
| `GET` | `/api/admin/users` | List all users |
| `GET` | `/api/admin/conversations/{id}` | View a conversation |
| `GET` | `/api/admin/stats` | Database statistics |
| `POST` | `/api/admin/ingest` | Re-ingest knowledge base documents |
| `GET` | `/webhook` | WhatsApp webhook verification |
| `POST` | `/webhook` | WhatsApp incoming message handler |

---

## 🧪 Testing

```bash
# Install test dependencies (included in requirements.txt)
pip install pytest pytest-asyncio

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_api.py -v
pytest tests/test_chat.py -v
pytest tests/test_rag.py -v
```

---

## 📄 Document Ingestion

### Automatic (on startup)
Documents in `knowledge_base/` are auto-ingested when the server starts for the first time.

### Manual (CLI)
```bash
python scripts/ingest.py                    # Default directory
python scripts/ingest.py /path/to/docs      # Custom directory
```

### Via API
```bash
curl -X POST http://localhost:8000/api/admin/ingest
```

### Supported Formats
- `.txt` — Plain text
- `.md` — Markdown
- `.pdf` — PDF documents
- `.docx` — Microsoft Word

---

## 🔌 Connecting WhatsApp (Production)

1. Create a [Meta Developer App](https://developers.facebook.com/)
2. Set up WhatsApp Business API
3. Get your Phone Number ID, Access Token, and App Secret
4. Update `.env` with your credentials
5. Expose your server (e.g., via [ngrok](https://ngrok.com/)):
   ```bash
   ngrok http 8000
   ```
6. Set the webhook URL in Meta Dashboard to: `https://your-ngrok-url/webhook`
7. Set the Verify Token to match your `WHATSAPP_VERIFY_TOKEN`

---

## 🤖 Configuring the LLM Provider

Bheem supports pluggable LLM providers configured via the `LLM_PROVIDER` environment variable.

### 1. Google Gemini (Default)

We use the official Google Gemini SDK. To use Gemini:

1. Obtain a Gemini API Key from Google AI Studio.
2. Set `LLM_PROVIDER=gemini` in your `.env` file.
3. Configure your API key and model name:
   ```env
   GEMINI_API_KEY=your_actual_api_key
   GEMINI_MODEL=gemini-2.5-flash
   ```
4. Restart the server.

### 2. Antigravity (OpenAI-compatible)

To use Antigravity or any OpenAI-compatible API:

1. Set `LLM_PROVIDER=antigravity` in your `.env` file.
2. Configure your API endpoint and credentials:
   ```env
   ANTIGRAVITY_API_KEY=your_actual_api_key
   ANTIGRAVITY_API_URL=https://api.antigravity.example.com/v1
   ANTIGRAVITY_MODEL=antigravity-default
   ```
3. Restart the server.

### 3. Mock Provider (Offline Testing)

To test the chatbot flow entirely offline without making API calls or spending credits:
1. Set `LLM_PROVIDER=mock` in your `.env` file.
2. Restart the server.

---

## 🛣️ Future Improvements

- [ ] Rich message support (buttons, lists, media)
- [ ] Multi-language support
- [ ] Conversation export (CSV/JSON)
- [ ] Rate limiting & abuse protection
- [ ] Webhook retry & deduplication
- [ ] Admin web dashboard (React/Vue)
- [ ] Automated testing with CI/CD
- [ ] Docker containerization
- [ ] Analytics & conversation insights
- [ ] Human handoff escalation

---

## 📝 Architecture Decisions

| Decision | Rationale |
|---|---|
| **SQLite** | Zero-config, perfect for prototyping. Swap for PostgreSQL via `DATABASE_URL` when scaling. |
| **ChromaDB (embedded)** | No separate server needed. Persistent storage with cosine similarity. |
| **Abstract LLM provider** | Mock for testing, plug in any OpenAI-compatible API for production. |
| **Async FastAPI** | Non-blocking I/O for handling concurrent WhatsApp messages. |
| **Paragraph-based chunking** | Preserves semantic context better than fixed-character splits. |

---

## 📄 License

MIT
