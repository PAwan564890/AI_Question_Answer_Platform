# AI Question-Answering Platform — React Frontend

A production-grade, responsive AI SaaS Web Application built with **React, TypeScript, Vite, and Tailwind CSS**. Designed to connect directly to the Python + FastAPI + Qdrant + Redis AI Question-Answering Platform backend.

---

## Key Features

- **JWT Authentication & RBAC**: Role-based access control supporting `ADMIN`, `USER`, and `READ_ONLY` roles.
- **Interactive AI Chat**: Real-time Q&A interface with Markdown rendering, response latency indicators, token usage counts, and RAG citation panel.
- **Knowledge Base Management**: Upload/ingest documents, view vector chunk counts, search, and delete documents.
- **Dedicated Vector Search**: Direct semantic similarity search over Qdrant vector database with similarity score matching.
- **Chat History & Audit Logs**: Complete conversation log tracking and immutable administrative audit trail.
- **System Health & Metrics**: Live telemetry dashboard tracking API, Redis, Qdrant, and LLM gateway status alongside Prometheus metric visualizations.
- **Responsive & Accessible**: Command-center design with dark mode, collapsible sidebar, and full mobile support.

---

## Tech Stack

- **Framework**: React 18 & TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS v3
- **Icons**: Lucide React
- **Data Fetching**: TanStack React Query v5 & Axios
- **Routing**: React Router DOM v6
- **Notifications**: Sonner
- **Charts**: Recharts
- **Markdown**: react-markdown

---

## Getting Started

### Prerequisites

- **Node.js**: v18+ or v20+
- **npm**: v9+ or v10+
- **Running Backend**: FastAPI backend running at `http://localhost:8000`

### Installation

```bash
cd ai-qa-platform/frontend
npm install
```

### Environment Configuration

Create a `.env` file in the `frontend/` directory (or use `.env.example`):

```env
VITE_API_BASE_URL=http://localhost:8000
```

### Development Server

Start the Vite development server with proxy configured:

```bash
npm run dev
```

The application will start at `http://localhost:5173`.

### Production Build

Build static assets for production deployment:

```bash
npm run build
```

Preview the production build locally:

```bash
npm run preview
```

---

## Docker Deployment

Build and run the frontend using Docker:

```bash
# Build Docker image
docker build -t ai-qa-frontend .

# Run container on port 3000
docker run -d -p 3000:80 --name ai-qa-frontend ai-qa-frontend
```

---

## API Endpoints Integrated

| Feature | Endpoint | Method | Role Required |
|---|---|---|---|
| Login | `/auth/login` | `POST` | Public |
| Current User | `/auth/me` | `GET` | Authenticated |
| Ask AI Question | `/chat` | `POST` | ADMIN, USER |
| Chat History | `/chat/history` | `GET` | Authenticated |
| List Documents | `/documents` | `GET` | Authenticated |
| Ingest Document | `/documents` | `POST` | ADMIN |
| Vector Search | `/documents/search` | `POST` | Authenticated |
| Delete Document | `/documents/{doc_id}` | `DELETE` | ADMIN |
| List Users | `/admin/users` | `GET` | ADMIN |
| Create User | `/admin/users` | `POST` | ADMIN |
| Update User | `/admin/users/{user_id}` | `PATCH` | ADMIN |
| Audit Logs | `/admin/audit` | `GET` | ADMIN |
| Health Check | `/health` | `GET` | Public |
| Readiness Check | `/health/ready` | `GET` | Public |
| Prometheus Metrics | `/metrics` | `GET` | ADMIN |
