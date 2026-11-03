import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";

type Props = {
  execute: boolean;
};

const runtimeOptions = ["python", "node", "shell"].map((value) => ({ label: value, value }));

export function SkillManifestExecutionFields({ execute }: Props) {
  return (
    <>
      <Card size="small" title="Skill 类型">
        <Form.Item label="执行 Skill" name="execute" valuePropName="checked">
          <Switch checkedChildren="执行" unCheckedChildren="仅说明" />
        </Form.Item>
        {!execute ? (
          <Alert
            description="仅说明 Skill 只会将指令提供给模型，不运行代码，也不会创建沙盒、网络或环境变量。"
            message="不会启动沙盒"
            showIcon
            type="info"
          />
        ) : null}
      </Card>
      {execute ? <ExecutableSettings /> : null}
    </>
  );
}

function ExecutableSettings() {
  return (
    <>
      <Card size="small" title="执行设置">
        <Form.Item label="执行环境" name="runtime">
          <Select options={runtimeOptions} />
        </Form.Item>
        <Form.Item label="入口文件" name="entrypoint">
          <Input placeholder="scripts/main.py" />
        </Form.Item>
        <Form.Item label="超时（秒）" name="timeoutSeconds">
          <InputNumber max={900} min={1} precision={0} />
        </Form.Item>
      </Card>
      <Card size="small" title="网络与环境变量">
        <Form.Item label="允许网络" name="networkEnabled" valuePropName="checked">
          <Switch checkedChildren="允许" unCheckedChildren="断网" />
        </Form.Item>
        <Form.List name="env">
          {(fields, { add, remove }) => (
            <>
              <Typography.Text>非敏感环境变量</Typography.Text>
              {fields.map((field) => (
                <Space key={field.key} align="baseline">
                  <Form.Item
                    name={[field.name, "name"]}
                    rules={[{ pattern: /^[A-Z][A-Z0-9_]{0,63}$/ }]}
                  >
                    <Input aria-label="环境变量名称" placeholder="API_BASE_URL" />
                  </Form.Item>
                  <Form.Item name={[field.name, "value"]}>
                    <Input aria-label="环境变量值" placeholder="https://example.internal" />
                  </Form.Item>
                  <Button danger onClick={() => remove(field.name)} type="link">
                    删除
                  </Button>
                </Space>
              ))}
              <Button onClick={() => add({})} type="dashed">
                添加环境变量
              </Button>
            </>
          )}
        </Form.List>
      </Card>
    </>
  );
}
