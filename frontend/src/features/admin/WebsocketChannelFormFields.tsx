import type { ChangeEvent } from "react";
import type { FormInstance } from "antd";
import { Button, Form, Input } from "antd";

import type { ImChannelCreate } from "@/shared/api/types";

type Props = {
  form: FormInstance<ImChannelCreate>;
};

export function WebsocketChannelFormFields({ form }: Props) {
  const addCurrentOrigin = () => {
    const fieldValue: unknown = form.getFieldValue("allowed_origins");
    const origins = Array.isArray(fieldValue)
      ? fieldValue.filter((origin): origin is string => typeof origin === "string")
      : [];
    if (!origins.includes(window.location.origin)) {
      form.setFieldValue("allowed_origins", [...origins, window.location.origin]);
    }
  };

  return (
    <>
      <div className="agent-websocket-create-fields">
        <Form.Item
          label="渠道名称"
          name="name"
          rules={[{ required: true, message: "请输入渠道名称" }]}
        >
          <Input maxLength={128} placeholder="例如：官网客服" />
        </Form.Item>
        <Form.Item
          getValueFromEvent={(event: ChangeEvent<HTMLTextAreaElement>) =>
            event.target.value.split("\n")
          }
          label="允许的 Origin"
          name="allowed_origins"
          rules={[
            {
              validator: (_, value: string[] | undefined) =>
                value?.some((item) => item.trim())
                  ? Promise.resolve()
                  : Promise.reject(new Error("至少配置一个 Origin")),
            },
          ]}
        >
          <Input.TextArea
            autoSize={{ minRows: 1, maxRows: 3 }}
            placeholder="https://portal.example.com"
          />
        </Form.Item>
      </div>
      <Button size="small" type="link" onClick={addCurrentOrigin}>
        填入当前地址（{window.location.origin}）
      </Button>
    </>
  );
}
