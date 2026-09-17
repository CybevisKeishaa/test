import { expect, test } from "@playwright/test";
import { API_URL } from "../playwright.config";
import {
  createTodo,
  login,
  logout,
  PASSWORD,
  register,
  todoRow,
  uniqueEmail,
} from "./helpers";

test.describe("Cross-user data isolation", () => {
  test("User B never sees User A's todos, in a separate session", async ({
    browser,
  }) => {
    const alice = uniqueEmail("alice");
    const bob = uniqueEmail("bob");
    const secret = `Alice private todo ${Date.now()}`;

    // Two contexts, so the two accounts have genuinely separate storage and
    // cookies rather than taking turns in one browser profile.
    const aliceContext = await browser.newContext();
    const bobContext = await browser.newContext();
    const alicePage = await aliceContext.newPage();
    const bobPage = await bobContext.newPage();

    try {
      await test.step("Alice registers and creates a private todo", async () => {
        await register(alicePage, alice);
        await createTodo(alicePage, secret, "Nobody else should read this");
      });

      await test.step("Bob registers in his own session", async () => {
        await register(bobPage, bob);
      });

      await test.step("Bob's list is empty", async () => {
        // The original cache key was the constant "todos:list", so whoever
        // listed first populated it for everybody: Bob was served Alice's
        // todos with no request of his own reaching the database.
        await expect(bobPage.getByText("No todos yet")).toBeVisible();
        await expect(bobPage.getByText(secret)).toHaveCount(0);
      });

      await test.step("Bob still sees nothing after a reload", async () => {
        await bobPage.reload();
        await expect(bobPage.getByText("No todos yet")).toBeVisible();
        await expect(bobPage.getByText(secret)).toHaveCount(0);
      });

      await test.step("Alice can still see her own todo", async () => {
        await alicePage.reload();
        await expect(todoRow(alicePage, secret)).toBeVisible();
      });
    } finally {
      await aliceContext.close();
      await bobContext.close();
    }
  });

  test("User B cannot read or modify User A's todo through the API", async ({
    browser,
    request,
  }) => {
    const alice = uniqueEmail("api-alice");
    const bob = uniqueEmail("api-bob");

    const context = await browser.newContext();
    const page = await context.newPage();

    try {
      await register(page, alice);
      await createTodo(page, "Alice API todo");

      // Read Alice's token straight out of her session, then put the browser
      // away: the rest is a direct API check that the UI cannot hide.
      const aliceToken = await page.evaluate(() =>
        localStorage.getItem("access_token")
      );
      expect(aliceToken).toBeTruthy();

      const aliceList = await request.get(`${API_URL}/api/v1/todos`, {
        headers: { Authorization: `Bearer ${aliceToken}` },
      });
      expect(aliceList.ok()).toBeTruthy();
      const aliceTodos = (await aliceList.json()).items;
      // Asserted explicitly: indexing an empty array here would fail with a
      // TypeError that says nothing about what actually went wrong.
      expect(aliceTodos).toHaveLength(1);
      const todoId = aliceTodos[0].id;

      const bobTokens = await request.post(
        `${API_URL}/api/v1/auth/register`,
        { data: { email: bob, password: PASSWORD } }
      );
      expect(bobTokens.status()).toBe(201);
      const bobAuth = {
        Authorization: `Bearer ${(await bobTokens.json()).access_token}`,
      };

      await test.step("Bob cannot read it", async () => {
        const response = await request.get(
          `${API_URL}/api/v1/todos/${todoId}`,
          { headers: bobAuth }
        );
        expect(response.status()).toBe(404);
        expect(await response.text()).not.toContain("Alice API todo");
      });

      await test.step("Bob cannot update it", async () => {
        const response = await request.put(
          `${API_URL}/api/v1/todos/${todoId}`,
          { headers: bobAuth, data: { title: "Hacked" } }
        );
        expect(response.status()).toBe(404);
      });

      await test.step("Bob cannot delete it", async () => {
        const response = await request.delete(
          `${API_URL}/api/v1/todos/${todoId}`,
          { headers: bobAuth }
        );
        expect(response.status()).toBe(404);
      });

      await test.step("Alice's todo is untouched", async () => {
        const response = await request.get(
          `${API_URL}/api/v1/todos/${todoId}`,
          { headers: { Authorization: `Bearer ${aliceToken}` } }
        );
        expect(response.status()).toBe(200);
        expect((await response.json()).title).toBe("Alice API todo");
      });
    } finally {
      await context.close();
    }
  });

  test("logging out clears the cached list before the next account signs in", async ({
    page,
  }) => {
    // Regression guard: react-query keys are per-query-name, not per-user, so
    // the next person to log in on this browser used to be served the previous
    // account's ["todos"] entry straight from memory.
    const first = uniqueEmail("tenant-a");
    const second = uniqueEmail("tenant-b");
    const secret = `First tenant todo ${Date.now()}`;

    await register(page, first);
    await createTodo(page, secret);
    await logout(page);

    // Client-side navigation on purpose: a full page load would empty the
    // react-query cache by itself and prove nothing.
    await page.getByRole("link", { name: "Sign up" }).click();
    // /login and /register both have an "Email" field, so filling before the
    // route has actually swapped writes into the form being unmounted.
    await expect(page).toHaveURL(/\/register$/);
    await expect(page.getByLabel("Confirm Password")).toBeVisible();

    await page.getByLabel("Email").fill(second);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Confirm Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Create Account" }).click();

    await expect(page.getByText(second, { exact: true })).toBeVisible();
    await expect(page.getByText("No todos yet")).toBeVisible();
    await expect(page.getByText(secret)).toHaveCount(0);
  });

  test("an unauthenticated visitor is redirected to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
  });
});
