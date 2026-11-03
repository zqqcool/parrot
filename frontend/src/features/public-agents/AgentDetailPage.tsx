import { useQuery } from "@tanstack/react-query";
import { Result, Skeleton } from "antd";
import { Link, useParams } from "react-router-dom";

import { publicApi } from "@/shared/api/client";
import { endpoints } from "@/shared/api/endpoints";
import { toUserErrorMessage } from "@/shared/http";
import { AppIcon } from "@/shared/icons";

export function AgentDetailPage() {
  const { slug = "" } = useParams();
  const query = useQuery({
    queryKey: ["public", "agent", slug],
    queryFn: () => publicApi.getAgent(slug),
    enabled: Boolean(slug),
  });
  const channels = useQuery({
    queryKey: ["public", "agent", slug, "channels"],
    queryFn: () => publicApi.listAgentChannels(slug),
    enabled: Boolean(slug),
  });
  if (query.isPending || channels.isPending) return <Skeleton active paragraph={{ rows: 6 }} />;
  if (query.error) {
    return (
      <Result
        status="error"
        title="智能体加载失败"
        subTitle={toUserErrorMessage(query.error, "请稍后刷新页面重试。")}
      />
    );
  }
  if (channels.error) {
    return (
      <Result
        status="error"
        title="渠道加载失败"
        subTitle={toUserErrorMessage(channels.error, "请稍后刷新页面重试。")}
      />
    );
  }
  if (!query.data) return <Result status="404" title="未找到智能体" />;
  const agent = query.data;
  return (
    <section className="agent-detail">
      <div className="page-heading">
        <span className="agent-icon">
          {agent.avatar_present ? (
            <img alt="" src={endpoints.public.agentAvatar(agent.slug)} />
          ) : (
            <AppIcon name="RobotOne" size="2xl" />
          )}
        </span>
        <h1>{agent.name}</h1>
        <p>{agent.description}</p>
      </div>
      <div className="entry-choice">
        <div>
          <AppIcon name="Message" size="xl" />
          <h2>WebSocket 渠道接入</h2>
          <p>请选择管理员手动创建并绑定给该智能体的渠道进入测试。</p>
          {channels.data?.length ? (
            <div className="entry-choice-channels">
              {channels.data.map((channel) => (
                <Link
                  className="entry-choice-channel"
                  key={channel.channel_key}
                  to={`/im/websocket/${channel.channel_key}`}
                >
                  <span>{channel.name}</span>
                  <span>进入测试</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="entry-choice-empty">当前智能体尚未配置可用渠道。</p>
          )}
        </div>
      </div>
    </section>
  );
}
