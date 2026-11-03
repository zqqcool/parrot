const logoUrl = new URL("../../assets/parrot-logo.png", import.meta.url).href;

type ParrotLogoProps = {
  size?: "small" | "large";
  className?: string;
  decorative?: boolean;
};

export function ParrotLogo({ size = "small", className, decorative = true }: ParrotLogoProps) {
  const classNames = ["brand-logo", `brand-logo-${size}`, className].filter(Boolean).join(" ");

  return (
    <img
      src={logoUrl}
      className={classNames}
      alt={decorative ? "" : "Parrot 智能体平台"}
      aria-hidden={decorative || undefined}
      draggable={false}
    />
  );
}
