import time

from playwright.async_api import expect

BASE_URL = "http://localhost:3000"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "WY3QGTJ7@q5eYq3"


async def launch_page(async_api):
    pw = await async_api.async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--window-size=1280,720", "--disable-dev-shm-usage"],
    )
    context = await browser.new_context()
    context.set_default_timeout(10000)
    page = await context.new_page()
    return pw, browser, context, page


async def close_browser(pw, browser, context):
    if context:
        await context.close()
    if browser:
        await browser.close()
    if pw:
        await pw.stop()


async def login(page, email: str = TEST_EMAIL, password: str = TEST_PASSWORD):
    await page.goto(f"{BASE_URL}/login")
    await page.locator("#email").fill(email)
    await page.locator("#password").fill(password)
    await page.get_by_role("button", name="Sign in").click()
    await page.wait_for_url("**/overview", timeout=15000)


def unique_email() -> str:
    return f"e2e+testsprite-{int(time.time() * 1000)}@example.com"

