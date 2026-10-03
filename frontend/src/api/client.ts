import axios, { AxiosError } from 'axios';
import { ApiErrorResponse } from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor: Attach JWT Token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => Promise.reject(error));

export class CustomApiError extends Error {
  code: string;
  requestId?: string;
  status?: number;

  constructor(message: string, code: string, requestId?: string, status?: number) {
    super(message);
    this.name = 'CustomApiError';
    this.code = code;
    this.requestId = requestId;
    this.status = status;
  }
}

// Response Interceptor: Uniform Error Processing
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    if (error.response) {
      const status = error.response.status;
      const data = error.response.data;

      // Handle 401 Unauthorized
      if (status === 401) {
        localStorage.removeItem('token');
        if (window.location.pathname !== '/login') {
          window.dispatchEvent(new Event('auth:unauthorized'));
        }
      }

      if (data && data.error) {
        return Promise.reject(
          new CustomApiError(
            data.error.message || 'An error occurred',
            data.error.code || 'UNKNOWN_ERROR',
            data.error.request_id,
            status
          )
        );
      }

      return Promise.reject(
        new CustomApiError(
          `Request failed with status ${status}`,
          `HTTP_${status}`,
          undefined,
          status
        )
      );
    } else if (error.request) {
      return Promise.reject(
        new CustomApiError(
          'Unable to connect to the backend server. Please verify your connection.',
          'NETWORK_ERROR'
        )
      );
    }

    return Promise.reject(new CustomApiError(error.message, 'CLIENT_ERROR'));
  }
);
