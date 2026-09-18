import type { Service } from "../../api/client";
import { formatDuration } from "../../utils/duration";
import { iconForService } from "../iconForService";

export function ServiceTiles({
  services,
  selectedIds,
  onToggle,
}: {
  services: Service[];
  selectedIds: number[];
  onToggle: (id: number) => void;
}) {
  return (
    <div className="tile-grid">
      {services.map((service) => {
        const Icon = iconForService(service.name);
        const selected = selectedIds.includes(service.id);
        return (
          <button
            key={service.id}
            type="button"
            className={`tile-button${selected ? " selected" : ""}`}
            onClick={() => onToggle(service.id)}
          >
            <Icon />
            <span>{service.name}</span>
            {/* UI_description.md п.34: в плитке должна быть видна и цена,
                и длительность услуги — раньше показывалась только цена. */}
            <span className="price">
              {service.price} ₽ · {formatDuration(service.duration_minutes)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
