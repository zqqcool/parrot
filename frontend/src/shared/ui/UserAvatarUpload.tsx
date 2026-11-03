import { useEffect, useMemo } from "react";
import { App, Avatar, Upload } from "antd";

import { AppIcon } from "@/shared/icons";

import "./user-avatar-upload.css";

type Props = {
  avatarUrl?: string;
  file: File | null;
  disabled?: boolean;
  onChange: (file: File | null) => void;
};

const acceptedTypes = ["image/jpeg", "image/png", "image/webp"];
const maxAvatarBytes = 2 * 1024 * 1024;

export function UserAvatarUpload({ avatarUrl, file, disabled = false, onChange }: Props) {
  const { message } = App.useApp();
  const localPreviewUrl = useMemo(() => (file ? URL.createObjectURL(file) : undefined), [file]);
  const previewUrl = localPreviewUrl ?? avatarUrl;

  useEffect(() => {
    return () => {
      if (localPreviewUrl) {
        URL.revokeObjectURL(localPreviewUrl);
      }
    };
  }, [localPreviewUrl]);

  const selectAvatar = (selectedFile: File) => {
    if (!acceptedTypes.includes(selectedFile.type)) {
      void message.error("仅支持 PNG、JPEG 或 WebP 图片");
      return Upload.LIST_IGNORE;
    }
    if (selectedFile.size > maxAvatarBytes) {
      void message.error("头像文件不能超过 2 MB");
      return Upload.LIST_IGNORE;
    }
    onChange(selectedFile);
    return false;
  };

  return (
    <div className="user-avatar-upload">
      <Upload
        accept="image/png,image/jpeg,image/webp"
        beforeUpload={selectAvatar}
        disabled={disabled}
        maxCount={1}
        showUploadList={false}
      >
        <button
          className="user-avatar-upload-trigger"
          type="button"
          aria-label="选择头像"
          disabled={disabled}
        >
          <Avatar
            className="user-avatar-upload-preview"
            icon={<AppIcon name="User" size="lg" />}
            size={72}
            src={previewUrl}
          />
          <span>{previewUrl ? "点击更换头像" : "点击上传头像"}</span>
        </button>
      </Upload>
      {file ? (
        <button
          className="user-avatar-upload-remove"
          type="button"
          disabled={disabled}
          onClick={() => onChange(null)}
        >
          移除本次选择
        </button>
      ) : null}
    </div>
  );
}
