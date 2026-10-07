// Deliberately long labels exercise intrinsic table width, not artificial CSS widths.
const nutrients = { energyKcal: 250, proteinG: 12, fatG: 8, carbsG: 30 }
const food = {
  id: '1', name: 'Wholegrain breakfast with fruit and yoghurt', brand: 'Example Foods',
  barcode: null, notes: '', description: '', size: 500, sizeUnit: 'g', numServings: 2,
  nutritionalInfoSize: 100, nutritionalInfoUnit: 'g', nutrientsFromIngredients: false,
  saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null, ...nutrients,
}
const intake = { id: '1', meal: 'breakfast', mealOrder: 1, numServings: 2, ...nutrients }
const day = {
  id: '1', planId: '1', day: '2026-01-12', dayNum: 1, tracked: true,
  completed: false, deficit: 300, energyKcalGoal: 2000, proteinGGoal: 100,
  fatGGoal: 60, carbsGGoal: 250, tdee: 2300, intakes: [intake], ...nutrients,
}
const plan = {
  id: '1', startDate: '2026-01-12', completed: false, energyKcalGoal: 14000,
  energyKcal: 12000, proteinGKg: 1.5, fatPerc: 30, deficit: 300, twee: 16000, days: [day],
}
const serving = { id: '1', servingSize: 250, servingUnit: 'g', ...nutrients }
const ingredient = { id: '1', foodId: '1', foodLabel: food.name, numServings: 2, ...nutrients }

export const listLayoutFixtures: Record<string, object> = {
  products: { foodProducts: [food] },
  recipes: { recipes: [food] },
  cupboard: { cupboardItems: [{ id: '1', foodId: '1', foodLabel: food.name, purchasedAt: '2026-01-12', started: true, finished: false, consumedPerc: 25, consumedServings: 1, remainingServings: 3 }] },
  measurements: { measurements: [{ id: '1', createdAt: new Date().toISOString(), weight: 75, bodyFatPerc: 20, bmr: 1700 }] },
  goals: { fatPercGoals: [{ id: '1', createdAt: '2026-01-12T12:00:00Z', bodyFatPerc: 18 }] },
  plans: { weekPlans: [plan] },
  days: { weekPlans: [plan] },
  exercises: { exercises: [{ id: '1', dayId: 1, type: 'running', time: '12:00:00', kcals: 300, duration: '00:30:00', distance: 5 }] },
  steps: { dayStepsList: [{ id: '1', dayId: 1, steps: 10000, kcals: 400 }] },
  'plans/1': { weekPlan: plan },
  'days/1': { day },
  'products/1': { foodProduct: { ...food, servings: [serving] } },
  'recipes/1': { recipe: { ...food, ingredients: [ingredient] } },
}
