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

/** The row containing a todo with this title. */
export function todoRow(page: Page, title: string) {
  return page.getByTestId("todo-row").filter({ hasText: title });
}

/**
 * A row carries two checkboxes -- "select for a bulk action" and "mark done".
 * Both have an accessible name, so tests address them by intent rather than
 * by position.
 */
export function completionCheckbox(page: Page, title: string) {
  return todoRow(page, title).getByRole("checkbox", { name: /^Mark "/ });
}

export function selectionCheckbox(page: Page, title: string) {
  return todoRow(page, title).getByRole("checkbox", { name: /^Select "/ });
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

  await completionCheckbox(page, title).click();

  const response = await saved;
  expect(response.status()).toBe(200);
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
}

/** Open the tag manager dialog from the header. */
export async function openTagManager(page: Page) {
  await page.getByRole("button", { name: "Tags" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Manage tags")).toBeVisible();
  return dialog;
}

export async function closeDialog(page: Page) {
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
}

/** Create a tag through the tag manager and close it again. */
export async function createTag(page: Page, name: string) {
  const dialog = await openTagManager(page);
  await dialog.getByLabel("New tag").fill(name);
  await dialog.getByRole("button", { name: "Add tag" }).click();
  await expect(dialog.getByRole("button", { name: `Rename ${name}` })).toBeVisible();
  await closeDialog(page);
}

/** Attach an existing tag to a todo through that todo's edit dialog. */
export async function attachTag(page: Page, todoTitle: string, tagName: string) {
  await todoRow(page, todoTitle).getByRole("button", { name: /^Edit "/ }).click();

  const dialog = page.getByRole("dialog");
  const chip = dialog.getByRole("button", { name: `Add tag ${tagName}` });
  await expect(chip).toBeVisible();
  await chip.click();
  // aria-pressed flips once the attach lands.
  await expect(
    dialog.getByRole("button", { name: `Remove tag ${tagName}` })
  ).toBeVisible();

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
}
