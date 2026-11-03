import type { ReactNode } from "react";
import { Button, Space } from "antd";

type Props = {
  cancelButton: ReactNode;
  disabled?: boolean;
  okButton: ReactNode;
  onTest: () => void;
  testing: boolean;
};

export function ModelConfigModalFooter({
  cancelButton,
  disabled,
  okButton,
  onTest,
  testing,
}: Props) {
  return (
    <Space>
      <Button disabled={disabled || testing} loading={testing} onClick={onTest}>
        测试连接
      </Button>
      {cancelButton}
      {okButton}
    </Space>
  );
}
