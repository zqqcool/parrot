import { Button, Input } from "antd";

import { AppIcon } from "@/shared/icons";

type ChatComposerProps = {
  canSteer: boolean;
  draft: string;
  onCancel: () => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
  submitting: boolean;
};

export function ChatComposer({
  canSteer,
  draft,
  onCancel,
  onChange,
  onSubmit,
  submitting,
}: ChatComposerProps) {
  return (
    <footer className={submitting ? "chat-composer chat-composer-stopping" : "chat-composer"}>
      <Input.TextArea
        value={draft}
        onChange={(event) => onChange(event.target.value)}
        onPressEnter={(event) => {
          if (!event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
        autoSize={{ minRows: 1, maxRows: 5 }}
        placeholder={
          canSteer ? "补充信息后按 Enter 继续" : "输入消息，Enter 发送，Shift+Enter 换行"
        }
        disabled={submitting}
      />
      {submitting ? (
        <Button
          className="chat-composer-action chat-composer-stop"
          danger
          onClick={onCancel}
          aria-label="停止生成"
        >
          停止
        </Button>
      ) : (
        <Button
          className="chat-composer-action"
          type="primary"
          aria-label="发送消息"
          onClick={onSubmit}
          disabled={!draft.trim()}
        >
          <AppIcon name="Send" size="lg" />
        </Button>
      )}
    </footer>
  );
}
