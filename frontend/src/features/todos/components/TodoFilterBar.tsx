import { Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useTags } from "@/features/tags/api/tags";
import type { TodoFilters, TodoStatus } from "../api/todos";

interface TodoFilterBarProps {
  filters: TodoFilters;
  /** Keyword is held locally so typing stays responsive; see TodoPage. */
  keywordDraft: string;
  onKeywordChange: (value: string) => void;
  onChange: (patch: Partial<TodoFilters>) => void;
  onClear: () => void;
  isFiltered: boolean;
}

const STATUS_OPTIONS: { value: TodoStatus; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "completed", label: "Completed" },
];

const selectClass = cn(
  "h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
  "outline-none transition-[color,box-shadow] focus-visible:border-ring",
  "focus-visible:ring-[3px] focus-visible:ring-ring/50"
);

export function TodoFilterBar({
  filters,
  keywordDraft,
  onKeywordChange,
  onChange,
  onClear,
  isFiltered,
}: TodoFilterBarProps) {
  const { data: tagData } = useTags();
  const tags = tagData?.items ?? [];

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <div className="space-y-1.5 lg:col-span-2">
        <Label htmlFor="filter-keyword">Search</Label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="filter-keyword"
            className="pl-8"
            placeholder="Title or description"
            value={keywordDraft}
            onChange={(event) => onKeywordChange(event.target.value)}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="filter-status">Status</Label>
        <select
          id="filter-status"
          className={selectClass}
          value={filters.status}
          onChange={(event) =>
            onChange({ status: event.target.value as TodoStatus })
          }
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="filter-tag">Tag</Label>
        <select
          id="filter-tag"
          className={selectClass}
          value={filters.tagId ?? ""}
          onChange={(event) =>
            onChange({ tagId: event.target.value || null })
          }
        >
          <option value="">All tags</option>
          {tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="filter-date-from">From</Label>
          <Input
            id="filter-date-from"
            type="date"
            value={filters.dateFrom}
            max={filters.dateTo || undefined}
            onChange={(event) => onChange({ dateFrom: event.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="filter-date-to">To</Label>
          <Input
            id="filter-date-to"
            type="date"
            value={filters.dateTo}
            min={filters.dateFrom || undefined}
            onChange={(event) => onChange({ dateTo: event.target.value })}
          />
        </div>
      </div>

      {isFiltered && (
        <div className="sm:col-span-2 lg:col-span-5">
          <Button variant="ghost" size="sm" onClick={onClear}>
            <X className="mr-1 h-3.5 w-3.5" />
            Clear filters
          </Button>
        </div>
      )}
    </div>
  );
}
