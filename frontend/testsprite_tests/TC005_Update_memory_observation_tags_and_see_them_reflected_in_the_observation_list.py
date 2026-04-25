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
        await expect(page.get_by_text("Memory posture")).to_be_visible()
        await expect(page.get_by_role("heading", name="Observation ledger")).to_be_visible()

        first_observation = page.locator("button").filter(has_text="Recorded").first()
        if await first_observation.count() > 0:
            await first_observation.click()
            await expect(page.get_by_role("heading", name="Observation detail")).to_be_visible()
            await expect(page.get_by_text("Captured content")).to_be_visible()
        else:
            await expect(page.get_by_text("No observations matched")).to_be_visible()
    finally:
        await close_browser(pw, browser, context)


asyncio.run(run_test())
