import { useState } from "react";
import { TodoItem } from "./TodoItem";
import { TodoForm } from "./TodoForm";
import type { Todo } from "../api/todos";
import { useDeleteTodo, useToggleTodo } from "../api/todos";

interface TodoListProps {
  todos: Todo[];
  selectedIds: Set<string>;
  onSelectedChange: (todoId: string, selected: boolean) => void;
  isFiltered: boolean;
}

export function TodoList({
  todos,
  selectedIds,
  onSelectedChange,
  isFiltered,
}: TodoListProps) {
  const [editingTodo, setEditingTodo] = useState<Todo | null>(null);
  const deleteTodo = useDeleteTodo();
  const toggleTodo = useToggleTodo();

  const handleToggle = (todo: Todo) => {
    toggleTodo.toggle(todo);
  };

  const handleEdit = (todo: Todo) => {
    setEditingTodo(todo);
  };

  const handleDelete = (id: string) => {
    deleteTodo.mutate(id);
  };

  if (todos.length === 0) {
    // An empty *filtered* list means something different from an empty
    // account, and telling them apart is the difference between "add a todo"
    // and "your filters are too narrow".
    return (
      <div className="text-center py-12 text-muted-foreground">
        {isFiltered ? (
          <>
            <p className="text-lg">No todos match these filters</p>
            <p className="text-sm mt-1">Try clearing or widening them</p>
          </>
        ) : (
          <>
            <p className="text-lg">No todos yet</p>
            <p className="text-sm mt-1">Create your first todo to get started</p>
          </>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {todos.map((todo) => (
          // Keyed by id, not array index: with an index key React reuses the
          // DOM node of a deleted row for its replacement, so the checkbox
          // state of the row above slides onto the wrong todo.
          <TodoItem
            key={todo.id}
            todo={todo}
            selected={selectedIds.has(todo.id)}
            onSelectedChange={onSelectedChange}
            onToggle={handleToggle}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        ))}
      </div>

      {editingTodo && (
        <TodoForm
          mode="edit"
          todo={editingTodo}
          open={!!editingTodo}
          onClose={() => setEditingTodo(null)}
        />
      )}
    </>
  );
}
