import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Auth0Provider } from "@auth0/auth0-react";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import Homepage from "./pages/Homepage";
import Callback from "./pages/Callback";
import UserChatPage from "./pages/UserChatPage";
import NotFound from "./pages/NotFound";

import DocumentationPage from "./pages/DocumentationPage";
import BlogPage from "./pages/BlogPage";
import ContactPage from "./pages/ContactPage";
import SettingsPage from "./pages/SettingsPage";
import ProfilePage from "./pages/ProfilePage";
import UsagePage from "./pages/UsagePage";
import HelpPage from "./pages/HelpPage";

const queryClient = new QueryClient();

const domain = import.meta.env.VITE_AUTH0_DOMAIN || "";
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID || "";
const audience = import.meta.env.VITE_AUTH0_AUDIENCE || "";

console.log("Auth0 Config Debug:", {
  domain,
  clientId,
  audience,
  redirect_uri: window.location.origin + "/callback"
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Auth0Provider
        domain={domain}
        clientId={clientId}
        authorizationParams={{
          redirect_uri: window.location.origin + "/callback",
          audience: audience,
        }}
        useRefreshTokens={true}
        cacheLocation="localstorage"
      >
        <AuthProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Homepage />} />
              <Route path="/callback" element={<Callback />} />

              <Route path="/documentation" element={<DocumentationPage />} />
              <Route path="/blog" element={<BlogPage />} />
              <Route path="/contact" element={<ContactPage />} />
              <Route
                path="/user/:userId"
                element={
                  <ProtectedRoute>
                    <UserChatPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/user/:userId/:usecaseId"
                element={
                  <ProtectedRoute>
                    <UserChatPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/user/:userId/settings"
                element={
                  <ProtectedRoute>
                    <SettingsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/user/:userId/profile"
                element={
                  <ProtectedRoute>
                    <ProfilePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/user/:userId/usage"
                element={
                  <ProtectedRoute>
                    <UsagePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/user/:userId/help"
                element={
                  <ProtectedRoute>
                    <HelpPage />
                  </ProtectedRoute>
                }
              />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </Auth0Provider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
