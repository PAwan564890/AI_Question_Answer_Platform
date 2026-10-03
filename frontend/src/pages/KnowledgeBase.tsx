import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { documentsApi } from '../api/documents';
import { DocumentOut } from '../types/api';
import { CustomApiError } from '../api/client';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { SkeletonTable } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import {
  Database,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  FileText,
  Layers,
  Calendar,
  User as UserIcon,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { toast } from 'sonner';

export const KnowledgeBase: React.FC = () => {
  const { role } = useAuth();
  const isAdmin = role === 'ADMIN';

  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Ingestion Modal State
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [text, setText] = useState<string>('');
  const [source, setSource] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Delete modal state
  const [deleteDocId, setDeleteDocId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const data = await documentsApi.list({ limit: 100 });
      setDocuments(data);
    } catch {
      toast.error('Failed to fetch knowledge base documents.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !text.trim()) {
      setFormError('Title and text content are required.');
      return;
    }

    setFormError(null);
    setIsSubmitting(true);

    try {
      await documentsApi.ingest({
        title: title.trim(),
        text: text.trim(),
        source: source.trim() || undefined,
      });

      toast.success('Document successfully ingested into RAG vector database!');
      setIsModalOpen(false);
      setTitle('');
      setText('');
      setSource('');
      fetchDocuments();
    } catch (err) {
      if (err instanceof CustomApiError) {
        setFormError(err.message);
      } else {
        setFormError('Failed to ingest document.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteDocId) return;
    setIsDeleting(true);
    try {
      await documentsApi.delete(deleteDocId);
      toast.success('Document deleted successfully.');
      setDeleteDocId(null);
      fetchDocuments();
    } catch (err) {
      if (err instanceof CustomApiError) {
        toast.error(err.message);
      } else {
        toast.error('Failed to delete document.');
      }
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredDocs = documents.filter(
    (doc) =>
      doc.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (doc.source && doc.source.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      {/* Header & Main Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Database className="w-5 h-5 text-cyan-400" />
            <span>Knowledge Base</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Manage vector-indexed knowledge documents used by the Retrieval-Augmented Generation system.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchDocuments}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>

          {isAdmin && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsModalOpen(true)}
              icon={<Plus className="w-4 h-4" />}
            >
              Add Document
            </Button>
          )}
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Input
            placeholder="Search documents by title or source..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <span className="text-xs text-slate-400 font-mono">
          Showing {filteredDocs.length} of {documents.length} documents
        </span>
      </div>

      {/* Document Table */}
      {loading ? (
        <SkeletonTable rows={4} />
      ) : filteredDocs.length === 0 ? (
        <EmptyState
          icon={<FileText className="w-8 h-8" />}
          title="No Knowledge Base Documents Found"
          description={
            searchTerm
              ? 'No documents matched your search filter.'
              : 'Upload knowledge documents to ground your AI assistant with context.'
          }
          actionLabel={isAdmin ? 'Ingest First Document' : undefined}
          onAction={() => setIsModalOpen(true)}
          actionIcon={<Plus className="w-4 h-4" />}
        />
      ) : (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-400 font-semibold border-b border-slate-800 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3.5">Title / Name</th>
                  <th className="px-5 py-3.5">Source Note</th>
                  <th className="px-5 py-3.5">Vector Chunks</th>
                  <th className="px-5 py-3.5">Created By</th>
                  <th className="px-5 py-3.5">Created At</th>
                  {isAdmin && <th className="px-5 py-3.5 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredDocs.map((doc) => (
                  <tr key={doc.doc_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-5 py-4 font-semibold text-slate-200">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-cyan-400 shrink-0" />
                        <span className="line-clamp-1">{doc.title}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-slate-400 font-mono">
                      {doc.source || <span className="text-slate-600">N/A</span>}
                    </td>
                    <td className="px-5 py-4">
                      <Badge variant="cyan" size="sm" icon={<Layers className="w-3 h-3" />}>
                        {doc.chunk_count} chunks
                      </Badge>
                    </td>
                    <td className="px-5 py-4 text-slate-300 font-medium">
                      <div className="flex items-center gap-1.5">
                        <UserIcon className="w-3.5 h-3.5 text-slate-500" />
                        <span>{doc.created_by}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-slate-400 font-mono">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-500" />
                        <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                      </div>
                    </td>
                    {isAdmin && (
                      <td className="px-5 py-4 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteDocId(doc.doc_id)}
                          className="text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                          icon={<Trash2 className="w-3.5 h-3.5" />}
                        >
                          Delete
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Document Ingestion Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Ingest Knowledge Document"
        subtitle="Add content to chunk and embed into the Qdrant vector database"
        maxWidth="lg"
      >
        <form onSubmit={handleIngest} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{formError}</span>
            </div>
          )}

          <Input
            label="Document Title"
            placeholder="e.g. Redis Caching & Rate Limiting Architecture"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Document Content / Text
            </label>
            <textarea
              rows={8}
              placeholder="Paste document text here..."
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-slate-100 text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors font-mono"
              required
            />
          </div>

          <Input
            label="Source Note / URL (Optional)"
            placeholder="e.g. https://docs.redis.io"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <Button type="button" variant="ghost" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={isSubmitting}>
              Ingest Document
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteDocId}
        onClose={() => setDeleteDocId(null)}
        title="Confirm Document Deletion"
        subtitle="This action will remove the document and all associated vector chunks from Qdrant."
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-300">
            Are you sure you want to delete document <span className="font-mono text-cyan-400">{deleteDocId}</span>?
          </p>
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <Button variant="ghost" onClick={() => setDeleteDocId(null)}>
              Cancel
            </Button>
            <Button variant="danger" isLoading={isDeleting} onClick={handleDelete}>
              Delete Document
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
