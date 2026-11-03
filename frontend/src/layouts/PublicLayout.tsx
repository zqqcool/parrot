import { Button } from "antd";
import { Link, Outlet, useLocation } from "react-router-dom";

import { ParrotLogo } from "@/shared/brand";
import { AppIcon } from "@/shared/icons";

export function PublicLayout() {
  const location = useLocation();
  const isTextChat = /^\/im\/websocket\/[^/]+$/.test(location.pathname);
  return (
    <div className={isTextChat ? "site-shell site-shell-chat" : "site-shell"}>
      <header className="site-header">
        <div className="site-header-inner">
          <Link className="brand-link" to="/">
            <ParrotLogo size="small" />
            <span>Parrot</span>
          </Link>
          <Button href="/admin" icon={<AppIcon name="Workbench" size="md" />}>
            管理控制台
          </Button>
        </div>
      </header>
      <main className={isTextChat ? "site-content site-content-chat" : "site-content"}>
        <Outlet />
      </main>
    </div>
  );
}
