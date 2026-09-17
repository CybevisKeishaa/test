import { useState } from "react";
import { Plus, LogOut, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { DEFAULT_PAGE_SIZE, useTodos } from "../api/todos";
import { TodoList } from "./TodoList";
import { TodoForm } from "./TodoForm";
import { useAuth } from "@/features/auth/hooks/useAuth";

export function TodoPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [page, setPage] = useState(1);
  const { data, isLoading, isFetching, error } = useTodos(page, DEFAULT_PAGE_SIZE);
  const { user, logout } = useAuth();

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / DEFAULT_PAGE_SIZE));

  // A delete can empty the last page; step back rather than showing nothing.
  if (page > pageCount && !isFetching) {
    setPage(pageCount);
  }

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
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
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
          <CardContent className="pt-4">
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

            {data && <TodoList todos={data.items} />}

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
                      disabled={page <= 1 || isFetching}
                      onClick={() => setPage((current) => Math.max(1, current - 1))}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      Page {page} / {pageCount}
                    </span>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      aria-label="Next page"
                      disabled={page >= pageCount || isFetching}
                      onClick={() =>
                        setPage((current) => Math.min(pageCount, current + 1))
                      }
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      {/* Create Todo Dialog */}
      <TodoForm
        mode="create"
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
      />
    </div>
  );
}
