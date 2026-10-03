export type Role = 'ADMIN' | 'USER' | 'READ_ONLY';

export interface UserOut {
  id: string;
  username: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserCreate {
  username: string;
  password: string;
  role: Role;
}

export interface UserUpdate {
  role?: Role | null;
  is_active?: boolean | null;
  password?: string | null;
}

export interface ChatRequest {
  question: string;
  model?: string | null;
  temperature?: number | null;
  use_rag?: boolean;
}

export interface Usage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
}

export interface Source {
  doc_id: string;
  title: string;
  chunk_index: number;
  score: number;
}

export interface ChatResponse {
  id: string;
  answer: string;
  provider: string;
  model: string;
  cached: boolean;
  usage: Usage;
  latency_ms: number;
  retries: number;
  fallback_used: boolean;
  sources: Source[];
}

export interface HistoryItem {
  id: string;
  user_id: string;
  question: string | null;
  answer: string | null;
  provider: string | null;
  model: string | null;
  cached: boolean;
  status: string;
  error_code: string | null;
  usage: Usage;
  latency_ms: number;
  retries: number;
  fallback_used: boolean;
  sources: Source[];
  created_at: string;
}

export interface DocumentCreate {
  title: string;
  text: string;
  source?: string | null;
}

export interface DocumentOut {
  doc_id: string;
  title: string;
  source?: string | null;
  chunk_count: number;
  created_by: string;
  created_at: string;
}

export interface SearchRequest {
  query: string;
  top_k?: number;
}

export interface SearchHit {
  doc_id: string;
  title: string;
  chunk_index: number;
  text: string;
  score: number;
}

export interface SearchResponse {
  results: SearchHit[];
}

export interface AuditEvent {
  id: string;
  actor_id: string;
  action: string;
  target_id?: string | null;
  changes?: Record<string, unknown> | null;
  created_at: string;
}

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'unhealthy';
  checks: {
    database: string;
    redis: string;
    llm: string;
    embeddings: string;
  };
  version: string;
}

export interface ReadyStatus {
  status: 'ready' | 'not_ready';
  checks: {
    database: string;
    redis: string;
  };
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id: string;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}
