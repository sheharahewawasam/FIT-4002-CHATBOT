"""
Seed the advisors and funds that were previously hardcoded in users.py.

Kept as a data migration so a fresh checkout gets a working set of users
without a manual step. Safe to re-run: uses get_or_create.
"""
from django.db import migrations

SEED = {
    "John":  ["Sample Superannuation Fund", "Summers Family Super Fund", "General"],
    "Emily": ["Ausis Super Fund", "General"],
    "Jake":  ["Triple A Super", "General"],
    "Shrek": ["General"],
}


def seed(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    Fund = apps.get_model("rag_api", "Fund")

    funds = {}
    for names in SEED.values():
        for name in names:
            if name not in funds:
                funds[name], _ = Fund.objects.get_or_create(name=name)

    for advisor_name, fund_names in SEED.items():
        advisor, _ = Advisor.objects.get_or_create(name=advisor_name)
        advisor.funds.set([funds[n] for n in fund_names])


def unseed(apps, schema_editor):
    apps.get_model("rag_api", "Advisor").objects.filter(name__in=SEED).delete()


class Migration(migrations.Migration):
    dependencies = [("rag_api", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
