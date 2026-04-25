import asyncio

from playwright import async_api
from playwright.async_api import expect

from _helpers import BASE_URL, close_browser, launch_page, login


async def run_test():
    pw = browser = context = None
    try:
        pw, browser, context, page = await launch_page(async_api)
        await login(page)

        await page.goto(f"{BASE_URL}/credentials")
        await expect(page.get_by_role("heading", name="Credentials")).to_be_visible()
        await expect(page.get_by_text("OAuth integrations")).to_be_visible()
        await expect(page.get_by_text("Connection checklist")).to_be_visible()

        has_empty_state = await page.get_by_text("No credentials yet").count() > 0
        has_credentials = await page.get_by_text("Health").count() > 0 or await page.get_by_text("Provider").count() > 0
        assert has_empty_state or has_credentials, "Credentials page should show either credentials or the empty state."
    finally:
        await close_browser(pw, browser, context)


asyncio.run(run_test())
