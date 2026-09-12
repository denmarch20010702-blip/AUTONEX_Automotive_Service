import { useBookingStatus } from "../../api/events";
import { formatSlotLabel } from "./SlotPicker";
import { CheckCircleIcon } from "../icons";
import { StatusIndicator } from "../StatusIndicator";

export function SuccessCard({
  bookingId,
  startAt,
  initialStatus,
  onRestart,
}: {
  bookingId: number;
  startAt: string;
  initialStatus: string;
  onRestart: () => void;
}) {
  // Живой статус — обновляется сам по мере того, как станция обрабатывает
  // заявку, без перезагрузки страницы (тот же SSE-канал из A6).
  const status = useBookingStatus(bookingId, initialStatus);

  return (
    <div className="success-card">
      <div className="success-icon">
        <CheckCircleIcon />
      </div>
      <h2>Запись подтверждена</h2>
      <p>
        Заявка №{bookingId} принята. Ждём тебя <strong>{formatSlotLabel(startAt)}</strong> —
        не забудь про этот визит.
      </p>
      <p>
        Статус: <StatusIndicator status={status} />
      </p>
      <button type="button" className="primary-button" onClick={onRestart}>
        Записаться ещё раз
      </button>
    </div>
  );
}
