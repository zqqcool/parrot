import { Alert, Space, Typography } from "antd";

import { HttpClientError, toUserErrorMessage } from "@/shared/http";

const detailLabels: Record<string, string> = {
  upstream_http_status: "上游 HTTP 状态",
  upstream_error_code: "供应商错误码",
  upstream_error_type: "供应商错误类型",
  upstream_message: "供应商错误信息",
  upstream_request_id: "供应商请求编号",
  failure_type: "失败类型",
  network_error: "网络错误类型",
  diagnostic: "诊断信息",
  expected_dimension: "期望向量维度",
  actual_dimension: "实际向量维度",
  expected_response_count: "期望响应数量",
  actual_response_count: "实际响应数量",
};

export function ModelConnectionTestError({ error }: { error: unknown }) {
  if (!error) return null;
  const details = error instanceof HttpClientError ? error.details : [];
  const requestId = error instanceof HttpClientError ? error.requestId : undefined;
  return (
    <Alert
      showIcon
      type="error"
      message={toUserErrorMessage(error, "连接测试失败，请检查配置后重试。")}
      description={
        <Space direction="vertical" size={2}>
          {details.map((detail, index) => (
            <Typography.Text key={`${detail.field}:${index}`}>
              <strong>{detailLabels[detail.field] ?? detail.field}：</strong>
              {detail.reason}
            </Typography.Text>
          ))}
          {requestId ? (
            <Typography.Text type="secondary">Parrot 请求编号：{requestId}</Typography.Text>
          ) : null}
        </Space>
      }
    />
  );
}
