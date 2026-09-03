import { ArrowLeft } from "@phosphor-icons/react";

export function AdminHomeLink({ className = "" }: { className?: string }) {
  const classes = ["admin-home-link", className].filter(Boolean).join(" ");

  return <a className={classes} href="/">
    <ArrowLeft aria-hidden="true" />
    返回主页面
  </a>;
}
