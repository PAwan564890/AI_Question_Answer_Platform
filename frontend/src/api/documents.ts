import { apiClient } from './client';
import { DocumentCreate, DocumentOut, SearchRequest, SearchResponse } from '../types/api';

export const documentsApi = {
  list: async (params?: { limit?: number; offset?: number }): Promise<DocumentOut[]> => {
    const response = await apiClient.get<DocumentOut[]>('/documents', { params });
    return response.data;
  },

  ingest: async (payload: DocumentCreate): Promise<DocumentOut> => {
    const response = await apiClient.post<DocumentOut>('/documents', payload);
    return response.data;
  },

  search: async (payload: SearchRequest): Promise<SearchResponse> => {
    const response = await apiClient.post<SearchResponse>('/documents/search', payload);
    return response.data;
  },

  delete: async (docId: string): Promise<void> => {
    await apiClient.delete(`/documents/${docId}`);
  },
};
