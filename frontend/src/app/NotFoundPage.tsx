import { Button } from "antd";
import { Link, useNavigate } from "react-router-dom";

import { ParrotLogo } from "@/shared/brand";
import { AppIcon } from "@/shared/icons";

import "./not-found-page.css";

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <main className="not-found-page">
      <section className="not-found-card" aria-labelledby="not-found-title">
        <Link className="not-found-brand" to="/" aria-label="返回 Parrot 智能体广场">
          <ParrotLogo decorative={false} />
          <span>Parrot</span>
        </Link>
        <div className="not-found-status" aria-hidden="true">
          404
        </div>
        <div className="not-found-copy">
          <h1 id="not-found-title">页面未找到</h1>
          <p>您访问的页面可能已被移动、删除，或地址输入有误。</p>
        </div>
        <div className="not-found-actions">
          <Button
            type="primary"
            icon={<AppIcon name="AllApplication" size="md" />}
            onClick={() => void navigate("/")}
          >
            返回智能体广场
          </Button>
          <Link to="/admin/login">前往管理控制台</Link>
        </div>
        <p className="not-found-code">错误代码：HTTP 404</p>
      </section>
    </main>
  );
}
