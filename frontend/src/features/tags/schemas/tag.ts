import { z } from "zod";

// Mirrors the backend rules in app/schemas/tag.py: 1..50 characters after
// trimming, and a hex colour if one is given.
export const MAX_TAG_NAME = 50;
const HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export const tagSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Tag name is required")
    .max(MAX_TAG_NAME, `Tag name must be at most ${MAX_TAG_NAME} characters`),
  // Empty is allowed and means "no colour"; anything else must be a hex value.
  color: z
    .string()
    .trim()
    .refine((value) => value === "" || HEX_COLOR.test(value), {
      message: "Use a hex colour such as #4f46e5",
    }),
});

export type TagFormData = z.infer<typeof tagSchema>;

/** A palette offered in the tag form, so most users never type a hex value. */
export const TAG_COLORS = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#ec4899",
  "#64748b",
] as const;
