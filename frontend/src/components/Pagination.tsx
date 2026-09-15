// UI_description.md п.40 (2026-09-15): журналы (шины, заявки) разрослись
// настолько, что приходилось много скроллить — постранично, по 50 строк на
// страницу, вместо всего списка сразу. Один переиспользуемый виджет вместо
// четырёх копий (журнал заявок и шин — и на станции, и в кабинете клиента).
export function Pagination({
  page,
  total,
  pageSize,
  onChange,
}: {
  page: number;
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (pageCount <= 1) return null;

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.75rem", margin: "0.6rem 0" }}>
      <button type="button" className="ghost-button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ‹ Назад
      </button>
      <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>
        Страница {page} из {pageCount}
      </span>
      <button type="button" className="ghost-button" disabled={page >= pageCount} onClick={() => onChange(page + 1)}>
        Вперёд ›
      </button>
    </div>
  );
}
