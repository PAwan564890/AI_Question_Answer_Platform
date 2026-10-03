import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { useAuth } from '../context/AuthContext';
import { chatApi } from '../api/chat';
import { ChatResponse, HistoryItem, Source } from '../types/api';
import { CustomApiError } from '../api/client';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import {
  Send,
  Bot,
  User as UserIcon,
  Copy,
  Check,
  Sparkles,
  FileText,
  Clock,
  Layers,
  Sliders,
  History as HistoryIcon,
  BookOpen,
  Info,
  AlertCircle,
  Loader2,
  Cpu,
  Server,
  Zap,
} from 'lucide-react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: string;
  response?: ChatResponse;
  error?: string;
}

export const Chat: React.FC = () => {
  const { user, role } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [useRag, setUseRag] = useState<boolean>(true);
  const [model, setModel] = useState<string>('');
  const [temperature, setTemperature] = useState<number>(0.7);
  const [showSettings, setShowSettings] = useState<boolean>(false);

  // Active message ID for displaying RAG context sources in the right sidebar
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);

  // History list for left sidebar
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const canSendChat = role === 'ADMIN' || role === 'USER';

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try {
      const history = await chatApi.getHistory({ limit: 20 });
      setHistoryItems(history);
    } catch {
      // Ignore background history fetch errors
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  /**
   * Core function handling user message submission.
   * Directly invokes `POST /chat` endpoint via Axios client (`chatApi.ask`).
   * No client-side mock data or hardcoded answers exist here.
   */
  const handleSend = async (customQuestion?: string) => {
    const textToSend = customQuestion || question;
    if (!textToSend.trim() || isLoading) return;

    const userMessageId = `user-${Date.now()}`;
    const newMsg: ChatMessage = {
      id: userMessageId,
      sender: 'user',
      text: textToSend.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, newMsg]);
    if (!customQuestion) setQuestion('');
    setIsLoading(true);

    try {
      // Send HTTP POST request to FastAPI /chat endpoint with Bearer JWT token
      const response = await chatApi.ask({
        question: textToSend.trim(),
        model: model.trim() || undefined,
        temperature: temperature,
        use_rag: useRag,
      });

      const aiMsg: ChatMessage = {
        id: response.id,
        sender: 'ai',
        text: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        response: response,
      };

      setMessages((prev) => [...prev, aiMsg]);
      setSelectedMessageId(response.id);
      fetchHistory();
    } catch (err) {
      let errMsg = 'Failed to generate answer from FastAPI backend.';
      if (err instanceof CustomApiError) {
        if (err.code === 'FORBIDDEN') {
          errMsg = 'Your account role (READ_ONLY) does not have permission to execute LLM queries.';
        } else if (err.code === 'RATE_LIMITED') {
          errMsg = 'Chat rate limit exceeded. Please wait before sending another request.';
        } else {
          errMsg = err.message || errMsg;
        }
      }
      const aiMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        sender: 'ai',
        text: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        error: errMsg,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Active message details for right context panel
  const activeMessage = messages.find((m) => m.id === selectedMessageId && m.sender === 'ai');
  const activeSources: Source[] = activeMessage?.response?.sources || [];
  const activeResponse = activeMessage?.response;

  const loadHistoryConversation = (item: HistoryItem) => {
    if (!item.question) return;
    setMessages([
      {
        id: `h-user-${item.id}`,
        sender: 'user',
        text: item.question,
        timestamp: new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
      {
        id: item.id,
        sender: 'ai',
        text: item.answer || '',
        timestamp: new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        response: {
          id: item.id,
          answer: item.answer || '',
          provider: item.provider || 'mock',
          model: item.model || 'mock-1',
          cached: item.cached,
          usage: item.usage,
          latency_ms: item.latency_ms,
          retries: item.retries,
          fallback_used: item.fallback_used,
          sources: item.sources,
        },
      },
    ]);
    setSelectedMessageId(item.id);
  };

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col md:flex-row gap-4 overflow-hidden">
      {/* LEFT: History Sidebar */}
      <div className="w-full md:w-64 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-3 flex flex-col shrink-0 hidden lg:flex">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800 px-2">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <HistoryIcon className="w-4 h-4 text-cyan-400" />
            <span>Recent Conversations</span>
          </h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setMessages([]);
              setSelectedMessageId(null);
            }}
            className="text-[11px] text-cyan-400 hover:text-cyan-300"
          >
            + New
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-1.5 pt-3 pr-1">
          {historyItems.length > 0 ? (
            historyItems.map((item) => (
              <button
                key={item.id}
                onClick={() => loadHistoryConversation(item)}
                className="w-full text-left p-2.5 rounded-xl text-xs hover:bg-slate-800/60 transition-colors border border-transparent hover:border-slate-700/60 space-y-1 group"
              >
                <p className="font-semibold text-slate-200 line-clamp-1 group-hover:text-cyan-400 transition-colors">
                  {item.question || 'Untitled Question'}
                </p>
                <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                  <span>{new Date(item.created_at).toLocaleDateString()}</span>
                  <span>{item.latency_ms}ms</span>
                </div>
              </button>
            ))
          ) : (
            <p className="text-xs text-slate-500 text-center py-6">No chat records stored in backend</p>
          )}
        </div>
      </div>

      {/* CENTER: Main Chat Conversation */}
      <div className="flex-1 bg-slate-900/80 border border-slate-800/80 rounded-2xl flex flex-col min-w-0 overflow-hidden shadow-xl">
        {/* Chat Control Bar */}
        <div className="p-3 border-b border-slate-800/80 bg-slate-900/90 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-cyan-500/10 text-cyan-400 rounded-xl">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                FastAPI Chat Endpoint
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              </h2>
              <p className="text-[11px] text-slate-400 font-mono">Connected to `POST /chat` with Bearer JWT</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* RAG Toggle */}
            <button
              onClick={() => setUseRag(!useRag)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
                useRag
                  ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>RAG: {useRag ? 'ON' : 'OFF'}</span>
            </button>

            {/* Config button */}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-2 text-slate-400 hover:text-slate-100 bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 rounded-xl transition-colors"
              title="LLM Settings"
            >
              <Sliders className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Optional LLM Parameter Drawer */}
        {showSettings && (
          <div className="p-3.5 bg-slate-950 border-b border-slate-800 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs animate-fade-in">
            <div>
              <label className="block text-slate-400 font-medium mb-1">Custom Model Name</label>
              <input
                type="text"
                placeholder="Default backend model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-slate-400 font-medium mb-1">Temperature ({temperature})</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-cyan-500"
              />
            </div>
          </div>
        )}

        {/* Backend Provider Status Bar */}
        {activeResponse && (
          <div className="px-4 py-2 bg-slate-950/90 border-b border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span>Backend Returned Provider:</span>
              <Badge variant={activeResponse.provider === 'mock' ? 'cyan' : 'green'} size="sm">
                {activeResponse.provider} ({activeResponse.model})
              </Badge>
            </div>
            {activeResponse.provider === 'mock' && (
              <span className="text-slate-500 hidden md:inline">
                (FastAPI backend is using MockLlmAdapter. Set LLM_PROVIDER=openai_compatible in backend .env to call live LLMs)
              </span>
            )}
          </div>
        )}

        {/* Chat Timeline */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4">
              <div className="p-4 bg-cyan-500/10 text-cyan-400 rounded-2xl border border-cyan-500/20">
                <Sparkles className="w-8 h-8" />
              </div>
              <h3 className="text-base font-semibold text-slate-200">Ask the AI Question-Answering Platform</h3>
              <p className="text-xs text-slate-400 max-w-md">
                Questions are sent to the FastAPI backend (`POST /chat`). The system retrieves relevant vector context from Qdrant and generates an answer.
              </p>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.sender === 'ai' && (
                  <div className="w-8 h-8 rounded-xl bg-cyan-600/20 text-cyan-400 flex items-center justify-center shrink-0 border border-cyan-500/30 text-xs font-bold mt-1">
                    <Bot className="w-4 h-4" />
                  </div>
                )}

                <div className={`max-w-2xl space-y-2 ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                  {/* Bubble Container */}
                  <div
                    onClick={() => msg.sender === 'ai' && setSelectedMessageId(msg.id)}
                    className={`p-4 rounded-2xl text-sm leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-cyan-600 text-white rounded-tr-none shadow-md shadow-cyan-600/20'
                        : 'bg-slate-900 border border-slate-800 text-slate-100 rounded-tl-none hover:border-slate-700/80 cursor-pointer transition-colors'
                    }`}
                  >
                    {msg.sender === 'user' ? (
                      <p className="whitespace-pre-wrap">{msg.text}</p>
                    ) : msg.error ? (
                      <div className="flex items-start gap-2.5 text-rose-400 text-xs">
                        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>{msg.error}</span>
                      </div>
                    ) : (
                      <div className="prose prose-invert max-w-none text-slate-200 text-sm">
                        <ReactMarkdown>{msg.text}</ReactMarkdown>
                      </div>
                    )}
                  </div>

                  {/* Real Metadata Returned by FastAPI */}
                  {msg.sender === 'ai' && msg.response && (
                    <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400 px-1 font-mono">
                      <span className="flex items-center gap-1" title="Real processing latency returned by FastAPI">
                        <Clock className="w-3 h-3 text-slate-500" />
                        {msg.response.latency_ms} ms
                      </span>

                      {/* Display token metrics or Redis cache hit notice */}
                      {msg.response.cached ? (
                        <span className="flex items-center gap-1 text-purple-400" title="Served directly from Redis response cache">
                          <Zap className="w-3 h-3" />
                          Redis Cache Hit (0 tokens spent)
                        </span>
                      ) : msg.response.usage?.total_tokens !== null && msg.response.usage?.total_tokens !== undefined ? (
                        <span className="flex items-center gap-1" title="Total tokens consumed">
                          <Layers className="w-3 h-3 text-slate-500" />
                          {msg.response.usage.total_tokens} tokens
                        </span>
                      ) : null}

                      {msg.response.fallback_used && <Badge variant="amber" size="sm">Fallback Adapter Used</Badge>}

                      {msg.response.sources && msg.response.sources.length > 0 && (
                        <button
                          onClick={() => setSelectedMessageId(msg.id)}
                          className="flex items-center gap-1 text-cyan-400 hover:underline font-medium"
                        >
                          <FileText className="w-3 h-3" />
                          {msg.response.sources.length} Cited Sources
                        </button>
                      )}

                      <button
                        onClick={() => copyToClipboard(msg.text, msg.id)}
                        className="ml-auto hover:text-slate-200 flex items-center gap-1 transition-colors"
                        title="Copy answer text"
                      >
                        {copiedId === msg.id ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>
                  )}
                </div>

                {msg.sender === 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-slate-800 text-slate-300 flex items-center justify-center shrink-0 border border-slate-700 text-xs font-bold mt-1">
                    {user?.username ? user.username.substring(0, 2).toUpperCase() : <UserIcon className="w-4 h-4" />}
                  </div>
                )}
              </div>
            ))
          )}

          {isLoading && (
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-xl bg-cyan-600/20 text-cyan-400 flex items-center justify-center shrink-0 border border-cyan-500/30">
                <Loader2 className="w-4 h-4 animate-spin" />
              </div>
              <div className="px-4 py-3 bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-none text-xs text-slate-400 flex items-center gap-2">
                <span className="font-semibold text-cyan-400">FastAPI processing</span>
                <span className="animate-pulse">Calling POST /chat & retrieving Qdrant context...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Composer */}
        <div className="p-3 border-t border-slate-800 bg-slate-900/90">
          {!canSendChat && (
            <div className="mb-2 p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300 font-medium flex items-center gap-2">
              <Info className="w-4 h-4 shrink-0" />
              <span>Your account role (READ_ONLY) permits document search but not AI chat generation.</span>
            </div>
          )}

          <div className="flex items-end gap-2 bg-slate-950 border border-slate-800 rounded-xl p-2 focus-within:border-cyan-500 transition-colors">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={canSendChat ? "Ask your question... (Press Enter to send, Shift+Enter for new line)" : "Chat disabled for READ_ONLY role"}
              disabled={!canSendChat || isLoading}
              rows={2}
              className="flex-1 bg-transparent border-0 resize-none text-slate-100 placeholder-slate-500 text-sm focus:outline-none p-1"
            />
            <Button
              onClick={() => handleSend()}
              disabled={!canSendChat || !question.trim() || isLoading}
              isLoading={isLoading}
              size="sm"
              icon={<Send className="w-4 h-4" />}
            >
              Send
            </Button>
          </div>
        </div>
      </div>

      {/* RIGHT: RAG Sources & Context Inspection Panel */}
      <div className="w-full md:w-80 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4 flex flex-col shrink-0">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-cyan-400" />
            <span>Retrieved RAG Sources</span>
          </h3>
          <Badge variant="cyan" size="sm">{activeSources.length} Documents</Badge>
        </div>

        {activeResponse && (
          <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl mb-3 space-y-1 font-mono text-[11px]">
            <div className="flex justify-between text-slate-400">
              <span>Provider:</span>
              <span className="text-slate-200 font-semibold">{activeResponse.provider}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Model:</span>
              <span className="text-slate-200 font-semibold">{activeResponse.model}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Latency:</span>
              <span className="text-slate-200 font-semibold">{activeResponse.latency_ms} ms</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Cached:</span>
              <span className="text-purple-400 font-semibold">{activeResponse.cached ? 'Yes (Redis)' : 'No'}</span>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {activeSources.length > 0 ? (
            activeSources.map((source, index) => (
              <Card key={index} className="p-3 space-y-2 bg-slate-950/70 border-slate-800">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-bold text-slate-200 line-clamp-1">{source.title}</span>
                  <Badge variant="green" size="sm">{(source.score * 100).toFixed(1)}%</Badge>
                </div>

                <div className="text-[11px] text-slate-400 space-y-1 font-mono">
                  <p>Chunk Index: {source.chunk_index}</p>
                  <p className="text-[10px] text-slate-500 truncate">Doc ID: {source.doc_id}</p>
                </div>
              </Card>
            ))
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center p-4 space-y-2 text-slate-500">
              <FileText className="w-8 h-8 stroke-1 text-slate-600" />
              <p className="text-xs">
                {activeResponse
                  ? 'No documents in the knowledge base matched this question above the score threshold.'
                  : 'Select an AI answer to inspect the cited knowledge base sources and similarity scores.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
