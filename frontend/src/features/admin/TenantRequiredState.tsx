import { Result } from "antd";

export function TenantRequiredState() {
  return <Result status="404" title="请先选择租户" />;
}
