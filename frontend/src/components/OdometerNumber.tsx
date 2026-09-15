// UI_description.md п.45 (2026-09-15, прямая просьба пользователя):
// механический счётчик — цифры визуально прокручиваются вверх/вниз при
// смене значения, соседние (предыдущая/следующая) цифры не показываются
// целиком, а затухают по краям (см. mask-image в styles.css).
function Digit({ value }: { value: number }) {
  return (
    <span className="odometer-digit">
      <span className="odometer-digit__strip" style={{ transform: `translateY(${-value * 1.2}em)` }}>
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i}>{i}</span>
        ))}
      </span>
    </span>
  );
}

// `value` — уже отформатированная строка (например, "12 345 ₽") — катятся
// только сами цифры, остальные символы (пробелы-разрядители, ₽, точка)
// выводятся как есть, без анимации.
export function OdometerNumber({ value }: { value: string }) {
  return (
    <span className="odometer">
      {value.split("").map((ch, i) =>
        /\d/.test(ch) ? (
          <Digit key={i} value={Number(ch)} />
        ) : (
          <span key={i} className="odometer-static">
            {ch}
          </span>
        ),
      )}
    </span>
  );
}
