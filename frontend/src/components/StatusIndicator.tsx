// Индикатор статуса заявки — зелёный/оранжевый/красный кружок с текстом
// (buisness/UI_description.md: "индикатор зелёного, красного и оранжевого
// цветов, с текстом"), общий для экрана станции и клиента.
// Соответствие цвета статусу — решение AI, не описано в спеке дословно:
// зелёный = работа завершена/можно забирать, оранжевый = в процессе,
// красный = отменена. Легко пересмотреть по обратной связи.
const STATUS_META: Record<string, { color: string; label: string }> = {
  accepted: { color: "#e0a339", label: "Принята" },
  on_post: { color: "#e0a339", label: "На посту" },
  awaiting_approval: { color: "#e0a339", label: "Ожидает согласования" },
  ready: { color: "#4caf6f", label: "Готова" },
  issued: { color: "#4caf6f", label: "Выдана" },
  cancelled: { color: "#d64545", label: "Отменена" },
};

export function StatusIndicator({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? { color: "#999", label: status };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
      <span
        style={{
          display: "inline-block",
          width: 12,
          height: 12,
          borderRadius: "50%",
          background: meta.color,
        }}
      />
      {meta.label}
    </span>
  );
}
