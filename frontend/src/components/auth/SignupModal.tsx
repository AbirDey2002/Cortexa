import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface SignupModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSwitchToLogin: () => void;
}

export function SignupModal({ open, onOpenChange, onSwitchToLogin }: SignupModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { loginWithRedirect } = useAuth0();

  const handleGoogleSignup = async () => {
    setError(null);
    setIsLoading(true);

    try {
      // Store that this is a signup attempt (not login) in sessionStorage
      sessionStorage.setItem("auth0_login_mode", "signup");

      // Use redirect instead of popup - redirects the entire page
      await loginWithRedirect({
        authorizationParams: {
          connection: "google-oauth2",
          screen_hint: "signup",
        },
        appState: {
          returnTo: window.location.pathname,
          mode: "signup",
        },
      });
      // Note: After redirect, user will be handled by Callback component
    } catch (err: any) {
      setError(err.error_description || err.message || "Failed to sign up with Google. Please try again.");
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[850px] p-0 overflow-hidden gap-0 border-none shadow-2xl">
        <div className="grid grid-cols-1 md:grid-cols-2 min-h-[500px]">
          {/* Left Side: Image */}
          <div className="hidden md:block relative bg-muted h-full">
            <img
              src="/signup.png"
              alt="Welcome to Cortexa"
              className="absolute inset-0 w-full h-full object-cover"
            />
            {/* Optional Overlay/Gradient if needed, but plain image requested */}
          </div>

          {/* Right Side: Content */}
          <div className="flex flex-col justify-center p-8 md:p-12 h-full bg-background">
            <DialogHeader className="space-y-4 mb-6">
              <div className="flex items-center justify-center gap-2">
                <img
                  src="/cortexa.png"
                  alt="Cortexa Logo"
                  className="h-10 w-10 object-contain"
                />
                <span className="text-2xl font-display font-bold text-foreground">Cortexa</span>
              </div>
              <DialogTitle className="text-3xl font-bold text-center tracking-tight">
                Create Account
              </DialogTitle>
              <DialogDescription className="text-center text-base">
                Join Cortexa today and start building.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 w-full max-w-sm mx-auto">
              {error && (
                <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
                  <span>{error}</span>
                </div>
              )}

              <Button
                type="button"
                variant="outline"
                className="w-full h-12 text-base font-medium border-border hover:bg-muted/50 transition-all shadow-sm"
                onClick={handleGoogleSignup}
                disabled={isLoading}
              >
                <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
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

              <div className="text-center text-sm text-muted-foreground pt-4">
                Already have an account?{" "}
                <button
                  type="button"
                  onClick={() => {
                    onOpenChange(false);
                    onSwitchToLogin();
                  }}
                  className="text-primary hover:underline font-semibold"
                >
                  Sign in
                </button>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


