"""
Bring across the advisors main added while this branch was diverged.

main kept advisors in a hardcoded dict in users.py; this branch moved them into
the database so uploaded documents can be owned by one. The merge takes the
database version, so main's two new advisers have to arrive as data rather than
as code, and Shrek's fund list has to be widened the same way it was there.

Fund names must match the fund_name metadata in Pinecone exactly - the filter is
an exact match, and a near miss returns nothing rather than erroring.
"""
from django.db import migrations

# name -> funds, copied from userList in main's rag_api/users.py
ADVISORS = {
    "Bob": ["Andres Family Superannuation Fund",
            "Bell Family Superannuation Fund",
            "General"],
    "Steve": ["Darto Super Fund",
              "Powell Superannuation Fund",
              "General"],
    "Shrek": ["A and C Super Fund", "General"],
}


def add_advisors(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    Fund = apps.get_model("rag_api", "Fund")

    for name, fund_names in ADVISORS.items():
        funds = [Fund.objects.get_or_create(name=f)[0] for f in fund_names]
        advisor, _ = Advisor.objects.get_or_create(name=name)
        advisor.funds.set(funds)


def remove_advisors(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    # Shrek predates this migration; only put his funds back as they were.
    Advisor.objects.filter(name__in=["Bob", "Steve"]).delete()
    shrek = Advisor.objects.filter(name="Shrek").first()
    if shrek:
        shrek.funds.set(shrek.funds.filter(name="General"))


class Migration(migrations.Migration):
    dependencies = [("rag_api", "0003_testdata_advisor")]
    operations = [migrations.RunPython(add_advisors, remove_advisors)]
