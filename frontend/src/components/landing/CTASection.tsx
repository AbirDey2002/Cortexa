import { Button } from "@/components/ui/button";
import { ArrowRight, Sparkles } from "lucide-react";

interface CTASectionProps {
  onSignUp: () => void;
}

export const CTASection = ({ onSignUp }: CTASectionProps) => {
  const handleSignUp = () => {
    onSignUp();
  };

  return (
    <section className="relative scroll-mt-20 py-20">
      {/* Content only - background is fixed in Homepage */}
      <div className="container mx-auto px-4 relative z-10 w-full">
        <div className="max-w-4xl mx-auto text-center flex flex-col items-center justify-center py-20">
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

