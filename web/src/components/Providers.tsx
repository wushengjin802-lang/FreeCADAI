"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#16734a",
          borderRadius: 6,
          fontFamily: '"Microsoft YaHei", "Segoe UI", sans-serif'
        },
        components: {
          Layout: { siderBg: "#1f2d2a", headerBg: "transparent" },
          Card: { borderRadiusLG: 8 },
          Table: { headerBg: "#fbfaf6" }
        }
      }}
    >
      <QueryClientProvider client={queryClient}>
        <App>{children}</App>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
