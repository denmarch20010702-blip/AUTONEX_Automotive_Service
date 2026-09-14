// UI_description.md п.17/22: маленькая красная точка — и в шапке рядом со
// ссылкой навигации, и продублированная прямо на месте, где нужно принять
// решение (конкретная строка заявки/доп. работы), а не только в общем месте.
export function NotificationDot({ show, title }: { show: boolean; title?: string }) {
  if (!show) return null;
  return (
    <span
      title={title}
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: "var(--color-danger)",
        marginLeft: "0.35rem",
        verticalAlign: "middle",
      }}
    />
  );
}
