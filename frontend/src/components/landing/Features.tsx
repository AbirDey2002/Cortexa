import { 
  FileText, 
  Sparkles, 
  Database, 
  GitCompare, 
  Target, 
  Cpu,
  ArrowRight
} from "lucide-react";

const features = [
  {
    icon: FileText,
    title: "Requirements Ingestion",
    description: "Upload and capture new requirements seamlessly. Import FSDs, user stories, and specifications in any format.",
    gradient: "from-blue-500 to-cyan-500"
  },
  {
    icon: Sparkles,
    title: "AI Test Generation",
    description: "Automatically generate comprehensive scenarios and test cases from your requirements using advanced AI models.",
    gradient: "from-purple-500 to-pink-500"
  },
  {
    icon: Database,
    title: "CortexaDB (VectorBase)",
    description: "Store application context for mature applications. Build intelligent knowledge bases that improve over time.",
    gradient: "from-green-500 to-emerald-500"
  },
  {
    icon: GitCompare,
    title: "Smart Comparison",
    description: "Compare requirements, scenarios, and test cases across versions. Identify gaps and inconsistencies instantly.",
    gradient: "from-orange-500 to-amber-500"
  },
  {
    icon: Target,
    title: "Coverage Analysis",
    description: "Check test coverage against your testbed. Generate missing test cases automatically to ensure completeness.",
    gradient: "from-red-500 to-rose-500"
  },
  {
    icon: Cpu,
    title: "Multi-Model Support",
    description: "Choose from a variety of AI models based on your testing needs. BYOK with 100% encryption guaranteed.",
    gradient: "from-indigo-500 to-violet-500"
  }
];

export const Features = () => {
  return (
    <section id="features" className="min-h-screen flex items-center relative">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-to-b from-background via-muted/20 to-background" />
      
      <div className="container mx-auto px-4 relative z-10 w-full">
        <div className="flex flex-col items-center justify-center min-h-screen py-20">
          {/* Section Header */}
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="inline-block px-4 py-1 rounded-full glass text-sm font-medium text-primary mb-4">
              Core Features
            </span>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-display font-bold mb-6">
              Everything You Need for{" "}
              <span className="text-gradient">Complete Testing</span>
            </h2>
            <p className="text-lg text-muted-foreground">
              From requirement ingestion to report generation, Cortexa covers your entire testing lifecycle with AI-powered automation.
            </p>
          </div>

          {/* Features Grid */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 w-full max-w-7xl">
            {features.map((feature, index) => (
              <FeatureCard key={feature.title} {...feature} index={index} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

const FeatureCard = ({ 
  icon: Icon, 
  title, 
  description, 
  gradient,
  index 
}: { 
  icon: React.ElementType; 
  title: string; 
  description: string;
  gradient: string;
  index: number;
}) => (
  <div 
    className="group p-6 rounded-2xl glass hover:bg-muted/30 transition-all duration-300 hover:scale-[1.02] hover:shadow-glow cursor-pointer"
    style={{ animationDelay: `${index * 0.1}s` }}
  >
    <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300`}>
      <Icon className="w-6 h-6 text-white" />
    </div>
    <h3 className="text-xl font-display font-semibold text-foreground mb-3 group-hover:text-primary transition-colors">
      {title}
    </h3>
    <p className="text-muted-foreground leading-relaxed mb-4">
      {description}
    </p>
    <div className="flex items-center text-primary text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
      Learn more <ArrowRight className="w-4 h-4 ml-1" />
    </div>
  </div>
);

