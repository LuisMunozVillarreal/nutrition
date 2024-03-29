# Generated by Django 4.2 on 2023-06-23 21:23

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("measurements", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Day",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "calories",
                    models.DecimalField(
                        decimal_places=1, default=0, max_digits=10
                    ),
                ),
                (
                    "protein_g",
                    models.DecimalField(
                        decimal_places=1, default=0, max_digits=10
                    ),
                ),
                (
                    "fat_g",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="Total Fat (g)",
                    ),
                ),
                (
                    "saturated_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "polyunsaturated_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "monosaturated_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "trans_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "carbs_g",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="Total Carbs (g)",
                    ),
                ),
                (
                    "fiber_carbs_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "sugar_carbs_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "sodium_mg",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "potassium_mg",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "vitamin_a_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "vitamin_c_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "calcium_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "iron_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("day", models.DateField()),
                (
                    "day_num",
                    models.PositiveIntegerField(help_text="Day in the plan."),
                ),
                (
                    "deficit",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Planned deficit (kcals)"
                    ),
                ),
                (
                    "tracked",
                    models.BooleanField(
                        default=True,
                        help_text="Indicates whether the day's intakes and exercises are taken into account for the calorie intake and goal, respectively. Otherwise, the estimated values are used. This field is toggled to true as soon as an exercise or an intake is logged.",
                    ),
                ),
                (
                    "calorie_goal",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "protein_g_goal",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "fat_g_goal",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "carbs_g_goal",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "calorie_intake_perc",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "protein_g_intake_perc",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "fat_g_intake_perc",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
                (
                    "carbs_g_intake_perc",
                    models.DecimalField(
                        decimal_places=1, editable=False, max_digits=10
                    ),
                ),
            ],
            options={
                "ordering": ["-plan", "day"],
            },
        ),
        migrations.CreateModel(
            name="Intake",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "calories",
                    models.DecimalField(
                        decimal_places=1, default=0, max_digits=10
                    ),
                ),
                (
                    "protein_g",
                    models.DecimalField(
                        decimal_places=1, default=0, max_digits=10
                    ),
                ),
                (
                    "fat_g",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="Total Fat (g)",
                    ),
                ),
                (
                    "saturated_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "polyunsaturated_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "monosaturated_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "trans_fat_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "carbs_g",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="Total Carbs (g)",
                    ),
                ),
                (
                    "fiber_carbs_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "sugar_carbs_g",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "sodium_mg",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "potassium_mg",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=10, null=True
                    ),
                ),
                (
                    "vitamin_a_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "vitamin_c_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "calcium_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "iron_perc",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("serving_size", models.PositiveIntegerField(default=100)),
                (
                    "serving_unit",
                    models.CharField(
                        choices=[
                            ("g", "gram(s)"),
                            ("mg", "miligram(s)"),
                            ("serving", "serving(s)"),
                            ("cup", "cup(s)"),
                            ("ml", "millilitre(s)"),
                        ],
                        default="g",
                        max_length=20,
                    ),
                ),
                (
                    "meal",
                    models.CharField(
                        choices=[
                            ("breakfast", "Breakfast"),
                            ("lunch", "Lunch"),
                            ("snack", "Snack"),
                            ("dinner", "Dinner"),
                        ],
                        max_length=20,
                    ),
                ),
                ("meal_order", models.PositiveIntegerField(editable=False)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="WeekPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "start_date",
                    models.DateField(
                        help_text="This field should not be changed after creation. Dependant fields and objects won't be recalculated."
                    ),
                ),
                (
                    "protein_g_kg",
                    models.DecimalField(
                        decimal_places=1,
                        help_text="Protein grams consumed per kilo of body weight",
                        max_digits=10,
                        verbose_name="Protein (g/kg)",
                    ),
                ),
                (
                    "fat_perc",
                    models.DecimalField(
                        decimal_places=1,
                        help_text="Fat percentage of the total calorie goal.",
                        max_digits=10,
                        verbose_name="Fat (%)",
                    ),
                ),
                (
                    "deficit",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="This deficit is the average per day. It might be different on each day of the week if the distribution is not even.",
                        verbose_name="Deficit (kcals/day)",
                    ),
                ),
                (
                    "measurement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calorie_plans",
                        to="measurements.measurement",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
