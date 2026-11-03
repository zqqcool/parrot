import { Alert, Empty, List, Spin, Tag } from "antd";

import type { RunTaskBoard } from "@/shared/api/types";

import { statusColor } from "./runDetailModel";

type RunTaskBoardProps = {
  error: unknown;
  loading: boolean;
  taskBoard: RunTaskBoard | undefined;
};

export function RunTaskBoard({ error, loading, taskBoard }: RunTaskBoardProps) {
  if (loading) return <Spin />;
  if (error) return <Empty description="任务拆解暂不可用" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  if (!taskBoard || taskBoard.status === "not_generated") {
    return <Empty description="本轮未生成子任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  if (taskBoard.status === "unavailable") {
    return <Alert message="该 Run 的任务拆解不可用" type="warning" showIcon />;
  }
  return (
    <List
      className="run-task-board"
      dataSource={taskBoard.tasks}
      locale={{ emptyText: "本轮未生成子任务" }}
      renderItem={(task) => (
        <List.Item>
          <List.Item.Meta title={task.title} description={task.objective} />
          <div className="run-task-board__meta">
            <Tag>{task.kind}</Tag>
            <Tag color={statusColor(task.status)}>{task.status}</Tag>
            {task.depends_on.length ? <span>依赖：{task.depends_on.join("、")}</span> : null}
            {task.child_interaction_id ? <span>子 Run：{task.child_interaction_id}</span> : null}
            {task.result_summary ? <p>{task.result_summary}</p> : null}
          </div>
        </List.Item>
      )}
    />
  );
}
