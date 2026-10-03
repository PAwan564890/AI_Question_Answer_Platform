import React, { useState, useEffect } from 'react';
import { adminApi } from '../api/admin';
import { AuditEvent } from '../types/api';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { SkeletonTable } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import { ShieldCheck, Search, RefreshCw, Calendar, User as UserIcon, Code2 } from 'lucide-react';
import { toast } from 'sonner';

export const Audit: React.FC = () => {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');

  const fetchAudit = async () => {
    setLoading(true);
    try {
      const data = await adminApi.listAudit({ limit: 100 });
      setEvents(data);
    } catch {
      toast.error('Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
  }, []);

  const filteredEvents = events.filter(
    (e) =>
      e.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.actor_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (e.target_id && e.target_id.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-cyan-400" />
            <span>System Audit Logs</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Immutably logged audit trail of user administration and knowledge base security events.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={fetchAudit}
          icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
        >
          Refresh
        </Button>
      </div>

      {/* Filter / Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Input
            placeholder="Filter by action or actor ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <span className="text-xs text-slate-400 font-mono">
          Showing {filteredEvents.length} audit records
        </span>
      </div>

      {/* Audit Table */}
      {loading ? (
        <SkeletonTable rows={5} />
      ) : filteredEvents.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck className="w-8 h-8" />}
          title="No Audit Logs Found"
          description="Admin security events will be listed here as administrative actions occur."
        />
      ) : (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-400 font-semibold border-b border-slate-800 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3.5">Timestamp</th>
                  <th className="px-5 py-3.5">Action</th>
                  <th className="px-5 py-3.5">Actor ID</th>
                  <th className="px-5 py-3.5">Target ID</th>
                  <th className="px-5 py-3.5">Changes / Context</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredEvents.map((evt) => (
                  <tr key={evt.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-5 py-4 font-mono text-slate-300">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-500" />
                        <span>{new Date(evt.created_at).toLocaleString()}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <Badge
                        variant={
                          evt.action.includes('create')
                            ? 'green'
                            : evt.action.includes('update')
                            ? 'amber'
                            : 'cyan'
                        }
                        size="md"
                      >
                        {evt.action}
                      </Badge>
                    </td>
                    <td className="px-5 py-4 font-mono text-slate-300">
                      <div className="flex items-center gap-1.5">
                        <UserIcon className="w-3.5 h-3.5 text-slate-500" />
                        <span className="truncate max-w-[120px]">{evt.actor_id}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 font-mono text-slate-400">
                      {evt.target_id || <span className="text-slate-600">N/A</span>}
                    </td>
                    <td className="px-5 py-4 font-mono text-slate-300">
                      {evt.changes ? (
                        <div className="flex items-center gap-1 text-[11px]">
                          <Code2 className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                          <span className="bg-slate-950 px-2 py-1 rounded border border-slate-800 text-cyan-400 max-w-xs truncate">
                            {JSON.stringify(evt.changes)}
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-600">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
