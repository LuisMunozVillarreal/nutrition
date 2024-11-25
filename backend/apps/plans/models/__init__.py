"""plans models module.

A week plan has:
- 7 days that refer to it
- protein grams goal per day and week, since it's not affected by TDEE or
  deficit
- estimated TDEE based on the exercise rate

A day in the week can be in 3 different "modes":
1. The day is in the future:
   - Every value is estimated based on the exercise rate with the deficit and
     the previous surpluses, if any, subtracted.
     Note: the subtracted surplus is divided between the remaining days in the
     plan.
     : estimated_calorie_goal = estimated_tdee - deficit
     : calorie_goal = estimated_calorie_goal
   - Remaining days: As per the first day, but substracting the incurred
     surpluses from previous days, if any.
     : estimated_calorie_goal: uses plan.remaing_energy
     : calorie_goal = estimated_calorie_goal
2. The day is ongoing:
   - No logged exercises
     : estimated_calorie_goal = estimated_tdee - deficit
     : calorie_goal = estimated_calorie_goal
   - Logged exercises
     : calorie_goal = tdee - deficit
3. The day is in the past:
   - The taken into account intake is the higher of the estimated goal or the
     actual intake

Fat and carbohydrates are based on the previous calorie goals
"""

# flake8: noqa: F401

from .day import Day
from .intake import Intake, IntakePicture
from .week import WeekPlan
