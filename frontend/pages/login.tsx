import { useEffect, useReducer, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import { useAuth } from "../contexts/AuthContext";
import AuthLayout from "../components/AuthLayout";
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  Spinner,
} from "@/components/ui";
import { authApi, getApiErrorMessage } from "../lib/api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type LoginFormState = {
  email: string;
  password: string;
  isSubmitting: boolean;
  isSsoLoading: boolean;
  formError: string;
};

type LoginFormAction =
  | { type: "field"; field: "email" | "password"; value: string }
  | { type: "set-error"; error: string }
  | { type: "submit-start" }
  | { type: "submit-end"; error?: string }
  | { type: "sso-start" }
  | { type: "sso-end"; error?: string };

const initialLoginFormState: LoginFormState = {
  email: "",
  password: "",
  isSubmitting: false,
  isSsoLoading: false,
  formError: "",
};

function loginFormReducer(state: LoginFormState, action: LoginFormAction): LoginFormState {
  switch (action.type) {
    case "field":
      return { ...state, [action.field]: action.value, formError: "" };
    case "set-error":
      return { ...state, formError: action.error };
    case "submit-start":
      return { ...state, formError: "", isSubmitting: true };
    case "submit-end":
      return { ...state, isSubmitting: false, formError: action.error ?? "" };
    case "sso-start":
      return { ...state, formError: "", isSsoLoading: true };
    case "sso-end":
      return { ...state, isSsoLoading: false, formError: action.error ?? "" };
    default:
      return state;
  }
}

function validateLoginForm(email: string, password: string): string | null {
  if (!email.trim()) {
    return "Email is required";
  }
  if (!EMAIL_PATTERN.test(email)) {
    return "Please enter a valid email address";
  }
  if (!password) {
    return "Password is required";
  }
  if (password.length < 6) {
    return "Password must be at least 6 characters";
  }
  return null;
}

export default function LoginPage() {
  const [{ email, password, isSubmitting, isSsoLoading, formError }, dispatchForm] = useReducer(
    loginFormReducer,
    initialLoginFormState,
  );

  const { login, isAuthenticated, loading, error, clearError } = useAuth();
  const router = useRouter();

  const { push } = router;
  const registeredParam = router.query.registered;
  const registered = Array.isArray(registeredParam) ? registeredParam[0] : registeredParam;
  const showRegisteredMessage = registered === "true" || registered === "1";

  useEffect(() => {
    if (!loading && isAuthenticated) {
      push("/companies");
    }
  }, [loading, isAuthenticated, push]);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    const validationError = validateLoginForm(email, password);
    if (validationError) {
      dispatchForm({ type: "set-error", error: validationError });
      return;
    }

    dispatchForm({ type: "submit-start" });
    let submitError: string | undefined;
    try {
      const result = await login(email, password);
      submitError = result.success ? undefined : result.error;
    } finally {
      dispatchForm({ type: "submit-end", error: submitError });
    }
  };

  const handleSsoLogin = async () => {
    if (!email.trim()) {
      dispatchForm({ type: "set-error", error: "Enter your work email to continue with SSO." });
      return;
    }
    if (!EMAIL_PATTERN.test(email)) {
      dispatchForm({ type: "set-error", error: "Please enter a valid email address." });
      return;
    }

    dispatchForm({ type: "sso-start" });
    let ssoError: string | undefined;
    try {
      const authorizeUrl = await authApi.getSsoAuthorizeUrl(email);
      window.location.href = authorizeUrl;
    } catch (err: unknown) {
      ssoError = getApiErrorMessage(err, "SSO login failed. Please try again.");
    } finally {
      dispatchForm({ type: "sso-end", error: ssoError });
    }
  };

  const handleFieldChange = (field: "email" | "password", value: string) => {
    clearError();
    dispatchForm({ type: "field", field, value });
  };

  if (loading) {
    return (
      <AuthLayout>
        <Spinner size="lg" label="Loading sign in" />
      </AuthLayout>
    );
  }

  if (isAuthenticated) {
    return null;
  }

  const displayError = formError || error;

  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm shadow-2xl">
          <CardHeader className="text-center pb-2">
            <CardTitle className="text-2xl font-bold">Welcome back</CardTitle>
            <CardDescription className="text-base mt-1">Sign in to continue operating your companies</CardDescription>
          </CardHeader>

          <CardContent className="pt-4">
            {showRegisteredMessage && (
              <Alert className="mb-4 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <svg className="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <AlertDescription>Account created. Sign in to open your company workspace.</AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              {displayError && (
                <Alert variant="destructive">
                  <AlertDescription>{displayError}</AlertDescription>
                </Alert>
              )}

              <FormField label="Email address" required htmlFor="email">
                <Input
                  id="email"
                  name="username"
                  type="email"
                  autoComplete="username"
                  aria-invalid={Boolean(displayError)}
                  required
                  value={email}
                  onChange={(e) => handleFieldChange("email", e.target.value)}
                  placeholder="you@example.com"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <FormField label="Password" required htmlFor="password">
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(displayError)}
                  required
                  value={password}
                  onChange={(e) => handleFieldChange("password", e.target.value)}
                  placeholder="Enter your password"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <Button type="submit" className="w-full h-11 text-base font-medium" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Signing in
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>

              <div className="flex items-center gap-3 py-2">
                <div className="h-px flex-1 bg-border/60" />
                <span className="text-xs uppercase tracking-wide text-muted-foreground">Or continue with SSO</span>
                <div className="h-px flex-1 bg-border/60" />
              </div>

              <Button
                type="button"
                variant="outline"
                className="w-full h-11 text-base font-medium"
                onClick={handleSsoLogin}
                disabled={isSsoLoading || isSubmitting}
              >
                {isSsoLoading ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Redirecting
                  </>
                ) : (
                  "Continue with Auth0 SSO"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Don&apos;t have an account?{" "}
                <Link href="/register" className="font-medium text-primary hover:text-primary/80 transition-colors">
                  Create one
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </AuthLayout>
  );
}
