import { useMutation, useQuery, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { ACCESS_TOKEN_KEY, api } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";

export interface Todo {
  id: string;
  title: string;
  description: string | null;
  completed: boolean;
  user_id: string;
  created_at: string;
  updated_at: string;
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

export const DEFAULT_PAGE_SIZE = 20;

/**
 * Query keys for the todo list.
 *
 * `list` includes every parameter that changes the response. A bare ["todos"]
 * key made page 2 overwrite the cached page 1 and then read it back, so
 * paging appeared to do nothing.
 */
export const todoKeys = {
  all: ["todos"] as const,
  list: (page: number, size: number) => ["todos", { page, size }] as const,
};

function invalidateTodoLists() {
  // Prefix match: every cached page is refetched, not just the current one.
  return queryClient.invalidateQueries({ queryKey: todoKeys.all });
}

export function useTodos(page: number = 1, size: number = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: todoKeys.list(page, size),
    queryFn: async (): Promise<TodoListResponse> => {
      const response = await api.get("/todos", {
        params: { page, size },
      });
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

      // Snapshot every cached page, not just one, since the mutation does not
      // know which page the item is currently displayed on.
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
