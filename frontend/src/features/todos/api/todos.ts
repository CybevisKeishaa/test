import { useMutation, useQuery, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { ACCESS_TOKEN_KEY, api } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import type { Tag } from "@/features/tags/api/tags";

export interface Todo {
  id: string;
  title: string;
  description: string | null;
  completed: boolean;
  user_id: string;
  created_at: string;
  updated_at: string;
  tags: Tag[];
}

export interface TodoListResponse {
  items: Todo[];
  total: number;
  page: number;
  size: number;
}

interface CreateTodoRequest {
  title: string;
  description?: string;
}

interface UpdateTodoRequest {
  title?: string;
  description?: string;
  completed?: boolean;
}

export type TodoStatus = "all" | "active" | "completed";

export const DEFAULT_PAGE_SIZE = 20;

/** Every input that changes which todos come back. */
export interface TodoFilters {
  page: number;
  size: number;
  status: TodoStatus;
  tagId: string | null;
  keyword: string;
  dateFrom: string;
  dateTo: string;
}

export const DEFAULT_FILTERS: TodoFilters = {
  page: 1,
  size: DEFAULT_PAGE_SIZE,
  status: "all",
  tagId: null,
  keyword: "",
  dateFrom: "",
  dateTo: "",
};

/** True when nothing is narrowing the list (page/size aside). */
export function hasActiveFilters(filters: TodoFilters): boolean {
  return (
    filters.status !== "all" ||
    filters.tagId !== null ||
    filters.keyword.trim() !== "" ||
    filters.dateFrom !== "" ||
    filters.dateTo !== ""
  );
}

/**
 * Query keys for the todo list.
 *
 * `list` carries every parameter that changes the response. A bare ["todos"]
 * key made page 2 overwrite the cached page 1 and read it straight back;
 * leaving a *filter* out would do the same thing with the filtered and
 * unfiltered lists. The server's cache key is built from the same set.
 */
export const todoKeys = {
  all: ["todos"] as const,
  list: (filters: TodoFilters) => ["todos", filters] as const,
};

function invalidateTodoLists() {
  // Prefix match: every cached page and filter combination is refetched.
  return queryClient.invalidateQueries({ queryKey: todoKeys.all });
}

function toQueryParams(filters: TodoFilters): Record<string, string | number> {
  const params: Record<string, string | number> = {
    page: filters.page,
    page_size: filters.size,
  };

  if (filters.status !== "all") params.status = filters.status;
  if (filters.tagId) params.tag_id = filters.tagId;
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim();
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;

  return params;
}

export function useTodos(filters: TodoFilters = DEFAULT_FILTERS) {
  return useQuery({
    queryKey: todoKeys.list(filters),
    queryFn: async (): Promise<TodoListResponse> => {
      const response = await api.get("/todos", { params: toQueryParams(filters) });
      return response.data;
    },
    // Logging out clears the cache, which would otherwise make every mounted
    // list refetch without a token on its way out.
    enabled: !!localStorage.getItem(ACCESS_TOKEN_KEY),
    placeholderData: (previous) => previous,
  });
}

export function useCreateTodo() {
  return useMutation({
    mutationFn: async (data: CreateTodoRequest): Promise<Todo> => {
      const response = await api.post("/todos", data);
      return response.data;
    },
    onSuccess: () => {
      invalidateTodoLists();
      toast.success("Todo created successfully!");
    },
    onError: () => {
      toast.error("Failed to create todo");
    },
  });
}

type TodoListSnapshot = [QueryKey, TodoListResponse | undefined][];

export function useUpdateTodo() {
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      data: UpdateTodoRequest;
    }): Promise<Todo> => {
      const response = await api.put(`/todos/${id}`, data);
      return response.data;
    },
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: todoKeys.all });

      // Snapshot every cached page and filter set, not just one, since the
      // mutation does not know which list the item is displayed in.
      const previous = queryClient.getQueriesData<TodoListResponse>({
        queryKey: todoKeys.all,
      }) as TodoListSnapshot;

      previous.forEach(([key, value]) => {
        if (!value) return;
        queryClient.setQueryData<TodoListResponse>(key, {
          ...value,
          items: value.items.map((todo) =>
            todo.id === id ? { ...todo, ...data } : todo
          ),
        });
      });

      return { previous };
    },
    onError: (_error, _variables, context) => {
      // Roll the optimistic write back. Previously onMutate returned a
      // snapshot that nothing ever restored, so a failed update left the UI
      // showing a change the server had rejected.
      context?.previous.forEach(([key, value]) => {
        queryClient.setQueryData(key, value);
      });
      toast.error("Failed to update todo");
    },
    onSettled: () => {
      invalidateTodoLists();
    },
  });
}

export function useDeleteTodo() {
  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.delete(`/todos/${id}`);
    },
    onSuccess: () => {
      invalidateTodoLists();
      toast.success("Todo deleted successfully!");
    },
    onError: () => {
      toast.error("Failed to delete todo");
    },
  });
}

export function useToggleTodo() {
  const updateTodo = useUpdateTodo();

  return {
    isPending: updateTodo.isPending,
    toggle: (todo: Todo) =>
      updateTodo.mutate({
        id: todo.id,
        data: { completed: !todo.completed },
      }),
  };
}

interface BulkStatusResponse {
  updated: number;
  completed: boolean;
}

export function useBulkSetStatus() {
  return useMutation({
    mutationFn: async ({
      todoIds,
      completed,
    }: {
      todoIds: string[];
      completed: boolean;
    }): Promise<BulkStatusResponse> => {
      const response = await api.patch("/todos/bulk-status", {
        todo_ids: todoIds,
        completed,
      });
      return response.data;
    },
    onSuccess: (data) => {
      invalidateTodoLists();
      toast.success(
        `${data.updated} todo${data.updated === 1 ? "" : "s"} marked ${
          data.completed ? "completed" : "active"
        }`
      );
    },
    onError: () => {
      // The server applies bulk updates all-or-nothing, so on failure nothing
      // changed and there is no partial state to reconcile.
      toast.error("Failed to update the selected todos");
    },
  });
}

export function useAttachTag() {
  return useMutation({
    mutationFn: async ({
      todoId,
      tagId,
    }: {
      todoId: string;
      tagId: string;
    }): Promise<Todo> => {
      const response = await api.post(`/todos/${todoId}/tags`, { tag_id: tagId });
      return response.data;
    },
    onSuccess: () => invalidateTodoLists(),
    onError: () => {
      toast.error("Failed to add the tag");
    },
  });
}

export function useDetachTag() {
  return useMutation({
    mutationFn: async ({
      todoId,
      tagId,
    }: {
      todoId: string;
      tagId: string;
    }): Promise<void> => {
      await api.delete(`/todos/${todoId}/tags/${tagId}`);
    },
    onSuccess: () => invalidateTodoLists(),
    onError: () => {
      toast.error("Failed to remove the tag");
    },
  });
}
