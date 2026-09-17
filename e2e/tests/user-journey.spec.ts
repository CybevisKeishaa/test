import { expect, test } from "@playwright/test";
import {
  completionCheckbox,
  createTodo,
  login,
  logout,
  register,
  todoRow,
  toggleTodo,
  uniqueEmail,
} from "./helpers";

test.describe("Full user journey", () => {
  test("register, create a todo, toggle it, verify, log out and back in", async ({
    page,
  }) => {
    const email = uniqueEmail("journey");
    const title = "Ship the assessment";

    await test.step("register", async () => {
      await register(page, email);
    });

    await test.step("the new account starts empty", async () => {
      await expect(page.getByText("No todos yet")).toBeVisible();
    });

    await test.step("create a todo", async () => {
      await createTodo(page, title, "Finish every tier");
      await expect(page.getByText("Finish every tier")).toBeVisible();
    });

    const checkbox = completionCheckbox(page, title);

    await test.step("toggle it complete", async () => {
      await expect(checkbox).not.toBeChecked();
      await toggleTodo(page, title);
      await expect(checkbox).toBeChecked();
      // Completion is styled, so assert what the user actually sees.
      await expect(page.getByText(title, { exact: true })).toHaveClass(
        /line-through/
      );
    });

    await test.step("completion survives a reload", async () => {
      // Regression guard: the list cache was neither scoped nor invalidated,
      // so a reload used to serve the pre-toggle body back.
      await page.reload();
      await expect(completionCheckbox(page, title)).toBeChecked();
    });

    await test.step("toggle it back to active", async () => {
      // Regression guard: `if todo_data.completed:` discarded the falsy value,
      // so a completed todo could never be reopened.
      await toggleTodo(page, title);
      await expect(completionCheckbox(page, title)).not.toBeChecked();

      await page.reload();
      await expect(completionCheckbox(page, title)).not.toBeChecked();
    });

    await test.step("log out", async () => {
      await logout(page);
    });

    await test.step("the session is really gone", async () => {
      // Visiting a protected route must bounce back to /login rather than
      // rendering the previous session out of the client cache.
      await page.goto("/");
      await expect(page).toHaveURL(/\/login$/);
    });

    await test.step("log back in and find the todo still there", async () => {
      await login(page, email);
      await expect(todoRow(page, title)).toBeVisible();
    });
  });

  test("a title-only edit keeps the description", async ({ page }) => {
    // Regression guard: model_dump() without exclude_unset blanked every field
    // the request did not mention.
    const email = uniqueEmail("partial");
    await register(page, email);

    await createTodo(page, "Original title", "Description to preserve");

    await todoRow(page, "Original title")
      .getByRole("button", { name: /^Edit "/ })
      .click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Title").fill("Renamed title");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();

    await expect(page.getByText("Renamed title", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Description to preserve", { exact: true })
    ).toBeVisible();
  });

  test("a wrong password shows an error instead of reloading the page", async ({
    page,
  }) => {
    // Regression guard: the 401 interceptor fired on the login request itself,
    // wiping storage and hard-navigating before the toast could be read.
    const email = uniqueEmail("badpass");
    await register(page, email);
    await logout(page);

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("WrongPassword@1");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Invalid email or password")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });
});
