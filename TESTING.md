# ForgeGraph Testing Documentation

This document provides an overview of the testing strategy and how to run tests for the ForgeGraph project.

## Testing Philosophy

ForgeGraph follows a comprehensive testing strategy with three layers:

1. **Unit Tests** - Test individual components, functions, and classes in isolation
2. **Integration Tests** - Test interactions between multiple components or modules
3. **End-to-End (E2E) Tests** - Test complete user flows through the application

## Backend Testing (Django + DRF)

### Test Structure

```
backend/tests/
├── conftest.py                          # Shared pytest fixtures
├── unit/
│   ├── domain/
│   │   ├── test_models.py              # Model behavior and methods
│   │   └── test_managers.py            # Custom managers and querysets
│   └── application/
│       └── test_serializers.py         # Serializer validation
├── integration/
│   ├── adapters/
│   │   ├── test_auth_api.py            # Auth API endpoints
│   │   ├── test_graph_api.py           # Graph API endpoints
│   │   └── test_prompt_api.py          # Prompt API endpoints
│   └── infrastructure/
│       └── test_orm_managers.py        # ORM manager integration
└── e2e/
    └── test_user_flows.py              # Complete user journeys
```

### Running Backend Tests

```bash
# Navigate to backend directory
cd backend

# Run all tests
pytest

# Run specific test file
pytest tests/unit/domain/test_models.py

# Run tests with coverage
pytest --cov=. --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run only E2E tests
pytest tests/e2e/

# Run tests matching a pattern
pytest -k "test_user"

# Run with verbose output
pytest -v

# Run with print statements visible
pytest -s
```

### Backend Test Coverage

#### Unit Tests

**Models (`test_models.py`)**
- User model: Creation, validation, string representation, superuser creation
- Graph model: CRUD operations, cascade deletion, timestamps
- GraphVersion model: Version management, checksum computation, uniqueness
- PromptTemplate model: Creation, cloning, visibility, categories
- Run model: Status management, duration calculation
- NodeRun model: Execution tracking, attempt handling

**Managers (`test_managers.py`)**
- GraphManager: User filtering, chaining
- GraphVersionManager: Latest version retrieval
- PromptTemplateManager: Public filtering, user visibility logic, cloning

**Serializers (`test_serializers.py`)**
- Registration/Login serializers: Field validation
- Graph serializers: CRUD validation, partial updates
- GraphVersion serializers: JSON structure validation
- Prompt serializers: Category validation, field constraints

#### Integration Tests

**API Endpoints**
- Auth API: Register, login, logout, token refresh, token blacklisting
- Graph API: List, create, update, delete, versioning
- Prompt API: CRUD operations, filtering, searching, cloning, publishing

#### E2E Tests

**Complete Flows**
- User registration → login → create resources → logout
- Multi-user isolation and permissions
- Graph workflow creation with prompts
- Error handling across the application

## Frontend Testing (NextJS + TypeScript)

### Test Structure

```
frontend/__tests__/
├── unit/
│   └── components/
│       ├── Header.test.tsx             # Header component
│       └── ProtectedRoute.test.tsx     # Route protection
├── integration/
│   └── contexts/
│       └── AuthContext.test.tsx        # Auth state management
└── e2e/
    ├── auth.spec.ts                    # Auth flows
    ├── graphs.spec.ts                  # Graph management
    └── prompts.spec.ts                 # Prompt library
```

### Running Frontend Tests

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies (if not already done)
npm install

# Run Jest unit/integration tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run Playwright E2E tests
npm run test:e2e

# Run only the graph editor E2E spec
npm run test:e2e -- __tests__/e2e/graph-editor.spec.ts

# Run Playwright E2E tests with UI
npm run test:e2e:ui

# Install Playwright browsers (first time only)
npx playwright install
```

### Frontend Test Coverage

#### Unit Tests

**Header Component (`Header.test.tsx`)**
- Unauthenticated state: Sign in/Get started buttons
- Authenticated state: Navigation links, user menu
- User menu interactions: Dropdown, logout
- Loading states during logout
- Accessibility features

**ProtectedRoute Component (`ProtectedRoute.test.tsx`)**
- Loading states with spinner
- Redirect to login for unauthenticated users
- Render children for authenticated users
- State transitions
- Edge cases with null/multiple children

#### Integration Tests

**AuthContext (`AuthContext.test.tsx`)**
- Hook usage outside provider throws error
- Initial authentication check on mount
- Login flow: Success and failure cases
- Registration flow: Success and validation errors
- Logout flow: API calls and state cleanup
- Token refresh: With and without access tokens
- Error management: Setting and clearing errors
- isAuthenticated derived state

#### E2E Tests (Playwright)

**Authentication (`auth.spec.ts`)**
- Landing page display
- Navigation to register/login pages
- User registration with validation
- User login with credentials
- Authenticated navigation display
- User logout and redirect
- Protected route access control

**Graphs (`graphs.spec.ts`)**
- Graphs page display
- Create graph modal and form
- Graph creation with validation
- Edit graph flow
- Delete graph with confirmation
- Graph details navigation
- Empty state handling

**Graph Editor (`graph-editor.spec.ts`)**
- Open editor for a graph
- Add nodes from the palette
- Connect/configure nodes and save
- Reload and verify persistence

**Prompts (`prompts.spec.ts`)**
- Prompt library page display
- Create prompt modal and form
- Filter prompts by category
- Search prompts by title
- Clone prompt functionality
- Edit prompt flow
- Delete prompt with confirmation
- Publish prompt to public

## Test Configuration

### Backend (pytest)

Configuration in `backend/pytest.ini` and `backend/tests/conftest.py`:

- Database: Uses Django test database
- Fixtures: Shared fixtures for user, api_client, authenticated_client
- Markers: `@pytest.mark.django_db` for database access

### Frontend (Jest)

Configuration in `frontend/jest.config.js` and `frontend/jest.setup.js`:

- Environment: jsdom for DOM testing
- Setup: Testing Library matchers, Next.js router mocks
- Module mapping: Path aliases (@/)
- Coverage: Components, contexts, pages, lib

### Frontend (Playwright)

Configuration in `frontend/playwright.config.ts`:

- Browsers: Chromium, Firefox, WebKit
- Base URL: http://localhost:3000
- Traces: On first retry
- Workers: Parallel in local, sequential in CI
- Web server: Auto-starts dev server

## CI/CD Integration

### GitHub Actions Example

```yaml
# Backend tests
- name: Run Backend Tests
  run: |
    cd backend
    pytest --cov=. --cov-report=xml

# Frontend unit tests
- name: Run Frontend Unit Tests
  run: |
    cd frontend
    npm test -- --coverage

# Frontend E2E tests
- name: Run Frontend E2E Tests
  run: |
    cd frontend
    npx playwright install --with-deps
    npm run test:e2e
```

## Writing New Tests

### Backend Unit Test Template

```python
"""
Unit tests for [Component Name].

Brief description of what is being tested.
"""

import pytest
from infrastructure.orm.models import YourModel

pytestmark = pytest.mark.django_db


class TestYourModel:
    """Tests for YourModel."""

    def test_feature_happy_path(self):
        """Should [expected behavior]."""
        # Arrange
        model = YourModel.objects.create(field="value")

        # Act
        result = model.some_method()

        # Assert
        assert result == expected_value
```

### Frontend Unit Test Template

```typescript
/**
 * Unit tests for [Component Name].
 *
 * Brief description of what is being tested.
 */

import { render, screen } from '@testing-library/react';
import YourComponent from '@/components/YourComponent';

describe('YourComponent', () => {
  it('should [expected behavior]', () => {
    // Arrange
    render(<YourComponent prop="value" />);

    // Act
    const element = screen.getByRole('button');

    // Assert
    expect(element).toBeInTheDocument();
  });
});
```

### E2E Test Template

```typescript
/**
 * E2E tests for [Feature Name].
 *
 * Brief description of user flows being tested.
 */

import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    // Setup: Login, navigate, etc.
    await page.goto('/some-page');
  });

  test('should complete user flow', async ({ page }) => {
    // Interact with the application
    await page.getByRole('button', { name: /click me/i }).click();

    // Verify outcome
    await expect(page.getByText('Success')).toBeVisible();
  });
});
```

## Best Practices

### General

1. **Arrange-Act-Assert**: Structure tests with clear setup, action, and verification
2. **Test Isolation**: Each test should be independent and not rely on other tests
3. **Descriptive Names**: Test names should clearly describe what they test
4. **One Assertion Per Test**: Focus each test on a single behavior
5. **Test Edge Cases**: Cover happy path, error conditions, and boundary cases

### Backend

1. **Use Fixtures**: Leverage pytest fixtures for common setup
2. **Test Database**: Use `@pytest.mark.django_db` for database tests
3. **Mock External APIs**: Don't make real external API calls in tests
4. **Test Permissions**: Verify authorization logic thoroughly

### Frontend

1. **Query by Role**: Prefer `getByRole` for better accessibility testing
2. **User Events**: Use `@testing-library/user-event` for interactions
3. **Async Operations**: Use `waitFor` for asynchronous assertions
4. **Avoid Implementation Details**: Test behavior, not implementation

### E2E

1. **Test User Journeys**: Focus on realistic user workflows
2. **Stable Selectors**: Use semantic HTML and ARIA roles
3. **Wait for Elements**: Use Playwright's auto-waiting, but add explicit waits when needed
4. **Clean State**: Reset state between tests or use test isolation

## Code Coverage Goals

- **Overall**: 80%+ coverage
- **Critical Paths**: 100% coverage (auth, data mutations)
- **UI Components**: 80%+ coverage
- **Business Logic**: 90%+ coverage

## Continuous Improvement

1. **Review Failed Tests**: Investigate and fix flaky tests immediately
2. **Update Tests**: Keep tests up-to-date with feature changes
3. **Add Tests for Bugs**: Write a failing test before fixing a bug
4. **Monitor Coverage**: Track coverage trends over time

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [React Testing Library](https://testing-library.com/react)
- [Playwright Documentation](https://playwright.dev/)
- [Jest Documentation](https://jestjs.io/)
