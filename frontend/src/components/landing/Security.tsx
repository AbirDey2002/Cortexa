import { Shield, Lock, Key, Eye, Server, CheckCircle } from "lucide-react";

const securityFeatures = [
  {
    icon: Key,
    title: "Bring Your Own Key (BYOK)",
    description: "Use your own encryption keys for complete control over your data security."
  },
  {
    icon: Lock,
    title: "End-to-End Encryption",
    description: "All data is encrypted in transit and at rest using industry-standard protocols."
  },
  {
    icon: Eye,
    title: "Privacy First",
    description: "No sensitive data is stored unencrypted. Your testing data remains yours."
  },
  {
    icon: Server,
    title: "Secure Infrastructure",
    description: "Enterprise-grade infrastructure with SOC 2 compliance and regular audits."
  }
];

export const Security = () => {
  return (
    <section className="relative scroll-mt-20 py-20">
      {/* Content only - background is fixed in Homepage */}
      <div className="container mx-auto px-4 relative z-10 w-full">
        <div className="grid lg:grid-cols-2 gap-12 items-center py-20">
          {/* Left Content */}
          <div>
            <span className="inline-flex items-center gap-2 px-4 py-1 rounded-full glass text-sm font-medium text-primary mb-6">
              <Shield className="w-4 h-4" />
              Security & Privacy
            </span>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-display font-bold mb-6">
              Your Data is{" "}
              <span className="text-gradient">Completely Protected</span>
            </h2>
            <p className="text-lg text-muted-foreground mb-8">
              We understand that your testing data contains sensitive information. That's why security isn't just a feature — it's the foundation of Cortexa.
            </p>
            
            {/* Trust Badges */}
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg glass">
                <CheckCircle className="w-5 h-5 text-green-500" />
                <span className="text-sm font-medium text-foreground">SOC 2 Compliant</span>
              </div>
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg glass">
                <CheckCircle className="w-5 h-5 text-green-500" />
                <span className="text-sm font-medium text-foreground">GDPR Ready</span>
              </div>
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg glass">
                <CheckCircle className="w-5 h-5 text-green-500" />
                <span className="text-sm font-medium text-foreground">256-bit Encryption</span>
              </div>
            </div>
          </div>

          {/* Right Grid */}
          <div className="grid sm:grid-cols-2 gap-4">
            {securityFeatures.map((feature, index) => (
              <div 
                key={feature.title}
                className="p-6 rounded-2xl glass hover:bg-muted/30 transition-all duration-300 group"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center mb-4 group-hover:bg-primary/30 transition-colors">
                  <feature.icon className="w-5 h-5 text-primary" />
                </div>
                <h3 className="text-lg font-display font-semibold text-foreground mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

