# 🏠 Proppanda AI Chatbot

An intelligent real estate chatbot backend built with **FastAPI** + **LangGraph**. It helps users discover properties through natural conversation, collects lead information, and automatically notifies listing agents via email when a prospect shows interest.

---

## 🧠 How It Works

The chatbot is powered by a **LangGraph state machine** where each user message flows through a graph of specialised nodes:

```
User Message
     │
     ▼
  [Router]  ──────────────────────────────────────────────────────────┐
     │                                                               │
     ├── LOAD_USER_DATA  → collects email at conversation start      │
     ├── PROPERTY_SEARCH → [Extractor] → [Decision] → [Search]      │
     │                                              → [Display]     │
     ├── CHECK_CAPABILITY → verifies agent is enabled for table      │
     ├── RESET_MEMORY    → clears conversation state                 │
     └── INTELLIGENT_CHAT → answers property questions + sends leads ─┘
```

### Key Flows

| Flow | Description |
|------|-------------|
| **Property Search** | User describes what they want → filters extracted → DB queried → results shown |
| **Lead Collection** | When user asks about a shown property, bot collects name, nationality, pass type, phone, lease duration before answering |
| **Email Notification** | After lead details are saved, an HTML email is immediately fired to the listing agent in the background |
| **Intelligent Chat** | General Q&A, company policy questions, property detail follow-ups |

---

## 🗂️ Project Structure

```
proppanda-com-bot/
├── app/
│   ├── api/
│   │   ├── endpoints/
│   │   │   └── chat.py          # POST /chat, GET /agent/{id}, session endpoints
│   │   └── middleware/
│   │       └── api_key.py       # X-API-KEY header validation
│   ├── core/
│   │   ├── state.py             # AgentState TypedDict (LangGraph state)
│   │   └── agent_resolver.py    # Resolves agent from DB by ID
│   ├── db/
│   │   ├── models.py            # SQLAlchemy models (Agent, PropPandaLead, etc.)
│   │   └── repositories/
│   │       ├── agent_repository.py   # Fetch agents by ID / email
│   │       ├── leads_repository.py   # Upsert lead & agent interaction records
│   │       └── prospect_repository.py
│   ├── graphs/
│   │   ├── master_graph.py      # LangGraph workflow definition & routing
│   │   └── nodes/
│   │       ├── router.py        # Classifies user intent → next node
│   │       ├── load_user_data.py # Collects email at conversation start
│   │       ├── extractor.py     # Extracts search filters & demographics via GPT
│   │       ├── decision.py      # Decides what info is still missing
│   │       ├── generator.py     # Asks for missing fields conversationally
│   │       ├── search_tool.py   # Runs SQL property search
│   │       ├── display_results.py # Formats & returns property cards
│   │       ├── intelligent_chat.py # General Q&A + lead email trigger
│   │       ├── capability_check.py # Checks agent's enabled property types
│   │       └── clear_memory.py  # Resets search state
│   ├── schemas/
│   │   └── property_search.py   # PropertySearchFilters Pydantic model
│   ├── services/
│   │   ├── email_service.py     # SMTP email sender (background task)
│   │   ├── openai_service.py    # OpenAI client wrapper
│   │   └── query_builder.py     # Builds raw SQL for property searches
│   └── tools/
│       └── knowledge_base.py    # Searches agent's KB documents
├── demo.html                    # Standalone frontend for local testing
├── Dockerfile                   # Container definition for Azure deployment
├── requirements.txt
└── .env                         # Local secrets (never committed)
```

---

## ⚙️ Setup

### Prerequisites
- Python 3.11+
- PostgreSQL database (Supabase recommended)
- OpenAI API key
- Gmail account with App Password for SMTP

### 1. Clone & create virtual environment

```bash
git clone https://github.com/proppanda-genzi-hub/proppanda-com-bot.git
cd proppanda-com-bot
python -m venv env
# Windows
env\Scripts\activate
# macOS/Linux
source env/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
# PostgreSQL (use asyncpg driver)
DATABASE_URL=postgresql+asyncpg://user:password@host:port/dbname

# OpenAI
OPENAI_API_KEY=sk-...

# API Key for X-API-KEY middleware
API_KEY=your-secret-key-here

# LocationIQ geocoding (free tier)
LOCATION_IQ_KEY=pk.xxx

# SMTP — Gmail SSL (port 465)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
```

> 💡 **Gmail App Password:** Go to Google Account → Security → 2-Step Verification → App Passwords. Generate one for "Mail".

### 4. Run locally

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

Open `demo.html` in your browser to chat with the bot directly.

---

## 🔌 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/chat` | Send a message, get AI reply + properties |
| `GET`  | `/api/v1/chat/agent/{agent_id}` | Get agent info & capabilities |
| `POST` | `/api/v1/chat/session/new` | Create a new session ID |
| `POST` | `/api/v1/chat/session/history` | Retrieve message history |
| `GET`  | `/api/v1/chat/health` | Health check |

### Chat request example

```json
POST /api/v1/chat/chat
Headers: { "X-API-KEY": "your-secret-key-here" }

{
  "message": "I'm looking for a 2-bedroom condo to rent in Bugis",
  "agent_id": "agent_abc123",
  "session_id": "optional-uuid",
  "user_name": "Harsha"
}
```

### Chat response example

```json
{
  "response": "Great! I found 3 properties near Bugis...",
  "session_id": "uuid",
  "agent_id": "agent_abc123",
  "active_flow": null,
  "properties": [ { "condo_name": "...", "rental_price": 2800, ... } ]
}
```

---

## 🏗️ Supported Property Tables

| Table | Triggered by |
|-------|-------------|
| `coliving_property` | "co-living", "coliving", "flatmates" |
| `coliving_rooms` | "room for rent", "looking for a room", "HDB room" |
| `residential_properties_for_rent` | "whole unit", "3-bedroom", "condo rent", "studio" |
| `residential_properties_for_resale` | "buy HDB", "buy condo", "resale flat" |
| `residential_properties_for_sale_by_developers` | "new launch", "developer sale" |
| `commercial_properties_for_rent` | "office space", "shop for rent" |
| `commercial_properties_for_resale` | "buy office", "commercial for sale" |
| `commercial_properties_for_sale_by_developers` | "new commercial launch" |

---

## 📧 Lead Email Notifications

When a user asks about a listed property, the bot:

1. Asks for their **name, nationality, pass type, phone, and lease duration** (all in one message)
2. Saves the lead to `prop_panda_com_leads` in the database
3. Fires a **background email** to the listing agent with:
   - Prospect's personal details
   - Property they asked about
   - AI-generated conversation summary

Emails are sent via **Gmail SSL SMTP** (port 465) and never block the chat response.

---

## 🚀 Deployment (Azure)

The project includes a `Dockerfile` and `supervisord.conf` for containerised deployment.

```bash
# Build image
docker build -t proppanda-bot .

# Run container
docker run -p 8000:8000 --env-file .env proppanda-bot
```

For Azure Container Apps, push to the `azure-testing` branch to trigger CI/CD.

---

## 🔐 Security

- All endpoints protected by `X-API-KEY` header middleware
- `.env` is gitignored — never committed
- SMTP password stored only in environment variables
- Database credentials use Supabase connection pooling

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI |
| AI Orchestration | LangGraph + LangChain |
| LLM | OpenAI GPT-4o |
| Database | PostgreSQL (via SQLAlchemy async + asyncpg) |
| Email | Python `smtplib` / Gmail SSL |
| Geocoding | LocationIQ |
| Deployment | Docker + Azure Container Apps |
