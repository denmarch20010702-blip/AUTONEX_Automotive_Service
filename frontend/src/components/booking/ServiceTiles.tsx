import type { Service } from "../../api/client";
import { iconForService } from "../icons";

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
            <span className="price">{service.price} ₽</span>
          </button>
        );
      })}
    </div>
  );
}
