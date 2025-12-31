import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { 
  Navbar, 
  Hero, 
  Features, 
  Security, 
  HowItWorks, 
  CTASection, 
  Footer 
} from "@/components/landing";

export default function Homepage() {
  const navigate = useNavigate();
  const { isAuthenticated, userId } = useAuth();

  // Redirect if already logged in
  useEffect(() => {
    if (isAuthenticated && userId) {
      navigate(`/user/${userId}`, { replace: true });
    }
  }, [isAuthenticated, userId, navigate]);

  // Don't render if already authenticated (will redirect)
  if (isAuthenticated && userId) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Security />
        <CTASection />
      </main>
      <Footer />
    </div>
  );
}
