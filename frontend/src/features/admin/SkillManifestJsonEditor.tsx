import { Alert, Input } from "antd";

type Props = {
  content: string;
  disabled?: boolean;
  error: string | null;
  onChange: (content: string) => void;
};

export function SkillManifestJsonEditor({ content, disabled, error, onChange }: Props) {
  return (
    <div className="skill-manifest-json-editor">
      {error ? <Alert message={error} showIcon type="error" /> : null}
      <Input.TextArea
        aria-label="manifest JSON"
        autoSize={{ minRows: 14 }}
        disabled={disabled}
        spellCheck={false}
        value={content}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
