import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * Small inline label. `color` is a hex value chosen by the user, so the text
 * colour is picked from the background's luminance rather than hard-coded --
 * white on a pale yellow tag is unreadable.
 */
function readableTextColor(hex?: string | null): string | undefined {
  if (!hex) return undefined;

  const value = hex.replace("#", "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value;

  if (full.length !== 6) return undefined;

  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);

  // Rec. 709 luma.
  const luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return luma > 0.6 ? "#1f2937" : "#ffffff";
}

// `color` is omitted from the span props first: the DOM attribute is
// `string | undefined`, and a tag's colour is nullable.
interface BadgeProps extends Omit<ComponentProps<"span">, "color"> {
  color?: string | null;
}

export function Badge({ className, color, style, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium leading-4",
        !color && "bg-secondary text-secondary-foreground",
        className
      )}
      style={
        color
          ? { backgroundColor: color, color: readableTextColor(color), ...style }
          : style
      }
      {...props}
    />
  );
}
