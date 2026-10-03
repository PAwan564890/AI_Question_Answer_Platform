import { apiClient } from './client';
import { LoginRequest, TokenResponse, UserOut } from '../types/api';

export const authApi = {
  login: async (credentials: LoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/login', credentials);
    return response.data;
  },

  me: async (): Promise<UserOut> => {
    const response = await apiClient.get<UserOut>('/auth/me');
    return response.data;
  },
};
