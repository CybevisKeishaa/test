import { expect, test } from "@playwright/test";
import {
  attachTag,
  closeDialog,
  completionCheckbox,
  createTag,
  createTodo,
  openTagManager,
  register,
  selectionCheckbox,
  todoRow,
  uniqueEmail,
} from "./helpers";

test.describe("Tags", () => {
  test("create a tag, attach it to a todo and see it on the row", async ({
    page,
  }) => {
    await register(page, uniqueEmail("tags"));

    await createTodo(page, "Write the report");
    await createTag(page, "work");
    await attachTag(page, "Write the report", "work");

    // The badge renders on the row itself, not only inside the edit dialog.
    await expect(
      todoRow(page, "Write the report").getByText("work", { exact: true })
    ).toBeVisible();

    // And it survives a reload, so it really reached the server.
    await page.reload();
    await expect(
      todoRow(page, "Write the report").getByText("work", { exact: true })
    ).toBeVisible();
  });

  test("a duplicate tag name is refused with the server's message", async ({
    page,
  }) => {
    await register(page, uniqueEmail("dupe-tag"));
    await createTag(page, "Work");

    const dialog = await openTagManager(page);
    // Different casing: the backend's uniqueness is case-insensitive.
    await dialog.getByLabel("New tag").fill("work");
    await dialog.getByRole("button", { name: "Add tag" }).click();

    await expect(
      page.getByText("You already have a tag named 'work'")
    ).toBeVisible();
    // Still exactly one tag. Counting rename buttons rather than looking for
    // "Rename work": Playwright matches accessible names case-insensitively,
    // so that would find the original "Work" and prove nothing.
    await expect(dialog.getByRole("button", { name: /^Rename / })).toHaveCount(1);
  });

  test("an empty tag name is caught before any request", async ({ page }) => {
    await register(page, uniqueEmail("blank-tag"));

    const dialog = await openTagManager(page);
    let requested = false;
    page.on("request", (request) => {
      if (request.url().includes("/api/v1/tags") && request.method() === "POST") {
        requested = true;
      }
    });

    await dialog.getByLabel("New tag").fill("   ");
    await dialog.getByRole("button", { name: "Add tag" }).click();

    await expect(dialog.getByText("Tag name is required")).toBeVisible();
    expect(requested).toBe(false);
  });

  test("renaming a tag updates the badge on the todo", async ({ page }) => {
    await register(page, uniqueEmail("rename-tag"));
    await createTodo(page, "Tagged todo");
    await createTag(page, "before");
    await attachTag(page, "Tagged todo", "before");

    const dialog = await openTagManager(page);
    await dialog.getByRole("button", { name: "Rename before" }).click();
    await dialog.getByLabel("Rename tag").fill("after");
    await dialog.getByRole("button", { name: "Save" }).click();
    await closeDialog(page);

    const row = todoRow(page, "Tagged todo");
    await expect(row.getByText("after", { exact: true })).toBeVisible();
    await expect(row.getByText("before", { exact: true })).toHaveCount(0);
  });

  test("deleting a tag removes it from the todo but keeps the todo", async ({
    page,
  }) => {
    await register(page, uniqueEmail("delete-tag"));
    await createTodo(page, "Survivor");
    await createTag(page, "doomed");
    await attachTag(page, "Survivor", "doomed");

    page.once("dialog", (confirmation) => confirmation.accept());

    const dialog = await openTagManager(page);
    await dialog.getByRole("button", { name: "Delete doomed" }).click();
    await expect(
      dialog.getByRole("button", { name: "Delete doomed" })
    ).toHaveCount(0);
    await closeDialog(page);

    await expect(todoRow(page, "Survivor")).toBeVisible();
    await expect(
      todoRow(page, "Survivor").getByText("doomed", { exact: true })
    ).toHaveCount(0);
  });
});

test.describe("Filters", () => {
  test("filter by status, keyword and tag, then clear", async ({ page }) => {
    await register(page, uniqueEmail("filters"));

    await createTodo(page, "Buy milk");
    await createTodo(page, "Write report");
    await createTag(page, "errand");
    await attachTag(page, "Buy milk", "errand");

    await test.step("mark one complete", async () => {
      await completionCheckbox(page, "Buy milk").click();
      await expect(completionCheckbox(page, "Buy milk")).toBeChecked();
    });

    await test.step("status", async () => {
      await page.getByLabel("Status", { exact: true }).selectOption("completed");
      await expect(todoRow(page, "Buy milk")).toBeVisible();
      await expect(todoRow(page, "Write report")).toHaveCount(0);

      await page.getByLabel("Status", { exact: true }).selectOption("active");
      await expect(todoRow(page, "Write report")).toBeVisible();
      await expect(todoRow(page, "Buy milk")).toHaveCount(0);

      await page.getByLabel("Status", { exact: true }).selectOption("all");
    });

    await test.step("keyword", async () => {
      await page.getByLabel("Search").fill("report");
      await expect(todoRow(page, "Write report")).toBeVisible();
      await expect(todoRow(page, "Buy milk")).toHaveCount(0);
      await page.getByLabel("Search").fill("");
      await expect(todoRow(page, "Buy milk")).toBeVisible();
    });

    await test.step("tag", async () => {
      await page
        .getByLabel("Tag", { exact: true })
        .selectOption({ label: "errand" });
      await expect(todoRow(page, "Buy milk")).toBeVisible();
      await expect(todoRow(page, "Write report")).toHaveCount(0);
    });

    await test.step("clear filters brings everything back", async () => {
      await page.getByRole("button", { name: "Clear filters" }).click();
      await expect(todoRow(page, "Buy milk")).toBeVisible();
      await expect(todoRow(page, "Write report")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Clear filters" })
      ).toHaveCount(0);
    });
  });

  test("a filtered empty list says so, rather than looking like an empty account", async ({
    page,
  }) => {
    await register(page, uniqueEmail("empty-filter"));
    await createTodo(page, "The only todo");

    await page.getByLabel("Search").fill("nothing matches this");

    await expect(page.getByText("No todos match these filters")).toBeVisible();
    await expect(page.getByText("No todos yet")).toHaveCount(0);
  });

  test("a date range excludes todos created outside it", async ({ page }) => {
    await register(page, uniqueEmail("date-filter"));
    await createTodo(page, "Created today");

    const tomorrow = new Date(Date.now() + 86_400_000)
      .toISOString()
      .slice(0, 10);

    await page.getByLabel("From", { exact: true }).fill(tomorrow);
    await expect(page.getByText("No todos match these filters")).toBeVisible();

    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(todoRow(page, "Created today")).toBeVisible();
  });
});

test.describe("Bulk actions", () => {
  test("select several todos and mark them completed, then active", async ({
    page,
  }) => {
    await register(page, uniqueEmail("bulk"));

    for (const title of ["First", "Second", "Third"]) {
      await createTodo(page, title);
    }

    await test.step("the bar only appears once something is selected", async () => {
      await expect(
        page.getByRole("region", { name: "Bulk actions" })
      ).toHaveCount(0);

      await selectionCheckbox(page, "First").click();
      await selectionCheckbox(page, "Second").click();

      await expect(page.getByText("2 selected")).toBeVisible();
    });

    await test.step("mark completed", async () => {
      await page.getByRole("button", { name: "Mark completed" }).click();

      await expect(completionCheckbox(page, "First")).toBeChecked();
      await expect(completionCheckbox(page, "Second")).toBeChecked();
      // The one that was never selected is untouched.
      await expect(completionCheckbox(page, "Third")).not.toBeChecked();

      // The selection clears once the write lands.
      await expect(
        page.getByRole("region", { name: "Bulk actions" })
      ).toHaveCount(0);
    });

    await test.step("it survives a reload", async () => {
      await page.reload();
      await expect(completionCheckbox(page, "First")).toBeChecked();
      await expect(completionCheckbox(page, "Third")).not.toBeChecked();
    });

    await test.step("mark active again", async () => {
      await selectionCheckbox(page, "First").click();
      await page.getByRole("button", { name: "Mark active" }).click();

      await expect(completionCheckbox(page, "First")).not.toBeChecked();
      await expect(completionCheckbox(page, "Second")).toBeChecked();
    });
  });

  test("clear selection leaves the todos alone", async ({ page }) => {
    await register(page, uniqueEmail("bulk-clear"));
    await createTodo(page, "Untouched");

    await selectionCheckbox(page, "Untouched").click();
    await expect(page.getByText("1 selected")).toBeVisible();

    await page.getByRole("button", { name: "Clear selection" }).click();

    await expect(page.getByRole("region", { name: "Bulk actions" })).toHaveCount(
      0
    );
    await expect(completionCheckbox(page, "Untouched")).not.toBeChecked();
  });
});
