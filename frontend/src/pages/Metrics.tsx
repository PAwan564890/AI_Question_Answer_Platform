import React, { useState, useEffect } from 'react';
import { opsApi } from '../api/ops';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { SkeletonCard } from '../components/ui/Skeleton';
import { BarChart3, RefreshCw, FileCode2, Activity, Layers, Zap } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { toast } from 'sonner';

export const Metrics: React.FC = () => {
  const [rawMetrics, setRawMetrics] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'raw'>('dashboard');

  const fetchMetrics = async () => {
    setLoading(true);
    try {
      const data = await opsApi.getMetrics();
      setRawMetrics(data);
    } catch {
      toast.error('Failed to fetch Prometheus metrics (Admin access required).');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
  }, []);

  // Basic parser for Prometheus text format to extract key metrics
  const parsePrometheusMetric = (metricName: string): number => {
    const lines = rawMetrics.split('\n');
    let total = 0;
    for (const line of lines) {
      if (line.startsWith(metricName) && !line.startsWith('#')) {
        const parts = line.split(' ');
        const val = parseFloat(parts[parts.length - 1]);
        if (!isNaN(val)) total += val;
      }
    }
    return total;
  };

  const totalHttpRequests = parsePrometheusMetric('http_requests_total');
  const totalHttpErrors = parsePrometheusMetric('http_errors_total');
  const totalLlmRequests = parsePrometheusMetric('llm_requests_total');
  const totalCacheRequests = parsePrometheusMetric('cache_requests_total');

  // Parse chart data by route
  const parseChartData = () => {
    const lines = rawMetrics.split('\n');
    const routeMap: Record<string, number> = {};

    for (const line of lines) {
      if (line.startsWith('http_requests_total') && !line.startsWith('#')) {
        const match = line.match(/route="([^"]+)"/);
        const route = match ? match[1] : 'other';
        const parts = line.split(' ');
        const val = parseFloat(parts[parts.length - 1]);
        if (!isNaN(val)) {
          routeMap[route] = (routeMap[route] || 0) + val;
        }
      }
    }

    return Object.entries(routeMap).map(([route, count]) => ({
      route: route.length > 20 ? route.substring(0, 18) + '...' : route,
      requests: count,
    }));
  };

  const chartData = parseChartData();

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-cyan-400" />
            <span>Prometheus System Metrics</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Real-time low-cardinality Prometheus telemetry for requests, latencies, cache, and LLM gateway.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex bg-slate-950 p-1 border border-slate-800 rounded-xl text-xs">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                activeTab === 'dashboard' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Visual Dashboard
            </button>
            <button
              onClick={() => setActiveTab('raw')}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                activeTab === 'raw' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Raw Prometheus Text
            </button>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={fetchMetrics}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {activeTab === 'dashboard' ? (
        <div className="space-y-6">
          {/* Key Metric Cards */}
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
                <Card hoverable className="space-y-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    HTTP Requests
                  </span>
                  <div className="text-3xl font-extrabold text-slate-100">{totalHttpRequests}</div>
                  <p className="text-xs text-slate-500">Total API calls served</p>
                </Card>

                <Card hoverable className="space-y-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    LLM Requests
                  </span>
                  <div className="text-3xl font-extrabold text-cyan-400">{totalLlmRequests}</div>
                  <p className="text-xs text-slate-500">Gateway LLM executions</p>
                </Card>

                <Card hoverable className="space-y-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    Cache Requests
                  </span>
                  <div className="text-3xl font-extrabold text-purple-400">{totalCacheRequests}</div>
                  <p className="text-xs text-slate-500">Redis cache queries</p>
                </Card>

                <Card hoverable className="space-y-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    HTTP Errors
                  </span>
                  <div className="text-3xl font-extrabold text-rose-400">{totalHttpErrors}</div>
                  <p className="text-xs text-slate-500">4xx / 5xx error responses</p>
                </Card>
              </>
            )}
          </div>

          {/* Chart */}
          <Card className="p-6 space-y-4">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span>HTTP Request Distribution by Route</span>
            </h3>

            <div className="h-72 w-full pt-4">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="route" stroke="#94a3b8" fontSize={11} />
                    <YAxis stroke="#94a3b8" fontSize={11} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '12px', fontSize: '12px' }}
                    />
                    <Bar dataKey="requests" fill="#06b6d4" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-slate-500">
                  No request metric samples available yet.
                </div>
              )}
            </div>
          </Card>
        </div>
      ) : (
        /* Raw Prometheus Viewer */
        <Card className="p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-xs font-bold text-slate-200 flex items-center gap-2 font-mono">
              <FileCode2 className="w-4 h-4 text-cyan-400" />
              <span>GET /metrics Response Payload</span>
            </h3>
            <span className="text-[11px] text-slate-500 font-mono">text/plain; version=0.0.4</span>
          </div>

          <pre className="p-4 bg-slate-950 border border-slate-800/80 rounded-xl text-[11px] font-mono text-cyan-300/90 overflow-x-auto h-[500px] leading-relaxed select-all">
            {rawMetrics || 'Loading Prometheus metrics text...'}
          </pre>
        </Card>
      )}
    </div>
  );
};
