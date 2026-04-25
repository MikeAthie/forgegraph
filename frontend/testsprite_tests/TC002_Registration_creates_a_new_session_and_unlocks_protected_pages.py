import asyncio

from playwright import async_api
from playwright.async_api import expect

from _helpers import BASE_URL, close_browser, launch_page, login, unique_email


async def run_test():
    pw = browser = context = None
    try:
        pw, browser, context, page = await launch_page(async_api)

        email = unique_email()
        password = "WY3QGTJ7@q5eYq3"

        await page.goto(f"{BASE_URL}/register")
        await expect(page.get_by_role("heading", name="Create account")).to_be_visible()
        await page.locator("#email").fill(email)
        await page.locator("#password").fill(password)
        await page.locator("#confirmPassword").fill(password)
        await page.get_by_role("button", name="Create account").click()

        await page.wait_for_url("**/login?registered=true", timeout=15000)
        await expect(page.get_by_text("Registration successful! Please sign in with your new account.")).to_be_visible()

        await login(page, email, password)
        await page.goto(f"{BASE_URL}/graphs")
        await expect(page.get_by_text("Manage definitions and revisions")).to_be_visible()
    finally:
        await close_browser(pw, browser, context)


asyncio.run(run_test())
