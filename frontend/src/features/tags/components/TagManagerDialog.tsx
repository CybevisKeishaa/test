import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  useCreateTag,
  useDeleteTag,
  useTags,
  useUpdateTag,
  type Tag,
} from "../api/tags";
import { TAG_COLORS, tagSchema, type TagFormData } from "../schemas/tag";

interface TagManagerDialogProps {
  open: boolean;
  onClose: () => void;
}

export function TagManagerDialog({ open, onClose }: TagManagerDialogProps) {
  const { data, isLoading } = useTags();
  const createTag = useCreateTag();
  const updateTag = useUpdateTag();
  const deleteTag = useDeleteTag();

  const [editing, setEditing] = useState<Tag | null>(null);

  const {
    control,
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<TagFormData>({
    resolver: zodResolver(tagSchema),
    defaultValues: { name: "", color: "" },
  });

  // useWatch subscribes properly; watch() re-reads on every render.
  const selectedColor = useWatch({ control, name: "color" });

  // Load the row being edited into the one form the dialog has.
  useEffect(() => {
    reset({ name: editing?.name ?? "", color: editing?.color ?? "" });
  }, [editing, reset]);

  // Never carry one session's draft into the next opening of the dialog.
  // Done on the way out rather than in an effect watching `open`, so there is
  // no cascading render and every close path goes through one place.
  const handleClose = () => {
    setEditing(null);
    reset({ name: "", color: "" });
    onClose();
  };

  const onSubmit = (values: TagFormData) => {
    // "" means "no colour"; the API wants null.
    const payload = { name: values.name, color: values.color || null };

    if (editing) {
      updateTag.mutate(
        { id: editing.id, data: payload },
        { onSuccess: () => setEditing(null) }
      );
    } else {
      createTag.mutate(payload, {
        onSuccess: () => reset({ name: "", color: "" }),
      });
    }
  };

  const tags = data?.items ?? [];
  const isPending = createTag.isPending || updateTag.isPending;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Manage tags</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="tag-name">
              {editing ? "Rename tag" : "New tag"}
            </Label>
            <Input
              id="tag-name"
              placeholder="e.g. Work"
              autoComplete="off"
              {...register("name")}
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="tag-color">Colour</Label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="No colour"
                aria-pressed={!selectedColor}
                onClick={() => setValue("color", "", { shouldValidate: true })}
                className={cn(
                  "h-6 w-6 rounded-full border bg-secondary",
                  !selectedColor && "ring-2 ring-ring ring-offset-2"
                )}
              />
              {TAG_COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  aria-label={`Colour ${color}`}
                  aria-pressed={selectedColor === color}
                  onClick={() => setValue("color", color, { shouldValidate: true })}
                  style={{ backgroundColor: color }}
                  className={cn(
                    "h-6 w-6 rounded-full border",
                    selectedColor === color && "ring-2 ring-ring ring-offset-2"
                  )}
                />
              ))}
            </div>
            <Input
              id="tag-color"
              placeholder="#4f46e5"
              autoComplete="off"
              {...register("color")}
            />
            {errors.color && (
              <p className="text-sm text-destructive">{errors.color.message}</p>
            )}
          </div>

          <div className="flex justify-end gap-2">
            {editing && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setEditing(null)}
              >
                <X className="mr-1 h-3.5 w-3.5" />
                Cancel
              </Button>
            )}
            <Button type="submit" size="sm" disabled={isPending}>
              {editing ? (
                <>
                  <Check className="mr-1 h-3.5 w-3.5" />
                  {updateTag.isPending ? "Saving..." : "Save"}
                </>
              ) : (
                <>
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  {createTag.isPending ? "Adding..." : "Add tag"}
                </>
              )}
            </Button>
          </div>
        </form>

        <Separator />

        <div className="max-h-64 space-y-1 overflow-y-auto">
          {isLoading && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Loading tags...
            </p>
          )}

          {!isLoading && tags.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No tags yet
            </p>
          )}

          {tags.map((tag) => (
            <div
              key={tag.id}
              className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent/50"
            >
              <Badge color={tag.color}>{tag.name}</Badge>
              <span className="flex-1" />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                aria-label={`Rename ${tag.name}`}
                onClick={() => setEditing(tag)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive hover:text-destructive"
                aria-label={`Delete ${tag.name}`}
                disabled={deleteTag.isPending}
                onClick={() => {
                  // Deleting a tag detaches it from every todo, so make that
                  // consequence explicit rather than discovering it after.
                  if (
                    window.confirm(
                      `Delete "${tag.name}"? It will be removed from every todo that uses it.`
                    )
                  ) {
                    deleteTag.mutate(tag.id);
                    if (editing?.id === tag.id) setEditing(null);
                  }
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
