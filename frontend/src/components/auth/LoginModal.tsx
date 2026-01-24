import { useState, useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSwitchToSignup: () => void;
  initialError?: string | null;
}

export function LoginModal({ open, onOpenChange, onSwitchToSignup, initialError }: LoginModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError || null);

  // Update error when initialError prop changes
  useEffect(() => {
    if (initialError) {
      setError(initialError);
    }
  }, [initialError]);
  const { loginWithRedirect, getAccessTokenSilently, logout } = useAuth0();
  const navigate = useNavigate();

  const handleGoogleLogin = async () => {
    setError(null);
    setIsLoading(true);

    try {
      // Store that this is a login attempt (not signup) in sessionStorage
      sessionStorage.setItem("auth0_login_mode", "login");

      // Use redirect instead of popup - redirects the entire page
      await loginWithRedirect({
        authorizationParams: {
          connection: "google-oauth2",
          screen_hint: "login",
        },
        appState: {
          returnTo: window.location.pathname,
          mode: "login",
        },
      });
      // Note: After redirect, user will be handled by Callback component
    } catch (err: any) {
      setError(err.error_description || err.message || "Failed to login with Google. Please try again.");
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center justify-center gap-2 mb-4">
            <img
              src="/cortexa.png"
              alt="Cortexa Logo"
              className="h-8 w-8 object-contain"
            />
            <span className="text-lg font-display font-bold text-foreground">Cortexa</span>
          </div>
          <DialogTitle className="text-2xl text-center">Welcome Back</DialogTitle>
          <DialogDescription className="text-center">
            Sign in to continue to Cortexa
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4">
          {error && (
            <div className="mb-4 flex items-center gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
              <span>{error}</span>
            </div>
          )}

          <Button
            type="button"
            variant="outline"
            className="w-full border-border hover:bg-muted/50 h-11"
            onClick={handleGoogleLogin}
            disabled={isLoading}
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </Button>
        </div>

        <div className="text-center text-sm text-muted-foreground mt-4">
          Don't have an account?{" "}
          <button
            type="button"
            onClick={() => {
              onOpenChange(false);
              onSwitchToSignup();
            }}
            className="text-primary hover:underline font-medium"
          >
            Sign up
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

