import { expect, type Page } from "@playwright/test";

/** Satisfies the backend rule of 8..72 characters. */
export const PASSWORD = "Password@123";

/**
 * A fresh address per call.
 *
 * Registration is permanent, so reusing a fixed address would make the second
 * run of the suite fail against a stack that was not torn down.
 *
 * The domain is deliberately not `.test`/`.invalid`/`.example`: those are
 * IANA special-use names and `email-validator`, behind pydantic's EmailStr,
 * rejects them with a 422.
 */
export function uniqueEmail(prefix: string): string {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `${prefix}-${suffix}@e2etest.com`;
}

export async function register(page: Page, email: string): Promise<void> {
  await page.goto("/register");

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create Account" }).click();

  await expectOnTodoPage(page, email);
}

export async function login(page: Page, email: string): Promise<void> {
  await page.goto("/login");

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();

  await expectOnTodoPage(page, email);
}

export async function expectOnTodoPage(page: Page, email: string): Promise<void> {
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Todo App" })).toBeVisible();
  // The header shows the signed-in address, which is how a test tells the two
  // accounts apart.
  await expect(page.getByText(email, { exact: true })).toBeVisible();
}

export async function createTodo(
  page: Page,
  title: string,
  description?: string
): Promise<void> {
  await page.getByRole("button", { name: "Add Todo" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  await dialog.getByLabel("Title").fill(title);
  if (description) {
    await dialog.getByLabel("Description (optional)").fill(description);
  }
  await dialog.getByRole("button", { name: "Create", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(todoRow(page, title)).toBeVisible();
}

/** The row containing a todo with this exact title. */
export function todoRow(page: Page, title: string) {
  return page
    .locator("div")
    .filter({ has: page.getByText(title, { exact: true }) })
    .filter({ has: page.getByRole("checkbox") })
    .last();
}

/**
 * Toggle a todo and wait for the write to actually land.
 *
 * The checkbox flips optimistically, so asserting on the UI proves nothing
 * about the server. Reloading straight after the click would abort the PUT
 * still in flight and the todo would come back unchanged.
 */
export async function toggleTodo(page: Page, title: string): Promise<void> {
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().includes("/api/v1/todos/")
  );

  await todoRow(page, title).getByRole("checkbox").click();

  const response = await saved;
  expect(response.status()).toBe(200);
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
}
