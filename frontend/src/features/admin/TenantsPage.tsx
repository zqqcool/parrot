import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Form, Input, Modal, Select } from "antd";

import { adminApi } from "@/shared/api/client";
import type { TenantCreate } from "@/shared/api/types";
import {
  AdminPageHeader,
  BinaryStatusTag,
  CreateButton,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

export function TenantsPage() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");
  const [form] = Form.useForm<TenantCreate>();
  const query = useQuery({
    queryKey: ["admin", "tenants", searchQuery],
    queryFn: () => adminApi.listTenants(searchQuery),
  });
  const create = useMutation({
    mutationFn: adminApi.createTenant,
    onSuccess: async () => {
      setOpen(false);
      form.resetFields();
      await client.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
  const tenants = (query.data ?? []).filter(
    (tenant) => statusFilter === "all" || tenant.status === statusFilter,
  );
  return (
    <section>
      <AdminPageHeader title="租户管理" description="管理平台工作空间及数据隔离边界。" />
      <SearchBar
        actions={<CreateButton onClick={() => setOpen(true)} />}
        advancedFilters={
          <Select
            aria-label="按状态筛选租户"
            options={[
              { value: "all", label: "全部状态" },
              { value: "active", label: "启用" },
              { value: "disabled", label: "禁用" },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
          />
        }
        hasActiveFilters={statusFilter !== "all"}
        placeholder="搜索租户名称或标识"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setStatusFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载租户失败，请稍后重试。" />
      <DataTable
        rowKey="id"
        loading={query.isFetching}
        dataSource={tenants}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        columns={[
          { title: "租户名称", dataIndex: "name" },
          { title: "租户标识", dataIndex: "slug" },
          {
            title: "状态",
            dataIndex: "status",
            render: (value: string) => (
              <BinaryStatusTag
                active={value === "active"}
                activeLabel="启用"
                inactiveLabel={value}
              />
            ),
          },
        ]}
      />
      <Modal
        title="新建租户"
        open={open}
        confirmLoading={create.isPending}
        onCancel={() => setOpen(false)}
        onOk={() => void form.validateFields().then((values) => create.mutate(values))}
      >
        <RequestErrorAlert error={create.error} fallback="创建租户失败，请稍后重试。" />
        <Form className="admin-modal-form" form={form} layout="vertical">
          <Form.Item
            name="name"
            label="租户名称"
            rules={[{ required: true, message: "请输入租户名称" }]}
          >
            <Input placeholder="例如：示例科技" />
          </Form.Item>
          <Form.Item
            name="slug"
            label="租户标识"
            extra="仅支持小写字母、数字和短横线，以字母开头"
            rules={[
              { required: true, message: "请输入租户标识" },
              { pattern: /^[a-z][a-z0-9-]{2,99}$/, message: "租户标识格式不正确" },
            ]}
          >
            <Input placeholder="例如：example-tech" />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
