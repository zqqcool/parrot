import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { HttpClientError } from "@/shared/http/errors";
import { BinaryStatusTag, RequestErrorAlert, RequestErrorNotifier } from "@/shared/ui";

describe("shared feedback primitives", () => {
  it("never renders a page-level alert for a request error", () => {
    const error = rejectedHttpError("req_page");
    const { container } = render(<RequestErrorAlert error={error} fallback="加载失败" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the server message once when a mutation fails", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    render(
      <AntdApp>
        <QueryClientProvider client={client}>
          <RequestErrorNotifier />
          <FailedSubmit />
        </QueryClientProvider>
      </AntdApp>,
    );

    await user.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() =>
      expect(document.querySelector(".ant-message-notice")).toBeInstanceOf(HTMLElement),
    );
    const notice = document.querySelector(".ant-message-notice");
    if (!(notice instanceof HTMLElement)) throw new Error("Expected a message container");
    expect(within(notice).getByText("当前账号没有执行此操作的权限。")).toBeInTheDocument();
    expect(within(notice).getByText("请求编号：req_submit")).toBeInTheDocument();
    expect(document.querySelectorAll(".ant-message-notice")).toHaveLength(1);
  });

  it("shows query failures through message without requiring page-level UI", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <AntdApp>
        <QueryClientProvider client={client}>
          <RequestErrorNotifier />
          <FailedQuery />
        </QueryClientProvider>
      </AntdApp>,
    );

    await waitFor(() => {
      expect(document.querySelector(".ant-message-notice")).toBeInstanceOf(HTMLElement);
      expect(screen.getByText("查询已失败")).toBeInTheDocument();
    });
    expect(document.body).toHaveTextContent(
      "可执行 Skill 的草稿尚未完成当前构建，请先点击“构建草稿”，构建成功后再发布。",
    );
  });

  it("allows an explicit local-only mutation to suppress the global message", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const messagesBefore = document.querySelectorAll(".ant-message-notice").length;
    render(
      <AntdApp>
        <QueryClientProvider client={client}>
          <RequestErrorNotifier />
          <LocallyHandledFailure />
        </QueryClientProvider>
      </AntdApp>,
    );

    await user.click(screen.getByRole("button", { name: "本地处理" }));

    await waitFor(() => expect(screen.getByText("本地错误提示")).toBeInTheDocument());
    expect(document.querySelectorAll(".ant-message-notice")).toHaveLength(messagesBefore);
  });

  it("renders consistent labels for binary status", () => {
    const { rerender } = render(
      <BinaryStatusTag active activeLabel="已发布" inactiveLabel="草稿" />,
    );
    expect(screen.getByText("已发布")).toBeInTheDocument();

    rerender(<BinaryStatusTag active={false} activeLabel="已发布" inactiveLabel="草稿" />);
    expect(screen.getByText("草稿")).toBeInTheDocument();
  });
});

function FailedSubmit() {
  const mutation = useMutation({
    mutationFn: () => Promise.reject(rejectedHttpError("req_submit")),
  });

  return <button onClick={() => mutation.mutate()}>提交</button>;
}

function FailedQuery() {
  const query = useQuery({
    queryKey: ["skills", "build"],
    queryFn: () => Promise.reject(rejectedHttpError("req_query")),
    retry: false,
  });
  return <span>{query.isError ? "查询已失败" : "正在查询"}</span>;
}

function LocallyHandledFailure() {
  const mutation = useMutation({
    mutationFn: () => Promise.reject(new Error("locally handled")),
    meta: { suppressGlobalErrorNotification: true },
  });

  return (
    <>
      <button onClick={() => mutation.mutate()}>本地处理</button>
      {mutation.isError ? <span>本地错误提示</span> : null}
    </>
  );
}

function rejectedHttpError(requestId: string) {
  return new HttpClientError({
    status: 409,
    statusText: "Conflict",
    url: "/api/v1/example",
    payload: {
      code: requestId === "req_query" ? "SKILL_BUILD_REQUIRED" : "FORBIDDEN",
      message:
        requestId === "req_query"
          ? "可执行 Skill 的草稿尚未完成当前构建，请先点击“构建草稿”，构建成功后再发布。"
          : "当前账号没有执行此操作的权限。",
      details: [],
      request_id: requestId,
    },
  });
}
