import { apiClient } from './client';
import { HealthStatus, ReadyStatus } from '../types/api';

export const opsApi = {
  getHealth: async (): Promise<HealthStatus> => {
    const response = await apiClient.get<HealthStatus>('/health');
    return response.data;
  },

  getLive: async (): Promise<{ status: string }> => {
    const response = await apiClient.get<{ status: string }>('/health/live');
    return response.data;
  },

  getReady: async (): Promise<ReadyStatus> => {
    const response = await apiClient.get<ReadyStatus>('/health/ready');
    return response.data;
  },

  getMetrics: async (): Promise<string> => {
    const response = await apiClient.get<string>('/metrics', {
      responseType: 'text',
    });
    return response.data;
  },
};
