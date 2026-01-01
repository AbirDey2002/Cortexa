import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Calendar, Clock, ArrowRight } from "lucide-react";
import { Navbar } from "@/components/landing/Navbar";
import { Footer } from "@/components/landing/Footer";

const blogPosts = [
  {
    title: "The Future of AI-Powered Testing",
    excerpt: "Exploring how artificial intelligence is revolutionizing software testing and quality assurance processes.",
    date: "March 15, 2024",
    readTime: "5 min read",
    category: "AI & Testing",
  },
  {
    title: "Best Practices for Requirements Management",
    excerpt: "Learn how to effectively capture, organize, and process requirements for better test case generation.",
    date: "March 10, 2024",
    readTime: "7 min read",
    category: "Best Practices",
  },
  {
    title: "Understanding Test Coverage Analysis",
    excerpt: "A comprehensive guide to analyzing test coverage and identifying gaps in your testing strategy.",
    date: "March 5, 2024",
    readTime: "6 min read",
    category: "Testing",
  },
  {
    title: "Getting Started with CortexaDB",
    excerpt: "Learn how to set up and use CortexaDB to build intelligent knowledge bases for your applications.",
    date: "February 28, 2024",
    readTime: "8 min read",
    category: "Tutorial",
  },
  {
    title: "Security Best Practices for Test Data",
    excerpt: "Essential security practices for handling sensitive test data and ensuring compliance.",
    date: "February 20, 2024",
    readTime: "5 min read",
    category: "Security",
  },
  {
    title: "Automating Test Case Generation with AI",
    excerpt: "Discover how AI can automate test case generation and accelerate your SDLC.",
    date: "February 15, 2024",
    readTime: "6 min read",
    category: "Automation",
  },
];

export default function BlogPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="container mx-auto px-4 pt-24 pb-16 max-w-6xl">
        <div className="mb-12">
          <h1 className="text-4xl sm:text-5xl font-display font-bold mb-4">
            Blog
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl">
            Insights, tutorials, and updates about AI-powered testing and software quality assurance.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
          {blogPosts.map((post, index) => (
            <Card key={index} className="hover:shadow-glow transition-all cursor-pointer group">
              <CardHeader>
                <div className="mb-2">
                  <span className="text-xs font-semibold text-primary bg-primary/20 px-2 py-1 rounded">
                    {post.category}
                  </span>
                </div>
                <CardTitle className="mb-2 group-hover:text-primary transition-colors">
                  {post.title}
                </CardTitle>
                <CardDescription>{post.excerpt}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
                  <div className="flex items-center gap-1">
                    <Calendar className="w-4 h-4" />
                    {post.date}
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    {post.readTime}
                  </div>
                </div>
                <Button variant="outline" className="w-full group-hover:border-primary">
                  Read More
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="text-center">
          <h2 className="text-2xl font-display font-bold mb-4">Stay Updated</h2>
          <p className="text-muted-foreground mb-6">
            Subscribe to our newsletter to get the latest articles and updates.
          </p>
          <div className="flex gap-2 max-w-md mx-auto">
            <input
              type="email"
              placeholder="Enter your email"
              className="flex-1 px-4 py-2 rounded-lg glass border border-border focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <Button>Subscribe</Button>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

