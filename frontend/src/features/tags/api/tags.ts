import { useMutation, useQuery } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { toast } from "sonner";
import { ACCESS_TOKEN_KEY, api } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import { todoKeys } from "@/features/todos/api/todos";

export interface Tag {
  id: string;
  user_id: string;
  name: string;
  color: string | null;
  created_at: string;
  updated_at: string;
}

interface TagListResponse {
  items: Tag[];
  total: number;
}

interface TagPayload {
  name: string;
  color?: string | null;
}

export const tagKeys = {
  all: ["tags"] as const,
};

/**
 * Tags are embedded in every todo payload, so a tag mutation invalidates the
 * todo lists too -- otherwise a renamed tag keeps its old label on screen
 * until something else happens to refetch.
 */
function invalidateTagsAndTodos() {
  queryClient.invalidateQueries({ queryKey: tagKeys.all });
  queryClient.invalidateQueries({ queryKey: todoKeys.all });
}

function errorMessage(error: unknown, fallback: string): string {
  if (isAxiosError<{ detail?: string }>(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export function useTags() {
  return useQuery({
    queryKey: tagKeys.all,
    queryFn: async (): Promise<TagListResponse> => {
      const response = await api.get("/tags");
      return response.data;
    },
    enabled: !!localStorage.getItem(ACCESS_TOKEN_KEY),
  });
}

export function useCreateTag() {
  return useMutation({
    mutationFn: async (data: TagPayload): Promise<Tag> => {
      const response = await api.post("/tags", data);
      return response.data;
    },
    onSuccess: (tag) => {
      invalidateTagsAndTodos();
      toast.success(`Tag "${tag.name}" created`);
    },
    onError: (error) => {
      // The 409 body names the clash ("You already have a tag named ..."),
      // which is more useful than a generic failure message.
      toast.error(errorMessage(error, "Failed to create tag"));
    },
  });
}

export function useUpdateTag() {
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: TagPayload;
    }): Promise<Tag> => {
      const response = await api.patch(`/tags/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      invalidateTagsAndTodos();
      toast.success("Tag updated");
    },
    onError: (error) => {
      toast.error(errorMessage(error, "Failed to update tag"));
    },
  });
}

export function useDeleteTag() {
  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.delete(`/tags/${id}`);
    },
    onSuccess: () => {
      invalidateTagsAndTodos();
      toast.success("Tag deleted");
    },
    onError: (error) => {
      toast.error(errorMessage(error, "Failed to delete tag"));
    },
  });
}
