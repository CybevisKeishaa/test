import { useMutation } from "@tanstack/react-query";
import { api, clearCachedUserData, clearSession, storeTokens } from "@/lib/api";

interface LoginRequest {
  email: string;
  password: string;
}

interface RegisterRequest {
  email: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export function useLogin() {
  return useMutation({
    mutationFn: async (data: LoginRequest): Promise<TokenResponse> => {
      const response = await api.post("/auth/login", data);
      return response.data;
    },
    onSuccess: (data) => {
      storeTokens(data);
      // After the switch, not before: a failed attempt must not wipe the
      // session of whoever is currently signed in on this browser.
      clearCachedUserData();
    },
  });
}

export function useRegister() {
  return useMutation({
    mutationFn: async (data: RegisterRequest): Promise<TokenResponse> => {
      const response = await api.post("/auth/register", data);
      return response.data;
    },
    onSuccess: (data) => {
      storeTokens(data);
      clearCachedUserData();
    },
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      await api.post("/auth/logout");
    },
    // Runs on success and on failure alike: if the server call fails we still
    // must not leave this browser holding the session.
    onSettled: () => {
      clearSession();
    },
  });
}

interface UserResponse {
  id: string;
  email: string;
  created_at: string;
}

export async function fetchCurrentUser(): Promise<UserResponse> {
  const response = await api.get("/auth/me");
  return response.data;
}
