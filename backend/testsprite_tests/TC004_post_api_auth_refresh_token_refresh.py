import requests
import uuid
import random
import string

BASE_URL = "http://localhost:8000"

def random_email():
    return f"testuser_{uuid.uuid4().hex}@example.com"

def random_password(length=12):
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))


def test_post_api_auth_refresh_token_refresh():
    session = requests.Session()
    # Register a new user
    email = random_email()
    password = random_password()
    register_payload = {"email": email, "password": password}
    register_url = f"{BASE_URL}/api/auth/register"
    try:
        r = session.post(register_url, json=register_payload, timeout=30)
        assert r.status_code == 201, f"Expected 201 Created on register, got {r.status_code}"
        user_data = r.json()
        assert "id" in user_data and "email" in user_data, "User payload must contain id and email"
        # Login with the registered user
        login_url = f"{BASE_URL}/api/auth/login"
        login_payload = {"email": email, "password": password}
        r = session.post(login_url, json=login_payload, timeout=30)
        assert r.status_code == 200, f"Expected 200 OK on login, got {r.status_code}"
        login_json = r.json()
        assert "access" in login_json, "Login response JSON must contain access token"
        # Refresh token should NOT be in JSON body
        assert "refresh" not in login_json, "Refresh token must NOT be in JSON response"

        # The refresh token must be in HttpOnly cookie named refresh_token
        cookies = session.cookies
        refresh_token_cookie = cookies.get("refresh_token")
        assert refresh_token_cookie is not None, "Refresh token cookie must be set after login"

        # POST /api/auth/refresh WITH valid refresh token cookie
        refresh_url = f"{BASE_URL}/api/auth/refresh"
        r = session.post(refresh_url, timeout=30)
        # The refresh endpoint returns 200 with JSON access token without refresh token
        if r.status_code == 200:
            refresh_json = r.json()
            assert "access" in refresh_json, "Refresh response JSON must contain access token"
            assert "refresh" not in refresh_json, "Refresh token must NOT be in refresh response JSON"
        else:
            # According to spec may raise 400 if refresh cookie missing or 401 if invalid refresh token
            # Since cookie is from login, it should be valid
            assert False, f"Unexpected status code on valid refresh token: {r.status_code} {r.text}"

        # POST /api/auth/refresh WITHOUT refresh cookie (simulate by clearing cookies)
        session.cookies.clear()
        r = session.post(refresh_url, timeout=30)
        # Missing refresh cookie may return 400
        assert r.status_code in (400, 401), f"Expected 400 or 401 on missing refresh cookie, got {r.status_code}"

        # POST /api/auth/refresh WITH invalid refresh cookie
        session.cookies.set("refresh_token", "INVALID_REFRESH_TOKEN")
        r = session.post(refresh_url, timeout=30)
        # Should return 401 Unauthorized for invalid refresh cookie
        assert r.status_code == 401, f"Expected 401 on invalid refresh token, got {r.status_code}"

    finally:
        # Cleanup - Login again to get fresh access and refresh token to logout and clear session
        try:
            # Login again to re-acquire valid tokens if possible
            r = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
            if r.status_code == 200:
                access_token = r.json().get("access")
                refresh_token = session.cookies.get("refresh_token")
                if access_token and refresh_token:
                    # Logout to invalidate refresh cookie
                    logout_url = f"{BASE_URL}/api/auth/logout"
                    headers = {"Authorization": f"Bearer {access_token}"}
                    session.cookies.set("refresh_token", refresh_token)
                    r = session.post(logout_url, headers=headers, timeout=30)
                    # Ignore logout response status here
        except Exception:
            pass


test_post_api_auth_refresh_token_refresh()