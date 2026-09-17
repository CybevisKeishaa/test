import { z } from "zod";

// Mirrors the backend bounds in app/schemas/user.py: 8 characters minimum,
// 72 bytes maximum because bcrypt truncates anything longer.
const MIN_PASSWORD = 8;
const MAX_PASSWORD = 72;

const passwordField = z
  .string()
  .min(MIN_PASSWORD, `Password must be at least ${MIN_PASSWORD} characters`)
  .max(MAX_PASSWORD, `Password must be at most ${MAX_PASSWORD} characters`);

export const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

export const registerSchema = z
  .object({
    email: z.string().email("Invalid email address"),
    password: passwordField,
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

export type LoginFormData = z.infer<typeof loginSchema>;
export type RegisterFormData = z.infer<typeof registerSchema>;
