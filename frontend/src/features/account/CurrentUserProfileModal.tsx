import { useEffect, useState } from "react";
import { Modal, Tabs } from "antd";

import { CurrentUserPasswordForm } from "@/features/account/CurrentUserPasswordForm";
import { CurrentUserProfileForm } from "@/features/account/CurrentUserProfileForm";
import type { Principal } from "@/shared/api/types";

type Props = {
  open: boolean;
  principal: Principal | undefined;
  onClose: () => void;
};

export function CurrentUserProfileModal({ open, principal, onClose }: Props) {
  const [activeKey, setActiveKey] = useState("profile");
  const [activeLoading, setActiveLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setActiveKey("profile");
      setActiveLoading(false);
    }
  }, [open]);

  const close = () => {
    if (!activeLoading) onClose();
  };

  return (
    <Modal
      closable={!activeLoading}
      destroyOnHidden
      footer={null}
      keyboard={!activeLoading}
      maskClosable={!activeLoading}
      open={open}
      title="个人资料"
      onCancel={close}
    >
      <Tabs
        activeKey={activeKey}
        destroyOnHidden
        items={[
          {
            key: "profile",
            label: "基本资料",
            children: (
              <CurrentUserProfileForm
                principal={principal}
                onClose={close}
                onLoadingChange={setActiveLoading}
              />
            ),
          },
          {
            key: "security",
            label: "安全设置",
            children: (
              <CurrentUserPasswordForm onChanged={onClose} onLoadingChange={setActiveLoading} />
            ),
          },
        ]}
        onChange={(key) => {
          if (!activeLoading) setActiveKey(key);
        }}
      />
    </Modal>
  );
}
