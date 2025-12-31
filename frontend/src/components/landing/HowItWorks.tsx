import { Upload, Sparkles, BarChart3, FileCheck } from "lucide-react";

const steps = [
  {
    step: "01",
    icon: Upload,
    title: "Upload Requirements",
    description: "Import your FSDs, user stories, or specifications in any format. Our AI understands and processes them instantly."
  },
  {
    step: "02",
    icon: Sparkles,
    title: "AI Generates Test Cases",
    description: "Cortexa's AI analyzes your requirements and generates comprehensive test scenarios and test cases automatically."
  },
  {
    step: "03",
    icon: BarChart3,
    title: "Analyze Coverage",
    description: "Review your test coverage, identify gaps, and let AI generate missing test cases to ensure completeness."
  },
  {
    step: "04",
    icon: FileCheck,
    title: "Export Reports",
    description: "Export your test cases and coverage reports in multiple formats. Share with your team seamlessly."
  }
];

export const HowItWorks = () => {
  return (
    <section id="how-it-works" className="min-h-screen flex items-center relative">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-to-b from-background via-muted/10 to-background" />
      
      <div className="container mx-auto px-4 relative z-10 w-full">
        <div className="flex flex-col items-center justify-center min-h-screen py-20">
          {/* Section Header */}
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="inline-block px-4 py-1 rounded-full glass text-sm font-medium text-primary mb-4">
              How It Works
            </span>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-display font-bold mb-6">
              From Requirements to{" "}
              <span className="text-gradient">Complete Coverage</span>
            </h2>
            <p className="text-lg text-muted-foreground">
              Four simple steps to transform your testing workflow and accelerate your SDLC.
            </p>
          </div>

          {/* Steps */}
          <div className="relative max-w-5xl mx-auto w-full">
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 relative">
              {/* Connecting Line - positioned at icon center (32px from top of each step card) */}
              <div className="hidden lg:block absolute top-8 left-0 right-0 h-0.5 bg-gradient-to-r from-primary/20 via-primary/40 to-primary/20" />
              
              {steps.map((step, index) => (
                <div 
                  key={step.step}
                  className="relative text-center"
                >
                  {/* Step Number */}
                  <div className="relative inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-primary shadow-glow mb-6 mx-auto z-10 bg-clip-padding">
                    <step.icon className="w-7 h-7 text-primary-foreground relative z-10" />
                    <span className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-background border-2 border-primary text-xs font-bold text-primary flex items-center justify-center z-20">
                      {index + 1}
                    </span>
                  </div>

                  <h3 className="text-xl font-display font-semibold text-foreground mb-3">
                    {step.title}
                  </h3>
                  <p className="text-muted-foreground text-sm leading-relaxed">
                    {step.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

