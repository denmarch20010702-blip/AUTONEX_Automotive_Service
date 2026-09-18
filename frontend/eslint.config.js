import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";

// Найдено при настройке линтера (2026-09-18): пакетный `recommended`/
// `recommended-latest` набор правил `eslint-plugin-react-hooks` (major v7)
// включает новые правила эры React Compiler (`purity`, `set-state-in-effect`,
// `static-components`...), которые массово (14 находок) flag'ают совершенно
// стандартные для классического React 18 паттерны этого проекта —
// `setLoading(true)` в начале fetch-эффекта, `Date.now()` в рендере для
// вычисляемого фильтра, компонент-иконку, выбранную по имени услуги. Это не
// баги, а нормальный код без React Compiler — включать этот набор означало
// бы переписывать десяток рабочих, покрытых тестами мест только чтобы
// удовлетворить экспериментальный линтер прямо перед сдачей, без реальной
// пользы. Берём только два по-настоящему ценных, устоявшихся правила плагина.
export default tseslint.config([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Реальная и полезная находка (совпадает с гипотезой из ручного
      // расследования "белого экрана" в этой же сессии) — файл, экспортирующий
      // и компонент, и хук/константу разом, ломает Vite Fast Refresh
      // (полный перемонтаж вместо точечного HMR). Оставлено предупреждением,
      // не ошибкой — разнесение по файлам (events.tsx, *SessionContext.tsx,
      // NotificationContext.tsx, icons.tsx, SlotPicker.tsx) — отдельная
      // рефакторинг-задача, не блокирующая CI прямо перед сдачей.
      "react-refresh/only-export-components": "warn",
      // Неиспользуемые переменные — реальная находка (мёртвый код), но
      // параметр/деструктуризация, начинающаяся с `_`, — осознанный "пропуск
      // значения", а не забытый код (стандартное соглашение).
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
]);
