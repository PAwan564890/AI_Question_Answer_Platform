import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { opsApi } from '../api/ops';
import { chatApi } from '../api/chat';
import { documentsApi } from '../api/documents';
import { DocumentOut, HealthStatus, HistoryItem } from '../types/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { SkeletonCard } from '../components/ui/Skeleton';
import {
  MessageSquare,
  Database,
  Clock,
  Activity,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Sparkles,
} from 'lucide-react';

export const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const loadDashboardData = async () => {
      setLoading(true);
      try {
        const [healthRes, historyRes, docsRes] = await Promise.allSettled([
          opsApi.getHealth(),
          chatApi.getHistory({ limit: 50 }),
          documentsApi.list({ limit: 50 }),
        ]);

        if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
        if (historyRes.status === 'fulfilled') setHistory(historyRes.value);
        if (docsRes.status === 'fulfilled') setDocuments(docsRes.value);
      } finally {
        setLoading(false);
      }
    };
    loadDashboardData();
  }, []);

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  };

  // Compute metrics from actual API data
  const totalQuestions = history.length;
  const todayStr = new Date().toISOString().split('T')[0];
  const questionsToday = history.filter((h) => h.created_at.startsWith(todayStr)).length;
  const avgLatency =
    history.length > 0
      ? Math.round(history.reduce((sum, item) => sum + item.latency_ms, 0) / history.length)
      : null;

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="p-6 bg-gradient-to-r from-cyan-950/40 via-slate-900 to-slate-900 border border-slate-800 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            {getGreeting()}, {user?.username}! <Sparkles className="w-5 h-5 text-amber-400" />
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Here is what's happening with your AI Question-Answering Infrastructure.
          </p>
        </div>
        <button
          onClick={() => navigate('/chat')}
          className="px-5 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold rounded-xl shadow-lg shadow-cyan-600/20 transition-all flex items-center gap-2 shrink-0 self-start md:self-auto"
        >
          <MessageSquare className="w-4 h-4" />
          <span>Ask AI Question</span>
        </button>
      </div>

      {/* Primary Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Questions</span>
                <div className="p-2 bg-cyan-500/10 text-cyan-400 rounded-xl">
                  <MessageSquare className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-slate-100">{totalQuestions}</span>
                <span className="text-xs text-slate-500">recorded</span>
              </div>
              <p className="text-xs text-slate-400">{questionsToday} asked today</p>
            </Card>

            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Knowledge Base</span>
                <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-xl">
                  <Database className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-slate-100">{documents.length}</span>
                <span className="text-xs text-slate-500">documents</span>
              </div>
              <p className="text-xs text-slate-400">Indexed in Qdrant Vector DB</p>
            </Card>

            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Avg Latency</span>
                <div className="p-2 bg-purple-500/10 text-purple-400 rounded-xl">
                  <Clock className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-slate-100">
                  {avgLatency !== null ? `${avgLatency} ms` : 'N/A'}
                </span>
              </div>
              <p className="text-xs text-slate-400">End-to-end processing speed</p>
            </Card>

            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">System Status</span>
                <div className="p-2 bg-amber-500/10 text-amber-400 rounded-xl">
                  <Activity className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    health?.status === 'ok'
                      ? 'green'
                      : health?.status === 'degraded'
                      ? 'amber'
                      : 'rose'
                  }
                  size="md"
                >
                  {health?.status ? health.status.toUpperCase() : 'N/A'}
                </Badge>
              </div>
              <p className="text-xs text-slate-400">API, Redis & Qdrant Checks</p>
            </Card>
          </>
        )}
      </div>

      {/* Main Dashboard Layout Grids */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* System Health Breakdown Card */}
        <Card className="lg:col-span-1 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span>Services Status</span>
            </h3>
            <button
              onClick={() => navigate('/health')}
              className="text-xs text-cyan-400 hover:underline flex items-center gap-1"
            >
              <span>View details</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          <div className="space-y-3">
            {health?.checks ? (
              Object.entries(health.checks).map(([key, val]) => (
                <div
                  key={key}
                  className="flex items-center justify-between p-3 bg-slate-900/50 border border-slate-800/80 rounded-xl text-xs"
                >
                  <span className="font-semibold text-slate-300 capitalize">{key}</span>
                  <div className="flex items-center gap-1.5 font-mono">
                    {val === 'ok' || val === 'mock' || val === 'hash' || val === 'configured' ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span className="text-emerald-400">{val}</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="w-4 h-4 text-amber-400" />
                        <span className="text-amber-400">{val}</span>
                      </>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500">Loading system status...</p>
            )}
          </div>
        </Card>

        {/* Recent Conversations Card */}
        <Card className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-cyan-400" />
              <span>Recent Conversations</span>
            </h3>
            <button
              onClick={() => navigate('/history')}
              className="text-xs text-cyan-400 hover:underline flex items-center gap-1"
            >
              <span>View all</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          <div className="space-y-3">
            {history.length > 0 ? (
              history.slice(0, 4).map((item) => (
                <div
                  key={item.id}
                  onClick={() => navigate('/chat', { state: { item } })}
                  className="p-3.5 bg-slate-900/50 border border-slate-800/80 hover:border-slate-700/80 rounded-xl cursor-pointer transition-all space-y-1.5"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-200 line-clamp-1">
                      {item.question || 'Untitled Question'}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 line-clamp-1">{item.answer || 'No answer recorded'}</p>
                  <div className="flex items-center gap-3 text-[10px] text-slate-500 pt-1 font-mono">
                    <span>Model: {item.model || 'mock'}</span>
                    <span>Latency: {item.latency_ms}ms</span>
                    <span>Sources: {item.sources?.length || 0}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="py-8 text-center text-xs text-slate-500">
                No recent conversations recorded. Start asking questions in the Chat!
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};
