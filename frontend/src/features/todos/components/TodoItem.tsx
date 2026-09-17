import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pencil, Trash2 } from "lucide-react";
import type { Todo } from "../api/todos";

interface TodoItemProps {
  todo: Todo;
  selected: boolean;
  onSelectedChange: (todoId: string, selected: boolean) => void;
  onToggle: (todo: Todo) => void;
  onEdit: (todo: Todo) => void;
  onDelete: (id: string) => void;
}

export function TodoItem({
  todo,
  selected,
  onSelectedChange,
  onToggle,
  onEdit,
  onDelete,
}: TodoItemProps) {
  return (
    <div
      data-testid="todo-row"
      className="flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors group"
    >
      {/* Two checkboxes share this row, so both carry an explicit accessible
          name -- "select for a bulk action" and "mark done" are very different
          actions to confuse. */}
      <Checkbox
        aria-label={`Select "${todo.title}"`}
        checked={selected}
        onCheckedChange={(value) => onSelectedChange(todo.id, value === true)}
      />

      <Checkbox
        id={`todo-${todo.id}`}
        aria-label={`Mark "${todo.title}" as ${
          todo.completed ? "active" : "completed"
        }`}
        checked={todo.completed}
        onCheckedChange={() => onToggle(todo)}
      />

      <div className="flex-1 min-w-0">
        <label
          htmlFor={`todo-${todo.id}`}
          className={`text-sm font-medium cursor-pointer ${
            todo.completed ? "line-through text-muted-foreground" : ""
          }`}
        >
          {todo.title}
        </label>
        {todo.description && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
            {todo.description}
          </p>
        )}
        {todo.tags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {todo.tags.map((tag) => (
              <Badge key={tag.id} color={tag.color}>
                {tag.name}
              </Badge>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          aria-label={`Edit "${todo.title}"`}
          onClick={() => onEdit(todo)}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-destructive hover:text-destructive"
          aria-label={`Delete "${todo.title}"`}
          onClick={() => onDelete(todo.id)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
