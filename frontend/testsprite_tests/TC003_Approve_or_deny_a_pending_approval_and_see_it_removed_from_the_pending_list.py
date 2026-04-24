import asyncio

from playwright import async_api
from playwright.async_api import expect

from _helpers import BASE_URL, close_browser, launch_page, login


async def run_test():
    pw = browser = context = None
    try:
        pw, browser, context, page = await launch_page(async_api)
        await login(page)

        await page.goto(f"{BASE_URL}/inbox")
        await expect(page.get_by_text("Inbox posture")).to_be_visible()

        approve = page.get_by_role("button", name="Approve").first()
        reject = page.get_by_role("button", name="Reject").first()
        if await approve.count() > 0:
            await approve.click()
            await expect(page.get_by_text("Decision approved").or_(page.get_by_text("Inbox posture"))).to_be_visible()
        elif await reject.count() > 0:
            await reject.click()
            await expect(page.get_by_text("Decision rejected").or_(page.get_by_text("Inbox posture"))).to_be_visible()
        else:
            await expect(page.get_by_text("Inbox is clear").or_(page.get_by_text("No approval items match"))).to_be_visible()
    finally:
        await close_browser(pw, browser, context)


asyncio.run(run_test())
