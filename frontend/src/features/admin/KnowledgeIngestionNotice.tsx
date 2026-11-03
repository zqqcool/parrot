import { Button, Collapse, Progress } from "antd";

import {
  isTerminalIngestion,
  type IngestionQueueItem,
} from "@/features/admin/useKnowledgeDocuments";

type Props = {
  items: IngestionQueueItem[];
  onDismiss: () => void;
};

export function KnowledgeIngestionNotice({ items, onDismiss }: Props) {
  if (!items.length) return null;

  const completed = items.filter((item) => item.status === "succeeded").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const terminal = completed + failed;
  const active = items.length - terminal;
  const allTerminal = active === 0;
  const percent = Math.round(
    items.reduce((sum, item) => sum + stagePercent(item.status), 0) / items.length,
  );
  const label = allTerminal
    ? `知识文件处理完成：${completed} 个成功${failed ? `，${failed} 个失败` : ""}`
    : `正在处理 ${active} 个知识文件`;

  return (
    <Collapse
      className="knowledge-ingestion-progress"
      defaultActiveKey={allTerminal ? [] : ["jobs"]}
      expandIconPosition="end"
      items={[
        {
          key: "jobs",
          label: (
            <div className="knowledge-ingestion-summary">
              <div>
                <strong>{label}</strong>
                <span>
                  阶段进度 · {terminal}/{items.length} 个已结束
                </span>
              </div>
              <Progress
                aria-label="知识文件处理阶段进度"
                percent={percent}
                showInfo={false}
                size="small"
                status={failed ? "exception" : allTerminal ? "success" : "active"}
              />
            </div>
          ),
          extra: allTerminal ? (
            <Button
              size="small"
              type="link"
              onClick={(event) => {
                event.stopPropagation();
                onDismiss();
              }}
            >
              清除记录
            </Button>
          ) : null,
          children: (
            <div className="knowledge-ingestion-jobs">
              {items.map((item) => (
                <div className="knowledge-ingestion-job" key={item.id}>
                  <span className="knowledge-ingestion-job-title" title={item.title}>
                    {item.title}
                  </span>
                  <span
                    className={`knowledge-ingestion-stage knowledge-ingestion-stage--${stageTone(item)}`}
                  >
                    {stageLabel(item)}
                  </span>
                  {item.error ? (
                    <span className="knowledge-ingestion-error">状态读取失败，请稍后重试</span>
                  ) : null}
                </div>
              ))}
              {!allTerminal ? <p>完成提取、切分并发布前，Agent 不会检索这些新文档。</p> : null}
            </div>
          ),
        },
      ]}
      size="small"
    />
  );
}

function stagePercent(status: string) {
  if (status === "queued") return 10;
  if (status === "running") return 60;
  if (isTerminalIngestion(status)) return 100;
  return 10;
}

function stageLabel(item: IngestionQueueItem) {
  if (item.error) return "状态读取失败";
  if (item.status === "queued") return "等待处理";
  if (item.status === "running") return "提取与切分中";
  if (item.status === "succeeded") return "已发布";
  if (item.status === "failed") return `处理失败${item.errorCode ? `：${item.errorCode}` : ""}`;
  return "等待状态更新";
}

function stageTone(item: IngestionQueueItem) {
  if (item.error || item.status === "failed") return "error";
  if (item.status === "succeeded") return "success";
  if (item.status === "running") return "active";
  return "waiting";
}
