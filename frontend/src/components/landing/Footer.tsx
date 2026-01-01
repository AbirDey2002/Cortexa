import { Link } from "react-router-dom";
import { Linkedin, Github, Instagram } from "lucide-react";

const footerLinks = {
  Product: [
    { label: "Features", href: "/#features" },
    { label: "Pricing", href: "/pricing" },
    { label: "Integrations", href: "/#features" },
    { label: "Changelog", href: "/blog" },
  ],
  Company: [
    { label: "About", href: "/#features" },
    { label: "Blog", href: "/blog" },
    { label: "Careers", href: "/contact" },
    { label: "Contact", href: "/contact" },
  ],
  Resources: [
    { label: "Documentation", href: "/documentation" },
    { label: "API Reference", href: "/documentation" },
    { label: "Guides", href: "/documentation" },
    { label: "Support", href: "/contact" },
  ],
  Legal: [
    { label: "Privacy Policy", href: "/contact" },
    { label: "Terms of Service", href: "/contact" },
    { label: "Security", href: "/#features" },
    { label: "GDPR", href: "/contact" },
  ],
};

const socialLinks = [
  { icon: Linkedin, href: "https://www.linkedin.com/in/abir-dey-42ab19235/", label: "LinkedIn" },
  { icon: Github, href: "https://github.com/AbirDey2002", label: "GitHub" },
  { icon: Instagram, href: "https://www.instagram.com/a.abir_._/?hl=en", label: "Instagram" },
];

export const Footer = () => {
  return (
    <footer className="relative z-10 py-16 border-t border-border bg-background/95 backdrop-blur-sm">
      <div className="container mx-auto px-4">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-8 mb-12">
          {/* Logo & Description */}
          <div className="col-span-2">
            <Link to="/" className="flex items-center gap-2 mb-4">
              <img 
                src="/cortexa.png" 
                alt="Cortexa Logo" 
                className="h-8 w-8 object-contain"
              />
              <span className="text-xl font-display font-bold text-foreground">
                Cortexa
              </span>
            </Link>
            <p className="text-sm text-muted-foreground mb-6 max-w-xs">
              AI-powered testing platform that covers your entire testing lifecycle from A to Z.
            </p>
            {/* Social Links */}
            <div className="flex items-center gap-3">
              {socialLinks.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  aria-label={social.label}
                  className="w-9 h-9 rounded-lg glass flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                >
                  <social.icon className="w-4 h-4" />
                </a>
              ))}
            </div>
          </div>

          {/* Link Columns */}
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h4 className="font-display font-semibold text-foreground mb-4">
                {category}
              </h4>
              <ul className="space-y-2">
                {links.map((link) => (
                  <li key={link.label}>
                    {link.href.startsWith('/') ? (
                      <Link
                        to={link.href}
                        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {link.label}
                      </Link>
                    ) : (
                      <a
                        href={link.href}
                        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {link.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">
            © {new Date().getFullYear()} Cortexa. All rights reserved.
          </p>
          <p className="text-sm text-muted-foreground">
            Your data is 100% encrypted and protected.
          </p>
        </div>
      </div>
    </footer>
  );
};

