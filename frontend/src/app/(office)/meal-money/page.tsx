// page.tsx — /meal-money/: Hela ya chakula, what is spent on the workers' meals each day, an office screen (WAGE-7,
// 03 §5.10). The screen itself is features/meals/meal-money-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { MealMoneyScreen } from "@/features/meals/meal-money-screen";

export default function MealMoneyPage() {
  return <MealMoneyScreen />;
}
