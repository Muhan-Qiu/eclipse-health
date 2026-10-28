import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider, useAppTheme } from "@/lib/theme";
import { isRetryableNetworkError } from "@/lib/api/error";
import "@/lib/i18n";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) =>
        isRetryableNetworkError(error) && failureCount < 2,
      refetchOnWindowFocus: false,
    },
  },
});

function ThemedToaster() {
  const { resolved } = useAppTheme();
  return <Toaster theme={resolved} />;
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={300}>
          {children}
          <ThemedToaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
