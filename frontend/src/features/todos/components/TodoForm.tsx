import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useTags } from "@/features/tags/api/tags";
import {
  useAttachTag,
  useCreateTodo,
  useDetachTag,
  useUpdateTodo,
} from "../api/todos";
import { todoSchema, type TodoFormData } from "../schemas/todo";
import type { Todo } from "../api/todos";

interface TodoFormProps {
  mode: "create" | "edit";
  todo?: Todo;
  open: boolean;
  onClose: () => void;
}

export function TodoForm({ mode, todo, open, onClose }: TodoFormProps) {
  const createTodo = useCreateTodo();
  const updateTodo = useUpdateTodo();
  const attachTag = useAttachTag();
  const detachTag = useDetachTag();
  const { data: tagData } = useTags();

  // Tracked locally: the `todo` prop is a snapshot taken when the dialog
  // opened, so it does not follow the refetch that each attach/detach causes.
  const [attachedIds, setAttachedIds] = useState<Set<string>>(
    () => new Set(todo?.tags.map((tag) => tag.id))
  );

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<TodoFormData>({
    resolver: zodResolver(todoSchema),
    defaultValues: {
      title: todo?.title || "",
      description: todo?.description || "",
    },
  });

  const onSubmit = (data: TodoFormData) => {
    if (mode === "create") {
      createTodo.mutate(data, {
        onSuccess: () => {
          reset();
          onClose();
        },
      });
    } else if (todo) {
      updateTodo.mutate(
        { id: todo.id, data },
        {
          onSuccess: () => {
            onClose();
          },
        }
      );
    }
  };

  const toggleTag = (tagId: string) => {
    if (!todo) return;

    const next = new Set(attachedIds);

    if (attachedIds.has(tagId)) {
      next.delete(tagId);
      setAttachedIds(next);
      detachTag.mutate(
        { todoId: todo.id, tagId },
        // Put it back if the server refused, rather than leaving the chip
        // showing a change that did not happen.
        { onError: () => setAttachedIds(new Set(attachedIds)) }
      );
    } else {
      next.add(tagId);
      setAttachedIds(next);
      attachTag.mutate(
        { todoId: todo.id, tagId },
        { onError: () => setAttachedIds(new Set(attachedIds)) }
      );
    }
  };

  const tags = tagData?.items ?? [];
  const isPending = createTodo.isPending || updateTodo.isPending;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Create Todo" : "Edit Todo"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              placeholder="What needs to be done?"
              {...register("title")}
            />
            {errors.title && (
              <p className="text-sm text-destructive">
                {errors.title.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description (optional)</Label>
            <Input
              id="description"
              placeholder="Add details..."
              {...register("description")}
            />
            {errors.description && (
              <p className="text-sm text-destructive">
                {errors.description.message}
              </p>
            )}
          </div>

          {mode === "edit" && (
            <div className="space-y-2">
              <Label>Tags</Label>
              {tags.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No tags yet &mdash; create one from &ldquo;Tags&rdquo; in the
                  header.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((tag) => {
                    const isAttached = attachedIds.has(tag.id);
                    return (
                      <button
                        key={tag.id}
                        type="button"
                        aria-pressed={isAttached}
                        aria-label={`${isAttached ? "Remove" : "Add"} tag ${tag.name}`}
                        onClick={() => toggleTag(tag.id)}
                        className={cn(
                          "rounded-full transition-opacity",
                          !isAttached && "opacity-40 hover:opacity-70"
                        )}
                      >
                        <Badge color={tag.color}>{tag.name}</Badge>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending
                ? mode === "create"
                  ? "Creating..."
                  : "Saving..."
                : mode === "create"
                ? "Create"
                : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
