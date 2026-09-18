import type { SVGProps } from "react";

import { BrakeIcon, DiagnosticsIcon, OilIcon, TireIcon, WashIcon, WrenchIcon } from "./icons";

// Вынесено из icons.tsx (2026-09-18) — см. api/eventsContext.ts за тем же
// приёмом и объяснением (react-refresh/only-export-components): icons.tsx
// теперь экспортирует только компоненты-иконки, эта функция — отдельно.
const KEYWORD_ICONS: Array<[string[], (props: SVGProps<SVGSVGElement>) => JSX.Element]> = [
  [["масл", "oil"], OilIcon],
  [["шин", "колес", "tire"], TireIcon],
  [["тормоз", "brake"], BrakeIcon],
  [["диагностик", "diagnost"], DiagnosticsIcon],
  [["мойк", "wash", "хим"], WashIcon],
];

export function iconForService(name: string) {
  const lower = name.toLowerCase();
  for (const [keywords, Icon] of KEYWORD_ICONS) {
    if (keywords.some((keyword) => lower.includes(keyword))) return Icon;
  }
  return WrenchIcon;
}
