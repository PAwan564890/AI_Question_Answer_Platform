import { apiClient } from './client';
import { AuditEvent, UserCreate, UserOut, UserUpdate } from '../types/api';

export const adminApi = {
  listUsers: async (params?: { limit?: number; offset?: number }): Promise<UserOut[]> => {
    const response = await apiClient.get<UserOut[]>('/admin/users', { params });
    return response.data;
  },

  createUser: async (payload: UserCreate): Promise<UserOut> => {
    const response = await apiClient.post<UserOut>('/admin/users', payload);
    return response.data;
  },

  updateUser: async (userId: string, payload: UserUpdate): Promise<UserOut> => {
    const response = await apiClient.patch<UserOut>(`/admin/users/${userId}`, payload);
    return response.data;
  },

  listAudit: async (params?: { limit?: number; offset?: number }): Promise<AuditEvent[]> => {
    const response = await apiClient.get<AuditEvent[]>('/admin/audit', { params });
    return response.data;
  },
};
