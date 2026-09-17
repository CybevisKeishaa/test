import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, LogOut, Plus, Tags } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { TagManagerDialog } from "@/features/tags/components/TagManagerDialog";
import {
  DEFAULT_FILTERS,
  hasActiveFilters,
  useBulkSetStatus,
  useTodos,
  type TodoFilters,
} from "../api/todos";
import { TodoBulkActions } from "./TodoBulkActions";
import { TodoFilterBar } from "./TodoFilterBar";
import { TodoForm } from "./TodoForm";
import { TodoList } from "./TodoList";

export function TodoPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showTagManager, setShowTagManager] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const [filters, setFilters] = useState<TodoFilters>(DEFAULT_FILTERS);
  // The input is uncontrolled by the query: typing stays instant while the
  // query key only moves once typing pauses.
  const [keywordDraft, setKeywordDraft] = useState("");
  const debouncedKeyword = useDebouncedValue(keywordDraft, 300);

  const effectiveFilters = useMemo(
    () => ({ ...filters, keyword: debouncedKeyword }),
    [filters, debouncedKeyword]
  );

  const { data, isLoading, isFetching, error } = useTodos(effectiveFilters);
  const { user, logout } = useAuth();
  const bulkSetStatus = useBulkSetStatus();

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / effectiveFilters.size));
  const isFiltered = hasActiveFilters(effectiveFilters);

  // Any change to what is being listed sends you back to page 1; staying on
  // page 4 of a result set that now has one page shows an empty list.
  const patchFilters = (patch: Partial<TodoFilters>) =>
    setFilters((current) => ({ ...current, ...patch, page: 1 }));

  // A delete can empty the last page; step back rather than showing nothing.
  if (effectiveFilters.page > pageCount && !isFetching) {
    setFilters((current) => ({ ...current, page: pageCount }));
  }

  // Typing a new search goes back to page 1, like every other filter change.
  // Done here rather than in an effect on the debounced value: an effect that
  // calls setState causes a cascading render for no benefit.
  const handleKeywordChange = (value: string) => {
    setKeywordDraft(value);
    setFilters((current) =>
      current.page === 1 ? current : { ...current, page: 1 }
    );
  };

  const clearFilters = () => {
    setKeywordDraft("");
    setFilters(DEFAULT_FILTERS);
  };

  const handleSelectedChange = (todoId: string, selected: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (selected) {
        next.add(todoId);
      } else {
        next.delete(todoId);
      }
      return next;
    });
  };

  const runBulkUpdate = (completed: boolean) => {
    bulkSetStatus.mutate(
      { todoIds: [...selectedIds], completed },
      // Only clear the selection once the write landed: after a failure the
      // server changed nothing, so the user should still have their selection
      // to retry with.
      { onSuccess: () => setSelectedIds(new Set()) }
    );
  };

  return (
    <div className="min-h-screen bg-muted/40">
      {/* Header */}
      <header className="bg-card border-b">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">Todo App</h1>
            {user && (
              <p className="text-sm text-muted-foreground">{user.email}</p>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowTagManager(true)}
            >
              <Tags className="h-4 w-4 mr-2" />
              Tags
            </Button>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-3xl mx-auto px-4 py-8">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">My Todos</CardTitle>
            <Button size="sm" onClick={() => setShowCreateForm(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Add Todo
            </Button>
          </CardHeader>
          <Separator />

          <CardContent className="pt-4 space-y-4">
            <TodoFilterBar
              filters={effectiveFilters}
              keywordDraft={keywordDraft}
              onKeywordChange={handleKeywordChange}
              onChange={patchFilters}
              onClear={clearFilters}
              isFiltered={isFiltered || keywordDraft !== ""}
            />

            <Separator />

            <div>
              <TodoBulkActions
                selectedCount={selectedIds.size}
                isPending={bulkSetStatus.isPending}
                onMarkCompleted={() => runBulkUpdate(true)}
                onMarkActive={() => runBulkUpdate(false)}
                onClearSelection={() => setSelectedIds(new Set())}
              />

              {isLoading && (
                <div className="text-center py-12 text-muted-foreground">
                  Loading todos...
                </div>
              )}

              {error && (
                <div className="text-center py-12 text-destructive">
                  Failed to load todos. Please try again.
                </div>
              )}

              {data && (
                <TodoList
                  todos={data.items}
                  selectedIds={selectedIds}
                  onSelectedChange={handleSelectedChange}
                  isFiltered={isFiltered}
                />
              )}

              {data && total > 0 && (
                <div className="mt-4 flex items-center justify-between gap-4">
                  <p className="text-sm text-muted-foreground">
                    Showing {data.items.length} of {total} todos
                  </p>

                  {pageCount > 1 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8"
                        aria-label="Previous page"
                        disabled={effectiveFilters.page <= 1 || isFetching}
                        onClick={() =>
                          setFilters((current) => ({
                            ...current,
                            page: Math.max(1, current.page - 1),
                          }))
                        }
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-sm text-muted-foreground tabular-nums">
                        Page {effectiveFilters.page} / {pageCount}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8"
                        aria-label="Next page"
                        disabled={
                          effectiveFilters.page >= pageCount || isFetching
                        }
                        onClick={() =>
                          setFilters((current) => ({
                            ...current,
                            page: Math.min(pageCount, current.page + 1),
                          }))
                        }
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </main>

      <TodoForm
        mode="create"
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
      />

      <TagManagerDialog
        open={showTagManager}
        onClose={() => setShowTagManager(false)}
      />
    </div>
  );
}
