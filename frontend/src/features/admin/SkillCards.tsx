import { Button, Card, Empty, Popconfirm, Skeleton, Tag } from "antd";
import { Link } from "react-router-dom";

import type { Skill } from "@/shared/api/types";

type Props = {
  canManage: boolean;
  loading: boolean;
  onPublish: (skill: Skill) => void;
  onView: (skill: Skill) => void;
  publishPending: boolean;
  skills: Skill[];
};

export function SkillCards({
  canManage,
  loading,
  onPublish,
  onView,
  publishPending,
  skills,
}: Props) {
  if (loading) return <SkillCardSkeletons />;
  if (!skills.length) return <Empty className="skills-empty" description="暂无匹配的 Skill" />;

  return (
    <div className="skills-grid">
      {skills.map((skill) => (
        <SkillCard
          canManage={canManage}
          key={skill.id}
          onPublish={onPublish}
          onView={onView}
          publishPending={publishPending}
          skill={skill}
        />
      ))}
    </div>
  );
}

function SkillCard({
  canManage,
  onPublish,
  onView,
  publishPending,
  skill,
}: Omit<Props, "loading" | "skills"> & { skill: Skill }) {
  const status = skillStatusPresentation(skill.status);

  return (
    <article aria-label={`Skill ${skill.name}`} className="skill-card">
      <Card>
        <header className="skill-card-heading">
          <strong title={skill.name}>{skill.name}</strong>
          <span aria-label={`当前版本 v${skill.version}`} className="skill-card-version">
            v{skill.version}
          </span>
        </header>
        <div className="skill-card-statuses">
          <Tag color={status.color}>{status.label}</Tag>
          {skill.has_draft ? <Tag color="gold">有待发布草稿</Tag> : null}
        </div>
        <p className="skill-card-description">{skill.description || "暂无说明"}</p>
        <SkillBoundAgents agents={skill.bound_agents} />
        <div className="skill-card-actions">
          <Button size="small" onClick={() => onView(skill)}>
            查看版本
          </Button>
          {canManage && skill.status !== "published" ? (
            <Popconfirm
              cancelText="取消"
              description="发布后即可绑定到智能体。"
              okText="确认发布"
              title="确认发布该 Skill？"
              onConfirm={() => onPublish(skill)}
            >
              <Button loading={publishPending} size="small" type="primary">
                发布
              </Button>
            </Popconfirm>
          ) : null}
        </div>
      </Card>
    </article>
  );
}

function SkillBoundAgents({ agents }: { agents: Skill["bound_agents"] | undefined }) {
  const agentCount = agents?.length ?? 0;
  return (
    <section
      aria-label="关联 Agent"
      className={
        agentCount
          ? "skill-card-bound-agents skill-card-bound-agents--active"
          : "skill-card-bound-agents"
      }
    >
      <div className="skill-card-bound-agents-heading">
        <span>关联 Agent</span>
        {agents !== null ? <strong>{agentCount}</strong> : null}
      </div>
      <div className="skill-card-bound-agents-content">
        {agents === null ? (
          "无查看关联 Agent 的权限"
        ) : agents?.length ? (
          <span className="skill-card-agent-links">
            {agents.map((agent) => (
              <Link
                aria-label={`查看关联 Agent ${agent.name}`}
                className="skill-card-agent-link"
                key={agent.id}
                title={agent.name}
                to={`/admin/agents/${agent.id}`}
              >
                {agent.name}
              </Link>
            ))}
          </span>
        ) : (
          "暂无关联"
        )}
      </div>
    </section>
  );
}

function SkillCardSkeletons() {
  return (
    <div aria-label="正在加载 Skill" className="skills-grid" role="status">
      {Array.from({ length: 5 }, (_, index) => (
        <Card className="skill-card" key={index}>
          <Skeleton active paragraph={{ rows: 6 }} title />
        </Card>
      ))}
    </div>
  );
}

function skillStatusPresentation(status: string) {
  if (status === "published") return { color: "green", label: "已发布" };
  if (status === "disabled") return { color: "red", label: "已停用" };
  return { color: "gold", label: "草稿" };
}
