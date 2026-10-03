import React, { useState } from 'react';
import { documentsApi } from '../api/documents';
import { SearchHit } from '../types/api';
import { CustomApiError } from '../api/client';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { SkeletonCard } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import { Search as SearchIcon, Copy, Check, FileText, Sparkles, Layers, Sliders } from 'lucide-react';
import { toast } from 'sonner';

export const Search: React.FC = () => {
  const [query, setQuery] = useState<string>('');
  const [topK, setTopK] = useState<number>(4);
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [hasSearched, setHasSearched] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;

    setLoading(true);
    setHasSearched(true);

    try {
      const res = await documentsApi.search({
        query: query.trim(),
        top_k: topK,
      });
      setResults(res.results);
    } catch (err) {
      if (err instanceof CustomApiError) {
        toast.error(err.message);
      } else {
        toast.error('Vector search failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const copyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Text copied to clipboard!');
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <SearchIcon className="w-5 h-5 text-cyan-400" />
          <span>Knowledge Search</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Search the indexed knowledge base using semantic/vector retrieval from Qdrant without executing an LLM call.
        </p>
      </div>

      {/* Search Input Bar */}
      <Card className="p-4 bg-slate-900/80">
        <form onSubmit={handleSearch} className="flex flex-col sm:flex-row items-center gap-3">
          <div className="flex-1 w-full">
            <Input
              placeholder="Ask something about your knowledge base... (e.g., How does caching work?)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              leftIcon={<SearchIcon className="w-4 h-4" />}
            />
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs">
              <Sliders className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-slate-400 font-medium">Top K:</span>
              <select
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
              >
                <option value={2} className="bg-slate-900">2</option>
                <option value={4} className="bg-slate-900">4</option>
                <option value={6} className="bg-slate-900">6</option>
                <option value={10} className="bg-slate-900">10</option>
              </select>
            </div>

            <Button
              type="submit"
              variant="primary"
              isLoading={loading}
              disabled={!query.trim()}
              className="w-full sm:w-auto"
            >
              Search
            </Button>
          </div>
        </form>
      </Card>

      {/* Search Results */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : hasSearched && results.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="w-8 h-8" />}
          title="No Vector Search Hits Found"
          description="Try broadening your query or upload more documents into the Knowledge Base."
        />
      ) : (
        <div className="space-y-4">
          {hasSearched && (
            <div className="flex items-center justify-between text-xs text-slate-400 px-1 font-mono">
              <span>Retrieved {results.length} relevant chunk(s)</span>
              <span>Sorted by cosine similarity score</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {results.map((hit, idx) => {
              const hitId = `${hit.doc_id}-${hit.chunk_index}`;
              return (
                <Card key={idx} hoverable className="space-y-3 flex flex-col justify-between">
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-cyan-400 shrink-0" />
                        <h4 className="text-sm font-bold text-slate-200 line-clamp-1">{hit.title}</h4>
                      </div>
                      <Badge variant="green" size="sm">
                        {(hit.score * 100).toFixed(1)}% Match
                      </Badge>
                    </div>

                    <p className="text-xs text-slate-300 font-mono bg-slate-950 p-3 rounded-xl border border-slate-800/80 leading-relaxed whitespace-pre-wrap">
                      {hit.text}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-[11px] text-slate-400 font-mono">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1">
                        <Layers className="w-3 h-3 text-slate-500" />
                        Chunk #{hit.chunk_index}
                      </span>
                      <span className="truncate max-w-[120px]">Doc: {hit.doc_id}</span>
                    </div>

                    <button
                      onClick={() => copyText(hit.text, hitId)}
                      className="hover:text-slate-200 flex items-center gap-1 transition-colors"
                      title="Copy text"
                    >
                      {copiedId === hitId ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
