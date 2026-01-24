import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { useAuth } from "@/contexts/AuthContext";
import { useCallback } from "react";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const API_BASE_URL = (import.meta as any).env?.VITE_BACKEND_URL || "http://localhost:8000";

// Base API functions (without auth - for public endpoints or when token is passed manually)
export async function apiGetBase<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: headers || {},
  });

  if (!res.ok) throw new Error(`GET ${path} failed`);
  return res.json();
}

export async function apiPostBase<T>(
  path: string,
  body?: any,
  headers?: Record<string, string>
): Promise<T> {
  return apiRequestBase<T>('POST', path, body, headers);
}

export async function apiPatchBase<T>(
  path: string,
  body?: any,
  headers?: Record<string, string>
): Promise<T> {
  return apiRequestBase<T>('PATCH', path, body, headers);
}

async function apiRequestBase<T>(
  method: string,
  path: string,
  body?: any,
  headers?: Record<string, string>
): Promise<T> {
  const isFormData = body instanceof FormData;

  const config: RequestInit = {
    method,
    body: isFormData ? body : (body ? JSON.stringify(body) : undefined),
  };

  if (!isFormData) {
    config.headers = {
      'Content-Type': 'application/json',
      ...headers
    };
  } else if (headers) {
    const nonContentTypeHeaders = Object.fromEntries(
      Object.entries(headers).filter(([key]) => key.toLowerCase() !== 'content-type')
    );
    if (Object.keys(nonContentTypeHeaders).length > 0) {
      config.headers = nonContentTypeHeaders;
    }
  }

  const res = await fetch(`${API_BASE_URL}${path}`, config);
  if (!res.ok) throw new Error(`${method} ${path} failed`);
  return res.json();
}

// Hook for authenticated API calls
export function useApi() {
  const { getAccessTokenSilently, isAuthenticated } = useAuth();

  const apiGet = useCallback(async <T,>(path: string): Promise<T> => {
    const headers: Record<string, string> = {};

    // Add JWT token if authenticated
    if (isAuthenticated) {
      try {
        const token = await getAccessTokenSilently();
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
      } catch (error) {
      }
    }

    const res = await fetch(`${API_BASE_URL}${path}`, {
      headers,
    });

    if (!res.ok) {
      // Handle 401 by attempting token refresh
      if (res.status === 401 && isAuthenticated) {
        try {
          const token = await getAccessTokenSilently();
          if (token) {
            // Retry with new token
            const retryRes = await fetch(`${API_BASE_URL}${path}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (!retryRes.ok) throw new Error(`GET ${path} failed`);
            return retryRes.json();
          }
        } catch (error) {
        }
      }
      throw new Error(`GET ${path} failed`);
    }

    return res.json();
  }, [isAuthenticated, getAccessTokenSilently]);

  const apiRequest = useCallback(async <T,>(
    method: string,
    path: string,
    body?: any,
    extraHeaders?: Record<string, string>
  ): Promise<T> => {
    const isFormData = body instanceof FormData;

    const config: RequestInit = {
      method,
      body: isFormData ? body : (body ? JSON.stringify(body) : undefined),
    };

    // Build headers object
    const requestHeaders: Record<string, string> = { ...extraHeaders };

    // Add JWT token if authenticated
    if (isAuthenticated) {
      try {
        const token = await getAccessTokenSilently();
        if (token) {
          requestHeaders.Authorization = `Bearer ${token}`;
        }
      } catch (error) {
      }
    }

    // Set headers if not FormData (FormData sets its own Content-Type with boundary)
    if (!isFormData) {
      config.headers = {
        'Content-Type': 'application/json',
        ...requestHeaders
      };
    } else if (Object.keys(requestHeaders).length > 0) {
      // For FormData, only add non-Content-Type headers
      const nonContentTypeHeaders = Object.fromEntries(
        Object.entries(requestHeaders).filter(([key]) => key.toLowerCase() !== 'content-type')
      );
      if (Object.keys(nonContentTypeHeaders).length > 0) {
        config.headers = nonContentTypeHeaders;
      }
    }

    const res = await fetch(`${API_BASE_URL}${path}`, config);

    if (!res.ok) {
      // Handle 401 by attempting token refresh
      if (res.status === 401 && isAuthenticated) {
        try {
          const token = await getAccessTokenSilently();
          if (token) {
            // Retry with new token
            const retryConfig = { ...config };
            if (retryConfig.headers) {
              (retryConfig.headers as Record<string, string>).Authorization = `Bearer ${token}`;
            }
            const retryRes = await fetch(`${API_BASE_URL}${path}`, retryConfig);
            if (!retryRes.ok) throw new Error(`${method} ${path} failed`);
            return retryRes.json();
          }
        } catch (error) {
        }
      }
      throw new Error(`${method} ${path} failed`);
    }

    return res.json();
  }, [isAuthenticated, getAccessTokenSilently]);

  const apiPost = useCallback(async <T,>(
    path: string,
    body?: any,
    extraHeaders?: Record<string, string>
  ): Promise<T> => {
    return apiRequest<T>('POST', path, body, extraHeaders);
  }, [apiRequest]);

  const apiPatch = useCallback(async <T,>(
    path: string,
    body?: any,
    extraHeaders?: Record<string, string>
  ): Promise<T> => {
    return apiRequest<T>('PATCH', path, body, extraHeaders);
  }, [apiRequest]);

  const apiDelete = useCallback(async <T,>(
    path: string,
    body?: any,
    extraHeaders?: Record<string, string>
  ): Promise<T> => {
    return apiRequest<T>('DELETE', path, body, extraHeaders);
  }, [apiRequest]);

  return { apiGet, apiPost, apiPatch, apiDelete };
}

// Legacy exports for backward compatibility (will be deprecated)
// These don't include auth tokens - use useApi hook instead
export async function apiGet<T>(path: string): Promise<T> {
  return apiGetBase<T>(path);
}

export async function apiPost<T>(path: string, body?: any, headers?: Record<string, string>): Promise<T> {
  return apiPostBase<T>(path, body, headers);
}

export function normalizeMarkdownText(text: string): string {
  try {
    let s = text ?? "";
    // Convert common escaped sequences to real characters for proper MD rendering
    s = s.replace(/\\n/g, "\n");
    s = s.replace(/\\t/g, "\t");
    return s;
  } catch {
    return text;
  }
}
