// Черновой справочник марок/моделей для подсказки в форме добавления
// автомобиля (см. buisness/UI_description.md, п.7). Список неполный и
// намеренно короткий — расширяется по мере необходимости, ручной ввод
// всегда работает независимо от того, есть марка в списке или нет.
export const CAR_CATALOG: Record<string, string[]> = {
  Lada: ["Granta", "Vesta", "Niva", "XRAY", "Largus"],
  Toyota: ["Corolla", "Camry", "RAV4", "Land Cruiser", "Yaris"],
  Kia: ["Rio", "Sportage", "K5", "Sorento", "Cerato"],
  Hyundai: ["Solaris", "Creta", "Tucson", "Elantra", "Santa Fe"],
  Volkswagen: ["Polo", "Tiguan", "Passat", "Golf", "Jetta"],
  Renault: ["Logan", "Duster", "Sandero", "Arkana"],
  Nissan: ["Qashqai", "X-Trail", "Almera", "Terrano"],
  Chevrolet: ["Niva", "Aveo", "Cruze"],
  Ford: ["Focus", "Kuga", "Mondeo", "EcoSport"],
  BMW: ["3-Series", "5-Series", "X3", "X5"],
  "Mercedes-Benz": ["C-Class", "E-Class", "GLC", "GLE"],
  Audi: ["A3", "A4", "A6", "Q5"],
  Skoda: ["Octavia", "Rapid", "Kodiaq", "Karoq"],
  Mazda: ["3", "6", "CX-5"],
  Honda: ["Civic", "CR-V", "Accord"],
  Mitsubishi: ["Outlander", "ASX", "Pajero"],
  Chery: ["Tiggo 7", "Tiggo 8", "Arrizo 5"],
  Geely: ["Coolray", "Atlas", "Emgrand"],
  Haval: ["Jolion", "F7", "Dargo"],
  GAZ: ["GAZelle", "Volga"],
  UAZ: ["Patriot", "Hunter"],
};

export const CAR_MAKES = Object.keys(CAR_CATALOG);

export function modelsForMake(make: string): string[] {
  return CAR_CATALOG[make] ?? [];
}
