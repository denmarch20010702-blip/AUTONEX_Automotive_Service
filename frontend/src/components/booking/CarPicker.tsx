import type { CarInfo } from "../../api/client";
import { CarIcon, PlusIcon } from "../icons";

export function CarPicker({
  cars,
  onSelect,
  onAddNew,
}: {
  cars: CarInfo[];
  onSelect: (car: CarInfo) => void;
  onAddNew: () => void;
}) {
  return (
    <div>
      <div className="tile-grid" style={{ marginBottom: "1.5rem" }}>
        {cars.map((car) => (
          <button
            key={car.id}
            type="button"
            className="tile-button"
            onClick={() => onSelect(car)}
          >
            <CarIcon />
            <span>
              {car.make} {car.model}
            </span>
            <span className="price">{car.mileage} км</span>
          </button>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "center" }}>
        <button type="button" className="add-car-button" onClick={onAddNew}>
          <CarIcon width={24} height={24} />
          <PlusIcon />
          добавить автомобиль
        </button>
      </div>
    </div>
  );
}
