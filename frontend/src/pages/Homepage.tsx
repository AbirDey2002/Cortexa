import { useEffect, useState, useRef } from "react";
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
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollRotation, setScrollRotation] = useState(0);

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
      navigate(`/user/${userId}`, { replace: true });
    }
  }, [isAuthenticated, userId, isLoading, navigate]);

  // Scroll handler for gradient circle rotation
  useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY;
      const windowHeight = window.innerHeight;
      const documentHeight = document.documentElement.scrollHeight;
      const scrollPercentage = Math.min(scrollY / (documentHeight - windowHeight), 1);
      
      // Rotate circles around center of viewport (360 degrees per full scroll)
      setScrollRotation(scrollPercentage * 360);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

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
    <div ref={containerRef} className="min-h-screen bg-background relative">
      {/* Fixed background elements - gradient and grid pattern */}
      <div className="fixed inset-0 bg-gradient-hero pointer-events-none z-0" />
      <div 
        className="fixed inset-0 opacity-[0.02] pointer-events-none z-0"
        style={{
          backgroundImage: `linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)`,
          backgroundSize: '60px 60px'
        }}
      />
      
      {/* Fixed gradient circles that rotate around center on scroll */}
      <div 
        className="fixed top-1/2 left-1/2 w-96 h-96 bg-primary/20 rounded-full blur-3xl animate-pulse-glow pointer-events-none z-0"
        style={{
          transform: `translate(-50%, -50%) translateX(-200px) translateY(-150px) rotate(${scrollRotation}deg)`,
          transformOrigin: '50% 50%',
        }}
      />
      <div 
        className="fixed top-1/2 left-1/2 w-80 h-80 bg-secondary/20 rounded-full blur-3xl pointer-events-none z-0"
        style={{
          transform: `translate(-50%, -50%) translateX(200px) translateY(150px) rotate(${-scrollRotation * 0.7}deg)`,
          transformOrigin: '50% 50%',
        }}
      />
      
      <Navbar />
      <main className="relative z-10">
        <Hero onGetStarted={() => setSignupModalOpen(true)} />
        <Features />
        <HowItWorks />
        <Security />
        <CTASection onSignUp={() => setSignupModalOpen(true)} />
      </main>
      <div className="relative z-10">
        <Footer />
      </div>

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
