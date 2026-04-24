import asyncio

from playwright import async_api
from playwright.async_api import expect

from _helpers import BASE_URL, close_browser, launch_page, login


async def run_test():
    pw = browser = context = None
    try:
        pw, browser, context, page = await launch_page(async_api)
        await login(page)

        await page.goto(f"{BASE_URL}/memory")
        await expect(page.get_by_role("heading", name="Observation ledger")).to_be_visible()
        await expect(page.get_by_role("heading", name="Observation detail")).to_be_visible()

        editable_fields = page.locator("#edit-memory-tags, textarea[name='tags'], input[name='tags']")
        assert await editable_fields.count() == 0, "Memory observations are inspect-only in the current UI."
        await expect(page.get_by_text("Inspect the full content")).to_be_visible()
    finally:
        await close_browser(pw, browser, context)


asyncio.run(run_test())
