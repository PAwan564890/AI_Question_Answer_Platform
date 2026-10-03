import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { chatApi } from '../api/chat';
import { HistoryItem } from '../types/api';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { SkeletonTable } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import {
  History as HistoryIcon,
  Search,
  RefreshCw,
  Clock,
  Layers,
  MessageSquare,
  Bot,
  User as UserIcon,
  ExternalLink,
  BookOpen,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';

export const History: React.FC = () => {
  const { role } = useAuth();
  const isAdmin = role === 'ADMIN';
  const navigate = useNavigate();

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [targetUserId, setTargetUserId] = useState<string>('own');
  const [selectedItem, setSelectedItem] = useState<HistoryItem | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const params: { limit: number; user_id?: string } = { limit: 100 };
      if (isAdmin && targetUserId !== 'own') {
        params.user_id = targetUserId;
      }
      const data = await chatApi.getHistory(params);
      setHistory(data);
    } catch {
      // Failed to load history
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [targetUserId]);

  const filteredHistory = history.filter(
    (item) =>
      (item.question && item.question.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (item.answer && item.answer.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <HistoryIcon className="w-5 h-5 text-cyan-400" />
            <span>Chat History</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Browse and inspect all stored AI questions, answers, and RAG metadata.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isAdmin && (
            <select
              value={targetUserId}
              onChange={(e) => setTargetUserId(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none"
            >
              <option value="own">My History</option>
              <option value="all">All Users (Admin)</option>
            </select>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={fetchHistory}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Input
            placeholder="Filter history by question or answer..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <span className="text-xs text-slate-400 font-mono">
          Showing {filteredHistory.length} records
        </span>
      </div>

      {/* History Table */}
      {loading ? (
        <SkeletonTable rows={5} />
      ) : filteredHistory.length === 0 ? (
        <EmptyState
          icon={<MessageSquare className="w-8 h-8" />}
          title="No Chat History Recorded"
          description={
            searchTerm
              ? 'No chat items match your search term.'
              : 'Start a conversation on the Chat page to record history.'
          }
          actionLabel="Go to Chat"
          onAction={() => navigate('/chat')}
        />
      ) : (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-400 font-semibold border-b border-slate-800 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3.5">Question</th>
                  <th className="px-5 py-3.5">Answer Preview</th>
                  <th className="px-5 py-3.5">Provider / Model</th>
                  <th className="px-5 py-3.5">Latency</th>
                  <th className="px-5 py-3.5">Tokens</th>
                  <th className="px-5 py-3.5">Sources</th>
                  <th className="px-5 py-3.5">Timestamp</th>
                  <th className="px-5 py-3.5 text-right">View</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredHistory.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-5 py-4 font-semibold text-slate-200 max-w-xs">
                      <p className="line-clamp-1">{item.question || 'Untitled Question'}</p>
                    </td>
                    <td className="px-5 py-4 text-slate-400 max-w-sm">
                      <p className="line-clamp-1">{item.answer || 'No answer recorded'}</p>
                    </td>
                    <td className="px-5 py-4 font-mono">
                      <div className="flex items-center gap-1.5">
                        <Badge variant="cyan" size="sm">
                          {item.provider || 'mock'}
                        </Badge>
                        <span className="text-slate-400 text-[11px]">{item.model}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 font-mono text-slate-300">
                      <div className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5 text-slate-500" />
                        <span>{item.latency_ms} ms</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 font-mono text-slate-300">
                      {item.usage?.total_tokens !== null && item.usage?.total_tokens !== undefined ? (
                        <div className="flex items-center gap-1">
                          <Layers className="w-3.5 h-3.5 text-slate-500" />
                          <span>{item.usage.total_tokens}</span>
                        </div>
                      ) : (
                        <span className="text-slate-600">N/A</span>
                      )}
                    </td>
                    <td className="px-5 py-4 font-mono">
                      <Badge variant="purple" size="sm">
                        {item.sources?.length || 0} sources
                      </Badge>
                    </td>
                    <td className="px-5 py-4 text-slate-400 font-mono text-[11px]">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedItem(item)}
                        icon={<ExternalLink className="w-3.5 h-3.5" />}
                      >
                        Inspect
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detail Inspection Modal */}
      <Modal
        isOpen={!!selectedItem}
        onClose={() => setSelectedItem(null)}
        title="Chat Record Inspection"
        subtitle={`Record ID: ${selectedItem?.id}`}
        maxWidth="xl"
      >
        {selectedItem && (
          <div className="space-y-4 text-xs">
            <div>
              <span className="text-slate-400 font-semibold uppercase tracking-wider block mb-1">
                Question
              </span>
              <p className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-slate-200 font-medium">
                {selectedItem.question}
              </p>
            </div>

            <div>
              <span className="text-slate-400 font-semibold uppercase tracking-wider block mb-1">
                AI Answer
              </span>
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl text-slate-200 prose prose-invert max-w-none">
                <ReactMarkdown>{selectedItem.answer || ''}</ReactMarkdown>
              </div>
            </div>

            {selectedItem.sources && selectedItem.sources.length > 0 && (
              <div>
                <span className="text-slate-400 font-semibold uppercase tracking-wider block mb-1 flex items-center gap-1">
                  <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
                  Cited Sources ({selectedItem.sources.length})
                </span>
                <div className="space-y-2 pt-1">
                  {selectedItem.sources.map((src, idx) => (
                    <div key={idx} className="p-2.5 bg-slate-950 border border-slate-800 rounded-xl flex justify-between items-center font-mono">
                      <div>
                        <p className="font-semibold text-slate-200">{src.title}</p>
                        <p className="text-[10px] text-slate-500">Doc: {src.doc_id} | Chunk #{src.chunk_index}</p>
                      </div>
                      <Badge variant="green" size="sm">
                        {(src.score * 100).toFixed(1)}% Match
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-[11px]">
              <div>
                <span className="text-slate-500 block">Provider</span>
                <span className="text-slate-200 font-bold">{selectedItem.provider}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Model</span>
                <span className="text-slate-200 font-bold">{selectedItem.model}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Latency</span>
                <span className="text-slate-200 font-bold">{selectedItem.latency_ms} ms</span>
              </div>
              <div>
                <span className="text-slate-500 block">Tokens</span>
                <span className="text-slate-200 font-bold">{selectedItem.usage?.total_tokens ?? 'N/A'}</span>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
