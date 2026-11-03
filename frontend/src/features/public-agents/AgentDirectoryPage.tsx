import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Empty, Input, Skeleton, Spin } from "antd";
import { Link } from "react-router-dom";

import { publicApi } from "@/shared/api/client";
import { endpoints } from "@/shared/api/endpoints";
import { AppIcon } from "@/shared/icons";

export function AgentDirectoryPage() {
  const [keyword, setKeyword] = useState("");
  const deferredKeyword = useDeferredValue(keyword.trim());
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const { data, error, fetchNextPage, hasNextPage, isFetchingNextPage, isPending } =
    useInfiniteQuery({
      queryKey: ["public", "agents", deferredKeyword],
      initialPageParam: 0,
      queryFn: ({ pageParam }) =>
        publicApi.listAgents({ offset: pageParam, limit: 15, search: deferredKeyword }),
      getNextPageParam: (lastPage, pages) =>
        lastPage.length === 15 ? pages.reduce((total, page) => total + page.length, 0) : undefined,
      placeholderData: (previousData) => previousData,
    });
  const agents = useMemo(() => data?.pages.flat() ?? [], [data]);

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !hasNextPage) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetchingNextPage) void fetchNextPage();
      },
      { rootMargin: "240px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  if (isPending) return <Skeleton active paragraph={{ rows: 8 }} />;
  if (error) return <Empty description="智能体列表暂不可用" />;
  return (
    <section className="directory" aria-labelledby="directory-title">
      <div className="directory-heading">
        <div>
          <span className="directory-kicker">智能体目录</span>
          <h1 id="directory-title">选择一个智能体开始交互</h1>
          <p>通过管理员人工绑定的 WebSocket 渠道接入智能体。</p>
        </div>
        <span className="directory-count">已加载 {agents.length} 个</span>
      </div>
      <div className="directory-toolbar">
        <Input
          allowClear
          value={keyword}
          prefix={<AppIcon name="Search" size="md" />}
          placeholder="搜索智能体名称或说明"
          aria-label="搜索智能体"
          onChange={(event) => setKeyword(event.target.value)}
        />
        <span>显示 {agents.length} 个智能体</span>
      </div>
      {agents.length ? (
        <div className="agent-list">
          {agents.map((agent) => (
            <Link className="agent-row" key={agent.id} to={`/agents/${agent.slug}`}>
              <span className="agent-icon">
                {agent.avatar_present ? (
                  <img alt="" src={endpoints.public.agentAvatar(agent.slug)} />
                ) : (
                  <AppIcon name="RobotOne" size="xl" />
                )}
              </span>
              <span className="agent-summary">
                <strong>{agent.name}</strong>
                <span>{agent.description || "已发布的 Parrot 智能体"}</span>
              </span>
              <span className="agent-capabilities" aria-label="可配置的交互渠道">
                <span>
                  <AppIcon name="Message" size="sm" /> WebSocket
                </span>
              </span>
              <span className="agent-open-action">
                打开
                <AppIcon name="ArrowRight" size="md" />
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="directory-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={deferredKeyword ? "未找到匹配的智能体" : "暂无可公开访问的智能体"}
          />
        </div>
      )}
      <div className="directory-load-more" ref={loadMoreRef} aria-live="polite">
        {isFetchingNextPage ? <Spin size="small" tip="正在加载更多智能体" /> : null}
        {!hasNextPage && agents.length ? <span>已加载全部智能体</span> : null}
      </div>
    </section>
  );
}
