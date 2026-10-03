import { apiClient } from './client';
import { ChatRequest, ChatResponse, HistoryItem } from '../types/api';

export const chatApi = {
  ask: async (payload: ChatRequest): Promise<ChatResponse> => {
    const response = await apiClient.post<ChatResponse>('/chat', payload);
    return response.data;
  },

  getHistory: async (params?: { limit?: number; offset?: number; user_id?: string }): Promise<HistoryItem[]> => {
    const response = await apiClient.get<HistoryItem[]>('/chat/history', { params });
    return response.data;
  },
};
