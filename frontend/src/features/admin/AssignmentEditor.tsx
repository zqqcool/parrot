import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Modal } from "antd";

import type { Assignment } from "@/shared/api/types";
import { MultiSelect, RequestErrorAlert } from "@/shared/ui";

type Option = { value: string; label: string };

type AssignmentEditorProps = {
  open: boolean;
  title: string;
  queryKey: readonly unknown[];
  options: Option[];
  load: () => Promise<Assignment>;
  save: (ids: string[]) => Promise<{ updated: boolean }>;
  onClose: () => void;
};

export function AssignmentEditor({
  open,
  title,
  queryKey,
  options,
  load,
  save,
  onClose,
}: AssignmentEditorProps) {
  const [ids, setIds] = useState<string[]>([]);
  const current = useQuery({ queryKey, queryFn: load, enabled: open });
  const mutation = useMutation({
    mutationFn: save,
    onSuccess: onClose,
  });

  useEffect(() => {
    if (current.data) setIds([...current.data.ids]);
  }, [current.data]);

  return (
    <Modal
      title={title}
      open={open}
      destroyOnHidden
      confirmLoading={mutation.isPending}
      okButtonProps={{ disabled: current.isPending || Boolean(current.error) }}
      onCancel={onClose}
      onOk={() => mutation.mutate(ids)}
    >
      <RequestErrorAlert
        error={current.error ?? mutation.error}
        fallback="更新授权失败，请稍后重试。"
      />
      <MultiSelect
        aria-label={title}
        loading={current.isPending}
        value={ids}
        options={options}
        onChange={setIds}
        style={{ width: "100%", marginTop: 12 }}
      />
    </Modal>
  );
}
