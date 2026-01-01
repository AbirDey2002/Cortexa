import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { HelpCircle, Book, MessageSquare, Video, FileText, Search, ArrowRight, Mail } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";

const helpCategories = [
  {
    icon: Book,
    title: "Getting Started",
    description: "Learn the basics of using Cortexa",
    articles: [
      "Creating your first test case",
      "Uploading requirements",
      "Understanding AI models",
    ],
  },
  {
    icon: FileText,
    title: "Features Guide",
    description: "Explore all Cortexa features",
    articles: [
      "Requirements ingestion",
      "Test case generation",
      "Coverage analysis",
    ],
  },
  {
    icon: Video,
    title: "Video Tutorials",
    description: "Watch step-by-step tutorials",
    articles: [
      "Quick start video",
      "Advanced features",
      "Best practices",
    ],
  },
  {
    icon: Search,
    title: "Troubleshooting",
    description: "Common issues and solutions",
    articles: [
      "Test generation errors",
      "Upload issues",
      "API problems",
    ],
  },
];

const faqs = [
  {
    question: "How do I generate test cases?",
    answer: "Upload your Functional Specification Document (FSD) or requirements, and Cortexa's AI will automatically generate comprehensive test cases for you.",
  },
  {
    question: "What file formats are supported?",
    answer: "Cortexa supports PDF, Word documents, text files, and markdown formats for requirements upload.",
  },
  {
    question: "Can I customize the AI model?",
    answer: "Yes, you can choose from multiple AI models in the model selector dropdown. Enterprise plans also support Bring Your Own Key (BYOK).",
  },
  {
    question: "How secure is my data?",
    answer: "All data is encrypted end-to-end. We use industry-standard encryption and offer BYOK for enterprise customers. Your data is never shared with third parties.",
  },
  {
    question: "What is CortexaDB?",
    answer: "CortexaDB is our vector database that stores your application context, allowing the AI to generate more accurate and contextual test cases over time.",
  },
];

export default function HelpPage() {
  const { userId } = useAuth();
  const navigate = useNavigate();

  if (!userId) {
    return null;
  }

  return (
    <Layout userId={userId}>
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <div className="mb-8">
          <h1 className="text-4xl font-display font-bold mb-2">Help Center</h1>
          <p className="text-muted-foreground">Find answers and learn how to use Cortexa</p>
        </div>

        {/* Search Bar */}
        <div className="mb-8">
          <div className="relative max-w-2xl">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search for help articles..."
              className="w-full pl-10 pr-4 py-3 rounded-lg glass border border-border focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>

        {/* Help Categories */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
          {helpCategories.map((category) => (
            <Card key={category.title} className="hover:shadow-glow transition-all cursor-pointer group">
              <CardHeader>
                <div className="w-12 h-12 rounded-lg bg-primary/20 flex items-center justify-center mb-4 group-hover:bg-primary/30 transition-colors">
                  <category.icon className="w-6 h-6 text-primary" />
                </div>
                <CardTitle className="mb-2">{category.title}</CardTitle>
                <CardDescription>{category.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {category.articles.map((article, index) => (
                    <li key={index} className="text-sm text-muted-foreground flex items-center gap-2">
                      <ArrowRight className="w-3 h-3 text-primary" />
                      {article}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* FAQs */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HelpCircle className="w-5 h-5 text-primary" />
              Frequently Asked Questions
            </CardTitle>
            <CardDescription>Common questions and answers</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {faqs.map((faq, index) => (
                <div key={index} className="pb-6 border-b border-border last:border-0 last:pb-0">
                  <h3 className="font-semibold text-lg mb-2">{faq.question}</h3>
                  <p className="text-muted-foreground">{faq.answer}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Contact Support */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-primary" />
              Still Need Help?
            </CardTitle>
            <CardDescription>Can't find what you're looking for? Contact our support team</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4">
              <Button
                variant="outline"
                onClick={() => navigate("/contact")}
                className="flex items-center gap-2"
              >
                <Mail className="w-4 h-4" />
                Contact Support
              </Button>
              <Button
                variant="outline"
                onClick={() => navigate("/documentation")}
                className="flex items-center gap-2"
              >
                <FileText className="w-4 h-4" />
                View Documentation
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}

