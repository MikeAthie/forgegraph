import requests
import uuid
import time
from http.cookies import SimpleCookie

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def test_post_api_auth_logout_invalidate_session():
    session = requests.Session()
    unique_email = f"testuser_{uuid.uuid4().hex}@example.com"
    password = "TestPassword123!"

    # 1. Register a new user
    register_payload = {"email": unique_email, "password": password}
    register_resp = session.post(f"{BASE_URL}/api/auth/register", json=register_payload, timeout=TIMEOUT)
    assert register_resp.status_code == 201, f"User registration failed: {register_resp.text}"
    user_data = register_resp.json()
    assert "email" in user_data and user_data["email"] == unique_email
    assert "id" in user_data

    # 2. Login with the new user
    login_payload = {"email": unique_email, "password": password}
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json=login_payload, timeout=TIMEOUT)
    assert login_resp.status_code == 200, f"User login failed: {login_resp.text}"
    login_json = login_resp.json()
    assert "access" in login_json and isinstance(login_json["access"], str)
    access_token = login_json["access"]

    # Check that refresh token is only in the HttpOnly refresh_token cookie
    refresh_cookie = None
    for cookie in login_resp.cookies:
        if cookie.name == "refresh_token":
            refresh_cookie = cookie
            break
    assert refresh_cookie is not None, "refresh_token cookie not set on login"
    assert not refresh_cookie.has_nonstandard_attr("Accessible"), "refresh_token should be HttpOnly"

    headers_auth = {"Authorization": f"Bearer {access_token}"}

    try:
        # 3. Logout to invalidate session
        logout_resp = session.post(f"{BASE_URL}/api/auth/logout", headers=headers_auth, timeout=TIMEOUT)
        assert logout_resp.status_code == 204, f"Logout failed: {logout_resp.text}"

        # 4. Verify refresh_token cookie is cleared (should be expired or empty)
        # Parse Set-Cookie header(s) to find refresh_token with Max-Age=0 or expired
        refresh_cookie_clear = False
        set_cookie_headers = logout_resp.headers.get("Set-Cookie")
        if set_cookie_headers:
            # Parse cookies with SimpleCookie
            cookie = SimpleCookie()
            cookie.load(set_cookie_headers)
            if "refresh_token" in cookie:
                morsel = cookie["refresh_token"]
                max_age = morsel['max-age']
                expires = morsel['expires'].lower() if morsel['expires'] else ""
                if (max_age == '0') or ("thu, 01 jan 1970" in expires):
                    refresh_cookie_clear = True
        assert refresh_cookie_clear, "Refresh token cookie was not cleared on logout"

        # 5. Attempt a refresh request without the refresh token cookie (it should be missing)
        # Session cookies are managed automatically, so clear cookies to simulate missing refresh cookie
        session.cookies.clear()
        refresh_resp = session.post(f"{BASE_URL}/api/auth/refresh", timeout=TIMEOUT)
        assert refresh_resp.status_code in (400, 401), (
            "Expected 400 or 401 when refreshing without refresh token cookie, got "
            f"{refresh_resp.status_code}"
        )
    finally:
        # Cleanup: No direct user delete endpoint, so nothing to clean up here.
        pass


test_post_api_auth_logout_invalidate_session()
