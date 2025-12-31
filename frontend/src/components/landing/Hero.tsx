import { Button } from "@/components/ui/button";
import { ArrowRight, Play, Sparkles, Shield, Zap } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";

const HARDCODED_USER_ID = "52588196-f538-42bf-adb8-df885ab0120c";

export const Hero = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleGetStarted = () => {
    login(HARDCODED_USER_ID);
    navigate(`/user/${HARDCODED_USER_ID}`);
  };

  return (
    <section className="relative min-h-screen flex items-center justify-center pt-20 overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-hero" />
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-3xl animate-pulse-glow" />
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-secondary/20 rounded-full blur-3xl" />
      
      {/* Grid Pattern */}
      <div 
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)`,
          backgroundSize: '60px 60px'
        }}
      />

      <div className="container mx-auto px-4 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8 animate-fade-in">
            <Sparkles className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-muted-foreground">
              AI-Powered Testing Platform
            </span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-display font-bold leading-tight mb-6 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            AI-Powered Testing{" "}
            <span className="text-gradient">From A to Z</span>
          </h1>

          {/* Subheadline */}
          <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            Generate test cases, capture requirements, analyze coverage, and accelerate your SDLC — all with intelligent automation and complete data protection.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
            <Button 
              size="lg" 
              onClick={handleGetStarted}
              className="bg-gradient-primary hover:opacity-90 text-primary-foreground font-semibold shadow-glow transition-all duration-300 hover:shadow-lg px-8 py-6 text-base"
            >
              Get Started Free
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
            <Button 
              size="lg" 
              variant="outline" 
              className="border-border bg-transparent hover:bg-muted/50 text-foreground px-8 py-6 text-base"
            >
              <Play className="w-5 h-5 mr-2" />
              Watch Demo
            </Button>
          </div>

          {/* Trust Indicators */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
            <TrustItem icon={Zap} text="Boost Productivity" />
            <TrustItem icon={Shield} text="100% Encrypted" />
            <TrustItem icon={Sparkles} text="AI-Powered" />
            <TrustItem icon={ArrowRight} text="Accelerate SDLC" />
          </div>
        </div>
      </div>
    </section>
  );
};

const TrustItem = ({ icon: Icon, text }: { icon: React.ElementType; text: string }) => (
  <div className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg glass hover:bg-muted/30 transition-colors">
    <Icon className="w-4 h-4 text-primary" />
    <span className="text-sm font-medium text-muted-foreground">{text}</span>
  </div>
);

