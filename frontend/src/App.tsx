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

const queryClient = new QueryClient();

const domain = import.meta.env.VITE_AUTH0_DOMAIN || "";
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID || "";
const audience = import.meta.env.VITE_AUTH0_AUDIENCE || "";

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
