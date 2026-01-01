import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Book, Code, FileText, Zap, Database, Key, ArrowRight } from "lucide-react";
import { Navbar } from "@/components/landing/Navbar";
import { Footer } from "@/components/landing/Footer";

const docsSections = [
  {
    icon: Zap,
    title: "Getting Started",
    description: "Quick start guide to get you up and running",
    topics: ["Installation", "First Test Case", "Basic Configuration"],
  },
  {
    icon: FileText,
    title: "Requirements Ingestion",
    description: "Learn how to upload and process requirements",
    topics: ["Supported Formats", "FSD Processing", "User Stories"],
  },
  {
    icon: Code,
    title: "API Reference",
    description: "Complete API documentation for integrations",
    topics: ["Authentication", "Endpoints", "Rate Limits"],
  },
  {
    icon: Database,
    title: "CortexaDB",
    description: "Vector database for application context",
    topics: ["Setup", "Data Ingestion", "Querying"],
  },
  {
    icon: Key,
    title: "Security & Encryption",
    description: "Security best practices and BYOK setup",
    topics: ["Encryption", "Key Management", "Compliance"],
  },
  {
    icon: Book,
    title: "Guides & Tutorials",
    description: "Step-by-step guides for common tasks",
    topics: ["Test Generation", "Coverage Analysis", "Report Export"],
  },
];

export default function DocumentationPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="container mx-auto px-4 pt-24 pb-16 max-w-6xl">
        <div className="mb-12">
          <h1 className="text-4xl sm:text-5xl font-display font-bold mb-4">
            Documentation
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl">
            Comprehensive guides and API reference for Cortexa's AI-powered testing platform.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
          {docsSections.map((section) => (
            <Card key={section.title} className="hover:shadow-glow transition-all cursor-pointer group">
              <CardHeader>
                <div className="w-12 h-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4 group-hover:bg-primary/30 transition-colors">
                  <section.icon className="w-6 h-6 text-primary" />
                </div>
                <CardTitle className="mb-2">{section.title}</CardTitle>
                <CardDescription>{section.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 mb-4">
                  {section.topics.map((topic, index) => (
                    <li key={index} className="text-sm text-muted-foreground flex items-center gap-2">
                      <ArrowRight className="w-3 h-3 text-primary" />
                      {topic}
                    </li>
                  ))}
                </ul>
                <Button variant="outline" className="w-full group-hover:border-primary">
                  Read More
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Quick Start Guide</CardTitle>
            <CardDescription>Get started with Cortexa in 5 minutes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <h3 className="font-semibold">1. Create an Account</h3>
              <p className="text-sm text-muted-foreground">
                Sign up for a free account to get started. No credit card required.
              </p>
            </div>
            <div className="space-y-2">
              <h3 className="font-semibold">2. Upload Your Requirements</h3>
              <p className="text-sm text-muted-foreground">
                Upload your FSD, user stories, or specifications in any format. Our AI will process them automatically.
              </p>
            </div>
            <div className="space-y-2">
              <h3 className="font-semibold">3. Generate Test Cases</h3>
              <p className="text-sm text-muted-foreground">
                Let Cortexa's AI generate comprehensive test cases from your requirements.
              </p>
            </div>
            <div className="space-y-2">
              <h3 className="font-semibold">4. Analyze Coverage</h3>
              <p className="text-sm text-muted-foreground">
                Review test coverage and identify gaps. Generate missing test cases automatically.
              </p>
            </div>
            <div className="space-y-2">
              <h3 className="font-semibold">5. Export Reports</h3>
              <p className="text-sm text-muted-foreground">
                Export your test cases and coverage reports in multiple formats.
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="text-center">
          <h2 className="text-2xl font-display font-bold mb-4">Need Help?</h2>
          <p className="text-muted-foreground mb-6">
            Can't find what you're looking for? Contact our support team.
          </p>
          <Button onClick={() => window.location.href = "/contact"}>
            Contact Support
          </Button>
        </div>
      </main>
      <Footer />
    </div>
  );
}

