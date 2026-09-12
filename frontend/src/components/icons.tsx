// Минималистичные пиктограммы (по buisness/UI_description.md). Иконка услуги
// подбирается эвристически по ключевым словам в названии — каталог услуг
// произвольный (заполняется станцией), точного соответствия иконки быть не
// может, это лишь приближение для наглядности.
import type { SVGProps } from "react";

function Svg(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    />
  );
}

export function OilIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M12 3c2.5 3 4 5.5 4 8a4 4 0 1 1-8 0c0-2.5 1.5-5 4-8Z" />
    </Svg>
  );
}

export function TireIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  );
}

export function BrakeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4v8l6 3" />
    </Svg>
  );
}

export function DiagnosticsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M3 12h4l2-6 4 12 2-6h6" />
    </Svg>
  );
}

export function WashIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M6 12c1-3 3-5 6-9 3 4 5 6 6 9a6 6 0 1 1-12 0Z" />
    </Svg>
  );
}

export function WrenchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.8 2.8-2-2 2.8-2.8Z" />
    </Svg>
  );
}

export function CarIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M3 13l1.5-4.5A2 2 0 0 1 6.4 7h11.2a2 2 0 0 1 1.9 1.5L21 13" />
      <rect x="2.5" y="13" width="19" height="5" rx="1.5" />
      <circle cx="7" cy="18.5" r="1.5" />
      <circle cx="17" cy="18.5" r="1.5" />
    </Svg>
  );
}

export function PlusIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg width="20" height="20" {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  );
}

export function CheckCircleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg width="56" height="56" {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.5 2.5 5-5" />
    </Svg>
  );
}

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
