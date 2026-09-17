import { CheckCheck, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface TodoBulkActionsProps {
  selectedCount: number;
  isPending: boolean;
  onMarkCompleted: () => void;
  onMarkActive: () => void;
  onClearSelection: () => void;
}

export function TodoBulkActions({
  selectedCount,
  isPending,
  onMarkCompleted,
  onMarkActive,
  onClearSelection,
}: TodoBulkActionsProps) {
  if (selectedCount === 0) return null;

  return (
    <div
      // Announced so a screen-reader user learns the bar appeared, rather than
      // only sighted users noticing it slide in.
      role="region"
      aria-label="Bulk actions"
      className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-accent/40 px-3 py-2"
    >
      <span className="text-sm font-medium">
        {selectedCount} selected
      </span>
      <span className="flex-1" />
      <Button size="sm" disabled={isPending} onClick={onMarkCompleted}>
        <CheckCheck className="mr-1 h-3.5 w-3.5" />
        Mark completed
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={isPending}
        onClick={onMarkActive}
      >
        <RotateCcw className="mr-1 h-3.5 w-3.5" />
        Mark active
      </Button>
      <Button size="sm" variant="ghost" onClick={onClearSelection}>
        <X className="mr-1 h-3.5 w-3.5" />
        Clear selection
      </Button>
    </div>
  );
}
