import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Sparkles, Mail, Lock, AlertCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { setUserIdInSession } from "@/contexts/AuthContext";

interface SignupModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSwitchToLogin: () => void;
}

export function SignupModal({ open, onOpenChange, onSwitchToLogin }: SignupModalProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { loginWithRedirect, getAccessTokenSilently } = useAuth0();
  const { toast } = useToast();
  const navigate = useNavigate();

  const handleEmailPasswordSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters long");
      return;
    }

    setIsLoading(true);

    try {
      // Check if user already exists in database
      const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
      const checkUserUrl = `${backendUrl}/users/check?email=${encodeURIComponent(email)}`;
      
      let userExists = false;
      try {
        const response = await fetch(checkUserUrl);
        if (response.ok) {
          const data = await response.json();
          userExists = data.exists === true;
        }
      } catch (err) {
      }

      if (userExists) {
        setError("An account with this email already exists. Please sign in instead.");
        setIsLoading(false);
        return;
      }

      // Create user in Auth0 via backend endpoint (no popup)
      const signupUrl = `${backendUrl}/users/auth0-signup`;
      
      const signupResponse = await fetch(signupUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
          name: email.split("@")[0], // Use email prefix as default name
        }),
      });

      if (!signupResponse.ok) {
        const errorData = await signupResponse.json().catch(() => ({ detail: "Failed to create account" }));
        throw new Error(errorData.detail || "Failed to create account");
      }

      const signupData = await signupResponse.json() as { user_id: string; email: string };
      
      // Store that this is a signup attempt and email for Auth0
      sessionStorage.setItem("auth0_login_mode", "signup");
      sessionStorage.setItem("auth0_login_email", email);
      
      // Use redirect instead of popup - redirects the entire page (no popup window)
      await loginWithRedirect({
        authorizationParams: {
          connection: "Username-Password-Authentication",
          login_hint: email,
          screen_hint: "login", // Login since user is already created
        },
        appState: {
          returnTo: window.location.pathname,
          mode: "signup",
        },
      });
      // Note: After redirect, user will be handled by Callback component
    } catch (err: any) {
      setError(err.error_description || err.message || "Failed to create account. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

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
          <DialogTitle className="text-2xl text-center">Create Account</DialogTitle>
          <DialogDescription className="text-center">
            Sign up to get started with Cortexa
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleEmailPasswordSignup} className="space-y-4 mt-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
              <AlertCircle className="w-4 h-4" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="signup-email">Email</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="signup-email"
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="pl-10"
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="signup-password">Password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="signup-password"
                type="password"
                placeholder="Create a password (min. 8 characters)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="pl-10"
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="signup-confirm-password">Confirm Password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="signup-confirm-password"
                type="password"
                placeholder="Confirm your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
                className="pl-10"
                disabled={isLoading}
              />
            </div>
          </div>

          <Button
            type="submit"
            className="w-full bg-gradient-primary hover:opacity-90 text-primary-foreground font-semibold shadow-glow"
            disabled={isLoading}
          >
            {isLoading ? "Creating account..." : "Sign Up"}
          </Button>
        </form>

        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full border-border hover:bg-muted/50"
          onClick={handleGoogleSignup}
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

        <div className="text-center text-sm text-muted-foreground mt-4">
          Already have an account?{" "}
          <button
            type="button"
            onClick={() => {
              onOpenChange(false);
              onSwitchToLogin();
            }}
            className="text-primary hover:underline font-medium"
          >
            Sign in
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

