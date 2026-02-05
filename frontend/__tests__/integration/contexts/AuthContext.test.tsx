/**
 * Integration tests for AuthContext and useAuth hook.
 *
 * Tests authentication state management, login/logout flows, and token handling.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { useRouter } from 'next/router';
import { ReactNode } from 'react';

import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import * as api from '@/lib/api';

// Mock dependencies
jest.mock('next/router');
jest.mock('@/lib/api');

const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockAuthApi = api.authApi as jest.Mocked<typeof api.authApi>;
const mockGetAccessToken = api.getAccessToken as jest.MockedFunction<typeof api.getAccessToken>;
const mockClearTokens = api.clearTokens as jest.MockedFunction<typeof api.clearTokens>;

describe('AuthContext', () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: mockPush,
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: '/',
      query: {},
      asPath: '/',
    } as any);
  });

  const wrapper = ({ children }: { children: ReactNode }) => (
    <AuthProvider>{children}</AuthProvider>
  );

  describe('useAuth Hook', () => {
    it('should throw error when used outside AuthProvider', () => {
      // Suppress console.error for this test
      const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});

      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');

      consoleError.mockRestore();
    });

    it('should provide auth context when used within AuthProvider', () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      expect(result.current).toBeDefined();
      expect(result.current.login).toBeInstanceOf(Function);
      expect(result.current.logout).toBeInstanceOf(Function);
      expect(result.current.register).toBeInstanceOf(Function);

      return waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });
  });

  describe('Initial State', () => {
    it('should start with loading true and user null', () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      // Initially loading
      expect(result.current.loading).toBe(true);
      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);

      return waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('should check authentication on mount', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));

      renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(mockAuthApi.refreshToken).toHaveBeenCalled();
      });
    });
  });

  describe('Login Flow', () => {
    it('should successfully login and set user', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockResolvedValueOnce({ id: '1', email: 'test@example.com' });
      mockAuthApi.login.mockResolvedValue({ access: 'token', refresh: 'refresh' });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      let loginResult: any;
      await act(async () => {
        mockAuthApi.getMe.mockResolvedValueOnce({ id: '1', email: 'test@example.com' });
        loginResult = await result.current.login('test@example.com', 'password123');
      });

      await waitFor(() => {
        expect(loginResult.success).toBe(true);
        expect(result.current.user).toEqual({ id: '1', email: 'test@example.com' });
        expect(result.current.isAuthenticated).toBe(true);
        expect(mockPush).toHaveBeenCalledWith('/graphs');
      });
    });

    it('should handle login failure with error message', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));
      mockAuthApi.login.mockRejectedValue({
        response: { data: { detail: 'Invalid credentials' } },
      });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      let loginResult: any;
      await act(async () => {
        loginResult = await result.current.login('test@example.com', 'wrongpassword');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.error).toBe('Invalid credentials');
      expect(result.current.error).toBe('Invalid credentials');
      expect(result.current.user).toBeNull();
    });

    it('should handle generic login error', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));
      mockAuthApi.login.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      let loginResult: any;
      await act(async () => {
        loginResult = await result.current.login('test@example.com', 'password123');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.error).toContain('Login failed');
    });

    it('should clear error before login attempt', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // First failed login
      mockAuthApi.login.mockRejectedValueOnce({
        response: { data: { detail: 'First error' } },
      });

      await act(async () => {
        await result.current.login('test@example.com', 'wrong');
      });

      expect(result.current.error).toBe('First error');

      // Second login attempt should clear previous error
      mockAuthApi.login.mockResolvedValue({ access: 'token', refresh: 'refresh' });
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });

      await act(async () => {
        await result.current.login('test@example.com', 'correct');
      });

      await waitFor(() => {
        expect(result.current.error).toBeNull();
      });
    });
  });

  describe('Registration Flow', () => {
    it('should successfully register and redirect to login', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));
      mockAuthApi.register.mockResolvedValue({ email: 'new@example.com' });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      let registerResult: any;
      await act(async () => {
        registerResult = await result.current.register('new@example.com', 'password123');
      });

      expect(registerResult.success).toBe(true);
      expect(mockPush).toHaveBeenCalledWith('/login?registered=true');
    });

    it('should handle registration failure with validation errors', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));
      mockAuthApi.register.mockRejectedValue({
        response: { data: { email: ['Email already exists'] } },
      });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      let registerResult: any;
      await act(async () => {
        registerResult = await result.current.register('existing@example.com', 'password123');
      });

      expect(registerResult.success).toBe(false);
      expect(registerResult.error).toBe('Email already exists');
      expect(result.current.error).toBe('Email already exists');
    });

    it('should handle generic registration error', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));
      mockAuthApi.register.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      let registerResult: any;
      await act(async () => {
        registerResult = await result.current.register('new@example.com', 'password123');
      });

      expect(registerResult.success).toBe(false);
      expect(registerResult.error).toContain('Registration failed');
    });
  });

  describe('Logout Flow', () => {
    it('should successfully logout and redirect', async () => {
      // Start authenticated
      mockGetAccessToken.mockReturnValue('token');
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });
      mockAuthApi.logout.mockResolvedValue();

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.user).toEqual({ id: '1', email: 'test@example.com' });
      });

      await act(async () => {
        await result.current.logout();
      });

      expect(mockAuthApi.logout).toHaveBeenCalled();
      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(mockPush).toHaveBeenCalledWith('/login');
    });

    it('should handle logout API errors gracefully', async () => {
      // Start authenticated
      mockGetAccessToken.mockReturnValue('token');
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });
      mockAuthApi.logout.mockRejectedValue(new Error('Network error'));

      const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.user).toEqual({ id: '1', email: 'test@example.com' });
      });

      await act(async () => {
        await result.current.logout();
      });

      // Should still clear user and redirect even if API call fails
      expect(result.current.user).toBeNull();
      expect(mockPush).toHaveBeenCalledWith('/login');
      expect(consoleError).toHaveBeenCalledWith('Logout error:', expect.any(Error));

      consoleError.mockRestore();
    });
  });

  describe('Token Refresh', () => {
    it('should refresh token if no access token exists', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(mockAuthApi.refreshToken).toHaveBeenCalled();
        expect(result.current.user).toEqual({ id: '1', email: 'test@example.com' });
        expect(result.current.loading).toBe(false);
      });
    });

    it('should skip refresh if access token exists', async () => {
      mockGetAccessToken.mockReturnValue('existing-token');
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(mockAuthApi.refreshToken).not.toHaveBeenCalled();
        expect(result.current.user).toEqual({ id: '1', email: 'test@example.com' });
      });
    });

    it('should clear tokens on authentication failure', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Unauthorized'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(mockClearTokens).toHaveBeenCalled();
        expect(result.current.user).toBeNull();
        expect(result.current.loading).toBe(false);
      });
    });
  });

  describe('Check Auth', () => {
    it('should allow manual auth check', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Now simulate token being available
      mockGetAccessToken.mockReturnValue('new-token');
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });

      await act(async () => {
        await result.current.checkAuth();
      });

      await waitFor(() => {
        expect(result.current.user).toEqual({ id: '1', email: 'test@example.com' });
      });
    });
  });

  describe('Error Management', () => {
    it('should provide clearError function', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));
      mockAuthApi.login.mockRejectedValue({
        response: { data: { detail: 'Login error' } },
      });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Create an error
      await act(async () => {
        await result.current.login('test@example.com', 'wrong');
      });

      expect(result.current.error).toBe('Login error');

      // Clear the error
      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('isAuthenticated Derived State', () => {
    it('should be false when user is null', async () => {
      mockGetAccessToken.mockReturnValue(null);
      mockAuthApi.refreshToken.mockResolvedValue();
      mockAuthApi.getMe.mockRejectedValue(new Error('Not authenticated'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(false);
      });
    });

    it('should be true when user exists', async () => {
      mockGetAccessToken.mockReturnValue('token');
      mockAuthApi.getMe.mockResolvedValue({ id: '1', email: 'test@example.com' });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });
    });
  });
});
