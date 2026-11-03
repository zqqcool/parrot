import { Space, Typography } from "antd";
import type { AlertProps } from "antd";

import { HttpClientError, toUserErrorMessage } from "@/shared/http";

type RequestErrorMessageProps = {
  error: unknown;
  fallback: string;
};

type RequestErrorAlertProps = Omit<AlertProps, "description" | "message" | "type"> &
  RequestErrorMessageProps;

export function RequestErrorMessage({ error, fallback }: RequestErrorMessageProps) {
  const requestId = error instanceof HttpClientError ? error.requestId : undefined;

  return (
    <Space direction="vertical" size={2}>
      <span>{toUserErrorMessage(error, fallback)}</span>
      {requestId ? <Typography.Text type="secondary">请求编号：{requestId}</Typography.Text> : null}
    </Space>
  );
}

export function RequestErrorAlert(props: RequestErrorAlertProps) {
  // Request failures are reported once by RequestErrorNotifier. Keeping this
  // compatibility component empty prevents legacy call sites from rendering a
  // second page-level alert while they are migrated to normal loading states.
  void props;
  return null;
}
