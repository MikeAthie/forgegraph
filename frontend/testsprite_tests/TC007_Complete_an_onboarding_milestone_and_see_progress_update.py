import asyncio

from playwright import async_api
from playwright.async_api import expect

from _helpers import BASE_URL, close_browser, launch_page, login


async def run_test():
    pw = browser = context = None
    try:
        pw, browser, context, page = await launch_page(async_api)
        await login(page)

        await page.goto(f"{BASE_URL}/onboarding")
        await expect(page.get_by_text("Learn onboarding basics")).to_be_visible()
        await expect(page.locator('[data-testid="onboarding-checklist-progress"]')).to_be_visible()
        await expect(page.locator('[data-testid="onboarding-checklist-progress-label"]')).to_be_visible()
    finally:
        await close_browser(pw, browser, context)


asyncio.run(run_test())
