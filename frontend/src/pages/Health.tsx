import React, { useState, useEffect } from 'react';
import { opsApi } from '../api/ops';
import { HealthStatus, ReadyStatus } from '../types/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { SkeletonCard } from '../components/ui/Skeleton';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Server,
  Database,
  Cpu,
  Zap,
  Info,
} from 'lucide-react';
import { toast } from 'sonner';

export const Health: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastChecked, setLastChecked] = useState<string>('');

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const [hRes, rRes] = await Promise.all([opsApi.getHealth(), opsApi.getReady()]);
      setHealth(hRes);
      setReady(rRes);
      setLastChecked(new Date().toLocaleTimeString());
    } catch {
      toast.error('Failed to update system health status.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const overallStatus = health?.status || 'unhealthy';

  const statusBg = {
    ok: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    degraded: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
    unhealthy: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            <span>System Health & Readiness</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Real-time status of application backend, database, cache, and model provider integrations.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-mono hidden sm:inline">
            Last checked: {lastChecked || 'Just now'}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchHealth}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Overall Health Status Card */}
      <Card className={`p-6 border ${statusBg[overallStatus]}`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-slate-950/60 rounded-2xl border border-current">
              {overallStatus === 'ok' ? (
                <CheckCircle2 className="w-8 h-8 text-emerald-400" />
              ) : overallStatus === 'degraded' ? (
                <AlertTriangle className="w-8 h-8 text-amber-400" />
              ) : (
                <XCircle className="w-8 h-8 text-rose-400" />
              )}
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider block opacity-80">
                System Status
              </span>
              <h3 className="text-2xl font-extrabold capitalize">{overallStatus}</h3>
            </div>
          </div>

          <div className="flex items-center gap-3 font-mono text-xs">
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 text-slate-300">
              <span>Readiness: </span>
              <span className="font-bold text-cyan-400">{ready?.status || 'N/A'}</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 text-slate-300">
              <span>Version: </span>
              <span className="font-bold text-cyan-400">{health?.version || '1.0.0'}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Dependency Components Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading && !health ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            {/* FastAPI Gateway */}
            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">FastAPI Tier</span>
                <div className="p-2 bg-cyan-500/10 text-cyan-400 rounded-xl">
                  <Server className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-200">REST API Gateway</span>
                <Badge variant="green" size="md">OK</Badge>
              </div>
              <p className="text-xs text-slate-400">Stateless Python API handling JWT & rate limiting</p>
            </Card>

            {/* Qdrant Vector Database */}
            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Qdrant Database</span>
                <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-xl">
                  <Database className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-200">Vector Storage</span>
                <Badge
                  variant={health?.checks.database === 'ok' ? 'green' : 'rose'}
                  size="md"
                >
                  {health?.checks.database?.toUpperCase() || 'FAIL'}
                </Badge>
              </div>
              <p className="text-xs text-slate-400">Stores document vectors, users, and audit events</p>
            </Card>

            {/* Redis Cache */}
            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Redis Cache</span>
                <div className="p-2 bg-rose-500/10 text-rose-400 rounded-xl">
                  <Zap className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-200">Rate Limiter & Cache</span>
                <Badge
                  variant={health?.checks.redis === 'ok' ? 'green' : 'amber'}
                  size="md"
                >
                  {health?.checks.redis?.toUpperCase() || 'FAIL'}
                </Badge>
              </div>
              <p className="text-xs text-slate-400">Atomic login throttle & shared response cache</p>
            </Card>

            {/* LLM Gateway */}
            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">LLM Provider</span>
                <div className="p-2 bg-purple-500/10 text-purple-400 rounded-xl">
                  <Cpu className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-200">LLM Adapter</span>
                <Badge variant="cyan" size="md">
                  {health?.checks.llm || 'mock'}
                </Badge>
              </div>
              <p className="text-xs text-slate-400">Gateway provider with bounded retries & backoff</p>
            </Card>

            {/* Embeddings Provider */}
            <Card hoverable className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Embedding Engine</span>
                <div className="p-2 bg-amber-500/10 text-amber-400 rounded-xl">
                  <Activity className="w-5 h-5" />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-200">Embedder</span>
                <Badge variant="amber" size="md">
                  {health?.checks.embeddings || 'hash'}
                </Badge>
              </div>
              <p className="text-xs text-slate-400">Lexical / Semantic text chunk embedder</p>
            </Card>
          </>
        )}
      </div>
    </div>
  );
};
