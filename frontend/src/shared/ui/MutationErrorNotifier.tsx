import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { App, Space, Typography } from "antd";

import { HttpClientError, toUserErrorMessage } from "@/shared/http";

const fallback = "请求处理失败，请稍后重试。";

/**
 * Reports each React Query request failure once through Ant Design message.
 * This is the sole notification boundary for API query and mutation errors.
 */
export function RequestErrorNotifier() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  useEffect(() => {
    const report = (error: unknown) => {
      if (isAbortError(error)) return;
      void message.error({ content: <ErrorMessageContent error={error} />, duration: 6 });
    };
    const unsubscribeQueries = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" || event.action.type !== "error") return;
      if (isSessionBootstrapQuery(event.query.queryKey)) return;
      report(event.action.error);
    });
    const unsubscribeMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type !== "updated" || event.action.type !== "error") return;
      if (event.mutation.options.meta?.suppressGlobalErrorNotification === true) return;
      report(event.action.error);
    });

    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
  }, [message, queryClient]);

  return null;
}

function ErrorMessageContent({ error }: { error: unknown }) {
  const requestId = error instanceof HttpClientError ? error.requestId : undefined;
  return (
    <Space direction="vertical" size={0}>
      <span>{toUserErrorMessage(error, fallback)}</span>
      {requestId ? <Typography.Text type="secondary">请求编号：{requestId}</Typography.Text> : null}
    </Space>
  );
}

function isSessionBootstrapQuery(queryKey: unknown) {
  return Array.isArray(queryKey) && queryKey[0] === "auth" && queryKey[1] === "session";
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}
