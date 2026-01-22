import React, { ReactNode } from "react";
import { useSidebar } from "@/components/ui/sidebar";

interface FloatingInputContainerProps {
  children: ReactNode;
}

export const FloatingInputContainer: React.FC<FloatingInputContainerProps> = ({
  children
}) => {
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";
  return (
    <div 
      className={`
        fixed bottom-0 z-20
        py-3 sm:py-4 md:py-6
        border-t border-gray-800 glassmorphism-input
        bg-background
        w-full md:max-w-4xl
        transition-all duration-300
        ${isSidebarCollapsed ? 'left-0 md:left-1/2 md:-translate-x-1/2' : 'left-0 md:left-1/2 md:-translate-x-1/2 md:ml-40'}
      `}
    >
      {children}
    </div>
  );
};
