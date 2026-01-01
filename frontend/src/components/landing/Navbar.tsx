import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { LoginModal } from "@/components/auth/LoginModal";
import { SignupModal } from "@/components/auth/SignupModal";

const navLinks = [
  { label: "Product", href: "/#features" },
  { label: "Features", href: "/#how-it-works" },
  { label: "Pricing", href: "/pricing" },
  { label: "Documentation", href: "/documentation" },
  { label: "Blog", href: "/blog" },
  { label: "Contact", href: "/contact" },
];

export const Navbar = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [signupModalOpen, setSignupModalOpen] = useState(false);
  const { isAuthenticated, userId } = useAuth();
  const navigate = useNavigate();

  const handleSignUp = () => {
    setSignupModalOpen(true);
  };

  const handleLogin = () => {
    setLoginModalOpen(true);
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16 md:h-20">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 group">
            <img 
              src="/cortexa.png" 
              alt="Cortexa Logo" 
              className="h-8 w-8 object-contain"
            />
            <span className="text-xl font-display font-bold text-foreground">
              Cortexa
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden lg:flex items-center gap-8">
            {navLinks.map((link) => (
              link.href.startsWith('/') ? (
                <Link
                  key={link.label}
                  to={link.href}
                  className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors duration-200"
                >
                  {link.label}
                </Link>
              ) : (
                <a
                  key={link.label}
                  href={link.href}
                  className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors duration-200"
                >
                  {link.label}
                </a>
              )
            ))}
          </div>

          {/* Desktop CTA */}
          <div className="hidden lg:flex items-center gap-3">
            {!isAuthenticated ? (
              <>
                <Button 
                  variant="ghost" 
                  onClick={handleLogin}
                  className="text-muted-foreground hover:text-foreground"
                >
                  Login
                </Button>
                <Button 
                  onClick={handleSignUp}
                  className="bg-gradient-primary hover:opacity-90 text-primary-foreground font-semibold shadow-glow transition-all duration-300 hover:shadow-lg"
                >
                  Sign Up
                </Button>
              </>
            ) : (
              <Button 
                onClick={() => userId && navigate(`/user/${userId}`)}
                className="bg-gradient-primary hover:opacity-90 text-primary-foreground font-semibold shadow-glow transition-all duration-300 hover:shadow-lg"
              >
                Go to Dashboard
              </Button>
            )}
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="lg:hidden p-2 text-foreground"
            aria-label="Toggle menu"
          >
            {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Menu */}
        {isOpen && (
          <div className="lg:hidden py-4 border-t border-border animate-fade-in">
            <div className="flex flex-col gap-4">
              {navLinks.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors py-2"
                  onClick={() => setIsOpen(false)}
                >
                  {link.label}
                </a>
              ))}
              <div className="flex flex-col gap-2 pt-4 border-t border-border">
                {!isAuthenticated ? (
                  <>
                    <Button 
                      variant="ghost" 
                      onClick={() => {
                        handleLogin();
                        setIsOpen(false);
                      }}
                      className="justify-start text-muted-foreground"
                    >
                      Login
                    </Button>
                    <Button 
                      onClick={() => {
                        handleSignUp();
                        setIsOpen(false);
                      }}
                      className="bg-gradient-primary text-primary-foreground font-semibold"
                    >
                      Sign Up
                    </Button>
                  </>
                ) : (
                  <Button 
                    onClick={() => {
                      if (userId) {
                        navigate(`/user/${userId}`);
                        setIsOpen(false);
                      }
                    }}
                    className="bg-gradient-primary text-primary-foreground font-semibold"
                  >
                    Go to Dashboard
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Auth Modals */}
      <LoginModal
        open={loginModalOpen}
        onOpenChange={setLoginModalOpen}
        onSwitchToSignup={() => setSignupModalOpen(true)}
      />
      <SignupModal
        open={signupModalOpen}
        onOpenChange={setSignupModalOpen}
        onSwitchToLogin={() => setLoginModalOpen(true)}
      />
    </nav>
  );
};

