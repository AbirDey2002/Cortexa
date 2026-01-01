import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { 
  Navbar, 
  Hero, 
  Features, 
  Security, 
  HowItWorks, 
  CTASection, 
  Footer 
} from "@/components/landing";
import { LoginModal } from "@/components/auth/LoginModal";
import { SignupModal } from "@/components/auth/SignupModal";

export default function Homepage() {
  const navigate = useNavigate();
  const { isAuthenticated, userId, isLoading } = useAuth();
  const { toast } = useToast();
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [signupModalOpen, setSignupModalOpen] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Check for login errors from Callback (e.g., Google login with no account)
  useEffect(() => {
    const errorMessage = sessionStorage.getItem("auth0_login_error");
    if (errorMessage) {
      sessionStorage.removeItem("auth0_login_error");
      setLoginError(errorMessage);
      setLoginModalOpen(true);
      toast({
        title: "Login Failed",
        description: errorMessage,
        variant: "destructive",
      });
    }
  }, [toast]);

  // Redirect if already logged in
  useEffect(() => {
    if (!isLoading && isAuthenticated && userId) {
      console.log("%c[FRONTEND-HOMEPAGE] User authenticated, redirecting to dashboard...", "color: red; font-weight: bold");
      navigate(`/user/${userId}`, { replace: true });
    }
  }, [isAuthenticated, userId, isLoading, navigate]);

  // Show loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main>
        <Hero onGetStarted={() => setSignupModalOpen(true)} />
        <Features />
        <HowItWorks />
        <Security />
        <CTASection onSignUp={() => setSignupModalOpen(true)} />
      </main>
      <Footer />

      {/* Auth Modals */}
      <LoginModal
        open={loginModalOpen}
        onOpenChange={(open) => {
          setLoginModalOpen(open);
          if (!open) {
            setLoginError(null); // Clear error when modal closes
          }
        }}
        onSwitchToSignup={() => setSignupModalOpen(true)}
        initialError={loginError}
      />
      <SignupModal
        open={signupModalOpen}
        onOpenChange={setSignupModalOpen}
        onSwitchToLogin={() => setLoginModalOpen(true)}
      />
    </div>
  );
}
