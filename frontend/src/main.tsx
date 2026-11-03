import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { BrowserRouter } from "react-router-dom";
import "antd/dist/reset.css";

import { App } from "@/app/App";
import { parrotTheme } from "@/app/theme";
import "@/app/admin.css";
import "@/features/admin/dashboard.css";
import "@/features/admin/skills.css";
import "@/features/admin/skill-workbench.css";
import "@/app/styles.css";
import "@/app/workspace.css";
import "@/shared/icons/styles.css";
import { AuthProvider } from "@/shared/auth/AuthProvider";
import { RequestErrorNotifier } from "@/shared/ui";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={parrotTheme}>
      <AntdApp className="parrot-theme-root">
        <QueryClientProvider client={queryClient}>
          <RequestErrorNotifier />
          <BrowserRouter>
            <AuthProvider>
              <App />
            </AuthProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
);
