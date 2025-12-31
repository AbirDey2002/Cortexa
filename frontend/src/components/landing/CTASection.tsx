import { Button } from "@/components/ui/button";
import { ArrowRight, Sparkles } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";

const HARDCODED_USER_ID = "52588196-f538-42bf-adb8-df885ab0120c";

export const CTASection = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSignUp = () => {
    login(HARDCODED_USER_ID);
    navigate(`/user/${HARDCODED_USER_ID}`);
  };

  return (
    <section className="min-h-screen flex items-center relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-background to-secondary/10" />
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-3xl" />
      <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-secondary/20 rounded-full blur-3xl" />
      
      <div className="container mx-auto px-4 relative z-10 w-full">
        <div className="max-w-4xl mx-auto text-center flex flex-col items-center justify-center min-h-screen">
          {/* Icon */}
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-primary shadow-glow mb-8 animate-float">
            <Sparkles className="w-8 h-8 text-primary-foreground" />
          </div>

          {/* Headline */}
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-display font-bold mb-6">
            Start Testing{" "}
            <span className="text-gradient">Smarter Today</span>
          </h2>

          {/* Subtext */}
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10">
            Join thousands of teams who have accelerated their SDLC with Cortexa's AI-powered testing platform. No credit card required to get started.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-8">
            <Button 
              size="lg" 
              onClick={handleSignUp}
              className="bg-gradient-primary hover:opacity-90 text-primary-foreground font-semibold shadow-glow transition-all duration-300 hover:shadow-lg px-10 py-6 text-base"
            >
              Sign Up Free
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
            <Button 
              size="lg" 
              variant="outline" 
              className="border-border bg-transparent hover:bg-muted/50 text-foreground px-10 py-6 text-base"
            >
              Contact Sales
            </Button>
          </div>

          {/* Trust Text */}
          <p className="text-sm text-muted-foreground">
            ✓ Free to start • ✓ No credit card required • ✓ Enterprise-grade security
          </p>
        </div>
      </div>
    </section>
  );
};

