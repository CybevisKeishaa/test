import axios, { type InternalAxiosRequestConfig } from "axios";
import { queryClient } from "./queryClient";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const ACCESS_TOKEN_KEY = "access_token";
export const REFRESH_TOKEN_KEY = "refresh_token";

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
});

export function storeTokens(tokens: {
  access_token: string;
  refresh_token: string;
}) {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

/**
 * Drop every cached server response for the previous user.
 *
 * This is the important half of a session change: react-query keys are per
 * query name, not per user, so leaving the cache in place lets the next
 * person to sign in on this browser read the previous user's todos straight
 * out of memory.
 *
 * removeQueries() rather than clear(): clear() also empties the *mutation*
 * cache, and doing that from inside a mutation's own callback drops the
 * in-flight mutation's observers, so its onSuccess never runs.
 */
export function clearCachedUserData() {
  queryClient.removeQueries();
}

/** Drop the tokens and the cached data together. */
export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  clearCachedUserData();
}

// Endpoints that legitimately answer 401: a failed login must surface its own
// error rather than being treated as an expired session.
const AUTH_ENDPOINTS = ["/auth/login", "/auth/register", "/auth/refresh"];

function isAuthEndpoint(url: string | undefined): boolean {
  return !!url && AUTH_ENDPOINTS.some((path) => url.includes(path));
}

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// One shared refresh in flight, so a burst of 401s does not fire a burst of
// refreshes -- which would fail anyway now that refresh tokens rotate.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) {
    throw new Error("No refresh token available");
  }

  // Bare axios: going through `api` would re-enter this interceptor.
  const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
    refresh_token: refreshToken,
  });

  storeTokens(data);
  return data.access_token;
}

function redirectToLogin() {
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined;

    const isExpiredSession =
      error.response?.status === 401 &&
      config &&
      !config._retried &&
      !isAuthEndpoint(config.url);

    if (!isExpiredSession) {
      return Promise.reject(error);
    }

    config._retried = true;

    try {
      refreshPromise =
        refreshPromise ??
        refreshAccessToken().finally(() => {
          refreshPromise = null;
        });

      const token = await refreshPromise;
      config.headers.Authorization = `Bearer ${token}`;
      return api(config);
    } catch {
      clearSession();
      redirectToLogin();
      return Promise.reject(error);
    }
  }
);
