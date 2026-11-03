import { Alert, Button, Form, Radio, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { SkillManifestExecutionFields } from "@/features/admin/SkillManifestExecutionFields";
import { SkillManifestJsonEditor } from "@/features/admin/SkillManifestJsonEditor";
import {
  manifestWarnings,
  parseManifest,
  toManifest,
  type ManifestFormValues,
} from "@/features/admin/skillManifestModel";

type EditMode = "form" | "json";

type Props = {
  content: string;
  disabled?: boolean;
  availablePaths?: string[];
  onChange: (content: string) => void;
};

export function SkillManifestForm({ content, disabled, availablePaths = [], onChange }: Props) {
  const [form] = Form.useForm<ManifestFormValues>();
  const [mode, setMode] = useState<EditMode>("form");
  const parsed = useMemo(() => parseManifest(content), [content]);
  const watchedValues = Form.useWatch([], form);
  const values = watchedValues ?? parsed.values;
  const warnings = useMemo(
    () => (values ? manifestWarnings(values, availablePaths) : []),
    [availablePaths, values],
  );

  useEffect(() => {
    if (parsed.values) form.setFieldsValue(parsed.values);
  }, [form, parsed]);

  const emitFormChange = () => {
    onChange(`${JSON.stringify(toManifest(form.getFieldsValue()), null, 2)}\n`);
  };

  return (
    <div className="skill-manifest-form">
      <div className="skill-manifest-form__header">
        <Typography.Paragraph type="secondary">
          通过表单配置受支持的执行参数，或直接编辑 <code>manifest.json</code>
          。后端仍会在保存时校验协议。
        </Typography.Paragraph>
        <Radio.Group
          aria-label="manifest 编辑方式"
          buttonStyle="solid"
          optionType="button"
          options={[
            { label: "表单配置", value: "form" },
            { label: "JSON", value: "json" },
          ]}
          value={mode}
          onChange={(event) => setMode(event.target.value as EditMode)}
        />
      </div>
      {mode === "json" ? (
        <SkillManifestJsonEditor
          content={content}
          disabled={disabled}
          error={parsed.error}
          onChange={onChange}
        />
      ) : (
        <Form disabled={disabled} form={form} layout="vertical" onValuesChange={emitFormChange}>
          {parsed.error ? (
            <Alert
              description={
                <Button type="link" onClick={() => setMode("json")}>
                  前往 JSON 编辑
                </Button>
              }
              message={parsed.error}
              showIcon
              type="error"
            />
          ) : (
            <>
              {warnings.map((message) => (
                <Alert key={message} message={message} showIcon type="warning" />
              ))}
              <SkillManifestExecutionFields execute={values?.execute === true} />
            </>
          )}
        </Form>
      )}
    </div>
  );
}
